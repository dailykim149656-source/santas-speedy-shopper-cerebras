"""Summarize committed D5027 sessions from local evidence; no network or provider calls."""
import hashlib
import json
import shutil
import subprocess
import sys
import os
import tempfile
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from statistics import median
from zoneinfo import ZoneInfo
from report_cadence import section as cadence_section
from generation_metrics import summarize as generation_metrics
from report_ab import section as ab_section
from report_longgap import section as longgap_section

BASE = Path(__file__).resolve().parent
CACHE = BASE.parent
REPO = Path(os.environ.get("BOUNTY_TEST_REPO", Path.cwd()))
REPORT = REPO.parent / 'D5027-1500-실행기록.md'
KST = ZoneInfo('Asia/Seoul')


def read(path):
    return json.loads(path.read_bytes())


def json_lines(path):
    for line in path.read_bytes().splitlines(keepends=True):
        if line.endswith(b'\n') and line.strip():
            yield json.loads(line)


def write_file(path, text):
    with tempfile.NamedTemporaryFile(mode='w', dir=path.parent, delete=False, encoding='utf-8') as f:
        f.write(text)
    os.replace(f.name, path)


def fmt(x):
    return '—' if x is None else f'{x:,.2f}'


def timing(calls, reason):
    for call in calls:
        if call.get('timed_sample') and call.get('stopReason') == reason:
            generation = call['serverGeneration']
            return generation['outputTokens'] / (generation['completionMs'] / 1000)
    return None


def collect():
    campaign = read(BASE / 'campaign.json')
    relay = defaultdict(list)
    for r in json_lines(CACHE / 'relay/logs/requests.jsonl'):
        relay[r.get('run_id')].append(r)
    history = list(json_lines(CACHE / 'iterations.jsonl'))[campaign['history_start']:]
    results = []
    for row in history:
        ident = row['id']
        evidence_path = REPO / 'runs' / ident / 'evidence.json'
        ev = read(evidence_path)
        plan = read(evidence_path.with_name('plan.json'))
        valid = row['valid'] is True and row['method_valid'] is True
        attempt_counts = {'first': [], 'final': [], 'unknown': []}
        error_count = 0
        wire = bool(relay[ident])
        for req in relay[ident]:
            root = CACHE / 'relay/logs' / ident
            path = root / f"{req['at_ms']}-{req.get('forwarded_sha256','')[:12]}.json"
            phase = 'unknown'
            if path.exists():
                body = read(path)
                phase = 'final' if any(m.get('role') == 'tool' for m in body['messages']) else 'first'
            attempts = req.get('attempts', [])
            attempt_counts[phase].append(len(attempts))
            error_count += sum(a.get('status') == 429 for a in attempts) + (req.get('status') == 429)
            wire = wire and req['received_sha256'] == req.get('forwarded_sha256') and not req.get('changes')
        timed = {}
        for call in ev['calls']:
            if call.get('timed_sample'):
                timed.setdefault(call.get('stopReason'), call)
        meta = {}
        for field, reason in [('first', 'toolUse'), ('final', 'stop')]:
            call = timed.get(reason, {})
            meta[field + '_cached_input'] = call.get('usage', {}).get('cacheRead')
            meta[field + '_output_tokens'] = call.get('serverGeneration', {}).get('outputTokens')
        meta['relay_mode'] = plan.get('request_relay', '').rsplit(':', 1)[-1]
        is_control = (plan['variant'], plan['temperature'], plan['thinking']) == ('synth-five-categories-cap', .2, 'low')
        is_control = is_control and plan.get('provider_max_retries') == 0 and plan.get('request_relay','').endswith(':retry-only')
        results.append(dict(id=ident,label=row['label'].split('-')[0],end=ev['ended']['time'],
                            first=timing(ev['calls'], 'toolUse'),final=timing(ev['calls'], 'stop'),
                            score=ev['score']['mean_exact_tps'],display=ev['score']['ui_rounded_tps'],
                            valid=valid, clean=row.get('context_clean'), rate_limited=row.get('rate_limited'),
                            attempts=attempt_counts, http429=error_count, clean_wire=wire, control=is_control,
                            media=ev['evidence_status'],products=sum(p.get('verified') is True for p in ev['products']),
                            commit=row['commit'], **meta, **generation_metrics(ident, ev['calls'])))
    return campaign,results


def archive_new_record(row):
    ident = row['id']
    dest = BASE / 'records' / ident
    if (dest / 'verified.json').is_file():
        return
    archive = Path.home() / 'Library/Application Support/Cerebras Speed Bounty/2026-11-22/raw-test'
    cmd = [sys.executable, '-B', str(REPO / 'tools/verify_run.py'), ident, '--raw', str(archive / (ident + '.json'))]
    check = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if check.returncode:
        print('New record needs verification:', row['label'], file=sys.stderr)
        return
    data = json.loads(check.stdout)
    if data['evidence_status'] != 'complete' or not data['raw_digest_checked'] or data['verified_products'] != 5:
        return
    dest.mkdir(parents=True, exist_ok=True)
    source = REPO / 'runs' / ident
    media = read(source / 'evidence.json')['media']
    for asset in data['checked_media']:
        path = dest / asset
        with tempfile.NamedTemporaryFile(dir=dest, delete=False) as stage, (source / asset).open('rb') as original:
            shutil.copyfileobj(original, stage)
        stage_path = Path(stage.name)
        with stage_path.open('rb') as contents:
            digest = hashlib.file_digest(contents, 'sha256').hexdigest()
        if digest != media[asset]['sha256']:
            stage_path.unlink()
            raise ValueError('Retained media digest mismatch for ' + row['label'])
        os.replace(stage.name, path)
    for name in ['evidence.json', 'plan.json']:
        shutil.copy2(source / name, dest / name)
    write_file(dest / 'verified.json', json.dumps(data, indent=2) + chr(10))


def main():
    campaign, results = collect()
    valid = [r for r in results if r['valid']]
    best = max(valid, key=lambda r:r['score'], default=None)
    milestones = read(BASE / 'milestones.json')
    fully_filmed = [r for r in valid if r['media'] == 'complete' or (BASE / 'records' / r['id'] / 'verified.json').is_file()]
    filmed_best = max(fully_filmed, key=lambda r:r['score'], default=None)
    if filmed_best and filmed_best['score'] > milestones['filmed_baseline']:
        archive_new_record(filmed_best)
    current = read(CACHE / 'status.json')
    lines=['# D5027 단독 반복 실험','',
           f"시작 {campaign['started']} · 마감 {campaign['deadline']} · 기준 기록 D5027 평균 {campaign['previous_best']:,.2f} TPS.",
           '', '매번 새 세션이 5개 상품을 실시간 조회한다. 온도 0.2, 낮은 추론 설정, 출력 상한 1,024토큰을 사용한다. 기본형은 원문을 유지하고 중계에서 429만 재시도한다. 첫 요청 도구 선택 방식 비교의 B에서는 첫 tool_choice를 required로 바꾼다. 점수는 한 세션에서 제공사가 측정한 각 생성 TPS의 산술평균이다.',
           '',f"종료 증빙 {len(results)}건, 상품·방식 통과 {len(valid)}건. " +
           (f"이번 유효 최고 {best['label']} **{best['score']:,.2f} TPS**, 유효 중앙값 {median(r['score'] for r in valid):,.2f} TPS." if best else '유효 점수는 아직 없다.'),
           '',f"최근 루프 상태 `{current.get('phase','')}` {current.get('label','')}.",
           '', '재시도 열은 첫 요청 / 도구 조회 후 요청의 중계 재전송 횟수다. 429 합계에는 마지막 실패 응답도 포함한다. clean과 rate_limited는 루프의 원래 판정값이다. 실패 중 남은 점수도 표시하며 유효 최고에서는 제외한다.',
           '', '| 완료 KST | 실행 | 첫 TPS | 최종 TPS | 세션 평균 | 유효 상품 | 방식 통과 | clean | rate_limited | 재시도 첫 / 최종 | 429 합계 | 생성 ms 첫 / 최종 | 추론 토큰 첫 / 최종 |',
           '|---|---|---:|---:|---:|---:|---|---|---|---|---:|---|---|']
    flag=lambda v: {True:'예',False:'아니오',None:'—'}.get(v,'—')
    for r in results:
        at=r['attempts']; text=' / '.join('+'.join(map(str,at[p])) or '—' for p in ('first','final'))
        if at['unknown']:text+=' (단계 미확인 '+str(at['unknown'])+')'
        kst=datetime.fromtimestamp(r['end']/1000,KST).strftime('%m-%d %H:%M:%S')
        reason_pair = ' / '.join(str(r[k]) if r[k] is not None else '—' for k in ('first_reasoning', 'final_reasoning'))
        lines.append(f"| {kst} | [{r['label']}](<speed-bounty-evidence-test/runs/{r['id']}/evidence.json>) | {fmt(r['first'])} | {fmt(r['final'])} | {fmt(r['score'])} | {r['products']}/5 | {flag(r['valid'])} | {flag(r['clean'])} | {flag(r['rate_limited'])} | {text} | {r['http429']} | {fmt(r['first_ms'])} / {fmt(r['final_ms'])} | {reason_pair} |")
    lines += ['', '[D5098~D5106 첫·최종 생성 시간과 429 원인 분석](<D5027-1500-원인분석.md>)']
    lines += cadence_section(BASE, REPO, results)
    lines += ab_section(BASE, results)
    lines += longgap_section(BASE, REPO, results)
    proof = BASE / 'records' / filmed_best['id'] / 'verified.json' if filmed_best else None
    preserved = bool(proof and proof.is_file())
    lines += ['', '## 마감까지의 목표', '',
              '| 단계 | 기준 | 이번 실험에서 원본·영상 확인 |', '|---|---:|---|']
    for label, threshold in [('전 구간 녹화 최고 경신', milestones['filmed_baseline']),
                             ('D5027 유효 최고 경신', milestones['record_baseline']),
                             ('최종 목표', milestones['goal_strict_greater_than'])]:
        achieved = preserved and filmed_best['score'] > threshold
        result = f"[{filmed_best['label']} 검산](<{proof}>)" if achieved else '미달성'
        lines.append(f"| {label} | 세션 평균 {threshold:,.2f} 초과 | {result} |")
    closure = CACHE / 'stop-requested'
    receipt = read(closure) if closure.is_file() and (BASE/'stop-after-longgap').exists() else {}
    if receipt.get('reason') == 'requested stop after four-slot comparison':
        closed_at = datetime.fromisoformat(receipt['time']).astimezone(KST)
        lines += ['', f"두 비교 뒤 기본형 반복을 끝내 달라는 사용자 요청에 따라 {closed_at:%m-%d %H:%M:%S} KST에 캠페인을 종료했다."]
    elif (BASE/'stop-after-longgap').is_file():
        lines += ['', '두 비교가 끝나면 사용자 요청에 따라 기본형 반복도 종료한다.']
    else:
        lines += ['', '01:30 KST에 중간 기록을 점검한다.']
    lines += ['', '점수 판정에는 원래 정밀도를 쓰며 원본 전체 영상과 60초 이내 데모를 따로 확인한다.']
    lines += ['', f"[중계 원장](<{CACHE/'relay/logs/requests.jsonl'}>) · [일반 루프 기록](<{CACHE/'iterations.jsonl'}>) · [구조화된 집계](<{BASE/'trials.json'}>)"]
    write_file(BASE/'trials.json',json.dumps(results,indent=2,ensure_ascii=False)+'\n')
    write_file(REPORT,'\n'.join(lines)+'\n')
    print('completed',len(results),'valid',len(valid),'best',None if not best else (best['label'],round(best['score'],2)))

if __name__=='__main__':
    main()
