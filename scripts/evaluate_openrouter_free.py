"""Opt-in synthetic-only free-model probe; never changes application settings.

Fixed model/provider, no redirects/proxies/retries/fallbacks/plugins. Verify current
zero pricing and endpoint health, enforce zero request prices and ZDR, then stop
on the first failed request. No application imports or database access.
"""
import argparse
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
import time
import unittest

import httpx
from dotenv import dotenv_values

from benchmark_local_reports import REFINED_SYSTEM
from evaluate_local_reports import SCHEMA, validate
from phi_holdout_cases import CASES

MODEL = 'google/gemma-4-31b-it:free'
PROVIDER = 'Google AI Studio'
BASE = 'https://openrouter.ai/api/v1/'
POLICY = dict(only=['google-ai-studio'], allow_fallbacks=False,
              require_parameters=True, data_collection='deny', zdr=True,
              max_price=dict(prompt=0, completion=0, request=0, image=0))


def zero_price(pricing):
    """All published billable price fields must be zero, not merely token cost."""
    if not isinstance(pricing, dict) or not {'prompt', 'completion'} <= pricing.keys():
        return False
    try:
        return all(type(value) is not bool and Decimal(str(value)).is_finite()
                   and Decimal(str(value)) == 0 for name, value in pricing.items() if name != 'discount')
    except (InvalidOperation, ValueError):
        return False


def check_endpoint(data):
    if data.get('id') != MODEL:
        raise ValueError('Model metadata mismatch')
    return next((ep for ep in data.get('endpoints', []) if ep.get('provider_name') == PROVIDER
        and ep.get('tag') == 'google-ai-studio' and ep.get('status') == 0
        and ep.get('model_id') == MODEL and zero_price(ep.get('pricing'))
        and {'response_format', 'max_tokens', 'temperature'} <= set(ep.get('supported_parameters', []))), None)


def payload(case):
    return dict(model=MODEL, stream=False, max_tokens=700, temperature=0,
        provider=POLICY, response_format={'type': 'json_object'}, messages=[
            {'role': 'system', 'content': REFINED_SYSTEM + '\nRequired JSON schema: ' + json.dumps(SCHEMA)},
            {'role': 'user', 'content': case['text']}])


def check_response(data, case):
    if data.get('error') or data.get('model') != MODEL or data.get('provider') != PROVIDER:
        raise ValueError('Unexpected model/provider or error envelope')
    usage = data.get('usage', {})
    if not zero_price({'prompt': usage.get('cost'), 'completion': 0}):
        raise ValueError('Reported cost missing, invalid or nonzero; stop and inspect account')
    choices = data.get('choices', [])
    if len(choices) != 1 or choices[0].get('finish_reason') != 'stop':
        raise ValueError('Incomplete completion')
    value = json.loads(choices[0]['message']['content'])
    validate(value, case['findings'], case['assets'])
    if case['uncertain'] and value['confidence'] == 1:
        raise ValueError('Unsupported absolute confidence')
    return value


def evaluate(client, key, evidence):
    """At most ten requests; no retries and no error-body/credential logging."""
    headers = {'Authorization': 'Bearer ' + key}
    metadata = client.get(BASE + 'models/' + MODEL + '/endpoints')
    evidence['metadata_status'] = metadata.status_code
    if metadata.status_code != 200:
        raise ValueError('Endpoint metadata unavailable')
    evidence['endpoint_metadata'] = metadata.json()['data']
    if not check_endpoint(evidence['endpoint_metadata']):
        raise ValueError('No healthy zero-priced pinned endpoint; no inference sent')
    for case in CASES:
        # Recheck published endpoint prices before each individual inference.
        current = client.get(BASE + 'models/' + MODEL + '/endpoints')
        if current.status_code != 200 or not check_endpoint(current.json()['data']):
            raise ValueError('Endpoint pricing/health changed; no next request sent')
        record = {'case': case['name']}
        evidence['runs'].append(record)
        started = time.monotonic()
        response = client.post(BASE + 'chat/completions', headers=headers, json=payload(case))
        record.update(http_status=response.status_code, seconds=round(time.monotonic()-started, 2))
        if response.status_code != 200:
            raise ValueError(f'Inference rejected HTTP {response.status_code}; no retry or fallback')
        data = response.json()
        record['response'] = data
        record['validated'] = check_response(data, case)
        record['automated_pass'] = True


class SafetyTests(unittest.TestCase):
    def test_zero_prices(self):
        self.assertTrue(zero_price({'prompt': '0', 'completion': '0', 'request': '0', 'discount': 0}))
        for item in ({}, {'prompt': '0', 'completion': '1'}, {'prompt': 'NaN', 'completion': 0},
                     {'prompt': True, 'completion': 0}, {'prompt': 0, 'completion': 0, 'request': '.01'},
                     {'prompt': '-1', 'completion': 0}):
            self.assertFalse(zero_price(item))

    def test_request_policy_and_no_expected_answer_leak(self):
        for case in CASES:
            body = payload(case)
            self.assertEqual(body['model'], MODEL)
            self.assertNotIn('models', body)
            self.assertNotIn('plugins', body)
            self.assertEqual(body['provider']['max_price'], dict(prompt=0, completion=0, request=0, image=0))
            self.assertFalse(body['provider']['allow_fallbacks'])
            self.assertTrue(body['provider']['zdr'])
            self.assertEqual(body['messages'][1]['content'], case['text'])
            self.assertNotIn(case['expected'], body['messages'][0]['content'])

    def test_no_retries_after_rejection_and_no_auth_on_metadata(self):
        requests = []
        endpoint = dict(id=MODEL, endpoints=[dict(model_id=MODEL, provider_name=PROVIDER,
            tag='google-ai-studio', status=0, pricing={'prompt': '0', 'completion': '0'},
            supported_parameters=['response_format', 'max_tokens', 'temperature'])])
        def handler(request):
            requests.append(request)
            return httpx.Response(402) if request.method == 'POST' else httpx.Response(200, json={'data': endpoint})
        evidence={'runs': []}
        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            with self.assertRaisesRegex(ValueError, 'HTTP 402'):
                evaluate(client, 'synthetic-secret', evidence)
        self.assertEqual(sum(r.method == 'POST' for r in requests), 1)
        self.assertTrue(all('authorization' not in r.headers for r in requests if r.method == 'GET'))
        self.assertNotIn('synthetic-secret', json.dumps(evidence))
        endpoint['endpoints'][0]['status']=-5
        self.assertIsNone(check_endpoint(endpoint))

    def test_response_cost_references_and_truncation(self):
        import copy
        case=CASES[8]
        value=dict(summary='No operating evidence', recommendation='Request evidence', limitations='No samples',
            confidence=0, affected_finding_ids=[], affected_asset_ids=[])
        data=dict(model=MODEL,provider=PROVIDER,usage={'cost':0},choices=[
            {'finish_reason':'stop','message':{'content':json.dumps(value)}}])
        self.assertEqual(check_response(data,case),value)
        for field,bad in [('cost',.01),('cost',None),('model','other'),('provider','other'),('finish_reason','length')]:
            item=copy.deepcopy(data)
            if field=='cost':item['usage']['cost']=bad
            elif field=='finish_reason':item['choices'][0][field]=bad
            else:item[field]=bad
            with self.assertRaises(ValueError):check_response(item,case)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--self-test',action='store_true')
    parser.add_argument('--run',action='store_true')
    args=parser.parse_args()
    if args.self_test and not unittest.TextTestRunner().run(
            unittest.defaultTestLoader.loadTestsFromTestCase(SafetyTests)).wasSuccessful():return 1
    if not args.run:return 0
    root=Path(__file__).resolve().parents[1]
    key=dotenv_values(root/'backend'/'.env').get('OPENROUTER_API_KEY')
    if not key:raise SystemExit('Saved backend/.env OpenRouter key required')
    evidence=dict(model=MODEL,provider=PROVIDER,system_prompt=REFINED_SYSTEM,schema=SCHEMA,
        cases=CASES,policy=POLICY,runs=[],manual_review_required=True,
        scope='Synthetic reduced schema only, not production report acceptance')
    evidence['fixture_sha256']=hashlib.sha256(json.dumps(evidence,sort_keys=True).encode()).hexdigest()
    output_dir=root/'temp'/'auditmind-demo'/'browser'/'free-evaluation'
    output_dir.mkdir(parents=True,exist_ok=True)
    output=output_dir/f'gemma4-free-{time.time_ns()}.json'
    output.write_text(json.dumps(evidence,indent=2),encoding='utf-8')
    try:
        with httpx.Client(timeout=90,follow_redirects=False,trust_env=False) as client:
            evaluate(client,key,evidence)
    except Exception as exc:
        evidence['stopped_reason']=str(exc) if isinstance(exc,ValueError) else type(exc).__name__
    evidence['complete']=len(evidence['runs'])==len(CASES) and all(r.get('automated_pass') for r in evidence['runs'])
    output.write_text(json.dumps(evidence,indent=2),encoding='utf-8')
    print(json.dumps({'complete':evidence['complete'],'attempted':len(evidence['runs']),
        'stopped_reason':evidence.get('stopped_reason'),'evidence':str(output)}))
    return int(not evidence['complete'])


if __name__=='__main__':raise SystemExit(main())
