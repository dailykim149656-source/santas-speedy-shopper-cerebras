"""Reconcile a speed1500 campaign offline and render its Korean results in Markdown."""
import argparse
from datetime import datetime
import hashlib
import json
import math
import os
from pathlib import Path
import re
from statistics import median
import subprocess

import ledger
from gift8_evidence import score_raw
from method_1700 import assess
import prefetch1500
import speed1500 as campaign
import validate


def read(path):
    return json.loads(path.read_bytes())


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check(errors, condition, message):
    if not condition:
        errors.append(message)


def link(label, path, folder):
    return f'[{label}](<{os.path.relpath(path, folder)}>)'


def num(value):
    return '—' if value is None else f'{value:,.2f}'


def med(values):
    return median(values) if values else None


def kst(timestamp):
    return datetime.fromtimestamp(timestamp / 1000, campaign.KST).strftime('%m-%d %H:%M:%S')


def read_rows(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def inspect_relay(plan, arm, rows, calls, log_root, errors):
    source_hash, mode = plan['request_relay'].split(':')[1:]
    expected_mode = 'final-only' if arm == 'F' else 'retry-only'
    ok = bool(rows) and mode == expected_mode
    success = [r for r in rows if r.get('status') == 200]
    ok = ok and len(success) == len(calls)
    if arm == 'F':
        ok = ok and bool(success) and success[0]['phase'] == 'first' and success[-1]['phase'] == 'final'
    for row in rows:
        ok = ok and row.get('relay_sha256') == source_hash and not row.get('error')
        forwarded = row.get('forwarded_sha256', '')
        body = log_root / plan['id'] / f"{row['at_ms']}-{forwarded[:12]}.json"
        check(errors, row.get('run_id') == plan['id'] and row.get('nonce') == plan['id'][:8]
              and body.is_file() and digest(body) == forwarded, '릴레이 요청 원본 또는 실행 ID 불일치')
        if arm == 'F' and row.get('phase') == 'final':
            changes = set(row.get('changes', []))
            ok = ok and 'removed_tools' in changes and changes <= {'removed_tools', 'removed_parallel_tool_calls', 'removed_tool_choice'}
            if body.is_file():
                ok = ok and not {'tools', 'parallel_tool_calls', 'tool_choice'}.intersection(read(body))
        else:
            ok = ok and row.get('received_sha256') == forwarded and not row.get('changes')
            ok = ok and row.get('phase') in (('first', 'repair') if arm == 'F' else ('passthrough',))
    for row, call in zip(success, calls):
        timing = row.get('timing') or {}
        check(errors, timing.get('completion_tokens') == call['outputTokens']
              and math.isclose((timing.get('completion_time') or 0) * 1000, call['completionMs'], abs_tol=1e-6),
              '릴레이 SSE와 서버 생성 시간·출력 토큰 불일치')
    return bool(ok)


def inspect_video(media, raw, score, products, evidence, errors):
    ready = read(media / 'ready.json')
    ready_ms = datetime.fromisoformat(ready['readyAt'].replace('Z', '+00:00')).timestamp() * 1000
    before = (ready.get('ready') is True and ready.get('sessionKey') == raw['sessionKey']
              and ready.get('initialSummary') == '' and ready.get('rehearsal') is False
              and ready_ms <= raw['startedWall'])
    if not (media / 'demo.mp4').is_file() or not (media / 'viewport-evidence.json').is_file():
        return before, False
    try:
        metadata, _, issues = ledger.media(media, raw, score, products)
        archived = evidence.get('media', {})
        for name in ('demo.mp4', 'original.mp4'):
            if archived.get(name):
                check(errors, archived[name]['sha256'] == metadata[name]['sha256'], f'{name} 원장 해시 불일치')
        return before, before and not issues
    except ledger.MEDIA_ERRORS:
        return before, False


def wire_contains(row, log_root, plan, context):
    file = log_root / plan['id'] / f"{row['at_ms']}-{row['forwarded_sha256'][:12]}.json"
    messages = read(file)['messages']
    texts = []
    for message in messages:
        if message.get('role') == 'user':
            content = message['content']
            texts.extend([content] if isinstance(content, str) else
                         [p['text'] for p in content if isinstance(p, dict) and 'text' in p])
    return sum(text.count(context) for text in texts) == 1 and any(plan['prompt'] in text for text in texts)


def observed_reasoning_chars(message):
    parts = message.get('content')
    if not isinstance(parts, list) or not any(isinstance(p, dict) and p.get('type') == 'text'
                                               and isinstance(p.get('text'), str) for p in parts):
        return None
    chars = 0
    for part in parts:
        if not isinstance(part, dict) or part.get('type') not in ('text', 'thinking') or part.get('redacted'):
            return None
        if part['type'] == 'thinking':
            if not isinstance(part.get('thinking'), str):
                return None
            chars += len(part['thinking'])
    return chars


def inspect_slot(directory, home, relay_by_id, errors):
    summary = read(directory / 'summary.json')
    plan = read(directory / 'plan.json')
    raw_path = directory / 'raw.json'
    raw = read(raw_path)
    validation = read(directory / 'validation.json')
    repo_run = campaign.REPO / 'runs' / plan['id']
    evidence = read(repo_run / 'evidence.json')
    slot_evidence = read(directory / 'evidence.json')
    slot, arm, ident = summary['slot'], summary['arm'], plan['id']
    issues = []
    check(issues, summary['campaign'] == home.name and int(directory.name) == slot
          and all(j.get('id') == ident for j in (summary, raw, evidence, slot_evidence)), '캠페인·슬롯·실행 ID 불일치')
    check(issues, raw['sessionKey'] == plan['sessionKey'] and raw['prompt'] == plan['prompt']
          and read(repo_run / 'plan.json') == plan and summary['label'] == plan['label'], '원장 계획과 실전 입력 불일치')
    git_path = f'runs/{ident}'
    commit = evidence.get('plan_commit', '')
    check(issues, re.fullmatch(r'[a-f0-9]{40}', commit) and
          json.loads(ledger.git(campaign.REPO, 'show', f'{commit}:{git_path}/plan.json')) == plan
          and json.loads(ledger.git(campaign.REPO, 'show', f'HEAD:{git_path}/evidence.json')) == evidence,
          'Git 커밋의 계획 또는 증빙과 파일 불일치')
    raw_sha = digest(raw_path)
    check(issues, validation.get('run_id') == ident and
          all(j.get(k) == raw_sha for j, k in ((summary, 'raw_sha256'), (validation, 'input_sha256'),
                                                        (evidence, 'private_raw_sha256'), (slot_evidence, 'private_raw_sha256'))),
          '원본 SHA-256 불일치')
    history = raw['history']['messages']
    users = [m for m in history if m.get('role') == 'user']
    check(issues, len(users) == 1 and users[0].get('__openclaw', {}).get('idempotencyKey') == ident + ':user',
          '새 세션의 고유 사용자 전송 내역 불일치')
    all_calls, score, _ = score_raw(raw)
    calls = [call for call in all_calls if call['timed_sample']]
    rates = [c['tokensPerSecond'] for c in calls]
    final = calls[-1] if calls and calls[-1]['stopReason'] == 'stop' else None
    mean, ui = score['mean_exact_tps'], score['ui_rounded_tps']
    check(issues, all(j['score'].get('mean_exact_tps') == mean and j['score'].get('ui_rounded_tps') == ui
                      and j['score'].get('official_patch_sha256') == plan['official_patch_sha256']
                      for j in (evidence, slot_evidence, validation))
          and summary.get('score') == mean and summary.get('ui') == ui and summary.get('call_count') == len(calls),
          '패치 해시·공식 평균·표시값·호출 수 불일치')
    scored = [(c['response_id'], c['outputTokens'], c['completionMs']) for c in calls]
    archived = [(c.get('responseId'), c['serverGeneration']['outputTokens'], c['serverGeneration']['completionMs'])
                for c in evidence['calls'] if c.get('timed_sample')]
    check(issues, scored == archived and scored == [(c['response_id'], c['outputTokens'], c['completionMs']) for c in validation['calls']],
          '원장 또는 검증 기록의 개별 호출 불일치')
    products = validation['products']
    urls = [p['url'] for p in products if p.get('verified')]
    true_products = validation.get('product_valid', validation['valid'])
    if true_products:
        shown, misleading = validate.answer_links(validation['final_text'])
        check(issues, len(urls) == len(set(urls)) == 5 and set(shown) == set(urls) and len(shown) == 5 and not misleading
              and all(p.get('http') == 200 and p.get('html_sha256') for p in products)
              and [p['url'] for p in evidence['products'] if p.get('verified')] == urls,
              '실상품 5개, 상세 페이지 또는 최종 답변 링크 불일치')
    rows = read(directory / 'relay.json')
    check(issues, rows == relay_by_id.get(ident, []), '슬롯별 릴레이 기록과 전체 로그 불일치')
    log_root = home.parent / 'relay/logs'
    relay_ok = inspect_relay(plan, arm, rows, calls, log_root, issues)
    receipts_ok = False
    if arm == 'P':
        receipt_dir = home / 'receipts' / ident
        try:
            merchant_rows, _, proof = prefetch1500.audit_receipts(receipt_dir, plan, raw, raw['startedWall'], raw['ended']['time'])
            prefetch1500.audit_dispatch(receipt_dir, plan, raw, merchant_rows, proof)
            expected = [f"{i}. [{p['name']}]({p['permalink']})" for i, p in enumerate(merchant_rows, 1)]
            context = prefetch1500.CONTEXT_PREFIX + json.dumps(merchant_rows, ensure_ascii=False, separators=(',', ':'))
            receipts_ok = bool(rows) and all(wire_contains(r, log_root, plan, context) for r in rows)
            relay_ok = relay_ok and receipts_ok and proof['context_sha256'] == validation.get('native_prefetch', {}).get('context_sha256')
            method = validation['final_text'].strip().splitlines() == expected and raw['ended']['terminal'] == 'final'
        except (OSError, ValueError, TypeError, KeyError, IndexError):
            method = relay_ok = False
        method = method and validation.get('method_valid') is True
    else:
        method = assess(plan, raw, validation)
    numbered = [f"{i}. [{p.get('catalog_name')}]({p.get('url')})" for i, p in enumerate(products, 1)]
    method = bool(method and relay_ok and len(numbered) == 5 and
                  validation['final_text'].strip().splitlines() == numbered)
    valid = bool(true_products and method)
    check(issues, summary['method_valid'] == method and summary['valid'] == valid
          and summary['product_valid'] == true_products and summary['relay_valid'] == relay_ok, '독립 유효성 평가와 실행 요약 불일치')
    ready_dirs = sorted(directory.glob('attempt-*/media/ready.json'))
    media = Path(summary['paths']['media'])
    check(issues, len(ready_dirs) == 1 and media / 'ready.json' in ready_dirs, '촬영 준비를 통과한 실행 시도 중복 또는 누락')
    before, screen = inspect_video(media, raw, ui, products, evidence, issues)
    check(issues, bool(summary['record']) == bool(valid and mean is not None and mean > campaign.RECORD),
          '원장 요약의 자체 기록 판정 불일치')
    if valid and mean is not None and mean > campaign.RECORD:
        check(issues, screen == summary['recorded_video'] and summary['goal'] == bool(mean >= 1500 and ui >= 1500 and screen),
              '신기록 후보 영상·공식 UI 또는 목표 판정 불일치')
    errors.extend(f'{plan["label"]} · {why}' for why in issues)
    retries = sum(a.get('status') == 429 for row in rows for a in row.get('attempts', []))
    final_429s = sum(row.get('status') == 429 for row in rows)
    request_count = sum(len(r.get('attempts', [])) + int('status' in r) for r in rows)
    check(errors, summary['provider_429s'] == retries + final_429s, f'{plan["label"]} · 429 응답 수 불일치')
    check(errors, summary.get('provider_attempts', request_count) == request_count, f'{plan["label"]} · 제공사 HTTP 요청 수 불일치')
    hashes = [r.get('forwarded_sha256', '') for r in rows if r.get('status') == 200]
    terminal = bool(rows and rows[-1].get('status') == 429 and raw['ended']['terminal'] == 'error')
    check(errors, terminal == bool(summary['terminal_429']), f'{plan["label"]} · 최종 429 분류 불일치')
    return dict(slot=slot, arm=arm, label=plan['label'], id=ident, session=raw['sessionKey'], start=raw['startedWall'],
                end=raw['ended']['time'], score=mean, ui=ui, first=rates[0] if rates else None,
                final=final['tokensPerSecond'] if final else None, final_tokens=final['outputTokens'] if final else None,
                reasoning_chars=observed_reasoning_chars(history[final['message_index']]) if final else None,
                calls=len(calls), call_ids=[c['response_id'] for c in calls], product_valid=true_products,
                method_valid=method, valid=valid and not issues, before=before, screen=screen, urls=urls,
                requests_429=retries + final_429s, retries=retries, terminal=terminal, raw_calls=calls,
                request_count=request_count, hashes=hashes,
                media=media, repo=repo_run, receipts=receipts_ok, private=directory, reasons=validation['reject_reasons'])


def audit(home):
    errors = []
    check(errors, read(home / 'protocol.json') == campaign.protocol(), '사전 등록 프로토콜과 실행 프로토콜 불일치')
    relay = {}
    log = home.parent / 'relay/logs/requests.jsonl'
    if log.is_file():
        for row in read_rows(log):
            relay.setdefault(row.get('run_id'), []).append(row)
    rows = []
    for path in sorted(home.glob('slots/[0-9][0-9][0-9]/summary.json')):
        try:
            rows.append(inspect_slot(path.parent, home, relay, errors))
        except (OSError, ValueError, TypeError, KeyError, IndexError, subprocess.CalledProcessError) as exc:
            errors.append(f'슬롯 {path.parent.name}의 증빙 판독 실패 · {exc}')
            break
    exploration = rows[:18]
    options, winner = campaign.selection(exploration)
    order = ''.join(campaign.ORDER) + ('A' + winner * 2 + 'A' if winner else '')
    check(errors, [r['slot'] for r in rows] == list(range(1, len(rows) + 1))
          and ''.join(r['arm'] for r in rows) == order[:len(rows)], '배정 순서 또는 슬롯 번호 불일치')
    for key in ('id', 'session', 'label'):
        check(errors, len({r[key] for r in rows}) == len(rows), f'중복 실행 식별자 {key}')
    terminals = {}
    for path in (home.parent / 'runs').glob('D*-speed1500-?.json'):
        raw = read(path)
        match = re.fullmatch(re.escape(home.name) + r' slot=(\d+) arm=[AFP](?:;.*)?', raw.get('experiment', ''))
        if match:
            slot = int(match[1])
            check(errors, slot not in terminals, f'슬롯 {slot}에 종결된 실전 전송이 둘 이상 존재')
            terminals[slot] = raw['id']
    check(errors, all(terminals.get(r['slot']) == r['id'] for r in rows), '슬롯 집계와 게이트웨이 종결 기록 불일치')
    ids = [ident for row in rows for ident in row['call_ids']]
    check(errors, all(ids) and len(ids) == len(set(ids)), '중복 또는 누락된 제공사 응답 ID')
    check(errors, all(a['end'] <= b['start'] for a, b in zip(rows, rows[1:])), '캠페인 실행 구간 중첩')
    if rows:
        check(errors, all(b['start'] - a['end'] >= 60_000 for a, b in zip(rows, rows[1:])),
              '사전 등록한 실행 간 60초 대기 미충족')
    if len(rows) > 18:
        previous, confirm = rows[17]['end'], rows[18]['start']
        check(errors, confirm - previous >= 900_000 and kst(previous)[:8] != kst(confirm)[:8], '확인 구간의 시각 또는 15분 간격 불충족')
    controller = home / 'report.json'
    if controller.is_file():
        current = read(controller)
        if current.get('completed') == len(rows):
            check(errors, current.get('winner') == winner and current.get('candidates') == options,
                  '원본 재집계와 컨트롤러의 후보 선정 불일치')
    return rows, options, winner, len(rows) == len(order), errors


def render(home, folder):
    rows, options, winner, complete, errors = audit(home)
    exploration, confirmation = rows[:18], rows[18:]
    valid = [r for r in rows if r['valid']]
    best = max(valid, key=lambda r: r['score'], default=None)
    records = [r for r in valid if r['score'] > campaign.RECORD]
    screened = [r for r in records if r['screen']]
    goals = [r for r in screened if r['score'] >= 1500 and r['ui'] >= 1500]
    text = ['# 쇼핑 바운티 1,500 TPS 실험 결과', '',
            f"탐색 {len(exploration)}/18회, 별도 확인 " + (f'{len(confirmation)}/4회.' if winner else '미배정.')
            + (' 예정된 실행을 마쳤다.' if complete else ' 아직 실험이 진행 중이다.'), '']
    if best:
        row_link = link(best['label'], best['repo'] / 'evidence.json', folder)
        text.append(f"유효 최고는 {row_link}의 **{num(best['score'])} TPS**다. 같은 실행에서 재검산한 정수 표시값은 {best['ui']:,}이다.")
        if best['screen']:
            text[-1] += ' ' + link('최고 실행 영상', best['media'] / 'demo.mp4', folder)
        else:
            text[-1] += ' 이 실행의 공식 UI와 상품 링크 5개를 함께 입증하는 영상은 확인되지 않았다.'
    elif rows:
        text.append('완료한 실행 중 상품과 호출 방식을 모두 검증한 기록은 아직 없다.')
    incumbent = campaign.REPO / 'runs/cd75e5e0-be7c-471f-a9ab-c9e6f0d1bd77/evidence.json'
    text += ['', f'이전 자체 최고 **{num(campaign.RECORD)} TPS**를 넘은 유효 세션 {len(records)}회, 영상·화면까지 확인된 경신 {len(screened)}회, 공식 평균과 화면이 모두 **1,500 이상**인 검증 기록 {len(goals)}회. ' + link('D5027 원본', incumbent, folder),
             '', '## 조건별 결과', '',
             '탐색 6개 블록의 결과다. A는 D5027의 기본 조회, F는 같은 조회 후 최종 호출의 도구 정의 제거, P는 상품 실시간 선조회 후 Kimi가 답하는 조건이다. 중앙값과 최고에는 상품·방식 모두 유효한 세션만 포함했다.', '',
             '| 조건 | 전송 | 상품 성공 | 상품·방식 유효 | 중앙값 TPS | 최고 TPS | 첫 호출 중앙값 | 최종 호출 중앙값 | 429 응답 / 종료 세션 |',
             '|---|---:|---:|---:|---:|---:|---:|---:|---:|']
    for arm in 'AFP':
        group = [r for r in exploration if r['arm'] == arm]
        ok = [r for r in group if r['valid']]
        scores = [r['score'] for r in ok]
        text.append(f"| {arm} | {len(group)} | {sum(r['product_valid'] for r in group)} | {len(ok)} | {num(med(scores))} | {num(max(scores, default=None))} | {num(med([r['first'] for r in ok if r['first'] is not None]))} | {num(med([r['final'] for r in ok if r['final'] is not None]))} | {sum(r['requests_429'] for r in group)} / {sum(r['terminal'] for r in group)} |")
    text += ['', '## 최종 호출에서 관측한 추론 길이', '',
             '탐색 중 상품과 방식을 모두 검증하고 최종 답변을 생성한 세션만 집계했다. 글자 수는 최종 응답에 기록된 추론 문자열의 길이다. 텍스트 블록만 있으면 관측값은 0자이며, 서버 내부의 추론량은 이 기록으로 알 수 없다. 블록 형식이 불완전하거나 가려진 경우는 관측 불가로 센다.', '',
             '| 조건 | 유효 최종 | 0자 | 1자 이상 | 관측 불가 | 글자 수 중앙값 | 출력 토큰 중앙값 | 정확히 161토큰 | 최종 TPS 중앙값 (0자 / 1자 이상) | 0자이면서 최종 ≥1,500 TPS |',
             '|---|---:|---:|---:|---:|---:|---:|---:|---|---:|']
    for arm in 'AFP':
        finals = [r for r in exploration if r['arm'] == arm and r['valid'] and r['final'] is not None]
        chars = [r['reasoning_chars'] for r in finals if r['reasoning_chars'] is not None]
        zero = [r for r in finals if r['reasoning_chars'] == 0]
        positive = [r for r in finals if r['reasoning_chars'] is not None and r['reasoning_chars'] > 0]
        tokens = [r['final_tokens'] for r in finals]
        text.append(f"| {arm} | {len(finals)} | {len(zero)} | {len(positive)} | {len(finals)-len(chars)} | {num(med(chars))} | {num(med(tokens))} | {tokens.count(161)} | {num(med([r['final'] for r in zero]))} / {num(med([r['final'] for r in positive]))} | {sum(r['final'] >= 1500 for r in zero)} |")
    text += ['', '## 같은 블록 안에서의 비교', '',
             '선별 기준은 완료한 18회 중 유효 대조쌍 4개 이상, A 대비 4승 이상, 차이 중앙값 +100 TPS 이상, 상품 성공 횟수 A 이상이다. 차이는 후보 세션 평균에서 같은 블록의 A 세션 평균을 뺀 값이다.', '',
             '| 블록 | 전송 순서 | F − A TPS | P − A TPS |', '|---:|---|---:|---:|']
    for offset in range(0, len(exploration), 3):
        block = exploration[offset:offset + 3]
        lookup = {r['arm']: r['score'] for r in block if r['valid']}
        delta = lambda a: num(lookup[a] - lookup['A']) if a in lookup and 'A' in lookup else '—'
        text.append(f"| {offset//3 + 1} | {''.join(r['arm'] for r in block)} | {delta('F')} | {delta('P')} |")
    for arm in 'FP':
        info = options[arm]
        text += ['', f"{arm}는 유효 {info['pairs']}쌍 중 {info['wins']}승, 차이 중앙값 {num(info['median_gain'])} TPS였다."]
    if len(exploration) == 18:
        text += ['', f'별도 확인 후보는 {winner}다.' if winner else '선별 기준을 충족한 후보가 없어 추가 확인 4회는 배정하지 않았다.']
    if confirmation:
        diffs = []
        for start in range(0, len(confirmation), 2):
            pair = confirmation[start:start+2]
            a = next((r for r in pair if r['arm'] == 'A'), None)
            b = next((r for r in pair if r['arm'] == winner), None)
            diffs.append(b['score'] - a['score'] if a and b and a['valid'] and b['valid'] else None)
        text += ['', f"별도 시간대 확인 {len(confirmation)}/4회. 탐색 종료 {kst(exploration[-1]['end'])} KST, 확인 시작 {kst(confirmation[0]['start'])} KST. 짝별 차이 " + ' / '.join(num(d) for d in diffs) + ' TPS.']
        if len(confirmation) == 4:
            text += ['', '두 쌍 모두 재현 기준을 통과했다.' if all(d is not None and d > 0 for d in diffs) else '두 쌍 모두 후보 우위라는 재현 기준에 미달했다.']
    text += ['', '## 실행별 근거', '',
             '점수는 각 세션에서 제공사가 측정한 모든 생성의 출력 토큰 ÷ 서버 생성 초를 산술평균한 값이다. 실패 도중 남은 표본도 표시했다. 첫·최종 열의 같은 값은 단일 생성일 수 있다. 촬영 열은 요청 전 빈 세션 준비 / 화면의 점수와 상품 링크 5개가 확인된 영상 순서다. 429 열은 재시도 응답과 각 요청의 마지막 429까지 모두 센다.', '',
             '| 슬롯 | 시작 KST | 조건 | 실행 증빙 | 상품 / 방식 | 측정 호출 | 첫 / 최종 TPS | 공식 평균 | UI 환산 | 촬영 | 429 응답 |',
             '|---:|---|---|---|---|---:|---|---:|---:|---|---:|']
    yn = lambda value: '✓' if value else '×'
    for r in rows:
        ev = link(r['label'], r['repo']/'evidence.json', folder) + ' · ' + link('계획', r['repo']/'plan.json', folder)
        capture = f"{yn(r['before'])} / {yn(r['screen'])}"
        if (r['media']/'demo.mp4').is_file():
            capture += ' · ' + link('영상' if r['screen'] else '부분 영상', r['media']/'demo.mp4', folder)
        text.append(f"| {r['slot']} | {kst(r['start'])} | {r['arm']} | {ev} | {yn(r['product_valid'])} / {yn(r['method_valid'])} | {r['calls']} | {num(r['first'])} / {num(r['final'])} | {num(r['score'])} | {r['ui'] if r['ui'] is not None else '—'} | {capture} | {r['requests_429']}{' (종료)' if r['terminal'] else ''} |")
    if any(r['calls'] for r in rows):
        text += ['', '## 호출별 서버 측정값', '',
                 '입력 해시는 릴레이가 전송한 요청 본문의 SHA-256 앞 12자리다. 링크에서 전체 해시와 각 시도의 HTTP 응답을 확인할 수 있다.', '',
                 '| 슬롯 | 생성 | 종료 | 출력 토큰 | 생성 ms | TPS | 입력 해시 |',
                 '|---:|---:|---|---:|---:|---:|---|']
        for row in rows:
            for i, call in enumerate(row['raw_calls']):
                key = row['hashes'][i][:12] if i < len(row['hashes']) else '해시 미확인'
                text.append(f"| {row['slot']} | {i+1} | {call['stopReason']} | {call['outputTokens']} | {call['completionMs']:.5f} | {num(call['tokensPerSecond'])} | {link(key, row['private']/'relay.json', folder)} |")
    native = [r for r in rows if r['arm'] == 'P']
    text += ['', '## 원본 검산과 해석', '',
             f"새 세션 전송 {len(rows)}회에서 고유 실행 ID {len(set(r['id'] for r in rows))}개를 대조했다. 릴레이에 기록된 제공사 HTTP 요청은 재시도 포함 {sum(r['request_count'] for r in rows)}회, 시간 측정이 있는 생성은 {sum(r['calls'] for r in rows)}회다. 429 응답은 총 {sum(r['requests_429'] for r in rows)}회로, 다음 시도로 이어진 429는 {sum(r['retries'] for r in rows)}회다. 촬영 준비가 전송보다 빠른 세션은 {sum(r['before'] for r in rows)}회다. P의 판매처 영수증 5개와 실제 모델 입력을 대조한 실행 {sum(r['receipts'] for r in native)}회, 상품·방식 모두 유효한 P 단일 생성 {sum(r['valid'] and r['calls']==1 for r in native)}회, P 전체 전송 {len(native)}회다.",
             '', '상세 페이지의 HTTP 상태와 본문 해시는 당시 검증 기록을 사용했다. F의 처음·복구 요청은 수신·전송 바이트 해시로, 최종 요청은 릴레이의 변경 필드 기록 및 보관한 전송 본문으로 확인했다. 429는 제공사 요청 횟수와 세션 성공률에 반영한다. 서비스 부하와 개별 생성 속도의 인과관계는 이 자료에서 분리할 수 없다.']
    text += ['', '사용자는 Claude에서 같은 API 키로 진행하던 별도 재실험을 중지했다고 알려 왔으며, 해당 진단은 탐색 18회 집계에서 제외했고 두 실험의 정확한 중첩 시각과 429의 원인은 확인되지 않았다.']
    incomplete = [r for r in rows if not r['valid']]
    if incomplete:
        text += ['', '**유효 비교에서 제외한 실행**', '']
        for r in incomplete:
            if r['terminal']:
                cause = '제공사 429로 최종 응답 실패'
            elif not r['product_valid']:
                cause = '상품 검증 실패'
            else:
                cause = '실험 방식 또는 릴레이 검증 실패'
            text.append(f"- {r['label']} · {cause}. " + link('검증 내역', r['private']/'validation.json', folder))
    if complete and valid and not errors:
        text += ['', '## 다음 비교', '']
        if len(goals) > 1:
            text.append('서로 다른 새 세션에서 1,500 TPS를 재현했다. 같은 설정에서 선물 카테고리만 바꿔 다른 상품 조합의 성공률과 중앙값을 측정할 수 있다.')
        elif len(goals) == 1:
            text.append('1,500 TPS를 넘긴 세션은 한 건이다. 해당 실행의 프롬프트와 설정으로 새 세션을 반복해 목표 재현 횟수와 전체 시도 수를 함께 기록하는 것이 다음 검증이다.')
        elif any(o['pairs'] < 4 for o in options.values()):
            text.append('비교 가능한 블록이 4개 미만인 후보가 있다. 다음 탐색은 같은 설정으로 A와 해당 후보를 교차해 빠졌던 유효 쌍을 확보하는 데 우선 배정할 수 있다.')
        elif winner:
            text.append(f'{winner} 조건이 탐색 기준을 통과했다. 그 조건을 기준으로 선물 조합 하나만 바꿔 속도 개선이 특정 상품명이나 링크에 의존하는지 시험할 수 있다.')
        else:
            text.append('어느 후보도 사전 선별선을 넘지 못했다. 다음 비교는 A의 다섯 줄 출력을 유지하고 최종 답변 지시만 바꿔 최종 생성 시간, 추론 출력 유무와 세션 평균을 짝별로 측정하는 것이 적절하다.')
    if best:
        text += ['', '최고 실행의 원본과 검증 자료 · ' + ' · '.join(link(name, best['private']/filename, folder)
                 for name, filename in [('세션 원본','raw.json'), ('상품 검증','validation.json'), ('릴레이 요청','relay.json')])]
    if errors:
        text += ['', '**감사 중 발견한 불일치**', '', *['- ' + e for e in errors]]
    else:
        text += ['', '완료된 슬롯의 원본 해시·호출별 산식·전송 식별자 대조에서 불일치가 없었다.']
    return '\n'.join(text).strip() + '\n', complete, errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--campaign', default='speed1500-20261122')
    parser.add_argument('--root', type=Path, default=campaign.BASE)
    parser.add_argument('--output', type=Path, help='Markdown output file. Default is stdout.')
    parser.add_argument('--require-complete', action='store_true')
    args = parser.parse_args()
    if not re.fullmatch(r'speed1500-[A-Za-z0-9-]+', args.campaign):
        parser.error('Invalid campaign name')
    if args.output and args.output.suffix.lower() != '.md':
        parser.error('Choose a Markdown output file')
    report, complete, errors = render(args.root.resolve() / args.campaign,
                                      args.output.resolve().parent if args.output else Path.cwd())
    if args.output:
        args.output.write_text(report)
    else:
        print(report, end='')
    return 1 if errors or (args.require_complete and not complete) else 0


if __name__ == '__main__':
    raise SystemExit(main())
