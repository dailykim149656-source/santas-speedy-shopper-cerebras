"""Regenerate the Korean report from the campaign journal and completed evidence."""
import os
import argparse
from collections import defaultdict
from datetime import datetime
import importlib.util
import json
from pathlib import Path
import sqlite3
from statistics import mean, median
import sys
import tempfile
from zoneinfo import ZoneInfo

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
CACHE = HERE.parent
PROJECT = Path(os.environ.get("BOUNTY_PROJECT_ROOT", Path.cwd().parent))
REPORT = PROJECT / '45초 교대 실험 결과 - 2026-11-23.md'
DB = CACHE.parent / 'shopper-test/agents/main/agent/openclaw-agent.sqlite'
DEADLINE = datetime(2026, 11, 23, 3, 0, tzinfo=ZoneInfo('Asia/Seoul'))
CONTROL = 'synth-five-categories-cap'
MERC = 'mercantile-five-categories-cap'
BASE_ID = 'cd75e5e0-be7c-471f-a9ab-c9e6f0d1bd77'
BASE_VIDEO_ID = 'a9530b69-3aed-4ea9-8fd9-9ee1fcb36b51'
spec = importlib.util.spec_from_file_location('shopper_metrics', CACHE / 'mercantile-abba-d5124/summarize.py')
metrics = importlib.util.module_from_spec(spec)
spec.loader.exec_module(metrics)
read = metrics.read


def fmt(value, decimals=0):
    return '—' if value is None else f'{value:,.{decimals}f}'


def arm_name(variant):
    return {CONTROL: 'A', MERC: 'B', 'A': 'A', 'B': 'B'}.get(variant, str(variant))


def score(ident):
    return read(metrics.REPO / 'runs' / ident / 'evidence.json')['score']['mean_exact_tps']


def call_detail(raw, db, message):
    usage = message.get('usage') or {}
    response_id = message.get('responseId')
    match = db.execute("""SELECT json_extract(event_json, '$.message.usage') FROM transcript_events
        WHERE session_id=? AND json_extract(event_json,'$.message.responseId')=?""",
        (raw['history']['sessionId'], response_id)).fetchall()
    reasoning = None
    if len(match) == 1 and match[0][0]:
        tx = json.loads(match[0][0])
        if all(tx.get(k) == usage.get(k) for k in ('output', 'input', 'cacheRead')):
            reasoning = tx.get('reasoningTokens')
    chars = sum(len(p.get('thinking') or '') for p in message.get('content') or []
                if isinstance(p,dict) and p.get('type') == 'thinking')
    return {'chars': chars, 'reasoning': reasoning, 'output': usage.get('output'),
            'cache': usage.get('cacheRead'), 'input': usage.get('input')}


def collect(campaign):
    iterations = metrics.lines(CACHE / 'iterations.jsonl')
    by_label = {r['label']: r for r in iterations}
    by_id = {r['id']: r for r in iterations}
    relay = defaultdict(list)
    for row in metrics.lines(CACHE / 'relay/logs/requests.jsonl'):
        relay[row.get('run_id')].append(row)
    rows, pending = [], []
    previous = None
    db = sqlite3.connect(DB.as_uri()+'?mode=ro', uri=True, timeout=3)
    try:
        for n, slot in enumerate(campaign['slots'],1):
            variant = {'A':CONTROL, 'B':MERC}.get(slot['arm'],slot['arm'])
            label = f"D{slot['number']}-{variant}"
            item = by_id.get(slot.get('id')) or by_label.get(label)
            if not item:
                pending.append((slot['number'],arm_name(variant),slot.get('result') or slot.get('phase') or '원장 결과 대기'))
                previous = None
                continue
            ident = item['id']
            ep = metrics.REPO / 'runs' / ident / 'evidence.json'
            if not ep.is_file() or not (metrics.RAW / (ident+'.json')).is_file():
                pending.append((slot['number'],arm_name(variant),'최종 증빙 대기'))
                previous = None
                continue
            e = read(ep)
            row = metrics.summary({'slot':n},item,relay[ident],previous)
            raw = read(metrics.RAW/(ident+'.json'))
            calls = [m for m in raw['history']['messages'] if m.get('role')=='assistant'
                     and (m.get('__openclaw') or {}).get('runId')==ident and m.get('serverGeneration')]
            row['first_detail'] = call_detail(raw,db,calls[0]) if calls and calls[0].get('stopReason')=='toolUse' else {}
            row['final_detail'] = call_detail(raw,db,calls[-1]) if calls and calls[-1].get('stopReason')=='stop' else {}
            row['number'] = slot['number']
            row['arm'] = arm_name(variant)
            row['media'] = (e['evidence_status']=='complete' and e.get('media',{}).get('attestation',{}).get('full_run') is True
                            and (ep.parent/'original.mp4').is_file() and (ep.parent/'demo.mp4').is_file())
            row['ep'] = ep
            previous = e['ended']['time']
            rows.append(row)
    finally:
        db.close()
    return rows, pending


def table(header):
    return ['| '+' | '.join(header)+' |','|'+'|'.join('---' for _ in header)+'|']


def line(cols):
    return '| '+' | '.join(str(x) for x in cols)+' |'


def build(campaign):
    rows, pending = collect(campaign)
    valid = [r for r in rows if r['valid'] and r['mean_tps'] is not None]
    record, filmed = score(BASE_ID), score(BASE_VIDEO_ID)
    latest = datetime.now(DEADLINE.tzinfo).isoformat(timespec='seconds')
    s=['# 45초 간격 D5027·Mercantile 교대 결과','',
       f"집계 시각 {latest[:10]} {latest[11:19]} KST. 예약 {len(campaign['slots'])}슬롯, 최종 증빙 {len(rows)}건, 상품과 방식 검증을 모두 통과한 세션 {len(valid)}건. "
       f"[교대 실행 원장](<{HERE/'campaign.json'}>) · [중계 요청 기록](<{CACHE/'relay/logs/requests.jsonl'}>)",'']
    if campaign.get('owner') == HERE.name:
        s.extend([f"기준은 [D5027](<{metrics.REPO/'runs'/BASE_ID/'evidence.json'}>) {fmt(record,2)} TPS다. "
                  f"AI Synthesis(A)와 Mercantile(B)을 교대로 실행하고, 직전 세션 종료 후 {campaign['cadence_seconds']}초 이상 대기한다.",''])
    if valid:
        high=max(valid,key=lambda r:r['mean_tps'])
        filmed_now=[r for r in valid if r['media']]
        s.append(f"이번 최고는 [D{high['number']}](<{high['ep']}>) {fmt(high['mean_tps'],2)} TPS다. "
                 f"기존 D5027({fmt(record,2)}) 초과 {sum(r['mean_tps']>record for r in valid)}건, 1,500 초과 {sum(r['mean_tps']>1500 for r in valid)}건이다.")
        if filmed_now:
            best=max(filmed_now,key=lambda r:r['mean_tps'])
            s.append(f"전체 영상과 데모를 보유한 이번 최고는 [D{best['number']} 영상](<{best['ep'].parent/'demo.mp4'}>) {fmt(best['mean_tps'],2)} TPS다. 기존 전체 녹화 최고 D5009는 {fmt(filmed,2)} TPS였다.")
        else:
            s.append(f"기존 전 구간 녹화 최고 D5009는 {fmt(filmed,2)} TPS다. 이번 캠페인에서 검증을 통과해 원본과 데모가 보존된 전 구간 영상은 0건이다.")
        s.append('')
    stop=campaign.get('stopped') or campaign.get('ended_at')
    if isinstance(stop,str):
        t=datetime.fromisoformat(stop.replace('Z','+00:00')).astimezone(DEADLINE.tzinfo)
        s.extend([f"감독기 종료 {t.strftime('%H:%M:%S')} KST · 03:00 마감 전 종료 {'예' if t<=DEADLINE else '아니오'}.",''])
    if rows:
        late=sum(datetime.fromisoformat(r['ended_kst'])>DEADLINE for r in rows)
        s.extend([f"세션 종료 시각 기준 마감 이내 {len(rows)-late}건, 마감 이후 {late}건.",''])
    s+=['## 판매처별 집계','',*table(['판매처','완료','유효','세션 평균 TPS','세션 최고 TPS','최종 표시 추론 0자/유효','판매처 조회 429','Cerebras 429','유효 세션 소요 중앙값'])]
    for a, name in [('A','A · AI Synthesis'),('B','B · Mercantile')]:
        rr=[r for r in rows if r['arm']==a];v=[r for r in valid if r['arm']==a]
        ts=[r['mean_tps'] for r in v]; finalized=[r for r in v if 'chars' in r['final_detail']]
        s.append(line([name,len(rr),len(v),fmt(mean(ts),2) if ts else '—',fmt(max(ts),2) if ts else '—',
                       f"{sum(r['final_detail']['chars']==0 for r in finalized)}/{len(finalized)}",
                       sum(r['lookup_429'] for r in rr),
                       sum(r['cerebras_429'] for r in rr) if all(r['cerebras_429'] is not None for r in rr) else '미확인',
                       fmt(median(r['elapsed_s'] for r in v),2)+'초' if v else '—']))
    s+=['','## 실행별 점수와 완료','',
        '대기는 직전 캠페인 세션 종료부터 이번 전송 시작까지의 실측 초다. 세션 소요는 전송에서 최종 이벤트까지다. 실패한 세션에서 일부 호출만 측정된 평균은 괄호에 부분값으로 표시하며 유효 평균 집계에서 제외한다.','',
        *table(['실행','군','완료 KST','대기 초','소요 초','첫 TPS','최종 TPS','세션 평균 TPS','모델 호출','검증 상품','방식','조회 429','Cerebras 429'])]
    for r in rows:
        s.append(line([f"[D{r['number']}](<{r['ep']}>)",r['arm'],r['ended_kst'][11:19],fmt(r['prior_end_gap_s'],2),
                       fmt(r['elapsed_s'],2),fmt(r['first_tps'],2),fmt(r['final_tps'],2),
                       fmt(r['mean_tps'],2)+(' (부분)' if r['mean_is_partial'] else ''),len(r['calls']),
                       f"{r['detail_pages_verified']}/5",'통과' if r['method_valid'] else '미통과',r['lookup_429'],fmt(r['cerebras_429'])]))
    if pending:
        s+=['','최종 증빙 대기 또는 전송 전 중단 슬롯. '+', '.join(f'D{i} ({a}, {cause})' for i,a,cause in pending)+'.']
    s+=['','## 호출별 추론량과 출력','',
        '추론 글자 수는 원본의 표시 추론 블록 길이이며 추론 토큰은 모델 응답 ID에 연결된 전사 사용량이다. '
        f"캐시는 최종 호출에서 읽은 입력 토큰 수다. [세션 DB](<{DB}>) · [원본 보관소](<{metrics.RAW}>)",'',
        *table(['실행','첫 추론 글자','첫 추론 토큰','최종 추론 글자','최종 추론 토큰','최종 총 출력 토큰','최종 미캐시 입력','최종 캐시 읽기'])]
    for r in rows:
        f,l=r['first_detail'],r['final_detail']
        s.append(line([f"D{r['number']}",fmt(f.get('chars')),fmt(f.get('reasoning')),fmt(l.get('chars')),
                       fmt(l.get('reasoning')),fmt(l.get('output')),fmt(l.get('input')),fmt(l.get('cache'))]))
    if campaign.get('owner') == HERE.name:
        results=[read(p) for p in sorted(HERE.glob('probe-??.result.json'))]
        s+=['','## 도구 선택 진단','',
            f"저장된 D5108 첫 요청 본문으로 auto·required를 비교한 별도 진단이며, 세션 TPS 집계에서 제외했다. "
            f"전송 시도 {sum(1 for _ in HERE.glob('probe-??.intent.json'))}/5회, 결과 {len(results)}/5건.",'',
            *table(['회차','도구 선택','HTTP','스트림 완료','추론 글자','추론 토큰','출력 토큰','TPS','도구 인자 일치'])]
        for p in results:
            match=p.get('tool_args_match')
            s.append(line([p['slot'],p['arm'],fmt(p.get('http')),'예' if p.get('stream_complete') else '아니오',
                           fmt(p.get('reasoning_chars')),fmt(p.get('reasoning_tokens')),fmt(p.get('output_tokens')),
                           fmt(p.get('tps'),2),'—' if match is None else '예' if match else '아니오']))
    return '\n'.join(s)+'\n'


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--stdout',action='store_true')
    parser.add_argument('--journal',type=Path,default=HERE/'campaign.json',help='journal used for offline readback checks')
    args=parser.parse_args()
    report=build(read(args.journal))
    if args.stdout:
        print(report,end='')
        return
    with tempfile.NamedTemporaryFile(mode='w',encoding='utf-8',dir=REPORT.parent,prefix='.merchant45-',delete=False) as f:
        f.write(report)
        staged=Path(f.name)
    staged.replace(REPORT)
    print(REPORT)

if __name__=='__main__':
    main()
