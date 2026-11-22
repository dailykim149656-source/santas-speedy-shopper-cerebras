"""Classify pending runs from primary shopping receipts without claiming page verification."""
from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path

WORK = Path(__file__).resolve().parent
spec = spec_from_file_location('campaign_finished_receipt', WORK.parent / 'd5027-pure-0235' / 'receipt.py')
finished = module_from_spec(spec)
spec.loader.exec_module(finished)


def assess(row):
    if row.get('result') != 'pending_validation' and row.get('valid') is not None:
        return finished.assess(row)
    ident = row['id']
    raw = finished.read(finished.RAW / (ident + '.json'))
    if raw.get('id') != ident:
        raise ValueError('private raw id mismatch')
    hits = finished.lookup_429_hosts(raw)
    requests = []
    with (WORK.parent / 'relay/logs/requests.jsonl').open('rb') as stream:
        for line in stream:
            if ident.encode() in line and line.endswith(b'\n'):
                item = json.loads(line)
                if item.get('run_id') == ident:
                    requests.append(item)
    return {'zero_token_429': False, 'merchant_429': bool(hits), 'merchant_429_hosts': sorted(set(hits)),
            'lookup_429_count': len(hits), 'detail_429_count': None, 'upstream_requests': len(requests),
            'cerebras_429_count': sum(int(r.get('status') == 429) + sum(a.get('status') == 429 for a in r.get('attempts', [])) for r in requests),
            'retry_after_until': None}
