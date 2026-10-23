"""Deterministic report input budgeting, without modifying source evidence."""
from copy import deepcopy
import hashlib
from typing import Callable

POLICY_VERSION = 'utf8-context-v1'


def bounded_text(value: str, limit: int, *, original_bytes: int | None = None,
                 original_sha256: str | None = None) -> tuple[str, dict | None]:
    raw = value.encode('utf-8')
    prefix = raw[:limit].decode('utf-8', errors='ignore')
    total = len(raw) if original_bytes is None else original_bytes
    if total == len(prefix.encode('utf-8')):
        return prefix, None
    return prefix, {'original_bytes': total, 'included_bytes': len(prefix.encode('utf-8')),
                    'original_sha256': original_sha256 or hashlib.sha256(raw).hexdigest(),
                    'selection': 'UTF-8 prefix; source unchanged'}


def budget_context(context: dict, limit: int, request_size: Callable[[dict], int]) -> dict:
    """Preserve capture order and complete citation objects; never clip a prompt.

    Keep at least one finding while dropping the sample tail, then drop citation
    tails. Base metadata/instructions that cannot fit fail closed.
    """
    result = deepcopy(context)
    findings, citations = result['sample_findings'], result['citations']
    metadata = {'policy_version': POLICY_VERSION, 'max_input_bytes': limit,
        'sample_candidates': len(findings), 'citation_candidates': len(citations),
        'omitted_finding_ids': [], 'omitted_citation_ids': [],
        'findings_not_sampled': max(0, context['total_findings'] - len(findings)),
        'sampling': 'Up to 20 critical/high/medium findings; severity, newest first, UUID tie-break. Low findings excluded.',
        'selection': 'Drop sample tail (retain one), then citation tail, then last finding; retain complete citation objects.'}
    result['input_budget'] = metadata
    while request_size(result) > limit:
        if len(findings) > 1:
            metadata['omitted_finding_ids'].insert(0, findings.pop()['finding_id'])
        elif citations:
            metadata['omitted_citation_ids'].insert(0, citations.pop()['citation_id'])
        elif findings:
            metadata['omitted_finding_ids'].insert(0, findings.pop()['finding_id'])
        else:
            raise ValueError('Report instructions and metadata exceed the configured input budget')
    return result
