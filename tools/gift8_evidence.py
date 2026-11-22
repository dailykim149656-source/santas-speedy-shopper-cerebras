#!/usr/bin/env python3
"""Separate gift8-v1 native evidence validator; never fabricates web_fetch history."""
import argparse
import concurrent.futures
import hashlib
import json
from pathlib import Path
import sys
import subprocess
import os

import ledger
import validate as retail
from scoring import call_rate, mean_rate, round_rate

IDS = [21951, 23345, 11125, 11141, 20209]
PROTOCOL = 'gift8-v1'


def jsjson(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode()


def canonical_card(product):
    prices = product['prices']
    def integer(value):
        if isinstance(value, bool) or not str(value).isdigit() or int(value) > 9007199254740991:
            raise ValueError('invalid catalog price')
        return int(value)
    if type(product.get('id')) is not int or not isinstance(product.get('name'), str) or not product['name'] or type(product.get('is_in_stock')) is not bool:
        raise ValueError('invalid catalog identity or stock')
    span = prices.get('price_range')
    return dict(id=product['id'], name=product['name'], url=product['permalink'],
                price_minor=integer(prices['price']),
                price_range_minor=None if span is None else [integer(span['min_amount']), integer(span['max_amount'])],
                currency=prices['currency_code'], stock=product['is_in_stock'],
                options=sorted(set(a['value'] for v in product.get('variations', [])
                                   for a in v.get('attributes', []) if isinstance(a.get('value'), str))))


def bounded_file(root, name):
    path = root / name
    if path.resolve().parent != root.resolve() or path.is_symlink() or not path.is_file():
        raise ValueError('missing or unsafe receipt file')
    return path


def score_raw(raw):
    calls, reasons = [], []
    for i, message in enumerate(raw['history']['messages']):
        if message.get('role') != 'assistant' or message.get('__openclaw', {}).get('runId') != raw['id']:
            continue
        authentic = message.get('provider') == 'cerebras' and message.get('model') == retail.MODEL
        if not authentic:
            reasons.append('non-Cerebras Kimi trial assistant call')
        if not message.get('responseId') or message.get('stopReason') not in ('stop', 'toolUse'):
            reasons.append('unsuccessful or unidentified assistant call')
        g = message.get('serverGeneration', {})
        ms, tokens = g.get('completionMs'), g.get('outputTokens')
        valid = retail.finite(ms) and ms > 0 and retail.finite(tokens) and tokens >= 1
        if not valid:
            reasons.append('assistant call missing valid serverGeneration')
        call = dict(message_index=i, response_id=message.get('responseId'), provider=message.get('provider'),
                    model=message.get('model'), stopReason=message.get('stopReason'),
                    serverGeneration=ledger.pick(g, ('completionMs', 'outputTokens')), timed_sample=bool(valid and authentic))
        if valid and authentic:
            call.update(completionMs=ms, outputTokens=tokens, tokensPerSecond=call_rate(tokens, ms))
        calls.append(call)
    rates = [c['tokensPerSecond'] for c in calls if c['timed_sample']]
    mean = mean_rate(rates) if rates else None
    rounded = round_rate(mean) if mean is not None else None
    score = dict(mean_exact_tps=mean, ui_rounded_tps=rounded,
                 ui_display=(f'{rounded:,}' if mean >= 100 else f'{mean:.1f}') if mean is not None else None,
                 call_count=len(rates), assistant_call_count=len(calls),
                 output_tokens=sum(c.get('outputTokens', 0) for c in calls),
                 generation_ms=sum(c.get('completionMs', 0) for c in calls),
                 formula='arithmetic mean of outputTokens / (completionMs / 1000)')
    if not rates:
        reasons.append('no authentic measured generation')
    return calls, score, reasons


def plugin_digest(directory):
    files = sorted(p for p in directory.rglob('*') if p.is_file() and not p.name.startswith('._'))
    if not files:
        raise ValueError('plugin source unavailable')
    return {str(p.relative_to(directory)): ledger.sha(p.read_bytes()) for p in files}


def validate(repo, raw_path, receipt_dir, manifest_path=None, plugin_dir=None):
    repo, raw_path, receipt_dir = Path(repo).resolve(), Path(raw_path), Path(receipt_dir).resolve()
    original = raw_path.read_bytes()
    raw = json.loads(original)
    ident, session = raw['id'], raw['sessionKey']
    dest = ledger.run_dir(repo, ident)
    manifest_path = Path(manifest_path) if manifest_path else dest / 'gift-manifest.json'
    calls, score, reasons = score_raw(raw)
    result = dict(protocol=PROTOCOL, run_id=ident, input_sha256=ledger.sha(original),
                  input_bytes=len(original), calls=calls, score=score, products=[], retail_sources=[],
                  actual_generation_count=len(calls),
                  expected_generation_count=1 if raw.get('variant') == 'gift8-prefetch' else 2,
                  structure_expected=len(calls) == (1 if raw.get('variant') == 'gift8-prefetch' else 2))
    def require(test, reason):
        if not test:
            raise ValueError(reason)
    try:
        manifest_bytes = manifest_path.read_bytes()
        manifest = json.loads(manifest_bytes)
        planned = ledger.read(dest / 'plan.json')
        require((dest / 'gift-manifest.json').read_bytes() == manifest_bytes, 'manifest differs from committed copy')
        for name in ('plan.json', 'gift-manifest.json'):
            relative = str((dest / name).relative_to(repo))
            require(subprocess.check_output(['git', '-C', str(repo), 'show', 'HEAD:' + relative]) == (dest / name).read_bytes(), 'plan or manifest not committed exactly')
        arm = manifest.get('arm')
        require(manifest.get('id') == ident and manifest.get('sessionKey') == session and manifest.get('protocol') == PROTOCOL
                and manifest.get('ids') == IDS and arm in ('tool', 'prefetch'), 'foreign manifest identity or protocol')
        require(planned.get('variant') == 'gift8-' + arm and planned.get('sessionKey') == session
                and planned.get('prompt') == raw.get('prompt'), 'plan differs from run')
        for key in ledger.PLAN:
            if key in planned:
                require(raw.get(key) == planned[key], 'raw differs from planned ' + key)
        prompt_sha = ledger.sha(raw['prompt'].encode())
        require(manifest.get('prompt_sha256') == prompt_sha, 'manifest prompt hash mismatch')
        start, end = raw['startedWall'], raw['ended']['time']
        require(retail.finite(start) and retail.finite(end) and start <= end and manifest['created_ms'] <= start, 'invalid run timing')
        require(raw['ended'].get('terminal') == 'final', 'run has no successful terminal event')
        runtime_dir = Path(plugin_dir) if plugin_dir else repo / 'tools/gift8-plugin'
        runtime_sha = ledger.sha(b''.join((runtime_dir / n).read_bytes() for n in sorted(('index.cjs', 'openclaw.plugin.json', 'package.json'))))
        require(manifest.get('plugin_sha256') == runtime_sha, 'plugin runtime digest mismatch')
        result.update(plugin_sha256=runtime_sha, arm=arm, manifest_sha256=ledger.sha(manifest_bytes),
                      plugin_files_sha256=plugin_digest(Path(plugin_dir) if plugin_dir else repo / 'tools/gift8-plugin'))
        messages = [(i, m) for i, m in enumerate(raw['history']['messages']) if m.get('__openclaw', {}).get('runId') == ident]
        assistants = [(i, m) for i, m in messages if m.get('role') == 'assistant']
        require(bool(assistants) and assistants[-1][1].get('stopReason') == 'stop', 'missing successful final assistant')
        final_index, final = assistants[-1]
        text = retail.text_content(final).strip()
        if text.startswith('```json\n') and text.endswith('\n```'):
            text = text[8:-4]
        elif text.startswith('```\n') and text.endswith('\n```'):
            text = text[4:-4]
        final_cards = json.loads(text)
        pending, results = {}, {}
        for i, m in messages:
            for part in m.get('content', []) if isinstance(m.get('content'), list) and m.get('role') == 'assistant' else []:
                if part.get('type') == 'toolCall':
                    require(part.get('name') == 'gift_lookup' and part.get('id') not in pending, 'unexpected or repeated native tool call')
                    pending[part['id']] = (i, part.get('arguments'))
            if m.get('role') == 'toolResult':
                call_id = m.get('toolCallId')
                require(call_id not in results, 'duplicate native tool result')
                results[call_id] = (i, m)
        require((len(pending) == len(results) == 5) if arm == 'tool' else pending.keys() == results.keys(), 'wrong native tool/result count')
        cards, receipts = [], []
        for product_id in IDS:
            receipt = ledger.read(bounded_file(receipt_dir, f'fetch-{product_id}.json'))
            require(all(receipt.get(k) == v for k, v in dict(id=ident, sessionKey=session, arm=arm, protocol=PROTOCOL, prompt_sha256=prompt_sha, product_id=product_id).items()), 'foreign receipt identity')
            require(start <= receipt['started_ms'] <= receipt['completed_ms'] <= end, 'stale or out-of-window receipt')
            expected_url = f'https://aisynthesis.com/wp-json/wc/store/v1/products/{product_id}?_fields=id,name,permalink,prices,stock_availability,variations,is_in_stock'
            require(receipt.get('status') == 200 and receipt.get('url') == expected_url and receipt.get('final_url') == expected_url, 'unexpected receipt URL or HTTP status')
            body_path = bounded_file(receipt_dir, receipt['body_file'])
            body = body_path.read_bytes()
            require(ledger.sha(body) == receipt['body_sha256'], 'receipt body hash mismatch')
            product = json.loads(body)
            card = canonical_card(product)
            require(card['id'] == product_id and retail.merchant(card['url'], product=True) and card['url'].startswith('https://aisynthesis.com/'), 'unsafe or foreign product card')
            require(jsjson(card) == jsjson(receipt['card']) and ledger.sha(jsjson(card)) == receipt['card_sha256'], 'card differs from source bytes')
            call_id = receipt.get('tool_call_id')
            if arm == 'tool':
                require(call_id in pending and call_id in results, 'receipt has no matching native call/result')
                ci, args = pending[call_id]
                ri, message = results[call_id]
                require(args == {'id': product_id} and ci < ri < final_index and message.get('isError') is False, 'wrong or reordered native call/result')
                require(message.get('toolName') == 'gift_lookup', 'native result tool identity mismatch')
                require(jsjson(json.loads(retail.text_content(message))) == jsjson(card), 'native result differs from card')
                # chat.history projects display-safe details and omits plugin-private fields.
                if 'details' in message:
                    details = message['details']
                    require(isinstance(details, dict) and jsjson(details.get('card')) == jsjson(card)
                            and details.get('receipt_file') == f'fetch-{product_id}.json', 'native result details differ from receipt')
            else:
                require(call_id is None, 'prefetch receipt pretends to be tool call')
            cards.append(card)
            receipts.append(receipt)
        result['native_tool_call_count'] = len(pending)
        result['structure_expected'] = result['structure_expected'] and (len(pending) == (5 if arm == 'tool' else 0))
        if arm == 'prefetch':
            links = []
            for call_id, (ci, args) in pending.items():
                require(isinstance(args, dict) and set(args) == {'id'} and type(args['id']) is int and args['id'] in IDS, 'unexpected prefetch follow-up arguments')
                product_id = args['id']
                receipt = receipts[IDS.index(product_id)]
                card = cards[IDS.index(product_id)]
                ri, message = results[call_id]
                require(ci < ri < final_index and message.get('isError') is False and message.get('toolName') == 'gift_lookup', 'wrong or reordered prefetch follow-up result')
                require(jsjson(json.loads(retail.text_content(message))) == jsjson(card), 'prefetch follow-up result differs from card')
                if 'details' in message:
                    details = message['details']
                    require(isinstance(details, dict) and jsjson(details.get('card')) == jsjson(card)
                            and details.get('receipt_file') == f'fetch-{product_id}.json', 'prefetch follow-up details differ from receipt')
                link_file = bounded_file(receipt_dir / 'calls', ledger.sha(call_id.encode()) + '.json')
                link = ledger.read(link_file)
                require(all(link.get(k) == v for k, v in dict(id=ident, sessionKey=session, arm=arm, product_id=product_id,
                            tool_call_id=call_id, receipt_file=f'fetch-{product_id}.json', card_sha256=receipt['card_sha256']).items()), 'foreign or spoofed prefetch call receipt')
                require(receipt['completed_ms'] <= link['timestamp_ms'] <= end, 'stale prefetch call receipt')
                links.append(dict(file=link_file.name, sha256=ledger.sha(link_file.read_bytes()), **link))
            result['followup_call_receipts'] = links
        require(jsjson(final_cards) == jsjson({'gifts': cards}), 'final must be exactly five unchanged ordered source cards')
        result['final_text'] = retail.text_content(final)
        result['receipts'] = receipts
        validate_events(receipt_dir, raw, manifest, cards, receipts, result)
        candidates = [dict(url=c['url'], catalog_name=c['name'], source_tool_call_id=r['tool_call_id']) for c, r in zip(cards, receipts)]
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
            result['products'] = list(pool.map(retail.verify_product, candidates))
        require(len(result['products']) == 5 and all(p['verified'] for p in result['products']), 'five independent product GET verifications did not pass')
    except (OSError, ValueError, TypeError, KeyError, AttributeError, IndexError, subprocess.CalledProcessError) as exc:
        reasons.append(str(exc) if type(exc) is ValueError else 'malformed or missing evidence: ' + type(exc).__name__)
    valid = not reasons
    mean, rounded = score['mean_exact_tps'], score['ui_rounded_tps']
    target = mean is not None and mean >= 1700 and rounded >= 1700
    result.update(valid=valid, status='passed' if valid and target else 'valid_below_target' if valid else 'rejected',
                  target_met=valid and target, reject_reasons=list(dict.fromkeys(reasons)),
                  target_reasons=[] if target else ['exact mean and rounded UI must both be at least 1700 TPS'])
    return result


def validate_events(receipt_dir, raw, manifest, cards, receipts, result):
    def require(test, reason):
        if not test:
            raise ValueError(reason)
    paths = sorted((receipt_dir / 'events').glob('*.json'))
    events = [ledger.read(p) for p in paths]
    start, end = raw['startedWall'], raw['ended']['time']
    for event in events:
        require(event.get('runId') == raw['id'] and event.get('sessionKey') == raw['sessionKey']
                and event.get('plugin_sha256') == manifest['plugin_sha256']
                and start <= event['timestamp_ms'] <= end, 'foreign or stale hook event')
    bindings = [e for e in events if e.get('type') == 'prompt_binding']
    inputs = sorted((e for e in events if e.get('type') == 'llm_input'), key=lambda e: e['timestamp_ms'])
    injections = [e for e in events if e.get('type') == 'prefetch_injection']
    require(len(bindings) == 1 and bindings[0].get('prompt_sha256') == manifest['prompt_sha256']
            and bindings[0].get('arm') == manifest['arm'], 'missing or mismatched prompt binding')
    require(bool(inputs), 'missing native llm_input proof')
    first = inputs[0]
    event = first['event']
    require(event.get('runId') == raw['id'] and event.get('provider') == 'cerebras' and event.get('model') == retail.MODEL
            and first.get('bound_prompt_sha256') == manifest['prompt_sha256']
            and first.get('prompt_sha256') == ledger.sha(event['prompt'].encode())
            and bindings[0]['timestamp_ms'] <= first['timestamp_ms'], 'first native model input mismatch')
    require(event['prompt'].count(raw['prompt']) == 1, 'first model input must contain exact bound user prompt once')
    history = event.get('historyMessages')
    require(isinstance(history, list) and all(isinstance(m, dict) and m.get('role') in ('user', 'system', 'custom') for m in history), 'first model input contains prior assistant or tool history')
    # This pre-submission hook also runs on retries without a recorded generation.
    result['llm_input_event_count'] = len(inputs)
    for observed in inputs:
        payload = observed.get('event', {})
        require(payload.get('runId') == raw['id'] and payload.get('provider') == 'cerebras'
                and payload.get('model') == retail.MODEL and payload.get('sessionId') == event.get('sessionId')
                and observed.get('bound_prompt_sha256') == manifest['prompt_sha256']
                and observed.get('prompt_sha256') == ledger.sha(payload['prompt'].encode())
                and bindings[0]['timestamp_ms'] <= observed['timestamp_ms'], 'foreign or unbound native model input')
    system = event['systemPrompt']
    marker = '\n<!-- OPENCLAW_CACHE_BOUNDARY -->\n\n'
    base = system
    if marker in system:
        base, suffix = system.split(marker, 1)
        allowed = [f'Current model identity: {model}. If asked what model you are, answer with this value for the current run.' for model in (retail.MODEL, 'cerebras/' + retail.MODEL)]
        require(suffix in allowed, 'unexpected native system prompt suffix')
    require(bindings[0].get('system_prompt_sha256') == ledger.sha(base.encode()), 'first system prompt differs from bound hook prompt')
    if manifest['arm'] == 'prefetch':
        require(all(link['timestamp_ms'] >= first['timestamp_ms'] for link in result.get('followup_call_receipts', [])), 'prefetch follow-up call preceded first model input')
        expected = 'Current merchant cards: ' + jsjson({'gifts': cards}).decode()
        require(len(injections) == 1 and injections[0].get('context') == expected
                and injections[0].get('context_sha256') == ledger.sha(expected.encode())
                and injections[0].get('prompt_sha256') == manifest['prompt_sha256'], 'missing or altered prefetch injection')
        require(max(r['completed_ms'] for r in receipts) <= injections[0]['timestamp_ms'] <= first['timestamp_ms']
                and event['prompt'].count(expected) == 1
                and event['prompt'].index(expected) < event['prompt'].index(raw['prompt']), 'prefetch cards not injected before first model input')
    else:
        require(not injections and 'Current merchant cards: ' not in event['prompt'], 'tool arm contains unexpected injected context')
        require(first['timestamp_ms'] <= min(r['started_ms'] for r in receipts), 'tool fetch preceded first model input')
    result['hook_evidence'] = [dict(file=p.name, sha256=ledger.sha(p.read_bytes()), type=e['type'], timestamp_ms=e['timestamp_ms']) for p, e in zip(paths, events)]
    result['first_input_sha256'] = ledger.sha(jsjson(first))


def finish(repo, raw_path, validation, receipt_dir, manifest_path=None, plugin_dir=None):
    """Revalidate, archive exact raw privately, and commit dedicated gift evidence."""
    repo, receipt_dir = Path(repo).resolve(), Path(receipt_dir).resolve()
    report = ledger.read(validation) if isinstance(validation, (str, Path)) else validation
    checked = validate(repo, raw_path, receipt_dir, manifest_path, plugin_dir)
    if report.get('input_sha256') != checked['input_sha256'] or report.get('score') != checked['score'] or report.get('valid') != checked['valid']:
        raise ValueError('saved validation differs from fresh validation')
    dest = ledger.run_dir(repo, checked['run_id'])
    original = Path(raw_path).read_bytes()
    private = receipt_dir / 'private-raw.json'
    if private.exists() and private.read_bytes() != original:
        raise ValueError('private raw archive already differs')
    ledger.atomic(private, original)
    os.chmod(private, 0o600)
    files = []
    # Store original public receipts and body bytes. Hook input content stays private;
    # their exact hashes and the validated first-input hash are committed instead.
    for source in sorted(receipt_dir.glob('fetch-*.json')) + sorted(receipt_dir.glob('body-*.bin')) + sorted((receipt_dir / 'calls').glob('*.json')):
        blob = source.read_bytes()
        ledger.encode(json.loads(blob))  # Reject accidental secret-bearing source evidence.
        target = dest / 'gift-receipts' / source.relative_to(receipt_dir)
        if target.exists() and target.read_bytes() != blob:
            raise ValueError('immutable gift receipt already differs')
        ledger.atomic(target, blob)
        files.append(target)
    record = dict(schema_version=1, protocol=PROTOCOL, id=checked['run_id'],
                  private_raw_sha256=checked['input_sha256'], private_raw_bytes=len(original),
                  score=checked['score'], calls=checked['calls'],
                  validation=ledger.pick(checked, ('valid', 'status', 'target_met', 'reject_reasons', 'target_reasons')),
                  products=[ledger.pick(p, ledger.PRODUCT) for p in checked['products']],
                  evidence_status='gift8_validated' if checked['valid'] else 'validation_rejected',
                  **ledger.pick(checked, ('llm_input_event_count', 'actual_generation_count', 'expected_generation_count', 'structure_expected', 'native_tool_call_count', 'followup_call_receipts', 'arm', 'manifest_sha256', 'plugin_sha256', 'plugin_files_sha256', 'receipts', 'hook_evidence', 'first_input_sha256', 'final_text')))
    output = dest / 'evidence.json'
    if output.exists() and ledger.read(output).get('private_raw_sha256') != checked['input_sha256']:
        raise ValueError('existing evidence bound to different raw')
    ledger.atomic(output, ledger.encode(record))
    files.append(output)
    commit = ledger.commit(repo, files, 'Record native gift benchmark ' + checked['run_id'])
    return dict(commit=commit, run_id=checked['run_id'], path=str(output), valid=checked['valid'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('validate', 'finish'))
    parser.add_argument('--repo', required=True)
    parser.add_argument('--raw', required=True)
    parser.add_argument('--receipt-dir', required=True)
    parser.add_argument('--manifest')
    parser.add_argument('--plugin-dir')
    parser.add_argument('--validation')
    args = parser.parse_args()
    if args.command == 'validate':
        result = validate(args.repo, args.raw, args.receipt_dir, args.manifest, args.plugin_dir)
    else:
        if not args.validation:
            parser.error('finish requires --validation')
        result = finish(args.repo, args.raw, args.validation, args.receipt_dir, args.manifest, args.plugin_dir)
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    return 0 if result.get('valid') else 1


if __name__ == '__main__':
    sys.exit(main())
