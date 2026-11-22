"""Keep the actual run and recorder evidence while five live detail checks are pending."""
import hashlib
import json
import math
from pathlib import Path

from ledger import atomic, encode
from scoring import call_rate, mean_rate, recording_required, round_rate
from validate import answer_links, finite, merchant, text_content


def deferred_capture(raw, plan, scratch, video_threshold, recorder):
    body = Path(raw).read_bytes()
    data = json.loads(body)
    ident = plan['id']
    if data.get('id') != ident or data.get('sessionKey') != plan['sessionKey'] or scratch.name != ident:
        raise ValueError('private queue session identity mismatch')
    assistants = [msg for msg in data['history']['messages'] if msg.get('role') == 'assistant'
                  and msg.get('__openclaw', {}).get('runId') == ident]
    rates = []
    for msg in assistants:
        sample = msg.get('serverGeneration') or {}
        ms, tokens = sample.get('completionMs'), sample.get('outputTokens')
        if finite(ms) and finite(tokens) and ms > 0 and tokens >= 1:
            rates.append(call_rate(tokens, ms))
    if not rates:
        return None
    score = mean_rate(rates)
    if score >= 1300:
        return None
    final = assistants[-1]
    urls, misleading = answer_links(text_content(final))
    urls_ok = (final.get('stopReason') == 'stop' and not misleading and len(urls) == 5
               and len(set(urls)) == 5 and all(merchant(url, product=True) for url in urls))
    ui = round_rate(score)
    # Capture a qualifying score now. Only the later live validator can declare it valid.
    retain = recording_required(score, ui, True, video_threshold, plan)
    needs_film = bool(urls_ok and retain)
    receipt = {'result': 'pending_validation', 'id': ident, 'label': plan['label'], 'arm': plan['variant'],
               'score': score, 'ui': ui, 'call_count': len(rates), 'p90': sorted(rates)[math.ceil(len(rates) * .9) - 1],
               'valid': None, 'method_valid': None, 'ended': data['ended']['time'],
               'raw_sha256': hashlib.sha256(body).hexdigest(), 'capture_complete': False}
    queue = scratch.parents[1] / 'd5027-fast-0235' / 'pending' / (ident + '.json')
    if queue.exists():
        raise RuntimeError('duplicate deferred capture')
    atomic(queue, encode(receipt))
    atomic(scratch / 'finish.json', encode({'run_id': ident, 'mean': ui, 'video_threshold_tps': video_threshold,
           'urls': urls if urls_ok else [], 'qualifying': needs_film, 'retain_verified_record': retain and ui < video_threshold,
           'preserve_unqualified': retain and not needs_film, 'discard_unverified': False}))
    receipt['recorder_exit'] = recorder.wait(timeout=1800 if retain else 150)
    receipt['capture_complete'] = True
    atomic(queue, encode(receipt))
    return receipt
