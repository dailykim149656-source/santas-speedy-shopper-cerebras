"""Read the D5027-only journal and write a point-in-time Korean report."""
import argparse
from collections import defaultdict
from datetime import datetime
import importlib.util
from pathlib import Path
import sys
import tempfile

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
PRIOR = HERE.parent / 'merchant45-20261123'
spec = importlib.util.spec_from_file_location('merchant_report', PRIOR / 'report.py')
previous = importlib.util.module_from_spec(spec)
spec.loader.exec_module(previous)
read, fmt = previous.read, previous.fmt
REPORT = previous.PROJECT / 'D5027 단독 실행 결과 - 2026-11-23.md'
RUNS = previous.metrics.REPO / 'runs'
SOURCE = HERE / 'campaign.json'
TZ = previous.DEADLINE.tzinfo


def yes(value):
    return {True: '예', False: '아니오', None: '—'}[value]


def clock_time(stamp):
    return datetime.fromisoformat(stamp).astimezone(TZ).strftime('%H:%M:%S')


def link(title, target):
    return f'[{title}](<{target}>)'


def seals(ident):
    entries = []
    for p in sorted((HERE/'sealed'/ident).glob('*/manifest.json')):
        m = read(p)
        check = m.get('verification', {})
        if m.get('id') != ident or check.get('raw_digest_checked') is not True or check.get('verified_products') != 5:
            continue
        files = m.get('files', {})
        full = (m.get('complete_full_run') is True and ('original.mp4' in files and 'demo.mp4' in files)
                and all((p.parent/name).is_file() for name in ('original.mp4', 'demo.mp4')))
        entries.append((full, p))
    return max(entries, default=(False, None), key=lambda x: x[0])


def build(state):
    slots = state['slots']
    closed = [s for s in slots if s.get('result') == 'terminal']
    rows, _ = previous.collect({'slots': closed})
    by_number = {r['number']: r for r in rows}
    receipt_by_number = {s['number']: s.get('receipt', {}) for s in slots}
    upstream = defaultdict(list)
    for log in previous.metrics.lines(previous.CACHE / 'relay/logs/requests.jsonl'):
        upstream[log.get('run_id')].append(log)
    for r in rows:
        full, manifest = seals(r['id'])
        r['manifest'] = manifest
        r['video'] = (manifest.parent/'demo.mp4' if full else
                      r['ep'].parent/'demo.mp4' if r['media'] else None)
    valid = [r for r in rows if r['valid'] and r['mean_tps'] is not None]
    full = [r for r in valid if r['video']]
    baseline = previous.score(previous.BASE_ID)
    film_base = previous.score(previous.BASE_VIDEO_ID)
    before = [s for s in slots if s.get('result') == 'presend_failure']
    phase = {'running':'진행 중','completed':'종료','interrupted':'오류로 중단','external_stop':'예약 변경으로 종료'}.get(state['phase'],state['phase'])
    cutoff = datetime.fromisoformat(state['deadline'])
    now = datetime.now(TZ)
    s = ['# D5027 단독 실행 결과','',
         f"{now:%Y-%m-%d %H:%M:%S} KST 기준 {phase}. 슬롯 {len(slots)}건 중 전송 전 실패 {len(before)}건, "
         f"최종 증빙 집계 {len(rows)}건, 상품·방식 검증 통과 {len(valid)}건이다. "
         + link('단독 실행 원장',SOURCE),'',
         f"운영 종료 예정은 {cutoff:%H:%M} KST, 바운티 마감은 {previous.DEADLINE:%H:%M} KST다. "
         "AI Synthesis에서 판매처 429가 확인되면 다음 슬롯부터 Mercantile을 쓴다. "
         "정상 종료 후 최소 45초, 출력이 0토큰인 Cerebras 429 종료 후 최소 15초를 기다린다.",'']
    for title, pool, base_id, label, threshold in [
            ('유효 평균 TPS', valid, previous.BASE_ID,'D5027',baseline),
            ('전 구간 영상이 있는 유효 평균 TPS',full,previous.BASE_VIDEO_ID,'D5009',film_base)]:
        _, base_manifest = seals(base_id)
        reference = link(label, base_manifest or RUNS/base_id/'evidence.json')
        result = '이번 캠페인에서 해당하는 세션은 아직 없다.'
        if pool:
            top = max(pool,key=lambda r:r['mean_tps'])
            result = f"이번 최고는 {link('D'+str(top['number']),top['video'] if pool is full else top['ep'])} {fmt(top['mean_tps'],2)} TPS다."
        s.append(f"- **{title}** · {result} 기존 {reference} {fmt(threshold,2)} TPS 초과 {sum(r['mean_tps']>threshold for r in pool)}건.")
    s.extend([f"- 1,500 TPS 초과는 {sum(r['mean_tps']>1500 for r in valid)}건이다. 두 기준과 목표는 반올림 전 세션 평균으로 판정한다.",''])
    if state.get('stopped'):
        stop = datetime.fromisoformat(state['stopped'])
        s.extend([f"감독기 종료 {clock_time(state['stopped'])} KST. 운영 종료 시각 이내 {'예' if stop<=cutoff else '아니오'}, "
                  f"바운티 마감 이내 {'예' if stop<=previous.DEADLINE else '아니오'}.",''])
    if rows:
        late = sum(datetime.fromisoformat(r['ended_kst'])>cutoff for r in rows)
        past = sum(datetime.fromisoformat(r['ended_kst'])>previous.DEADLINE for r in rows)
        s.extend([f"세션 종료 기준 운영 종료 시각 이후 {late}건, 바운티 마감 이후 {past}건.",''])
    fallback = state.get('fallback_from')
    b_count = sum(sl['arm']==previous.MERC for sl in slots)
    s += [f"판매처 전환 계기 {fallback.split('-')[0] if fallback else '없음'}. Mercantile 배정 {b_count}건. "
          f"0토큰 429 확정 {sum(rec.get('zero_token_429') is True for rec in receipt_by_number.values())}건.",'',
          '## 실행별 점수','',
          '모델 호출은 오류를 포함한 총 호출 수이며, 괄호는 서버 생성 시간이 측정된 호출 수다. '
          '상품은 검증한 상세 페이지 수다. 전송 전 실패는 별도로 기재한다.','',
          *previous.table(['실행','판매처','종료 KST','소요 초','모델 호출 (측정)','첫 TPS','최종 TPS','평균 TPS','상품','방식','유효','전체 영상','증빙 봉인'])]
    for r in rows:
        e = read(r['ep'])
        value = fmt(r['mean_tps'],2) + (' (부분)' if r['mean_is_partial'] else '')
        s.append(previous.line([link('D'+str(r['number']),r['ep']), 'AI Synthesis' if r['arm']=='A' else 'Mercantile',
            clock_time(r['ended_kst']),fmt(r['elapsed_s'],2), f"{len(e['calls'])} ({len(r['calls'])})",fmt(r['first_tps'],2),
            fmt(r['final_tps'],2),value,f"{r['detail_pages_verified']}/5",yes(r['method_valid']),yes(r['valid']),
            link('보존',r['video']) if r['video'] else '미보존',link('검증본',r['manifest']) if r['manifest'] else '미확인']))
    for sl in slots:
        if sl['number'] in by_number:
            continue
        if sl.get('result') == 'presend_failure':
            p = RUNS/sl['id']/'preflight.json'
            cause = read(p).get('cause_class','원인 미기록') if p.exists() else '증빙 대기'
            s += ['',f"- 전송 전 실패 {link('D'+str(sl['number']),p)} · {cause}."]
        else:
            s += ['',f"- D{sl['number']} 최종 증빙 대기."]
    s += ['','## 429와 중계 시도','',
        '중계 전송은 모델 요청별 최초 전송과 재전송을 더한 횟수다. 모델 요청 순서대로 표기한다. '
        'Cerebras 429는 중계 재시도 중 수신한 응답을 포함하며, rate_limited는 실행 원장의 종료 지표다. '
        +link('중계 로그',previous.CACHE/'relay/logs/requests.jsonl'),'',
        *previous.table(['실행','context_clean','rate_limited','중계 전송/모델 요청','Cerebras 429','0토큰 429','판매처 조회 429','상세 429','다음 최소 대기 초'])]
    for sl in closed:
        r = by_number.get(sl['number'])
        if not r:
            continue
        rec = receipt_by_number[sl['number']]
        logs = sorted(upstream[r['id']],key=lambda x:x['at_ms'])
        attempts = [str(len(log['attempts'])+1) if isinstance(log.get('attempts'),list) else '미확인' for log in logs]
        s.append(previous.line([f"D{r['number']}",yes(r['context_clean']),yes(r['rate_limited']),
             ' + '.join(attempts) or '—',fmt(rec.get('cerebras_429_count')),yes(rec.get('zero_token_429')),
             fmt(rec.get('lookup_429_count')),fmt(rec.get('detail_429_count')),fmt(sl.get('cooldown'))]))
    s += ['','## 앞선 교대 실험과 진단','',
          'D5128·D5129 교대 실행과 D5108 본문 재전송 진단은 별도 원장에 집계했다. '
          +link('45초 교대 실험 및 진단 결과',previous.REPORT)]
    return '\n'.join(s)+'\n'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--stdout',action='store_true')
    args = parser.parse_args()
    if not SOURCE.is_file():
        print('단독 캠페인 원장 생성 대기.')
        return
    result = build(read(SOURCE))
    if args.stdout:
        print(result,end='')
        return
    with tempfile.NamedTemporaryFile(mode='w',encoding='utf-8',dir=REPORT.parent,prefix='.d5027-pure-',delete=False) as f:
        f.write(result)
        tmp = Path(f.name)
    tmp.replace(REPORT)
    print(REPORT)


if __name__ == '__main__':
    main()
