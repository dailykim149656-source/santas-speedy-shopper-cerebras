#!/usr/bin/env python3
"""Offline Korean report and independent audit of the isolated gift8 campaign.

No model calls, HTTP fetches, media encoding, or source-evidence writes. Exit 2
means the report was written but the campaign/audit is incomplete or blocked.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
from statistics import mean, median
import subprocess
import uuid

from scoring import call_rate, mean_rate, round_rate
from first5027 import terminal_429
from gift8_evidence import canonical_card, jsjson, validate_events
from ledger import read_capture_file
import gift8_film

REPO = Path(__file__).resolve().parents[1]
MAIN_ROOT = Path.home() / 'Library/Caches/cerebras-speed-bounty/2026-11-22'
TEST_ROOT = MAIN_ROOT.with_name(MAIN_ROOT.name + '-test')
ARCHIVE = Path.home() / 'Library/Application Support/Cerebras Speed Bounty/2026-11-22/raw-test'
ORDER = 'ABBABAAB'
IDS = [21951, 23345, 11125, 11141, 20209]
MODEL = 'moonshotai-kimi-k3.1-pro-trial'


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def digest(body):
    return hashlib.sha256(body).hexdigest()


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + '.writing')
    temp.write_text(value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n')
    temp.chmod(0o600)
    temp.replace(path)


class Sources:
    def __init__(self):
        self.files = {}

    def blob(self, path):
        path = Path(path)
        if path.is_symlink() or not path.is_file():
            raise ValueError('missing or non-regular source: ' + str(path))
        body = path.read_bytes()
        self.files[str(path.resolve())] = dict(sha256=digest(body), bytes=len(body))
        return body

    def json(self, path):
        return json.loads(self.blob(path))

    def rows(self, path):
        if not path.exists():
            return []
        return [json.loads(line) for line in self.blob(path).splitlines() if line.strip()]


def independent_score(raw):
    """All same-run assistant calls, in native history order; never token-weighted."""
    calls, reasons = [], []
    for index, message in enumerate(raw['history']['messages']):
        if message.get('role') != 'assistant' or message.get('__openclaw', {}).get('runId') != raw['id']:
            continue
        generation = message.get('serverGeneration', {})
        tokens, ms = generation.get('outputTokens'), generation.get('completionMs')
        authentic = message.get('provider') == 'cerebras' and message.get('model') == MODEL
        measured = finite(tokens) and tokens >= 1 and finite(ms) and ms > 0
        if not authentic:
            reasons.append('non-Cerebras Kimi assistant')
        if not message.get('responseId') or message.get('stopReason') not in ('stop', 'toolUse'):
            reasons.append('unsuccessful or unidentified assistant call')
        if not measured:
            reasons.append('invalid serverGeneration')
        call = dict(message_index=index, response_id=message.get('responseId'), provider=message.get('provider'),
                    model=message.get('model'), stopReason=message.get('stopReason'),
                    serverGeneration={k: generation[k] for k in ('completionMs', 'outputTokens') if k in generation},
                    timed_sample=bool(authentic and measured))
        if authentic and measured:
            call.update(outputTokens=tokens, completionMs=ms, tokensPerSecond=call_rate(tokens, ms))
        calls.append(call)
    rates = [c['tokensPerSecond'] for c in calls if c['timed_sample']]
    exact = mean_rate(rates) if rates else None
    rounded = round_rate(exact) if exact is not None else None
    score = dict(mean_exact_tps=exact, ui_rounded_tps=rounded,
                 ui_display=(f'{rounded:,}' if exact >= 100 else f'{exact:.1f}') if exact is not None else None,
                 call_count=len(rates), assistant_call_count=len(calls),
                 output_tokens=sum(c.get('outputTokens', 0) for c in calls),
                 generation_ms=sum(c.get('completionMs', 0) for c in calls),
                 formula='arithmetic mean of outputTokens / (completionMs / 1000)')
    if not rates:
        reasons.append('no authentic measured generation')
    return calls, score, reasons


def committed(repo, head, path, sources):
    body = sources.blob(path)
    saved = subprocess.check_output(['git', '-C', str(repo), 'show', head + ':' + str(path.relative_to(repo))], stderr=subprocess.PIPE)
    if saved != body:
        raise ValueError('working source differs from pinned commit: ' + str(path))
    return json.loads(body)


def audit_trial(row, repo, cache, archive, head, sources):
    result = dict(row, audit_errors=[], valid=False, reported_valid=row.get('valid') is True)
    errors = result['audit_errors']
    try:
        ident, label = row['id'], row['label']
        if str(uuid.UUID(ident)) != ident or not label.startswith('D') or '/' in label:
            raise ValueError('invalid run identity')
        root = repo / 'runs' / ident
        plan = committed(repo, head, root / 'plan.json', sources)
        result['sessionKey'] = plan['sessionKey']
        evidence = committed(repo, head, root / 'evidence.json', sources)
        manifest = committed(repo, head, root / 'gift-manifest.json', sources)
        raw_path = cache / 'runs' / (label + '.json')
        raw_bytes = sources.blob(raw_path)
        raw = json.loads(raw_bytes)
        validation = sources.json(cache / 'capture' / ident / 'validation.json')
        receipts_dir = cache / 'gift8-5051/receipts' / ident
        for path in (archive / (ident + '.json'), receipts_dir / 'private-raw.json'):
            if sources.blob(path) != raw_bytes:
                errors.append('raw archive byte mismatch: ' + str(path))
        if (raw.get('id') != ident or evidence.get('id') != ident or validation.get('run_id') != ident
                or raw.get('label') != label or plan.get('label') != label
                or raw.get('sessionKey') != plan.get('sessionKey') or manifest.get('sessionKey') != plan.get('sessionKey')):
            errors.append('raw/plan/evidence/session identity mismatch')
        for key in ('variant', 'prompt', 'thinking', 'temperature', 'top_p', 'max_completion_tokens', 'capturePolicy'):
            if raw.get(key) != plan.get(key):
                errors.append('raw plan mismatch: ' + key)
        if evidence.get('private_raw_sha256') != digest(raw_bytes) or evidence.get('private_raw_bytes') != len(raw_bytes) or validation.get('input_sha256') != digest(raw_bytes):
            errors.append('raw hash or byte count mismatch')
        calls, score, method_reasons = independent_score(raw)
        native_count = sum(part.get('type') == 'toolCall' for message in raw['history']['messages']
                           if message.get('role') == 'assistant' and message.get('__openclaw', {}).get('runId') == ident
                           for part in message.get('content', []) if isinstance(part, dict))
        expected_generations = 1 if plan['variant'] == 'gift8-prefetch' else 2
        result.update(score=score['mean_exact_tps'], ui=score['ui_rounded_tps'], calls=calls,
                      first_tps=calls[0].get('tokensPerSecond') if calls else None,
                      final_tps=calls[-1].get('tokensPerSecond') if calls else None,
                      call_count=len(calls), score_details=score, method_reasons=method_reasons,
                      started_wall=raw.get('startedWall'), ended_wall=raw.get('ended', {}).get('time'),
                      actual_generation_count=len(calls), expected_generation_count=expected_generations,
                      native_tool_call_count=native_count,
                      structure_expected=len(calls) == expected_generations and native_count == (0 if expected_generations == 1 else 5))
        if evidence.get('score') != score or validation.get('score') != score or evidence.get('calls') != calls or validation.get('calls') != calls:
            errors.append('independent all-call arithmetic or call identities differ from saved evidence')
        for key in ('score', 'ui', 'first_tps', 'final_tps', 'call_count', 'started_wall', 'ended_wall'):
            if row.get(key) != result.get(key):
                errors.append('iteration differs from raw: ' + key)
        expected_variant = 'gift8-tool' if row.get('arm') == 'A' else 'gift8-prefetch' if row.get('arm') == 'B' else None
        if plan.get('variant') != expected_variant or row.get('variant') != expected_variant:
            errors.append('arm/variant mismatch')
        saved_valid = evidence.get('validation', {}).get('valid') is True
        if saved_valid != (validation.get('valid') is True) or saved_valid != result['reported_valid']:
            errors.append('saved validity flags disagree')
        if 'method_valid' in row and row['method_valid'] is not saved_valid:
            errors.append('iteration method validity differs from evidence')
        for key in ('actual_generation_count', 'expected_generation_count', 'native_tool_call_count', 'structure_expected'):
            for saved in (evidence, validation):
                if key in saved and (saved_valid or key in ('actual_generation_count', 'expected_generation_count')) and saved[key] != result[key]:
                    errors.append('raw structural diagnostic differs from saved evidence: ' + key)
        products = [p['url'] for p in evidence.get('products', []) if p.get('verified') is True]
        if products != row.get('product_urls') or products != [p['url'] for p in validation.get('products', []) if p.get('verified') is True]:
            errors.append('verified product lists disagree')
        result['product_urls'] = products
        log = cache.parent / 'gateway.log'
        result['terminal_429'] = terminal_429(raw, log if log.exists() else None)
        if log.exists():
            sources.blob(log)
        if row.get('terminal_429') is not result['terminal_429']:
            errors.append('terminal 429 differs from correlated raw/log evidence')
        manifest_bytes = sources.blob(cache / 'gift8-5051/manifests' / (ident + '.json'))
        if (json.loads(manifest_bytes) != manifest or manifest.get('id') != ident or manifest.get('ids') != IDS
                or manifest.get('protocol') != 'gift8-v1' or manifest.get('arm') != plan['variant'].removeprefix('gift8-')):
            errors.append('manifest identity/protocol differs')
        if saved_valid:
            if method_reasons or raw.get('ended', {}).get('terminal') != 'final':
                errors.append('valid result contains unsuccessful or unmeasured calls')
            if len(products) != 5 or len(set(products)) != 5:
                errors.append('valid result lacks five distinct products')
            plugin = repo / 'tools/gift8-plugin'
            plugin_sha = digest(b''.join(sources.blob(plugin / n) for n in sorted(('index.cjs', 'openclaw.plugin.json', 'package.json'))))
            if (manifest.get('plugin_sha256') != plugin_sha or evidence.get('plugin_sha256') != plugin_sha
                    or evidence.get('manifest_sha256') != digest(manifest_bytes)
                    or manifest.get('prompt_sha256') != digest(raw['prompt'].encode())):
                errors.append('plugin/manifest/prompt hash mismatch')
            cards, receipts = [], []
            messages = [(i, m) for i, m in enumerate(raw['history']['messages']) if m.get('__openclaw', {}).get('runId') == ident]
            native_calls, native_results = {}, {}
            for index, message in messages:
                if message.get('role') == 'assistant':
                    for part in message.get('content', []):
                        if part.get('type') == 'toolCall':
                            if part.get('id') in native_calls or part.get('name') != 'gift_lookup':
                                errors.append('unexpected or duplicate native tool call')
                            native_calls[part.get('id')] = (index, part.get('arguments'))
                elif message.get('role') == 'toolResult':
                    if message.get('toolCallId') in native_results:
                        errors.append('duplicate native tool result')
                    native_results[message.get('toolCallId')] = (index, message)
            final_index = max(i for i, m in messages if m.get('role') == 'assistant')
            if not (len(native_calls) == len(native_results) == 5 if manifest['arm'] == 'tool' else native_calls.keys() == native_results.keys()):
                errors.append('native tool/result counts differ from arm protocol')
            for product_id in IDS:
                receipt = sources.json(receipts_dir / f'fetch-{product_id}.json')
                public_receipt = committed(repo, head, root / 'gift-receipts' / f'fetch-{product_id}.json', sources)
                body_name = receipt['body_file']
                if Path(body_name).name != body_name:
                    raise ValueError('unsafe receipt body filename')
                body = sources.blob(receipts_dir / body_name)
                committed(repo, head, root / 'gift-receipts' / body_name, sources)
                if sources.blob(root / 'gift-receipts' / body_name) != body or public_receipt != receipt or digest(body) != receipt['body_sha256']:
                    errors.append('receipt/public body hash mismatch')
                card = canonical_card(json.loads(body))
                expected_url = f'https://aisynthesis.com/wp-json/wc/store/v1/products/{product_id}?_fields=id,name,permalink,prices,stock_availability,variations,is_in_stock'
                if (card['id'] != product_id or jsjson(card) != jsjson(receipt['card']) or digest(jsjson(card)) != receipt['card_sha256']
                        or any(receipt.get(k) != v for k, v in dict(id=ident, sessionKey=plan['sessionKey'], arm=manifest['arm'], product_id=product_id,
                                                                  prompt_sha256=manifest['prompt_sha256'], protocol='gift8-v1').items())
                        or receipt.get('url') != expected_url or receipt.get('final_url') != expected_url
                        or receipt.get('status') != 200 or not raw['startedWall'] <= receipt['started_ms'] <= receipt['completed_ms'] <= raw['ended']['time']):
                    errors.append('receipt identity, timing or exact card mismatch')
                call_id = receipt.get('tool_call_id')
                if manifest['arm'] == 'tool':
                    ci, args = native_calls[call_id]
                    ri, message = native_results[call_id]
                    text = ''.join(p.get('text', '') for p in message.get('content', []) if p.get('type') == 'text')
                    if (args != {'id': product_id} or not ci < ri < final_index or message.get('isError') is not False
                            or message.get('toolName') != 'gift_lookup' or jsjson(json.loads(text)) != jsjson(card)):
                        errors.append('native call/result identity, order or card mismatch')
                    if 'details' in message and (not isinstance(message['details'], dict)
                            or jsjson(message['details'].get('card')) != jsjson(card)
                            or message['details'].get('receipt_file') != f'fetch-{product_id}.json'):
                        errors.append('native optional result details differ from receipt')
                elif call_id is not None:
                    errors.append('prefetch receipt claims native tool call')
                cards.append(card)
                receipts.append(receipt)
            followup_links = []
            if manifest['arm'] == 'prefetch':
                for call_id, (ci, args) in native_calls.items():
                    if not isinstance(args, dict) or set(args) != {'id'} or type(args['id']) is not int or args['id'] not in IDS:
                        raise ValueError('unexpected prefetch follow-up arguments')
                    product_id = args['id']
                    receipt, card = receipts[IDS.index(product_id)], cards[IDS.index(product_id)]
                    ri, message = native_results[call_id]
                    text = ''.join(p.get('text', '') for p in message.get('content', []) if p.get('type') == 'text')
                    if (not ci < ri < final_index or message.get('isError') is not False
                            or message.get('toolName') != 'gift_lookup' or jsjson(json.loads(text)) != jsjson(card)):
                        errors.append('prefetch follow-up native result identity, order or card mismatch')
                    if 'details' in message and (not isinstance(message['details'], dict)
                            or jsjson(message['details'].get('card')) != jsjson(card)
                            or message['details'].get('receipt_file') != f'fetch-{product_id}.json'):
                        errors.append('prefetch follow-up optional details differ from receipt')
                    name = digest(call_id.encode()) + '.json'
                    link_bytes = sources.blob(receipts_dir / 'calls' / name)
                    link = json.loads(link_bytes)
                    public = root / 'gift-receipts/calls' / name
                    committed(repo, head, public, sources)
                    if sources.blob(public) != link_bytes:
                        errors.append('prefetch follow-up public receipt byte mismatch')
                    expected = dict(id=ident, sessionKey=plan['sessionKey'], arm='prefetch', product_id=product_id,
                                    tool_call_id=call_id, receipt_file=f'fetch-{product_id}.json', card_sha256=receipt['card_sha256'])
                    if (any(link.get(k) != v for k, v in expected.items())
                            or not receipt['completed_ms'] <= link['timestamp_ms'] <= raw['ended']['time']):
                        errors.append('prefetch follow-up receipt identity, card hash or timing mismatch')
                    followup_links.append(dict(file=name, sha256=digest(link_bytes), **link))
                if (native_calls or 'followup_call_receipts' in evidence) and evidence.get('followup_call_receipts') != followup_links:
                    errors.append('prefetch follow-up receipt hashes differ from committed evidence')
                if (native_calls or 'followup_call_receipts' in validation) and validation.get('followup_call_receipts') != followup_links:
                    errors.append('prefetch follow-up receipt hashes differ from saved validation')
                result['followup_call_receipts'] = followup_links
            if products != [card['url'] for card in cards]:
                errors.append('verified product URLs differ from exact source cards')
            assistants = [m for m in raw['history']['messages'] if m.get('role') == 'assistant' and m.get('__openclaw', {}).get('runId') == ident]
            text = ''.join(p.get('text', '') for p in assistants[-1].get('content', []) if p.get('type') == 'text').strip()
            if text.startswith('```json\n') and text.endswith('\n```'):
                text = text[8:-4]
            elif text.startswith('```\n') and text.endswith('\n```'):
                text = text[4:-4]
            if jsjson(json.loads(text)) != jsjson(dict(gifts=cards)):
                errors.append('final JSON differs from five exact source cards')
            hook_result = dict(calls=calls, followup_call_receipts=followup_links)
            for path in sorted((receipts_dir / 'events').glob('*.json')):
                sources.blob(path)
            validate_events(receipts_dir, raw, manifest, cards, receipts, hook_result)
            if any(hook_result.get(k) != evidence.get(k) for k in ('hook_evidence', 'first_input_sha256')):
                errors.append('hook hash or first-input hash mismatch')
        result['valid'] = saved_valid and not errors
    except (OSError, ValueError, TypeError, KeyError, IndexError, AttributeError, subprocess.SubprocessError) as error:
        errors.append(str(error) if isinstance(error, ValueError) else type(error).__name__ + ': ' + str(error)[:300])
    result['audit_passed'] = not errors
    result['single_generation_success'] = bool(result['valid'] and result.get('actual_generation_count') == 1)
    return result


def pair_results(rows):
    pairs = []
    for block in range(4):
        group = rows[block * 2:block * 2 + 2]
        a = next((r for r in group if r.get('arm') == 'A'), None)
        b = next((r for r in group if r.get('arm') == 'B'), None)
        reasons = []
        for side, row in (('A', a), ('B', b)):
            if row is None or not row.get('valid'):
                reasons.append(side + ' missing or invalid')
            elif not all(finite(row.get(k)) for k in ('first_tps', 'score', 'started_wall')):
                reasons.append(side + ' missing finite metrics')
        if a and b:
            urls = a.get('product_urls', [])
            if len(urls) != 5 or len(set(urls)) != 5 or urls != b.get('product_urls'):
                reasons.append('ordered five product URLs differ or are incomplete')
            if not finite(a.get('started_wall')) or not finite(b.get('started_wall')) or abs(a['started_wall'] - b['started_wall']) > 900000:
                reasons.append('send starts differ by more than 15 minutes or are missing')
        pairs.append(dict(pair=block + 1, a=a.get('label') if a else None, b=b.get('label') if b else None,
                          valid=not reasons, reasons=reasons,
                          delta_first_tps=b['first_tps'] - a['first_tps'] if not reasons else None,
                          delta_official_mean_tps=b['score'] - a['score'] if not reasons else None))
    return pairs


def span_audit(caches, campaign_ids, sources):
    spans, incomplete, errors, excluded = [], [], [], []
    for scope, cache in caches.items():
        directory = cache / 'runs'
        labels = set()
        for path in directory.glob('*.json'):
            if path.name.startswith('._'):
                continue
            for suffix in ('.send-intent.json', '.pending.json', '.terminal.json'):
                if path.name.endswith(suffix):
                    labels.add(path.name[:-len(suffix)])
                    break
            else:
                if path.name.count('.') == 1:
                    labels.add(path.stem)
        for label in sorted(labels):
            values = {}
            try:
                for suffix in ('.json', '.send-intent.json', '.pending.json', '.terminal.json'):
                    path = directory / (label + suffix)
                    if path.exists():
                        values[suffix] = sources.json(path)
                raw = values.get('.json', {})
                marker = values.get('.send-intent.json', values.get('.pending.json', {}))
                identity = raw.get('id', marker.get('id'))
                start = marker.get('startedWall', raw.get('startedWall'))
                end = raw.get('ended', {}).get('time')
                terminal = raw.get('ended', {}).get('terminal')
                if scope == 'test' and identity not in campaign_ids and not re.fullmatch(r'D[0-9]+-gift8-(?:tool|prefetch)', label):
                    excluded.append(dict(scope=scope, label=label, id=identity, start=start, end=end,
                                         reason='historical same-root test outside gift8 versus main/exp audit'))
                    continue
                if not values.get('.json') or not finite(start) or not finite(end) or end < start or terminal not in ('final', 'error', 'aborted'):
                    incomplete.append(dict(scope=scope, label=label, id=identity, started=start, ended=end))
                    continue
                if marker and (marker.get('id') != identity or marker.get('sessionKey') != raw.get('sessionKey') or marker.get('startedWall', start) != raw.get('startedWall')):
                    errors.append(scope + '/' + label + ': timing identity mismatch')
                spans.append(dict(scope=scope, label=label, id=identity, start=start, end=end))
            except (OSError, ValueError, TypeError, KeyError) as error:
                incomplete.append(dict(scope=scope, label=label, error=str(error)))
    overlaps = []
    comparisons = 0
    campaign_comparisons = 0
    for i, a in enumerate(spans):
        for b in spans[i + 1:]:
            comparisons += 1
            if a['id'] in campaign_ids or b['id'] in campaign_ids:
                campaign_comparisons += 1
            if max(a['start'], b['start']) < min(a['end'], b['end']):
                overlaps.append(dict(a=a, b=b, campaign_related=a['id'] in campaign_ids or b['id'] in campaign_ids))
    campaign_overlaps = [p for p in overlaps if p['campaign_related']]
    return dict(passed=not incomplete and not errors and not campaign_overlaps, spans=spans, incomplete_sends=incomplete,
                errors=errors, comparisons=comparisons, campaign_comparisons=campaign_comparisons,
                all_historical_overlaps=overlaps, campaign_overlaps=campaign_overlaps,
                historical_test_exclusions=excluded,
                scope='all local main/exp spans plus current gift8 test sends; older same-root test sends explicitly excluded')


def reservation_audit(events, rows, expected_locks=None):
    opened, intervals, errors = {}, [], []
    for event in events:
        kind, pid, at = event.get('event'), event.get('pid'), event.get('at_ms')
        if kind not in ('reserved', 'releasing'):
            continue
        if type(pid) is not int or not finite(at):
            errors.append('malformed reservation event')
            continue
        if kind == 'reserved':
            if pid in opened:
                errors.append('duplicate open reservation for PID ' + str(pid))
            if expected_locks is not None and set(event.get('locks', [])) != set(expected_locks):
                errors.append('reservation does not name the three expected profile locks')
            opened[pid] = event
        elif pid not in opened:
            errors.append('release without same-PID reservation: ' + str(pid))
        else:
            start = opened.pop(pid)
            if at < start['at_ms']:
                errors.append('reservation release precedes acquisition')
            intervals.append(dict(pid=pid, start=start['at_ms'], end=at, locks=start.get('locks', [])))
    coverage = []
    for row in rows:
        matches = [r for r in intervals if finite(row.get('started_wall')) and finite(row.get('ended_wall'))
                   and r['start'] <= row['started_wall'] <= row['ended_wall'] <= r['end']]
        coverage.append(dict(id=row.get('id'), label=row.get('label'), passed=len(matches) == 1, intervals=matches))
    return dict(passed=bool(rows) and not errors and not opened and all(r['passed'] for r in coverage),
                intervals=intervals, still_open=list(opened.values()), errors=errors, coverage=coverage)


def target_clip_verified(row, inspection):
    """Gift8 clip criterion; full-run coverage remains an independent diagnostic."""
    try:
        duration = float(inspection['media']['demo.mp4']['ffprobe']['format']['duration'])
        urls = row['product_urls']
        return bool(row.get('valid') is True and row.get('audit_passed') is True
                    and finite(row.get('score')) and row['score'] >= 1700
                    and type(row.get('ui')) is int and row['ui'] >= 1700
                    and inspection.get('id') == row['id']
                    and inspection.get('sessionKey') == row['sessionKey']
                    and inspection.get('displayedMean') == row['ui']
                    and isinstance(urls, list) and len(urls) == len(set(urls)) == 5
                    and inspection.get('verifiedProductURLs') == urls
                    and inspection.get('viewportVerified') is True
                    and inspection.get('real_time_verified') is True
                    and inspection.get('playable') is True
                    and finite(duration) and 0 < duration <= 60)
    except (KeyError, TypeError, ValueError):
        return False


def completion_state(sent_count, completed_count, verified_targets, raw_targets, audit_ok):
    comparison_complete = sent_count == completed_count == 8
    raw_ids = {row['id'] if isinstance(row, dict) else row for row in raw_targets}
    missing_clips = bool(raw_ids - set(verified_targets))
    goal_complete = bool(verified_targets) and audit_ok and not missing_clips
    passed = audit_ok and not missing_clips and (comparison_complete or goal_complete)
    return dict(comparison_complete=comparison_complete, goal_complete=goal_complete,
                complete=passed, passed=passed,
                status='goal_complete' if goal_complete else 'passed' if passed else
                'target_needs_attention' if raw_targets else 'incomplete_or_blocked')


def inspect_movies(rows, repo, cache, destination, audit_dir, sources):
    runtime = gift8_film.film
    runtime.REPO, runtime.CACHE = repo, cache
    results, copies = [], []
    for row in rows:
        if not row.get('sessionKey'):
            continue
        base = cache / 'film-gift8-5051' / row['id']
        receipt = base / 'receipt.json'
        if receipt.exists():
            sources.blob(receipt)
        for directory in runtime.attempts(base):
            item = dict(id=row['id'], label=row['label'], directory=str(directory), inspection=None, issues=[])
            for name in ('ready.json', 'recording.json', 'capture-timeline.json', 'viewport-evidence.json'):
                if (directory / name).exists():
                    sources.blob(directory / name)
            try:
                saved_put = runtime.put
                inspection_path = audit_dir / (row['id'] + '-' + directory.name + '.json')
                runtime.put = lambda path, value: write(inspection_path, value)
                try:
                    info = runtime.inspect(row['label'], dict(id=row['id'], sessionKey=row['sessionKey']), directory)
                finally:
                    runtime.put = saved_put
                item['inspection'] = info
                for name, media in info.get('media', {}).items():
                    sources.files[str((directory / name).resolve())] = dict(sha256=media['sha256'], bytes=media['bytes'])
                item['inspection_path'] = str(inspection_path)
                item['target_verified'] = target_clip_verified(row, info)
            except (OSError, ValueError, TypeError, KeyError, subprocess.SubprocessError) as error:
                item['issues'].append('inspection: ' + str(error))
            demo = directory / 'demo.mp4'
            if demo.is_file() and not demo.is_symlink():
                playable_demo = False
                try:
                    body, media = read_capture_file(demo)
                    playable_demo = True
                    sources.files[str(demo.resolve())] = dict(sha256=media['sha256'], bytes=media['bytes'])
                    copied = destination / (row['label'] + '-' + row['id'][:8] + '-' + directory.name + '.mp4')
                    copied.parent.mkdir(parents=True, exist_ok=True)
                    if copied.exists() and (copied.is_symlink() or copied.read_bytes() != body):
                        raise ValueError('existing demo destination differs; refusing overwrite')
                    if not copied.exists():
                        shutil.copyfile(demo, copied)
                        copied.chmod(0o600)
                    if digest(copied.read_bytes()) != media['sha256']:
                        raise ValueError('copied media hash mismatch')
                    item['copied_demo'] = str(copied)
                    copies.append(dict(source=str(demo), path=str(copied), **media))
                except (OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
                    item['issues'].append('demo: ' + str(error))
                    item['copy_failed'] = playable_demo
            results.append(item)
    return results, copies


def build(repo, cache, archive, caches, destination, audit_dir):
    sources = Sources()
    campaign = cache / 'gift8-5051'
    rows = sources.rows(campaign / 'iterations.jsonl')
    head = subprocess.check_output(['git', '-C', str(repo), 'rev-parse', 'HEAD'], text=True).strip()
    errors = []
    identifiers = [r.get('id') for r in rows]
    if len(rows) > 8 or len(set(identifiers)) != len(rows):
        errors.append('more than eight rows or duplicate identities')
    if ''.join(r.get('arm', '?') for r in rows) != ORDER[:len(rows)]:
        errors.append('send order differs from ABBABAAB')
    audited = [audit_trial(row, repo, cache, archive, head, sources) for row in rows]
    for row in audited:
        errors.extend(row['label'] + ': ' + message for message in row['audit_errors'])
    spans = span_audit(caches, set(identifiers), sources)
    reservations = reservation_audit(sources.rows(campaign / 'reservation.jsonl'), audited,
                                     [str(path / 'loop.lock') for path in caches.values()])
    sent = []
    for path in (cache / 'runs').glob('D*-gift8-*.send-intent.json'):
        marker = sources.json(path)
        sent.append(dict(id=marker.get('id'), path=str(path)))
    if len(sent) != len(rows) or {r['id'] for r in sent} != set(identifiers):
        errors.append('send intents and completed iteration rows differ')
    pairs = pair_results(audited)
    movies, copies = inspect_movies(audited, repo, cache, destination, audit_dir, sources)
    for movie in movies:
        if movie.get('copy_failed'):
            errors.append(movie['label'] + ': playable demo could not be copied and verified')
    conditions = {}
    for arm in 'AB':
        group = [r for r in audited if r.get('arm') == arm]
        valid = [r for r in group if r['valid']]
        conditions[arm] = dict(sent=len(group), valid=len(valid), failed=len(group)-len(valid),
                               terminal_429=sum(r.get('terminal_429') is True for r in group),
                               success_rate=len(valid)/len(group) if group else None,
                               single_generation_successes=sum(r['single_generation_success'] for r in valid),
                               single_generation_success_rate=sum(r['single_generation_success'] for r in valid)/len(group) if group else None,
                               extra_generation_successes=sum(r.get('actual_generation_count', 0) > 1 for r in valid))
    valid_pairs = [p for p in pairs if p['valid']]
    comparison = dict(valid_pairs=len(valid_pairs), first_tps_wins=sum(p['delta_first_tps'] > 0 for p in valid_pairs),
                      mean_wins=sum(p['delta_official_mean_tps'] > 0 for p in valid_pairs))
    for metric in ('first_tps', 'official_mean_tps'):
        values = [p['delta_' + metric] for p in valid_pairs]
        comparison['mean_delta_' + metric] = mean(values) if values else None
        comparison['median_delta_' + metric] = median(values) if values else None
    targets = [r for r in audited if r['valid'] and finite(r.get('score')) and r['score'] >= 1700 and r.get('ui', 0) >= 1700]
    for row in targets:
        if not any(m['id'] == row['id'] and m.get('target_verified') for m in movies):
            errors.append(row['label'] + ': 1700 target lacks verified same-run playable clip, official UI and five URL holds')
    warnings = []
    for path in cache.glob('*reservation.jsonl'):
        if path.name.startswith('._'):
            continue
        old = reservation_audit(sources.rows(path), [])
        if old['still_open']:
            warnings.append('legacy reservation lacks release: ' + str(path))
    if spans['all_historical_overlaps']:
        warnings.append('Historical overlap list must be read separately from this campaign; no hardware inference is made.')
    verified_targets = sorted({m['id'] for m in movies if m.get('target_verified')})
    completion = completion_state(len(sent), len(rows), verified_targets, targets,
                                  not errors and spans['passed'] and reservations['passed'])
    return dict(schema_version=1, generated_at=datetime.now(timezone.utc).isoformat(), pinned_commit=head,
                **completion,
                expected_order=ORDER, sent_count=len(sent), completed_count=len(rows), rows=audited,
                conditions=conditions, pairs=pairs, comparison=comparison, no_overlap=spans, reservation=reservations,
                movies=movies, copied_demos=copies, target_runs=[r['id'] for r in targets],
                verified_target_runs=verified_targets, errors=errors, warnings=warnings,
                target_clip_criterion=dict(raw_mean_min_tps=1700, displayed_ui_min_tps=1700, verified_products=5,
                                           max_demo_seconds=60, requires_full_run=False),
                sources=sources.files, limitations=['Local persisted evidence only; no fresh merchant validation or provider query.',
                'Four within-study pairs do not establish hardware performance or legal/compliance conclusions.'])


def korean_report(audit, audit_path, checksums_path):
    def number(value):
        return f'{value:,.3f}' if finite(value) else '없음'
    headline = ('1700 TPS 목표 클립 검증 완료' if audit['goal_complete'] else '8회 비교 감사 통과' if audit['passed'] else
                '목표 점수의 영상·감사 확인 필요' if audit['status'] == 'target_needs_attention' else '진행 중 또는 감사 보류')
    lines = ['# gift8 비교 및 목표 클립 보고서', '',
             f"상태: **{headline}**. 실제 전송 {audit['sent_count']}/8회, 완료 기록 {audit['completed_count']}/8회. 8회 비교 완료: {'예' if audit['comparison_complete'] else '아니요'}.", '',
             'A는 모델의 gift_lookup 호출, B는 첫 모델 호출 전 상품 정보 주입입니다. 지정 순서는 ABBABAAB이며, 인접한 두 실행을 한 쌍으로 비교합니다.', '',
             '공식 점수는 각 호출의 `outputTokens / (completionMs / 1000)`를 구한 뒤 모든 호출 속도를 산술평균합니다. 첫 호출과 최종 호출의 속도는 별도 진단값입니다.', '',
             '| 조건 | 전송 | 유효 | 실패 | 종료 429 | 성공률 |', '|---|---:|---:|---:|---:|---:|']
    for arm, c in audit['conditions'].items():
        rate = f"{100*c['success_rate']:.1f}%" if c['success_rate'] is not None else '없음'
        lines.append(f"| {arm} | {c['sent']} | {c['valid']} | {c['failed']} | {c['terminal_429']} | {rate} |")
    b = audit['conditions']['B']
    lines += ['', f"B의 유효한 1회 생성 성공은 {b['single_generation_successes']}/{b['sent']}회이며, 유효하지만 추가 생성이 발생한 성공은 {b['extra_generation_successes']}회입니다. 추가 도구 호출·생성은 제외하지 않고 공식 평균과 전체 성공률에 그대로 포함했습니다. 1회 생성 가설과 실제 과제 성공 여부는 별도 지표입니다."]
    lines += ['', '| 실행 | 조건 | 유효 | 첫 호출 TPS | 최종 호출 TPS | 전체 호출 평균 TPS | UI | 호출 수 |', '|---|---|---|---:|---:|---:|---:|---:|']
    for r in audit['rows']:
        lines.append(f"| {r['label']} | {r.get('arm')} | {'예' if r['valid'] else '아니요'} | {number(r.get('first_tps'))} | {number(r.get('final_tps'))} | {number(r.get('score'))} | {r.get('ui')} | {r.get('call_count')} |")
    lines += ['', '| 쌍 | A | B | 유효 | 첫 호출 B−A TPS | 공식 평균 B−A TPS | 제외 이유 |', '|---|---|---|---|---:|---:|---|']
    for p in audit['pairs']:
        lines.append(f"| {p['pair']} | {p['a'] or '없음'} | {p['b'] or '없음'} | {'예' if p['valid'] else '아니요'} | {number(p['delta_first_tps'])} | {number(p['delta_official_mean_tps'])} | {'; '.join(p['reasons']) or '없음'} |")
    c = audit['comparison']
    lines += ['', '유효 비교쌍은 두 실행 모두 검증을 통과하고, 순서까지 같은 서로 다른 상품 URL 5개를 반환하며, 시작 시각 차이가 15분 이내인 경우입니다.', '',
              f"유효 {c['valid_pairs']}/4쌍. B의 첫 호출 우세 {c['first_tps_wins']}쌍, 공식 평균 우세 {c['mean_wins']}쌍. 첫 호출 차이 중앙값 {number(c['median_delta_first_tps'])} TPS, 공식 평균 차이 중앙값 {number(c['median_delta_official_mean_tps'])} TPS.", '',
              f"로컬 실행 구간 비교 {audit['no_overlap']['comparisons']}건(이 캠페인 관련 {audit['no_overlap']['campaign_comparisons']}건). 캠페인 중첩 {len(audit['no_overlap']['campaign_overlaps'])}건, 미완료 전송 {len(audit['no_overlap']['incomplete_sends'])}건. 예약·해제 동일 PID 및 전 실행 구간 포함 검사는 {'통과' if audit['reservation']['passed'] else '미통과'}입니다.", '',
              f"중첩 감사 범위는 이번 gift8 전송과 로컬 main/exp의 모든 실행입니다. 같은 test 프로필의 과거 실행 {len(audit['no_overlap']['historical_test_exclusions'])}건은 상세 JSON에 제외 이유와 시각을 남겼으며, 이번 캠페인 중첩으로 계산하지 않았습니다.", '',
              '| 영상 | 재검사 분류 | 첫 프레임 시점 | UI·5 URL 검증 | 1700 목표 클립 | 전체 실행 촬영 |', '|---|---|---|---|---|---|']
    for item in audit['movies']:
        info = item.get('inspection') or {}
        movie = f"[{Path(item['copied_demo']).name}](<{item['copied_demo']}>)" if item.get('copied_demo') else item['label'] + ' (재생 파일 없음)'
        lines.append(f"| {movie} | {info.get('classification', 'unavailable')} | {info.get('timing', 'unknown')} | {info.get('viewportVerified', False)} | {item.get('target_verified', False)} | {info.get('full_run_verified', False)} |")
    lines += ['', '원본 영상은 재생성하거나 편집하지 않았습니다. 복사한 모든 재생 가능 demo는 SHA256을 원본과 대조했습니다. 1700 TPS 목표 클립은 같은 원본 실행·세션의 공식 평균과 실제 UI 점수 모두 1700 이상, 검증된 상품 URL 5개, 실제 시간 흐름 및 60초 이하 재생 클립을 요구합니다. 첫 프레임이 전송 전이어야 한다는 조건은 목표 클립 판정에 추가하지 않습니다. 부분·종료 후 촬영 여부와 전체 실행 촬영 검증은 별도로 표시하며, 목표 클립 통과를 전체 실행 촬영이나 주최 측 수락으로 해석하지 않습니다.', '',
              '감사 오류: ' + ('; '.join(audit['errors']) or '없음'), '',
              '실행 실패 사유: ' + ('; '.join(r['label'] + ': ' + ', '.join(r.get('rejection', [])) for r in audit['rows'] if not r['valid']) or '없음'), '',
              '주의 기록: ' + ('; '.join(audit['warnings']) or '없음'), '',
              '미완료 전송 또는 닫히지 않은 예약이 있으면 완료 감사를 통과할 수 없습니다. 이 결과는 이번 실행 범위의 관측이며 하드웨어 성능이나 법적 사항으로 일반화하지 않습니다.', '',
              f"[상세 감사 JSON](<{audit_path}>) · [출처·복사 파일 SHA256 목록](<{checksums_path}>)", '']
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--copy-demos', required=True, type=Path)
    args = parser.parse_args()
    root = Path(os.environ.get('BOUNTY_ROOT', TEST_ROOT)).resolve()
    archive = Path(os.environ.get('BOUNTY_RAW_ARCHIVE', ARCHIVE)).resolve()
    branch = subprocess.check_output(['git', '-C', str(REPO), 'branch', '--show-current'], text=True).strip()
    if root != TEST_ROOT.resolve() or archive != ARCHIVE.resolve() or branch != 'test':
        parser.error('requires the isolated test root, raw-test archive and test branch')
    output, destination = args.output.resolve(), args.copy_demos.resolve()
    if not output.is_relative_to(REPO.parent) or not destination.is_relative_to(REPO.parent):
        parser.error('report and demo copies must stay inside the project directory')
    os.umask(0o077)
    audit_path = output.with_suffix('.audit.json')
    checksums_path = output.with_suffix('.sha256.json')
    audit = build(REPO, root / 'mean-2000', archive,
                  dict(test=root/'mean-2000', main=MAIN_ROOT/'mean-2000', exp=MAIN_ROOT.with_name(MAIN_ROOT.name+'-exp2000')/'mean-2000'),
                  destination, output.parent/(output.stem+'-media-inspections'))
    write(audit_path, audit)
    write(output, korean_report(audit, audit_path, checksums_path))
    artifacts = {}
    for path in ([output, audit_path] + [Path(m['path']) for m in audit['copied_demos']]
                 + [Path(m['inspection_path']) for m in audit['movies'] if m.get('inspection_path')]):
        body = path.read_bytes()
        artifacts[str(path)] = dict(sha256=digest(body), bytes=len(body))
    write(checksums_path, dict(sources=audit['sources'], artifacts=artifacts))
    print(json.dumps(dict(status=audit['status'], report=str(output), audit=str(audit_path), checksums=str(checksums_path), copied_demos=len(audit['copied_demos'])), ensure_ascii=False))
    return 0 if audit['passed'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
