"""Offline D5027 first-call analysis. Cooldown authorization belongs to the controller."""
import json
import math
from pathlib import Path
import re
from statistics import mean, median

from variants import arm_key
from scoring import call_rate
from method_1700 import ordered_candidates

ARMS = {'A': 'synth-five-categories-cap', 'B': 'first5027-extract-text',
        'C': 'first5027-defer-answer'}
ORDER = 'BACCABABCCBA'
METRICS = ('first_tps', 'first_ms', 'first_tokens', 'first_think_chars', 'final_tps', 'score')


def _finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def _arm(side):
    return (ARMS[side], .2, 'low')


def _number(row):
    match = re.fullmatch(r'D(\d+)-.+', row.get('label', ''))
    return int(match[1]) if match else None


def _valid(row):
    return row.get('valid') is True and row.get('method_valid') is True and _finite(row.get('score'))


def terminal_429(raw, gateway_log=None):
    """A recovered retry is never a terminal failure; logs require same-run terminal evidence."""
    if raw.get('ended', {}).get('terminal') != 'error':
        return False
    ident = raw.get('id')
    if not isinstance(ident, str) or not ident:
        return False
    assistants = [m for m in raw.get('history', {}).get('messages', [])
                  if m.get('role') == 'assistant' and m.get('__openclaw', {}).get('runId') == ident]
    if assistants and assistants[-1].get('stopReason') == 'stop':
        return False
    pattern = re.compile(r'\b429\b|high[ -]traffic|too many requests', re.I)
    if gateway_log is not None:
        try:
            lines = Path(gateway_log).read_text().splitlines()
        except OSError:
            lines = []
        run_token = re.compile(r'\brunId=' + re.escape(ident) + r'(?=\s|$)')
        correlated = [line for line in lines if run_token.search(line)]
        provider_ends = [(index, line) for index, line in enumerate(correlated)
                         if 'embedded run agent end:' in line]
        if provider_ends:
            index, last = provider_ends[-1]
            # A later generic lane error does not erase the provider's raw cause.
            # A real abort after the provider error does supersede that cause.
            aborted = re.compile(r'\baborted=true\b|\berror=(?:"|\')?(?:AbortError|aborted)\b|\b(?:run|agent) aborted(?=\s|$)', re.I)
            if any(aborted.search(line) for line in correlated[index:]):
                return False
            return bool(re.search(r'\bisError=true\b', last)
                        and re.search(r'\bprovider=cerebras\b', last)
                        and pattern.search(last.split('rawError=', 1)[-1]))
    if assistants:
        last = assistants[-1]
        if (last.get('provider') == 'cerebras' and last.get('stopReason') == 'error'
                and pattern.search(str(last.get('errorMessage', '')))):
            return True
    return False


def metrics(plan, raw, validation, gateway_log=None):
    """Extract diagnostics only from matching run/message/response/server identities."""
    result = {key: None for key in METRICS if key != 'score'}
    result.update(started_wall=raw.get('startedWall'), product_urls=None,
                  first_arguments=None, terminal_429=False, identity_valid=False,
                  diagnostic_reasons=[])
    try:
        if not plan.get('id') or not (raw['id'] == validation['run_id'] == plan['id']):
            raise ValueError('run identity mismatch')
        for key in ('sessionKey', 'label', 'prompt', 'variant', 'thinking', 'temperature',
                    'top_p', 'max_completion_tokens', 'workspace_agents_md'):
            if raw.get(key) != plan.get(key):
                raise ValueError('plan/raw identity mismatch: ' + key)
        result['terminal_429'] = terminal_429(raw, gateway_log)
        assistants = [(i, m) for i, m in enumerate(raw['history']['messages'])
                      if m.get('role') == 'assistant' and m.get('__openclaw', {}).get('runId') == plan['id']]
        calls = validation['calls']
        if not assistants:
            raise ValueError('no first assistant')
        measured = {c['message_index']: c for c in calls}
        if len(measured) != len(calls):
            raise ValueError('duplicate measurement index')
        for index, message in assistants:
            if not message.get('serverGeneration') and message.get('stopReason') == 'error':
                continue
            call = measured.pop(index)
            server = message['serverGeneration']
            if (call['message_index'] != index or not message.get('responseId')
                    or call['response_id'] != message['responseId']
                    or any(call[key] != server[key] for key in ('outputTokens', 'completionMs'))
                    or not _finite(server['completionMs']) or server['completionMs'] <= 0
                    or not _finite(server['outputTokens']) or server['outputTokens'] <= 0):
                raise ValueError('measurement identity mismatch')
        if measured:
            raise ValueError('measurement outside run assistant identities')
        first, final = assistants[0][1], assistants[-1][1]
        server = first['serverGeneration']
        result.update(first_ms=server['completionMs'], first_tokens=server['outputTokens'],
                      first_tps=call_rate(server['outputTokens'], server['completionMs']),
                      first_think_chars=sum(len(p.get('thinking', '')) for p in first['content']
                                            if p.get('type') == 'thinking'),
                      first_arguments=[p.get('arguments') for p in first['content'] if p.get('type') == 'toolCall'],
                      final_tps=call_rate(final['serverGeneration']['outputTokens'],
                                          final['serverGeneration']['completionMs']) if final.get('stopReason') == 'stop' else None,
                      product_urls=ordered_candidates(plan, validation), identity_valid=True)
    except (KeyError, TypeError, ValueError, AttributeError, IndexError) as exc:
        result['diagnostic_reasons'].append(str(exc))
    return result


def _pair(a, candidate, phase, block, side):
    reasons = []
    for name, row in (('A', a), (side, candidate)):
        if row is None:
            reasons.append(name + ' not sent')
            continue
        if not _valid(row):
            reasons.append(name + ' product/method invalid')
        if any(not _finite(row.get(key)) for key in ('first_tps', 'first_ms', 'score')):
            reasons.append(name + ' missing measurement')
        urls = row.get('product_urls')
        if not isinstance(urls, list) or len(urls) != 5 or len(set(urls)) != 5:
            reasons.append(name + ' missing five distinct ordered products')
    if a is not None and candidate is not None:
        if a.get('product_urls') != candidate.get('product_urls'):
            reasons.append('ordered products differ (inventory change)')
        times = [a.get('started_wall'), candidate.get('started_wall')]
        if not all(_finite(t) for t in times):
            reasons.append('missing send timestamp')
        elif abs(times[0] - times[1]) > 900_000:
            reasons.append('send times more than 15 minutes apart')
    pair = {'phase': phase, 'block': block, 'candidate': side,
            'a': a.get('label') if a else None, 'b': candidate.get('label') if candidate else None,
            'control_shared': phase == 'exploration', 'valid': not reasons, 'reasons': reasons}
    for key in ('first_tps', 'first_ms', 'score'):
        pair['delta_' + key] = candidate[key] - a[key] if not reasons else None
    return pair


def _comparison(pairs, minimum, counts=None):
    valid = [p for p in pairs if p['valid']]
    result = {'pairs': pairs, 'valid_pairs': len(valid),
              'wins': sum(p['delta_first_tps'] > 0 for p in valid)}
    for key in ('first_tps', 'first_ms', 'score'):
        values = [p['delta_' + key] for p in valid]
        result['median_delta_' + key] = median(values) if values else None
        result['mean_delta_' + key] = mean(values) if values else None
    reasons = []
    if len(valid) < minimum:
        reasons.append('insufficient valid pairs')
    if result['wins'] < minimum:
        reasons.append('insufficient first-call wins')
    if result['median_delta_first_tps'] is None or result['median_delta_first_tps'] < 100:
        reasons.append('median first-call gain below 100 TPS')
    if result['median_delta_score'] is None or result['median_delta_score'] < 0:
        reasons.append('median official mean gain below zero')
    if counts is not None and counts[1] < counts[0]:
        reasons.append('product/method valid count below A')
    result.update(qualified=not reasons, reasons=reasons)
    return result


def summary(repo: Path, start: int, rows: list[dict]):
    """Rows are actual completed sends (including failures), never preflight-only plans.

    started_wall uses the raw startedWall epoch milliseconds. pause_required is an
    advisory event; the controller persists/acknowledges cooldown and resumes the
    returned next_arm without deriving a permanent pause from old failures.
    """
    selected = sorted((r for r in rows if _number(r) is not None and _number(r) >= start), key=_number)
    out = dict(start=start, completed=len(selected), rows=selected, pairs=[], conditions={},
               selection={}, promotion=None, confirmation=None, next_arm=None, reason='',
               terminal_429_streak=0, pause_required=False)
    for row in reversed(selected):
        if row.get('terminal_429') is not True:
            break
        out['terminal_429_streak'] += 1
    out['pause_required'] = out['terminal_429_streak'] >= 2
    numbers, ids = [_number(r) for r in selected], [r.get('id') for r in selected]
    if len(numbers) != len(set(numbers)) or any(not isinstance(i, str) or not i for i in ids) or len(ids) != len(set(ids)):
        out['reason'] = 'stop: duplicate trial number or duplicate/missing run identity'
        return out
    if len(selected) > 16:
        out['reason'] = 'stop: exceeds maximum 16 actual sends'
        return out
    for index, row in enumerate(selected[:12]):
        if row.get('arm') != arm_key(_arm(ORDER[index])):
            out['reason'] = 'stop: unexpected arm at ' + row['label']
            return out
    exploration = selected[:12]
    for side in ARMS:
        arm_rows = [r for r in selected if r.get('arm') == arm_key(_arm(side))]
        out['conditions'][side] = {'arm': ARMS[side], 'sent': len(arm_rows),
            'product_valid': sum(r.get('valid') is True for r in arm_rows),
            'method_valid': sum(r.get('method_valid') is True for r in arm_rows),
            'valid': sum(_valid(r) for r in arm_rows),
            'success_rate': sum(_valid(r) for r in arm_rows) / len(arm_rows) if arm_rows else None,
            'terminal_429': sum(r.get('terminal_429') is True for r in arm_rows), 'metrics': {}}
        for key in METRICS:
            values = [r[key] for r in arm_rows if _finite(r.get(key))]
            out['conditions'][side]['metrics'][key] = {'count': len(values), 'mean': mean(values) if values else None,
                                                     'median': median(values) if values else None}
    for block in range(4):
        group = {ORDER[i]: exploration[i] for i in range(block * 3, min(block * 3 + 3, len(exploration)))}
        for side in 'BC':
            out['pairs'].append(_pair(group.get('A'), group.get(side), 'exploration', block + 1, side))
    counts = {s: sum(_valid(r) for r in exploration if r.get('arm') == arm_key(_arm(s))) for s in ARMS}
    for side in 'BC':
        comparison = _comparison([p for p in out['pairs'] if p['candidate'] == side], 3, (counts['A'], counts[side]))
        if len(exploration) < 12:
            comparison['qualified'] = False
            comparison['reasons'].append('exploration incomplete')
        out['selection'][side] = comparison
    qualified = [s for s in 'BC' if out['selection'][s]['qualified']]
    winner = max(qualified, key=lambda s: (out['selection'][s]['median_delta_first_tps'],
                 -out['selection'][s]['median_delta_first_ms'], s == 'B')) if qualified else None
    out['promotion'] = ARMS[winner] if winner else None
    confirmation_order = ['A', winner, winner, 'A'] if winner else []
    for index, row in enumerate(selected[12:]):
        if not winner or row.get('arm') != arm_key(_arm(confirmation_order[index])):
            out['reason'] = 'stop: unexpected confirmation arm at ' + row['label']
            return out
    if winner:
        tail = selected[12:]
        confirm_pairs = []
        for block, (ai, bi) in enumerate(((0, 1), (3, 2))):
            confirm_pairs.append(_pair(tail[ai] if len(tail) > ai else None,
                                      tail[bi] if len(tail) > bi else None, 'confirmation', block + 1, winner))
        out['confirmation'] = _comparison(confirm_pairs, 2)
        out['pairs'].extend(confirm_pairs)
    target = next((r for r in selected if _valid(r) and r['score'] >= 1700), None)
    if target:
        out['reason'] = 'stop: raw target at ' + target['label'] + '; verify official screen/video/hash before new sends'
    elif len(selected) < 12:
        out['next_arm'] = _arm(ORDER[len(selected)])
        out['reason'] = f'exploration slot {len(selected) + 1}/12'
    elif not winner:
        out['reason'] = 'stop: no candidate meets predeclared selection criteria; improvement unconfirmed'
    elif len(selected) < 16:
        out['next_arm'] = _arm(confirmation_order[len(selected) - 12])
        out['reason'] = f'confirmation slot {len(selected) - 11}/4'
    else:
        out['reason'] = ('stop: repeated improvement confirmed' if out['confirmation']['qualified']
                         else 'stop: maximum 16 sends; repeated improvement unconfirmed')
    return out
