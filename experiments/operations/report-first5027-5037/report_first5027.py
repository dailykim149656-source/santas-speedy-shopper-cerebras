#!/usr/bin/env python3
"""Offline Korean first5027 report; never sends a model request or starts a recorder.
Usage: python3 -B /tmp/report_first5027.py --output /tmp/report.md
Optional --copy-demos PROJECT_LOCAL_DIRECTORY copies only independently verified demos.
Outputs report plus OUTPUT.audit.json (exact numbers, hashes and audit findings).
"""
import argparse
from datetime import datetime, timezone
import hashlib
import importlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import sys
from urllib.parse import urlsplit, parse_qsl
sys.dont_write_bytecode = True

DEFAULT_PROJECT = Path(os.environ.get("BOUNTY_PROJECT_ROOT", Path.cwd().parent))
DEFAULT_BASE = Path.home() / 'Library/Caches/cerebras-speed-bounty'
DEFAULT_ARCHIVE = Path.home() / 'Library/Application Support/Cerebras Speed Bounty/2026-11-22/raw-test'


def read(path, default=None):
    if not path.exists() and default is not None:
        return default
    return json.loads(path.read_bytes())


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda: f.read(1024 * 1024), b''):
            h.update(b)
    return h.hexdigest()


def finite(x):
    return type(x) in (int, float) and math.isfinite(x)


def require(value, message):
    if not value:
        raise ValueError(message)


def number(label):
    m = re.fullmatch(r'D(\d+)-[a-z0-9-]+', label or '')
    return int(m[1]) if m else -1


def safe(s):
    # Only diagnostics and public merchant metadata are rendered, never raw messages.
    s = str(s)
    s = re.sub(r'(?i)(bearer\s+|(?:api[_-]?key|token|secret)\s*[=:]\s*)\S+', r'\1[REDACTED]', s)
    return s.replace('|', '\\|').replace('\n', ' ')[:600]


def public_arguments(items):
    out = []
    for item in items or []:
        if not isinstance(item, dict):
            out.append('[REDACTED invalid argument object]')
            continue
        clean = {}
        for key, value in item.items():
            if key == 'url' and isinstance(value, str):
                u = urlsplit(value)
                query = parse_qsl(u.query, keep_blank_values=True)
                clean[key] = value if (u.scheme == 'https' and u.netloc == 'aisynthesis.com'
                    and u.path == '/wp-json/wc/store/v1/products' and not u.fragment
                    and all(k in {'search','per_page','stock_status','_fields','_run'} for k,v in query)
                    and all(len(v) < 64 and re.fullmatch(r'[a-zA-Z0-9,_-]*',v) for k,v in query)) else '[REDACTED noncatalog URL]'
            elif key == 'extractMode' and value in ('text','markdown'):
                clean[key] = value
            elif key == 'maxChars' and type(value) is int:
                clean[key] = value
            else:
                clean[safe(key)] = '[REDACTED unexpected argument]'
        out.append(clean)
    return out


def f(x):
    return format(x, '.12g') if finite(x) else '—'


def stamp(ms):
    return datetime.fromtimestamp(ms / 1000, timezone.utc).isoformat() if finite(ms) else '미확인'


def sources(paths):
    return {str(p): {'sha256': sha(p), 'bytes': p.stat().st_size} for p in paths if p.is_file()}


def extract(plan, raw, validation, evidence, api):
    ident = plan['id']
    require(raw.get('id') == validation.get('run_id') == evidence.get('id') == ident, 'run identity mismatch')
    for key in ('id','label','sessionKey','capturePolicy','variant','thinking','temperature','top_p',
                'max_completion_tokens','video_threshold_tps','prior_verified_mean_tps',
                'context_injection','workspace_agents_md','prompt'):
        require(raw.get(key) == plan.get(key), 'plan/raw mismatch: ' + key)
    require(evidence.get('startedWall') == raw.get('startedWall') and evidence.get('ended') ==
            {k: raw.get('ended', {}).get(k) for k in ('elapsedMs', 'terminal', 'time') if k in raw.get('ended', {})}, 'raw/evidence timing mismatch')
    assistants = [(i, m) for i, m in enumerate(raw.get('history', {}).get('messages', []))
                  if m.get('role') == 'assistant' and m.get('__openclaw', {}).get('runId') == ident]
    ecalls = evidence.get('calls', [])
    require(len(ecalls) == len(assistants), 'evidence assistant count mismatch')
    calls = []
    for (i, m), c in zip(assistants, ecalls):
        g = m.get('serverGeneration', {})
        for key in ('provider', 'model', 'responseId', 'stopReason'):
            require(c.get(key) == m.get(key), 'evidence call identity mismatch: ' + key)
        require(c.get('message_index') == i and c.get('serverGeneration') ==
                {k: g[k] for k in ('completionMs', 'outputTokens') if k in g}, 'evidence call timing mismatch')
        measured = finite(g.get('outputTokens')) and g['outputTokens'] >= 1 and finite(g.get('completionMs')) and g['completionMs'] > 0
        require(c.get('timed_sample') is measured, 'timed sample inclusion mismatch')
        if measured:
            require(m.get('responseId'), 'missing measured response identity')
            calls.append(dict(message_index=i, response_id=m['responseId'], outputTokens=g['outputTokens'], completionMs=g['completionMs'],
                              tps=api['scoring'].call_rate(g['outputTokens'], g['completionMs']), stopReason=m.get('stopReason')))
    vcalls = validation.get('calls', [])
    require(len(vcalls) == len(calls), 'validation measured count mismatch')
    for c, v in zip(calls, vcalls):
        for k in ('message_index', 'response_id', 'outputTokens', 'completionMs'):
            require(c[k] == v.get(k), 'validation call mismatch: ' + k)
    rates = [c['tps'] for c in calls]
    score = api['scoring'].mean_rate(rates) if rates else None
    ui = api['scoring'].round_rate(score) if score is not None else None
    for obj in (evidence, validation):
        require(obj['score'].get('mean_exact_tps') == score and obj['score'].get('ui_rounded_tps') == ui, 'all-call mean mismatch')
    require(evidence['validation'].get('valid') == validation.get('valid'), 'validation flag mismatch')
    require(evidence.get('products') == [dict(api['ledger'].pick(p, api['ledger'].PRODUCT),
            product_evidence=api['ledger'].pick(p.get('product_evidence', {}), ('matching_schema_product', 'woocommerce_product_heading', 'woocommerce_sticky_product_price_and_cart')))
            for p in validation.get('products', [])], 'product receipt mismatch')
    diag = api['first'].metrics(plan, raw, validation)
    # metrics intentionally preserves a measured first response when final response fails.
    method = api['method'].assess_first5027(plan, raw, validation)
    row = dict(id=ident, label=plan['label'], arm=api['variants'].arm_key((plan['variant'], plan['temperature'], plan['thinking'])),
               score=score, ui=ui, valid=validation.get('valid') is True, method_valid=method, call_count=len(calls), **diag)
    return row, calls


def audit_trial(plan_path, args, api):
    plan = read(plan_path)
    ident, label = plan['id'], plan['label']
    epath = plan_path.with_name('evidence.json')
    rawpath = args.archive / (ident + '.json')
    if not rawpath.exists():
        rawpath = args.cache / 'runs' / (label + '.json')
    vpath = args.cache / 'capture' / ident / 'validation.json'
    result = dict(id=ident, label=label, errors=[], evidence_path=str(epath), state='pending', row=None, calls=[], products=[])
    paths = [plan_path, epath, rawpath, vpath]
    result['sources'] = sources(paths)
    if not epath.exists() or not rawpath.exists() or not vpath.exists():
        result['errors'].append('완료 원본·장부·검증 자료가 아직 모두 없음')
        return result
    try:
        e, raw, val = read(epath), read(rawpath), read(vpath)
        require(e.get('private_raw_sha256') == val.get('input_sha256') == sha(rawpath), 'raw SHA256 mismatch')
        require(e.get('private_raw_bytes') == rawpath.stat().st_size, 'raw byte count mismatch')
        result['raw_sha256'] = sha(rawpath)
        # Checks committed provenance, evidence calls, product receipts and scoring definition offline.
        api['verify'].committed(args.repo, plan_path)
        result['archive_verification'] = api['verify'].verify(args.repo, ident, plan, rawpath)
        row, calls = extract(plan, raw, val, e, api)
        row['terminal_429'] = api['first'].terminal_429(raw, args.cache.parent / 'gateway.log')
        row['first_arguments'] = public_arguments(row.get('first_arguments'))
        result.update(row=row, calls=calls, state='complete', terminal=raw.get('ended', {}).get('terminal'),
                      fail_reasons=[safe(x) for x in val.get('reject_reasons', [])],
                      products=[{k: p.get(k) for k in ('url', 'catalog_name', 'verified', 'html_sha256', 'http', 'checked_at')} for p in e.get('products', [])])
        if not row['method_valid']:
            result['fail_reasons'].append('D5027 첫 응답·5개 인자·조회/상품 순서 방식 검증 미통과')
        if row['diagnostic_reasons']:
            result['fail_reasons'].extend(row['diagnostic_reasons'])
    except (OSError, ValueError, KeyError, TypeError, AttributeError, IndexError, api['subprocess'].SubprocessError) as exc:
        result.update(state='audit_failed', errors=[safe(type(exc).__name__ + ': ' + str(exc))])
    return result


def intervals(cache, campaign, start=None):
    """Every raw run, plus sends lacking a raw terminal; never use iteration rows as intervals."""
    found, issues, source = {}, [], []
    for path in sorted((cache / 'runs').glob('*.json')):
        if path.name.startswith('._'):
            continue
        try:
            obj = read(path)
        except (OSError, ValueError):
            issues.append(campaign + ': unreadable ' + path.name)
            continue
        if start is not None and number(obj.get('label', path.name.split('.')[0])) < start:
            continue
        if path.name.endswith(('.send-intent.json', '.pending.json')):
            ident = obj.get('id')
            if ident:
                item = found.setdefault(ident, {'campaign': campaign, 'id': ident, 'label': obj.get('label', path.name.split('.')[0]), 'send_ms': None, 'end_ms': None, 'raw': False})
                if finite(obj.get('startedWall')):
                    if finite(item.get('send_ms')) and item['send_ms'] != obj['startedWall']:
                        issues.append(campaign + ': send receipt differs from raw ' + path.name)
                    else:
                        item['send_ms'] = obj['startedWall']
                source.append(path)
        elif path.name.count('.') == 1 and ('history' in obj or 'startedWall' in obj):
            ident = obj.get('id')
            if not ident:
                issues.append(campaign + ': raw missing id ' + path.name)
                continue
            old = found.get(ident, {})
            send, end = obj.get('startedWall'), obj.get('ended', {}).get('time')
            if finite(old.get('send_ms')) and send != old['send_ms']:
                issues.append(campaign + ': send receipt differs from raw ' + path.name)
            found[ident] = dict(campaign=campaign, id=ident, label=obj.get('label', path.stem), send_ms=send, end_ms=end,
                                raw=True, terminal=obj.get('ended', {}).get('terminal'), raw_path=str(path), raw_sha256=sha(path))
            source.append(path)
    # Terminal receipt permits bounding a pending send, but does not masquerade as raw evidence.
    for item in found.values():
        p = cache / 'runs' / (item['label'] + '.terminal.json')
        if p.exists():
            t = read(p)
            if t.get('id') != item['id']:
                issues.append(campaign + ': terminal identity mismatch ' + item['label'])
            elif not finite(item['end_ms']):
                item['end_ms'] = t.get('ended', {}).get('time')
                item['terminal'] = t.get('ended', {}).get('terminal')
            source.append(p)
        if not finite(item['send_ms']) or not finite(item['end_ms']) or item['end_ms'] < item['send_ms']:
            issues.append(campaign + ': interval incomplete ' + item['label'])
    return list(found.values()), issues, sources(source)


def overlap_audit(args):
    test, issues, src = intervals(args.cache, 'test', args.start)
    foreign = []
    for name, cache in (('main', args.main_cache), ('exp', args.exp_cache)):
        rows, errors, s = intervals(cache, name)
        for row in rows:
            ep = args.project / ('speed-bounty-evidence' if name == 'main' else 'speed-bounty-evidence-2000') / 'runs' / row['id'] / 'evidence.json'
            if ep.exists() and row['raw']:
                e = read(ep)
                if not (e.get('id') == row['id'] and e.get('private_raw_sha256') == row['raw_sha256']
                        and e.get('startedWall') == row['send_ms'] and e.get('ended',{}).get('time') == row['end_ms']):
                    errors.append(name + ': raw/evidence interval identity or SHA mismatch ' + row['label'])
                s.update(sources([ep]))
        foreign += rows
        issues += errors
        src.update(s)
    overlaps = []
    for t in test:
        for x in foreign:
            if finite(t['send_ms']) and finite(x['send_ms']):
                te = t['end_ms'] if finite(t['end_ms']) else float('inf')
                xe = x['end_ms'] if finite(x['end_ms']) else float('inf')
                if max(t['send_ms'], x['send_ms']) < min(te, xe):
                    overlaps.append(dict(test=t['label'], foreign=x['label'], campaign=x['campaign'],
                                         from_ms=max(t['send_ms'], x['send_ms']),
                                         to_ms=min(te, xe) if finite(min(te, xe)) else None))
    receipt = args.cache / f'first5027-{args.start}-reservation.jsonl'
    events = [json.loads(s) for s in receipt.read_text().splitlines() if s.strip()] if receipt.exists() else []
    src.update(sources([receipt, args.exp_cache / 'status.json']))
    reservations, current = [], None
    expected = {str(args.cache / 'loop.lock'), str(args.main_cache / 'loop.lock'), str(args.exp_cache / 'loop.lock')}
    for event in events:
        if event.get('event') == 'reserved':
            if current is not None:
                # Exclusive test flock was obtained again. A reboot may have interrupted
                # the old controller before it could record its release. Never use the
                # old open interval as positive evidence of lock coverage.
                current['superseded_at_ms'] = event['at_ms']
            if set(event.get('locks', [])) != expected:
                issues.append('reservation lock paths differ')
            current = dict(start_ms=event['at_ms'], end_ms=None, pid=event.get('pid'),
                           paths_verified=set(event.get('locks', [])) == expected)
            reservations.append(current)
        elif event.get('event') == 'releasing':
            if current is None or current['pid'] != event.get('pid'):
                issues.append('release without matching reservation')
            else:
                current['end_ms'] = event['at_ms']
                current = None
    uncovered = [t['label'] for t in test if not any(
        r['paths_verified'] and finite(t['send_ms']) and finite(t['end_ms']) and finite(r['end_ms']) and
        r['start_ms'] <= t['send_ms'] <= t['end_ms'] <= r['end_ms'] for r in reservations)]
    if uncovered:
        issues.append('test sends outside reservation receipt: ' + ', '.join(uncovered))
    exp_end = max([x['end_ms'] for x in foreign if x['campaign'] == 'exp' and finite(x['end_ms'])], default=None)
    first = min([x['send_ms'] for x in test if finite(x['send_ms'])], default=None)
    if first is not None and exp_end is not None and first < exp_end:
        issues.append('test first send precedes latest exp terminal')
    return dict(verified=bool(test) and not issues and not overlaps, test_intervals=test, foreign_intervals=foreign,
                interval_comparisons=len(test) * len(foreign), overlaps=overlaps, issues=issues,
                exp_latest_end_ms=exp_end, first_test_send_ms=first,
                exp_to_test_gap_ms=first-exp_end if first is not None and exp_end is not None else None,
                exp_status={k: read(args.exp_cache / 'status.json', {}).get(k) for k in ('phase', 'first', 'time')},
                reservation_events=[{k: e.get(k) for k in ('event', 'at_ms', 'pid', 'owner', 'number', 'slot', 'arm')} for e in events],
                reservations=reservations, sources=src,
                scope='All local main/exp raw intervals vs every test send; receipt proves recorded lock ownership, not other hosts or uninstrumented clients.')


def film_audit(trial, args, api):
    base = args.films / trial['id']
    receipt = base / 'receipt.json'
    out = dict(receipt_path=str(receipt), receipt_present=receipt.exists(), verified=False, viewport_verified=False, full_run_verified=False, issues=[])
    if not receipt.exists():
        out['issues'].append('최종 녹화 영수증 없음 / 녹화 진행 가능')
        return out
    r = read(receipt)
    out['receipt_sha256'] = sha(receipt)
    if not r.get('directory'):
        out['issues'].append('녹화 디렉터리 없는 실패 영수증')
        return out
    directory = Path(r['directory']).resolve()
    try:
        require(directory.is_relative_to(base.resolve()), 'receipt directory outside run film folder')
        plan = read(args.repo / 'runs' / trial['id'] / 'plan.json')
        require(r.get('id') == trial['id'] and r.get('sessionKey') == plan['sessionKey'], 'film receipt identity mismatch')
        # inspect launches only ffprobe and writes only via put(); redirect that write to memory.
        film = api['film']
        saved = (film.REPO, film.CACHE, film.put)
        captured = []
        try:
            film.REPO, film.CACHE = args.repo, args.cache
            film.put = lambda path, value: captured.append(value)
            current = film.inspect(trial['label'], {'id': trial['id'], 'sessionKey': plan['sessionKey']}, directory)
        finally:
            film.REPO, film.CACHE, film.put = saved
        require(len(captured) == 1, 'unexpected film inspection writes')
        for key in ('media', 'source_provenance', 'playable', 'viewportVerified', 'full_run_verified', 'real_time_verified',
                    'timing', 'classification', 'displayedMean', 'verifiedProductURLs', 'viewportProofSha256', 'firstFrameMinusSendMs', 'firstFrameMinusTerminalMs'):
            require(r.get(key) == current.get(key), 'stale or inconsistent final receipt: ' + key)
        require(current['playable'], 'film not playable')
        row = trial.get('row')
        if current['viewportVerified']:
            require(row is not None and row['valid'] and row['ui'] == current.get('displayedMean'), 'UI lacks independently audited valid run')
            require(set(current['verifiedProductURLs']) == {p['url'] for p in trial['products'] if p['verified']}, 'UI product mismatch')
        out.update(verified=True, viewport_verified=current['viewportVerified'], full_run_verified=current['full_run_verified'],
                   timing=current['timing'], first_frame_minus_send_ms=current.get('firstFrameMinusSendMs'),
                   first_frame_minus_terminal_ms=current.get('firstFrameMinusTerminalMs'), displayed_mean=current.get('displayedMean') if current['viewportVerified'] else None,
                   directory=str(directory), media=current['media'], issues=current.get('issues', []),
                   target_viewport_verified=bool(row and row['valid'] and row['method_valid'] and row['score'] >= 1700
                                                 and row['ui'] >= 1700 and current['viewportVerified']),
                   target_verified=bool(row and row['valid'] and row['method_valid'] and row['score'] >= 1700 and row['ui'] >= 1700
                                        and current['viewportVerified'] and current['full_run_verified']))
    except (OSError, ValueError, KeyError, TypeError, api['subprocess'].SubprocessError) as exc:
        out['issues'].append(safe(type(exc).__name__ + ': ' + str(exc)))
    return out


def feasibility(project, repo):
    source = project / 'TPS 2000 달성 전략 및 딥리서치 분석 보고서 - 2026-11-22.md'
    variants = project / 'speed-bounty-evidence-2000/tools/variants.py'
    ids = {'D5009': 'a9530b69-3aed-4ea9-8fd9-9ee1fcb36b51',
           'D5025': '2559637b-529b-4b98-a7c5-11a150fc23c0',
           'D5027': 'cd75e5e0-be7c-471f-a9ab-c9e6f0d1bd77'}
    files = {label: repo / 'runs' / ident / 'evidence.json' for label, ident in ids.items()}
    if not all(p.is_file() for p in (source, variants, *files.values())):
        return None
    historical = {label: read(path) for label, path in files.items()}
    for label, evidence in historical.items():
        plan = read(files[label].with_name('plan.json'))
        require(evidence['id'] == plan['id'] == ids[label] and plan['label'].split('-')[0] == label,
                'historical evidence label mismatch')
    first = historical['D5025']['calls'][0]['serverGeneration']
    final = historical['D5009']['calls'][-1]['serverGeneration']
    first_rate = 1000 * first['outputTokens'] / first['completionMs']
    ms_per_token = (final['completionMs'] - 15) / final['outputTokens']
    projected = 1000 * 650 / (15 + 650 * ms_per_token)
    return dict(strategy=str(source), variants=str(variants), sources=sources([*files.values(),source,variants]),
                d5009_final_tps=1000 * final['outputTokens']/final['completionMs'],
                d5009_average=historical['D5009']['score']['mean_exact_tps'], d5009_final_tokens=final['outputTokens'],
                d5009_final_ms=final['completionMs'], d5027_average=historical['D5027']['score']['mean_exact_tps'],
                d5025_first_tps=first_rate, needed_final_tps=2 * 1700 - first_rate,
                projected_final_tps=projected, projected_average=(first_rate + projected)/2)


def render(data, output):
    rows = data['trials']; summary = data['summary']; overlap = data['overlap']
    good = [t for t in rows if t.get('row') and t['row']['valid'] and t['row']['method_valid']]
    best = max(good, key=lambda t: t['row']['score'], default=None)
    L = ['# D5027 첫 호출 TPS 비교 실험 결과', '', f"집계: {data['generated_at']} · 상태: {data['status']} · 실제 전송 {data['actual_sends']}/16회 · 원본 검증 완료 {sum(t['state']=='complete' for t in rows)}회.", '',
         '탐색 12회(B–A–C / C–A–B / A–B–C / C–B–A), 선별 시 A–승자 / 승자–A 재확인 최대 4회. A 대조값을 각 묶음의 B·C 비교에 공유한다. 실패도 전송 수·성공률 분모에 포함한다. 쌍의 전송 간격은 15분 이하여야 한다.', '',
         'A는 D5027 URL 전용 인자, B는 다섯 인자에 extractMode="text"만 추가, C는 첫 호출을 바로 작성하고 최종 답변 계획을 미루라는 작업공간 지침 한 줄만 추가한다. 모델·공식 패치 공통, temperature=0.2, thinking=low, top_p 미지정, 출력 상한 1,024. filter/mixer/oscillator/echo/cable의 재고 상품을 각 1개 조회하고 번호 링크 5개를 답한다.', '',
         '첫 TPS=출력 토큰/(서버 ms/1,000). 공식 평균은 같은 실행에서 측정된 모든 assistant 호출 TPS의 산술평균이며 추가 호출도 포함한다. 표는 최대 12 유효숫자, 동반 audit.json에는 원래 정밀도를 보존한다. 반올림 계산값은 실제 화면 관측값과 구분한다. 추론은 글자 수만 집계하며 내용은 공개하지 않는다.', '']
    if best:
        L += [f"최고 유효 실행은 **{best['label'].split('-')[0]} · {f(best['row']['score'])} TPS**다. 최고 1회 기록과 반복 개선 판정은 별개다.", '']
    if data['preflight']:
        labels = ', '.join(item['label'].split('-')[0] for item in data['preflight'])
        L += [f"모델 전송 전에 끝난 시도는 {len(data['preflight'])}회({labels})다. 전송 수와 조건별 성공률 계산에서 제외했다.", '']
    L += ['| 실행 | 조건 | 첫 토큰 / ms / TPS / 추론 글자 | 최종 TPS | 전체 호출 수 / 공식 평균 / 계산 반올림 | 상품 / 방식 | 최종 429 |', '|---|---|---|---:|---|---|---|']
    for t in rows:
        r = t.get('row')
        if not r:
            L.append(f"| {t['label']} | — | 자료 대기/검증 실패 | — | — | — | — |")
            continue
        side = next((s for s, arm in data['arms'].items() if r['arm'].startswith(arm+'|')), '?')
        L.append(f"| {t['label'].split('-')[0]} | {side} | {' / '.join(f(r.get(k)) for k in ('first_tokens','first_ms','first_tps','first_think_chars'))} | {f(r['final_tps'])} | {r['call_count']} / {f(r['score'])} / {f(r['ui'])} | {sum(p['verified'] is True for p in t['products'])}/5 · {'통과' if r['method_valid'] else '미통과'} | {'예' if r['terminal_429'] else '아니오'} |")
    L += ['', '조건별 성공률(상품·방식 모두 통과 / 전체 전송):']
    for side, item in summary.get('conditions', {}).items():
        L.append(f"- {side}: {item['valid']}/{item['sent']} ({f(item['success_rate']*100 if item['success_rate'] is not None else None)}%).")
    L += ['', '| 단계·묶음·변경 | A / 변경 실행 | 첫 TPS 차이 | 서버 ms 차이 | 공식 평균 차이 | 유효성·제외 사유 |', '|---|---|---:|---:|---:|---|']
    for pair in summary.get('pairs', []):
        L.append(f"| {pair['phase']} {pair['block']} {pair['candidate']} | {pair['a'] or '미전송'} / {pair['b'] or '미전송'} | {f(pair['delta_first_tps'])} | {f(pair['delta_first_ms'])} | {f(pair['delta_score'])} | {'유효' if pair['valid'] else safe('; '.join(pair['reasons']))} |")
    L += ['', '선별 기준: 유효 쌍 ≥3, 첫 호출 승리 ≥3, 첫 TPS 차이 중앙값 ≥+100, 공식 평균 차이 중앙값 ≥0, 상품·방식 유효 횟수 ≥A. 동률은 서버 시간 감소, 다음 B 우선. 재확인은 두 쌍 모두 유효·승리하고 중앙값 기준을 모두 충족해야 한다.']
    for side, s in summary.get('selection', {}).items():
        L.append(f"- {side}: 유효 {s['valid_pairs']}쌍 / {s['wins']}승; 첫 TPS 중앙값 {f(s['median_delta_first_tps'])}, 서버 ms 중앙값 {f(s['median_delta_first_ms'])}, 공식 평균 중앙값 {f(s['median_delta_score'])}; {'선별' if s['qualified'] else safe('; '.join(s['reasons']))}.")
    L += [f"- 승자: {summary.get('promotion') or '없음/미확정'}. 재확인: {json.dumps(summary.get('confirmation'), ensure_ascii=False) if summary.get('confirmation') else '실행되지 않음/대기'}.", f"- 일정 판정: {safe(summary.get('reason'))}.", '', '동시 전송 독립 감사:']
    L += [f"- main/exp 원본 구간 {len(overlap['foreign_intervals'])}개 × 새 test 전송 {len(overlap['test_intervals'])}개 = {overlap['interval_comparisons']}개 비교. 겹침 {len(overlap['overlaps'])}건. {'무겹침 검증 통과' if overlap['verified'] else '전송 없음 또는 감사 미완료/이상 있음'}.",
          f"- exp 최종 종료 {stamp(overlap['exp_latest_end_ms'])}, test 첫 전송 {stamp(overlap['first_test_send_ms'])}, 간격 {f(overlap['exp_to_test_gap_ms'])}ms. 기록된 예약 구간 {len(overlap['reservations'])}개.",
          '- 예약 영수증과 실제 구간을 독립 대조했다. 이 검사는 로컬 main/test/exp 범위이며 다른 호스트·별도 클라이언트의 쿼터 사용 여부는 입증하지 못한다.']
    for issue in overlap['issues']:
        L.append('- 감사 제한: ' + safe(issue))
    open_count = sum(item['end_ms'] is None for item in overlap['reservations'])
    if open_count:
        L.append(f'- 해제 시각 기록이 없는 예약 {open_count}개는 전송 구간을 입증하는 데 사용하지 않았다.')
    for o in overlap['overlaps']:
        L.append(f"- 겹침: {o['test']} / {o['campaign']} {o['foreign']}: {stamp(o['from_ms'])}–{stamp(o['to_ms'])}.")
    L += ['', f"원본 평균·계산 반올림 모두 1,700 이상이며 상품·방식 유효: {sum(t.get('row') is not None and t['row']['valid'] and t['row']['method_valid'] and t['row']['score'] >= 1700 and t['row']['ui'] >= 1700 for t in rows)}회. 같은 실행의 원본·실제 UI·전체 실행 영상까지 목표 확인: {sum(t['film'].get('target_verified',False) for t in rows)}회.", '', '| 실행 | 최종 영상 영수증/ffprobe | 첫 프레임 시점 | 실제 화면 평균 | 전체 실행 증명 |', '|---|---|---|---:|---|']
    for t in rows:
        v = t['film']; duration = v.get('media', {}).get('demo.mp4', {}).get('ffprobe', {}).get('format', {}).get('duration')
        L.append(f"| {t['label'].split('-')[0]} | {'검증 통과 · '+str(duration)+'초' if v['verified'] else safe('; '.join(v['issues']))} | {v.get('timing','미확인')} / 전송 대비 {f(v.get('first_frame_minus_send_ms'))}ms | {f(v.get('displayed_mean')) if v.get('viewport_verified') else '미검증'} | {'통과' if v.get('full_run_verified') else '미충족'} |")
    L += ['', '각 실행의 호출·실제 인자·상품·실패 사유:']
    for t in rows:
        L += ['', f"### {t['label']}", f"원본 SHA-256: `{t.get('raw_sha256','미검증')}`. [장부](<{t['evidence_path']}>) · [최종 녹화 영수증](<{t['film']['receipt_path']}>)"]
        for c in t['calls']:
            L.append(f"- 호출 {c['message_index']}: {c['outputTokens']}토큰 / {c['completionMs']}ms / {f(c['tps'])} TPS ({c['stopReason']}).")
        if t.get('row'):
            for a in t['row'].get('first_arguments') or []:
                L.append('- 실제 첫 호출 인자: `' + safe(json.dumps(a, ensure_ascii=False)) + '`.')
        for p in t['products']:
            L.append(f"- 상품: [{safe(p['catalog_name'])}]({p['url']}) · {'검증 통과' if p['verified'] else '미통과'} · HTML SHA-256 `{p['html_sha256']}`.")
        for error in t.get('fail_reasons', []) + t['errors']:
            L.append('- 실패/제외: ' + safe(error))
    L += ['', '상품 검증은 당시 독립 GET 결과의 해시·신원·상세페이지 판정 영수증을 원본 및 커밋 장부와 대조했다. 이 보고서 생성기는 재조회하지 않으므로 현재 재고나 당시 HTML 본문을 새로 검증했다고 주장하지 않는다. 실패 실행의 계산 반올림값을 공식 UI 관측값으로 만들지 않는다.', '',
          '감사 자료: ['+output.name+'.audit.json](<'+output.name+'.audit.json>). 모든 raw/장부/영상 소스 해시, 정밀 지표, 교차 구간, 잠금 영수증 및 오류를 기록했다.']
    if data.get('feasibility'):
        s = data['feasibility']
        strategy = os.path.relpath(s['strategy'], output.parent)
        code = os.path.relpath(s['variants'], output.parent)
        L += ['', '## 1,700 TPS 달성 가능성', '',
              f"D5009의 최종 호출은 {s['d5009_final_tokens']}토큰을 {s['d5009_final_ms']:.2f}ms에 생성해 {s['d5009_final_tps']:,.2f} TPS였고, 공식 평균은 {s['d5009_average']:,.2f} TPS였다. D5027의 공식 평균은 {s['d5027_average']:,.2f} TPS였다. 두 호출로 끝나는 새 실행에서 D5025의 첫 호출 {s['d5025_first_tps']:,.2f} TPS를 재현하면, 평균 1,700을 위해 최종 호출이 최소 **{s['needed_final_tps']:,.2f} TPS**여야 한다.", '',
              f"전략 문서처럼 최종 호출의 고정 지연을 15ms로 가정하고 D5009의 토큰당 처리시간을 유지하면, 650토큰 최종 호출의 예상값은 약 {s['projected_final_tps']:,.0f} TPS다. 서로 다른 실행인 D5025의 첫 호출과 D5009 기반 추정치를 조합한 예상 평균은 약 {s['projected_average']:,.0f} TPS다. 후속 실험에서는 실제 조회한 상품 속성으로 더 긴 카드를 작성해 최종 호출 TPS와 전체 평균을 함께 측정할 수 있다. 이 카드 조건은 `exp-tps-2000`에 구현됐으며 D6001–D6007의 7회 전송에서는 사용되지 않았다. [전략 보고서](<{strategy}>) · [상품 카드 조건 구현](<{code}>)"]
    return '\n'.join(L) + '\n'


def copy_demos(trials, destination, project, *, include_playable=False):
    project = project.resolve()
    dest = destination.resolve()
    require(dest.is_relative_to(project) and dest != project, '--copy-demos must be a project-local subdirectory')
    dest.mkdir(parents=True, exist_ok=True)
    manifest = []
    for t in trials:
        v = t['film']
        if not v['verified'] or not (include_playable or v['viewport_verified']):
            continue
        src = Path(v['directory'])/'demo.mp4'; target = dest/(t['label'].split('-')[0]+'.mp4')
        expected = v['media']['demo.mp4']['sha256']
        require(sha(src) == expected, 'demo changed after inspection')
        if target.exists():
            require(sha(target) == expected, 'refusing to overwrite different demo')
        else:
            shutil.copyfile(src,target)
        require(sha(target) == expected, 'copied demo hash mismatch')
        manifest.append(dict(id=t['id'],file=target.name,sha256=expected,bytes=target.stat().st_size,
                             timing=v.get('timing'), viewport_verified=v['viewport_verified'],
                             full_run_verified=v.get('full_run_verified', False)))
    manifest_path = dest/'checksums-first5027.json'
    require(not manifest_path.exists(), 'refusing to overwrite existing checksum manifest')
    manifest_path.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    return manifest


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--project', type=Path, default=DEFAULT_PROJECT)
    p.add_argument('--repo', type=Path)
    p.add_argument('--cache', type=Path, default=DEFAULT_BASE/'2026-11-22-test/mean-2000')
    p.add_argument('--main-cache', type=Path, default=DEFAULT_BASE/'2026-11-22/mean-2000')
    p.add_argument('--exp-cache', type=Path, default=DEFAULT_BASE/'2026-11-22-exp2000/mean-2000')
    p.add_argument('--archive', type=Path, default=DEFAULT_ARCHIVE)
    p.add_argument('--films', type=Path)
    p.add_argument('--start', type=int, default=5037)
    p.add_argument('--copy-demos', type=Path)
    p.add_argument('--include-playable', action='store_true', help='Also copy playable study clips without verified UI score')
    args = p.parse_args()
    args.project = args.project.resolve(); args.repo = (args.repo or args.project/'speed-bounty-evidence-test').resolve()
    args.films = args.films or args.cache/f'film-first5027-{args.start}'
    sys.path.insert(0, str(args.repo/'tools'))
    api = {k: importlib.import_module(v) for k,v in dict(first='first5027', film='first5027_film', method='method_1700',
           scoring='scoring', variants='variants', verify='verify_run', ledger='ledger', subprocess='subprocess').items()}
    plans = sorted([q for q in (args.repo/'runs').glob('*/plan.json') if number(read(q).get('label')) >= args.start], key=lambda q: number(read(q)['label']))
    sent, preflight = [], []
    for q in plans:
        plan = read(q); label = plan['label']
        is_sent = any((args.cache/'runs'/(label+s)).exists() for s in ('.send-intent.json','.pending.json','.ack.json','.terminal.json','.json'))
        if is_sent:
            sent.append(audit_trial(q,args,api))
        elif q.with_name('preflight.json').exists():
            pre = importlib.import_module('preflight_recovery').verify_preflight(args.repo,args.cache,plan['id'])
            preflight.append(dict(id=plan['id'],label=label,source=sources([q.with_name('preflight.json')]),
                                  status=pre['status'], cause=pre.get('cause_class'), not_counted=True))
    valid_rows = [t['row'] for t in sent if t['row']]
    summary = api['first'].summary(args.repo, args.start, valid_rows)
    if len(valid_rows) != len(sent):
        summary = dict(reason='완료 전송의 원본 감사가 아직 완결되지 않아 선별·쌍별 판정을 보류함',conditions={},pairs=[],selection={},promotion=None,confirmation=None)
    for t in sent:
        t['film'] = film_audit(t,args,api)
    overlap = overlap_audit(args)
    issues = [t['label'] for t in sent if t['state']=='audit_failed']
    actual = len(overlap['test_intervals'])
    if actual != len(sent):
        issues.append('test intervals and committed sent plans differ')
    if actual > 16:
        issues.append('actual send budget exceeds 16')
    data = dict(generated_at=datetime.now(timezone.utc).isoformat(), status='partial', actual_sends=actual, budget=16,
                code_sources=sources([Path(__file__), *[args.repo/'tools'/name for name in ('first5027.py','first5027_film.py','run_first5027.py','method_1700.py','scoring.py','verify_run.py','ledger.py')]]),
                arms=api['first'].ARMS, trials=sent, preflight=preflight, summary=summary, overlap=overlap, issues=issues,
                feasibility=feasibility(args.project, args.repo),
                controller_status={k: read(args.cache/'status.json',{}).get(k) for k in ('phase','first','reason','time')})
    if data['controller_status'].get('first') == args.start and data['controller_status'].get('phase') in ('first5027_stopped','user_stop'):
        data['status'] = 'stopped; audit issues' if issues or overlap['issues'] or overlap['overlaps'] else 'stopped'
    if args.copy_demos:
        data['copied_demos'] = copy_demos(sent, args.copy_demos, args.project, include_playable=args.include_playable)
    args.output = args.output.resolve(); args.output.parent.mkdir(parents=True,exist_ok=True)
    audit = args.output.with_name(args.output.name+'.audit.json')
    args.output.write_text(render(data,args.output))
    audit.write_text(json.dumps(data,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
    print(json.dumps(dict(output=str(args.output),audit=str(audit),status=data['status'],actual_sends=actual,audit_errors=issues),ensure_ascii=False))
    return 2 if issues else 0

if __name__ == '__main__':
    raise SystemExit(main())
