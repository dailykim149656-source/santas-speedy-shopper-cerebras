"""Read-only classification from the completed session, product receipts and upstream log."""
import os
import json
import re
from pathlib import Path
from urllib.parse import urlsplit

CACHE = Path(__file__).resolve().parents[1]
REPO = Path(os.environ.get("BOUNTY_TEST_REPO", Path.cwd()))
RAW = Path.home() / 'Library/Application Support/Cerebras Speed Bounty/2026-11-22/raw-test'
MERCHANTS = {'aisynthesis.com', 'mercantile.wordpress.org'}


def read(path):
    return json.loads(path.read_bytes())


def merchant_host(url):
    return (urlsplit(url or '').hostname or '').removeprefix('www.')


def lookup_429_hosts(raw):
    requests = {}
    hits = []
    for msg in raw['history']['messages']:
        if msg.get('__openclaw', {}).get('runId') != raw['id']:
            continue
        if msg.get('role') == 'assistant':
            for block in msg.get('content') or []:
                if block.get('type') == 'toolCall' and block.get('name') == 'web_fetch':
                    host = merchant_host((block.get('arguments') or {}).get('url'))
                    if host in MERCHANTS:
                        requests[block['id']] = host
        if msg.get('role') != 'toolResult' or msg.get('toolCallId') not in requests:
            continue
        data = msg.get('details')
        if not isinstance(data, dict):
            body = '\n'.join(b.get('text', '') for b in msg.get('content', []) if isinstance(b, dict))
            try:
                data = json.loads(body)
            except ValueError:
                data = {}
        if not isinstance(data, dict):
            continue
        if data.get('status') == 429 or (msg.get('isError') and
                re.search(r'^Web fetch failed\s*\(429\):', data.get('error', ''), re.M)):
            hits.append(requests[msg['toolCallId']])
    return hits


def assess(row):
    ident = row['id']
    evidence = read(REPO / 'runs' / ident / 'evidence.json')
    if evidence['id'] != ident:
        raise ValueError('evidence id mismatch')
    upstream = []
    with (CACHE / 'relay/logs/requests.jsonl').open('rb') as stream:
        for line in stream:
            if ident.encode() not in line or not line.endswith(b'\n'):
                continue
            request = json.loads(line)
            if request.get('run_id') == ident:
                upstream.append(request)
    calls = evidence['calls']
    accounted = bool(calls) and len(calls) == len(upstream)
    zero = (accounted and evidence['ended'].get('terminal') == 'error'
            and row.get('rate_limited') is True and row.get('valid') is False
            and all(c.get('provider') == 'cerebras' and c.get('stopReason') == 'error'
                    and c.get('timed_sample') is False and c.get('usage', {}).get('output') == 0
                    and not c.get('tool_inputs') for c in calls)
            and all(r.get('status') == 429 and not r.get('error')
                    and isinstance(r.get('attempts'), list)
                    and all(a.get('status') == 429 for a in r['attempts']) for r in upstream))
    raw = read(RAW / (ident + '.json'))
    if raw['id'] != ident:
        raise ValueError('private raw id mismatch')
    hits = lookup_429_hosts(raw)
    detail_hits = [merchant_host(p.get('url')) for p in evidence['products']
                   if p.get('http') == 429 and merchant_host(p.get('url')) in MERCHANTS]
    return {'zero_token_429': zero, 'merchant_429': bool(hits or detail_hits),
            'merchant_429_hosts': sorted(set(hits + detail_hits)), 'lookup_429_count': len(hits),
            'detail_429_count': len(detail_hits), 'upstream_requests': len(upstream),
            'cerebras_429_count': sum(int(r.get('status') == 429) + sum(a.get('status') == 429 for a in r.get('attempts', [])) for r in upstream),
            'retry_after_until': None}  # The relay forwards final upstream headers but does not persist them.
