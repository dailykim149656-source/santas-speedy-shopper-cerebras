"""Print completed Mercantile crossover slots using only recorded evidence."""
import os
import json
import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from zoneinfo import ZoneInfo


CAMPAIGN = Path(__file__).resolve().parent
CACHE = CAMPAIGN.parent
REPO = Path(os.environ.get("BOUNTY_TEST_REPO", Path.cwd()))
RAW = Path.home() / 'Library/Application Support/Cerebras Speed Bounty/2026-11-22/raw-test'
KST = ZoneInfo('Asia/Seoul')


def read(path):
    return json.loads(path.read_bytes())


def lines(path):
    with path.open() as stream:
        return [json.loads(line) for line in stream if line.endswith('\n') and line.strip()]


def kst(ms):
    return datetime.fromtimestamp(ms / 1000, KST).isoformat(timespec='milliseconds')


def shopping(raw, products):
    requests, receipts = {}, {}
    first_ids = []
    for msg in raw['history']['messages']:
        if msg.get('__openclaw', {}).get('runId') != raw['id']:
            continue
        if msg['role'] == 'assistant':
            batch = []
            for item in msg.get('content') or []:
                if isinstance(item, dict) and item.get('type') == 'toolCall' and item.get('name') == 'web_fetch':
                    url = item['arguments']['url']
                    requests[item['id']] = parse_qs(urlsplit(url).query).get('search', [None])[0]
                    batch.append(item['id'])
            if not first_ids:
                first_ids = batch
        if msg['role'] != 'toolResult' or msg.get('toolCallId') not in requests:
            continue
        ident = msg['toolCallId']
        content = '\n'.join(c.get('text', '') for c in msg.get('content', []) if isinstance(c, dict))
        payload = msg.get('details')
        if not isinstance(payload, dict):
            try:
                payload = json.loads(content)
            except ValueError:
                payload = {}
        status = payload.get('status')
        if not isinstance(status, int) and msg.get('isError'):
            match = re.search(r'Web fetch failed\s*\((\d{3})\)|\bHTTP(?:/[\d.]+)?\s+(\d{3})\b', payload.get('error') or content, re.I)
            status = int(match.group(1) or match.group(2)) if match else None
        receipts[ident] = {'query': requests[ident], 'http': status, 'error': msg.get('isError'),
                           'fetched_at': payload.get('fetchedAt'), 'took_ms': payload.get('tookMs')}
    first = [receipts.get(ident, {}) for ident in first_ids]
    span = None
    if len(first) == 5 and all(r.get('fetched_at') and isinstance(r.get('took_ms'), (float, int)) for r in first):
        ends = [round(datetime.fromisoformat(r['fetched_at'].replace('Z','+00:00')).timestamp() * 1000) for r in first]
        span = max(ends) - min(end - r['took_ms'] for end, r in zip(ends, first))
    outcomes = [{'query': query, 'initial': ident in first_ids, 'received': ident in receipts,
                 'http': receipts.get(ident, {}).get('http'), 'error': receipts.get(ident, {}).get('error')}
                for ident, query in requests.items()]
    return {'lookup_count': len(requests), 'lookup_results': outcomes,
            'lookup_429': sum(r['http'] == 429 for r in outcomes),
            'first_batch_ms': span, 'detail_pages_checked': len(products),
            'detail_pages_verified': sum(p.get('verified') is True for p in products),
            'detail_page_429_observed': sum(p.get('http') == 429 for p in products),
            'detail_page_http_unknown': sum(p.get('http') is None for p in products)}


def summary(slot, iteration, relay, prev_end):
    ident = iteration['id']
    evidence = read(REPO / 'runs' / ident / 'evidence.json')
    raw = read(RAW / (ident + '.json'))
    valid = iteration['valid'] is True and iteration['method_valid'] is True
    calls = []
    for c in evidence['calls']:
        if c.get('timed_sample'):
            g = c['serverGeneration']
            calls.append({'stop_reason': c['stopReason'], 'output': g['outputTokens'],
                          'ms': g['completionMs'], 'tps': g['outputTokens'] * 1000 / g['completionMs']})
    finals = [c['tps'] for c in calls if c['stop_reason'] == 'stop']
    phases = []
    for r in sorted(relay, key=lambda x: x['at_ms']):
        count = sum(a.get('status') == 429 for a in r.get('attempts', [])) + int(r.get('status') == 429)
        phases.append({'phase': r.get('phase'), 'schedule': r.get('retry_schedule'),
                       'same_body': bool(r.get('received_sha256')) and r['received_sha256'] == r.get('forwarded_sha256'),
                       'status': r.get('status'), 'http429': count})
    start, end = evidence['startedWall'], evidence['ended']['time']
    return {'slot': slot['slot'], 'label': iteration['label'], 'id': ident,
            'started_kst': kst(start), 'ended_kst': kst(end), 'elapsed_s': evidence['ended']['elapsedMs'] / 1000,
            'wall_s': (end-start) / 1000, 'prior_end_gap_s': None if prev_end is None else (start-prev_end) / 1000,
            'valid': valid, 'shopping_valid': iteration['valid'], 'method_valid': iteration['method_valid'],
            'context_clean': iteration.get('context_clean'), 'rate_limited': iteration.get('rate_limited'),
            'first_tps': calls[0]['tps'] if calls else None, 'final_tps': finals[-1] if finals else None,
            'mean_tps': evidence['score'].get('mean_exact_tps'), 'mean_is_partial': bool(calls) and not finals,
            'calls': calls, **shopping(raw, evidence['products']), 'relay_requests': phases,
            'cerebras_429': sum(p['http429'] for p in phases) if phases else None}


def main():
    campaign = read(CAMPAIGN / 'campaign.json')
    iterations = lines(CACHE / 'iterations.jsonl')
    by_label = {r['label']: i for i, r in enumerate(iterations)}
    by_id = defaultdict(list)
    for r in lines(CACHE / 'relay/logs/requests.jsonl'):
        by_id[r.get('run_id')].append(r)
    rows = []
    for slot in campaign['slots']:
        index = by_label.get(f"D{slot['number']:04d}-{slot['arm']}")
        if index is None:
            continue
        r = iterations[index]
        prev = read(REPO / 'runs' / iterations[index - 1]['id'] / 'evidence.json')['ended']['time'] if index else None
        rows.append(summary(slot, r, by_id[r['id']], prev))
    print(json.dumps(rows, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()
