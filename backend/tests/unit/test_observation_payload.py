import copy
import uuid
from types import SimpleNamespace
import pytest
from app.models.enums import Domain, Severity
from app.services import observation_payload as contract
from app.services.finding_observations import observation_values


def captured(**scan_changes):
    raw = {key: None for key in contract.RAW_KEYS}
    raw.update(plugin_id="1001", port="443", protocol="tcp", severity="2", plugin_name="Test",
        plugin_family="Test", svc_name="", cve=[], host="test", synopsis=None)
    row = SimpleNamespace(domain=Domain.vulnerability_management, severity=Severity.medium,
        category="Nessus 1001 (443/tcp)", description="Test", event_count=None,
        first_seen=None, last_seen=None, details=None, raw_data=raw, source="nessus",
        row=1, hostname="test", ip="10.0.0.1", cloud_id=None)
    scan = SimpleNamespace(id=uuid.uuid4(), org_id=uuid.uuid4(), scan_type="nessus", profile=None, filename="test.nessus")
    for key,value in scan_changes.items(): setattr(scan,key,value)
    result=observation_values(row,SimpleNamespace(id=uuid.uuid4()),scan,uuid.uuid4(),1)
    return scan,result


def test_only_new_native_capture_gets_server_mapping_stamp():
    scan,value=captured()
    assert value['payload'][contract.MAPPING_KEY]==contract.MAPPING_VERSION
    replacement,identity=contract.validate(value['payload'],org_id=scan.org_id,source_identity=value['source_identity'])
    assert replacement['details'] is None and identity['port']==443
    assert contract.MAPPING_KEY not in captured(scan_type='json')[1]['payload']
    assert contract.MAPPING_KEY not in captured(profile='custom')[1]['payload']


@pytest.mark.parametrize('change', ['unversioned','unknown_version','workflow','raw_extra','severity','category','description','identity','boolean','details','event_count','naive_time','time_order','domain_object','plugin_output'])
def test_strict_mapping_rejects_unsupported_or_inconsistent_fields(change):
    scan,value=captured();payload=copy.deepcopy(value['payload']);identity=value['source_identity']
    if change=='unversioned':payload.pop(contract.MAPPING_KEY)
    elif change=='unknown_version':payload[contract.MAPPING_KEY]='future'
    elif change=='workflow':payload['workflow_status']='resolved'
    elif change=='raw_extra':payload['raw_data']['workflow_status']='resolved'
    elif change=='severity':payload['severity']='critical'
    elif change=='category':payload['category']='other'
    elif change=='description':payload['description']='not mapped'
    elif change=='identity':identity={**identity,'port':'80'}
    elif change=='boolean':payload['raw_data']['port']=True
    elif change=='details':payload['details']={'workflow_status':'resolved'}
    elif change=='event_count':payload['event_count']=1
    elif change=='naive_time':payload['first_seen']='2026-11-13T00:00:00'
    elif change=='time_order':payload.update(first_seen='2026-11-14T00:00:00Z',last_seen='2026-11-13T00:00:00Z')
    elif change=='domain_object':payload['domain']={}
    elif change=='plugin_output':payload['raw_data']['plugin_output']='x'*4001
    with pytest.raises(ValueError):contract.validate(payload,org_id=scan.org_id,source_identity=identity)


def test_hashes_cover_full_values_and_summaries_are_bounded():
    first='x'*5000+'a';second='x'*5000+'b'
    summary=contract.summary(first)
    assert len(summary['value'])==2000 and summary['truncated']
    assert summary['sha256']!=contract.summary(second)['sha256']
    assert contract.summary(None)['value'] is None
    assert contract.timestamp('2026-11-13T08:00:00-05:00')=='2026-11-13T13:00:00+00:00'


def test_oversized_payload_is_rejected(monkeypatch):
    scan,value=captured();monkeypatch.setattr(contract,'MAX_BYTES',100)
    with pytest.raises(ValueError,match='size'):contract.validate(value['payload'],org_id=scan.org_id,source_identity=value['source_identity'])
