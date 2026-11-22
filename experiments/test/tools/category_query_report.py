"""Audit consecutive five-query shopping runs against the historical D5027 record."""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import hashlib
import html
import json
import math
from pathlib import Path
import re
from statistics import mean, median
from urllib.parse import urlsplit
from uuid import UUID

from scoring import call_rate, mean_rate, round_rate
from validate import (MARKDOWN_TOKEN, MODEL, answer_links, finite, merchant, text_content,
                      unwrap_json, verify_product)
from variants import SYNTH_CATEGORIES, catalogs


# Historical run cd75e5e0, both original server timings.
D5027_MEAN = mean_rate([call_rate(447, 431.721325), call_rate(161, 96.180553)])
TARGET = 1673


def require(condition, message):
    if not condition:
        raise ValueError(message)


def error_kind(raw):
    messages = (raw.get('history') or {}).get('messages', [])
    signals = [str(raw.get('error', ''))]
    for message in messages:
        if message.get('role') == 'assistant' and message.get('stopReason') == 'error':
            signals.extend(str(message.get(k, '')) for k in ('errorCode', 'errorType', 'errorMessage'))
    return ('provider_429' if any(re.search(r'\b429\b|queue_exceeded|too_many_requests_error',
                                            s, re.I) for s in signals) else None)


def score_calls(messages):
    calls = []
    for m in messages:
        if m.get('role') != 'assistant':
            continue
        timing = m.get('serverGeneration') or {}
        tokens, ms = timing.get('outputTokens'), timing.get('completionMs')
        timed = type(tokens) is int and tokens > 0 and finite(ms) and ms > 0
        calls.append(dict(response_id=m.get('responseId'), stop=m.get('stopReason'),
                          tokens=tokens, ms=ms, tps=call_rate(tokens, ms) if timed else None))
    return calls


def check_receipt(directory, run, call, category, url, cards):
    receipt = json.loads((directory / (category + '.json')).read_bytes())
    body = (directory / ('body-' + category + '.txt')).read_bytes()
    for field, value in [('runId', run['id']), ('sessionKey', run['sessionKey']),
                         ('callId', call['id']), ('query', category), ('url', url),
                         ('finalUrl', url), ('status', 200),
                         ('product', {k: cards[0][k] for k in ('name', 'permalink')})]:
        require(receipt.get(field) == value, f'{category}: receipt {field} mismatch')
    require(finite(receipt.get('startedMs')) and finite(receipt.get('completedMs'))
            and run['sentAt'] <= receipt['startedMs'] <= receipt['completedMs'] <= run['endedAt'],
            f'{category}: receipt timestamp outside session')
    require(hashlib.sha256(body).hexdigest() == receipt.get('bodySha256')
            and json.loads(body) == cards, f'{category}: product body does not match receipt/transcript')


def checked_products(directory, run, messages):
    tool = 'search_category'
    urls = catalogs(run['id'][:8], 1, shops='synth-categories')
    begin, final = messages[1], messages[-1]
    calls = [p for p in begin['content'] if p.get('type') == 'toolCall']
    results = {m['toolCallId']: m for m in messages[2:-1]}
    require(len(calls) == len(results) == 5 and len({c.get('id') for c in calls}) == 5,
            'expected five unique tool calls and results')
    products = []
    for call, query, url in zip(calls, SYNTH_CATEGORIES, urls):
        args = {'query': query}
        require(call.get('name') == tool and call.get('arguments') == args,
                f'{query}: wrong tool, arguments or order')
        m = results.get(call.get('id'), {})
        require(m.get('toolName') == tool and m.get('isError') is False
                and (m.get('__openclaw') or {}).get('resultContentSource') in (None, 'network'),
                f'{query}: missing successful network result')
        payload = m.get('details') or unwrap_json(text_content(m))
        require(payload.get('url') == payload.get('finalUrl') == url and payload.get('status') == 200
                and not payload.get('cached') and payload.get('truncated') is False,
                f'{query}: unexpected URL, status, cache or truncation')
        fetched_at = datetime.fromisoformat(payload['fetchedAt'].replace('Z', '+00:00'))
        require(fetched_at.tzinfo is not None and run['sentAt'] <= fetched_at.timestamp() * 1000 <= run['endedAt'],
                f'{query}: lookup occurred outside this session')
        cards = unwrap_json(payload['text'])
        require(isinstance(cards, list) and len(cards) == 1 and isinstance(cards[0], dict),
                f'{query}: expected one product')
        card = cards[0]
        require(isinstance(card.get('name'), str) and card['name'].strip()
                and merchant(card.get('permalink'), product=True)
                and urlsplit(card['permalink']).hostname == 'aisynthesis.com',
                f'{query}: invalid merchant or product')
        check_receipt(directory / 'receipts' / run['id'], run, call, query, url, cards)
        products.append(dict(url=card['permalink'], catalog_name=html.unescape(card['name']),
                             source_tool_call_id=call['id'], query=query))
    text = text_content(final)
    urls, misleading = answer_links(text)
    expected = [(p['catalog_name'], p['url']) for p in products]
    links = [(html.unescape(m[3]), html.unescape(m[4] or m[5])) for m in MARKDOWN_TOKEN.finditer(text)
             if not m[1] and not m[2]]
    require(not misleading and len(set(urls)) == 5 and urls == [p['url'] for p in products]
            and links == expected, 'final answer does not pair five exact product names and URLs in order')
    return products


def assess(directory, plan, *, verify=verify_product):
    path = directory / (plan['label'] + '.json')
    result = dict(slot=plan['slot'], id=plan['id'],
                  sent=False, valid=False, status='missing_record', calls=[], pages=[], provider_failures=[])
    if not path.exists():
        return result
    try:
        raw = json.loads(path.read_bytes())
        result['status'] = 'invalid'
        require(all(raw.get(k) == plan.get(k) for k in
                    ('id', 'sessionKey', 'slot', 'arm', 'label', 'prompt')), 'raw/plan identity mismatch')
        result['sent'] = finite(raw.get('sentAt'))
        messages = (raw.get('history') or {}).get('messages', [])
        calls = result['calls'] = score_calls(messages)
        rate_error = error_kind(raw)
        failures = raw.get('providerFailures') or []
        result['provider_failures'] = [{'status': f.get('status'), 'stage': f.get('stage') or 'unknown'}
                                       for f in failures]
        result['provider_diagnostics_available'] = raw.get('providerDiagnosticsAvailable', 'providerFailures' in raw)
        if rate_error or any(e.get('status') == 429 for e in failures):
            result['provider_429_observed'] = True
        if not result['sent']:
            result['status'] = 'not_sent'
            result['reason'] = raw.get('error', 'chat.send timestamp unavailable')
            return result
        require(not raw.get('error') and (raw.get('ended') or {}).get('terminal') == 'final'
                and finite(raw.get('endedAt')) and raw['endedAt'] >= raw['sentAt'],
                'session did not terminate successfully')
        roles = [m.get('role') for m in messages]
        require(roles == ['user','assistant'] + ['toolResult'] * 5 + ['assistant'],
                'expected one fresh prompt, five search results and two model calls')
        require(text_content(messages[0]) == plan['prompt'] and all(
            (m.get('__openclaw') or {}).get('runId') == plan['id'] for m in messages[1:]),
            'prompt or transcript run ID mismatch')
        require(all(m.get('provider') == 'cerebras' and m.get('model') == MODEL for m in messages
                    if m.get('role') == 'assistant'), 'unexpected provider/model')
        require([c['stop'] for c in calls] == ['toolUse','stop']
                and all(c['tps'] is not None and c['response_id'] for c in calls)
                and calls[0]['response_id'] != calls[1]['response_id'], 'missing/duplicate model timing or ID')
        require(not any(p.get('type') == 'toolCall' for p in messages[-1]['content']),
                'final answer attempted another tool call')
        rates = [c['tps'] for c in calls]
        average = mean_rate(rates)
        official = raw.get('official') or {}
        expected = dict(meanTokensPerSecond=average, p90TokensPerSecond=max(rates),
                        outputTokens=sum(c['tokens'] for c in calls), generationMs=sum(c['ms'] for c in calls))
        require(official.get('calls') == 2 and all(finite(official.get(k)) and math.isclose(
            official[k], v, rel_tol=1e-12) for k,v in expected.items()), 'official score does not match all calls')
        result.update(first_tps=rates[0], final_tps=rates[1], mean_tps=average, displayed=round_rate(average))
        products = checked_products(directory, raw, messages)
        with ThreadPoolExecutor(max_workers=5) as pool:
            pages = result['pages'] = list(pool.map(verify, products))
        require(len(pages) == 5 and all(p.get('verified') for p in pages),
                'five independent merchant page checks did not pass')
        result.update(valid=True, status='valid')
    except (OSError, KeyError, ValueError, TypeError, AttributeError, IndexError) as exc:
        result['reason'] = str(exc)
        if result.get('provider_429_observed'):
            result['status'] = 'provider_429'
    return result


def summarize(rows):
    ids = Counter(c['response_id'] for r in rows for c in r['calls'] if c['response_id'])
    for row in rows:
        if row['valid'] and any(ids[c['response_id']] > 1 for c in row['calls']):
            row.update(valid=False, status='invalid', reason='provider response ID repeated across trials')
    valid = [r for r in rows if r['valid']]
    rates = [r['mean_tps'] for r in valid]
    sent = sum(r['sent'] for r in rows)
    return dict(planned=len(rows), sent=sent, valid=len(valid), valid_fraction=len(valid)/sent if sent else None,
                status_counts=dict(Counter(r['status'] for r in rows)),
                observed_provider_429_sessions=sum(bool(r.get('provider_429_observed')) for r in rows),
                provider_diagnostics_available_sessions=sum(bool(r.get('provider_diagnostics_available'))
                                                           for r in rows if r['sent']),
                transcript_429_by_stage=dict(Counter(e['stage'] for r in rows for e in r['provider_failures']
                                                     if e['status'] == 429)),
                average_valid_session_tps=mean(rates) if rates else None,
                median_valid_session_tps=median(rates) if rates else None,
                average_first_tps=mean(r['first_tps'] for r in valid) if valid else None,
                average_final_tps=mean(r['final_tps'] for r in valid) if valid else None,
                best_valid_session_tps=max(rates, default=None),
                best_slot=max(valid, key=lambda r:r['mean_tps'])['slot'] if valid else None,
                historical_D5027_mean=D5027_MEAN,
                best_minus_historical=max(rates)-D5027_MEAN if rates else None,
                average_minus_historical=mean(rates)-D5027_MEAN if rates else None,
                above_historical=sum(rate > D5027_MEAN for rate in rates),
                target=TARGET, above_raw_target=sum(rate > TARGET for rate in rates),
                above_display_target=sum(r['displayed'] > TARGET for r in valid))


def read_plan(directory):
    plan = json.loads((directory / 'plan.json').read_bytes())
    trials = plan['trials']
    require(len(trials) == plan['count'] and trials, 'expected nonempty consecutive planned trials')
    ids = set()
    for i,trial in enumerate(trials):
        run_id = trial['id']
        require(trial['slot'] == i+1 and trial['arm'] == 'B'
                and trial['label'] == f'slot-{i+1:03d}-B' and str(UUID(run_id)) == run_id
                and run_id not in ids and trial['sessionKey'] == f'agent:main:category-ab-b-{run_id}',
                'invalid or duplicate planned slot')
        ids.add(run_id)
    return trials


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory',type=Path)
    parser.add_argument('--output',type=Path,help='Defaults to report.json in the experiment directory')
    args = parser.parse_args()
    trials = read_plan(args.directory)
    rows = [assess(args.directory, trial) for trial in trials]
    summary = summarize(rows)
    report = json.dumps(dict(summary=summary,trials=rows),ensure_ascii=False,indent=2,allow_nan=False)+'\n'
    output = args.output or args.directory/'report.json'
    output.write_text(report,encoding='utf-8')
    print(json.dumps(summary,ensure_ascii=False,indent=2))


if __name__ == '__main__':
    main()
