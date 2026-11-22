"""Render campaign rates, validated records, and pending shopping sessions from local receipts."""
import os
import argparse
from collections import defaultdict
from datetime import datetime
import json
import re
from pathlib import Path
from statistics import median
from tempfile import NamedTemporaryFile
from zoneinfo import ZoneInfo

FAST = Path(__file__).resolve().parent
CACHE = FAST.parent
PURE = CACHE / 'd5027-pure-0235'
ORIGINAL = CACHE / 'd5027-original-0235'
FAST2 = CACHE / 'd5027-fast2-0235'
ACCELERATED = {FAST, FAST2}
PROJECT = Path(os.environ.get("BOUNTY_PROJECT_ROOT", Path.cwd().parent))
RUNS = PROJECT / 'speed-bounty-evidence-test' / 'runs'
RAW = Path.home() / 'Library/Application Support/Cerebras Speed Bounty/2026-11-22/raw-test'
TARGET = PROJECT / 'D5027 가속 실행 결과 - 2026-11-23.md'
FINAL_REPORT = PROJECT / 'D5027 최종 실행 결과 - 2026-11-23.md'
TZ = ZoneInfo('Asia/Seoul')


def read(path):
    return json.loads(path.read_bytes())


def lines(path):
    with path.open('rb') as stream:
        return [json.loads(line) for line in stream if line.endswith(b'\n') and line.strip()]


def fmt(num):
    return '—' if num is None else f'{num:,.2f}'


def link(label, file):
    return f'[{label}](<{file}>)'


def table(values):
    return '| ' + ' | '.join(str(v) for v in values) + ' |'


def time_text(stamp):
    return datetime.fromisoformat(stamp).astimezone(TZ).strftime('%H:%M:%S')


def snapshots(directory, data, history, gateway):
    result = []
    for slot in data['slots']:
        number = slot['number']
        label = f"D{number}-{slot['arm']}"
        ident = slot.get('id')
        session = CACHE / 'runs' / (label + '.session.json')
        if ident is None and session.is_file():
            ident = read(session)['id']
        logs = gateway.get(ident, [])
        received = {r['at_ms'] for r in logs}
        if ident is not None and not slot.get('result'):
            for saved in (CACHE/'relay/logs'/ident).glob('*.json'):
                stamp = re.fullmatch(r'(\d+)-[0-9a-f]{12}\.json', saved.name)
                if stamp:
                    received.add(int(stamp[1]))

        queue = FAST / 'pending' / (str(ident) + '.json')
        closed = FAST / 'finalized' / (str(ident) + '.json')
        accelerated = directory in ACCELERATED
        queue_data = read(queue) if accelerated and queue.is_file() else {}
        closed_data = read(closed) if accelerated and closed.is_file() else {}
        if any(item.get('id') != ident for item in (queue_data, closed_data) if item):
            raise ValueError(f'{label} 가속 큐 영수증 ID 불일치')
        ep = RUNS / str(ident) / 'evidence.json'
        evidence = read(ep) if ep.is_file() else {}
        row = history.get(ident, {})
        if row and row['label'] != label:
            raise ValueError(f'{label} 원장 ID 불일치')
        if evidence and evidence['id'] != ident:
            raise ValueError(f'{label} 증빙 ID 불일치')
        if evidence and row and evidence['validation']['valid'] != row['valid']:
            raise ValueError(f'{label} 검증 판정 불일치')
        valid = bool(evidence and row.get('valid') is True and row.get('method_valid') is True
                     and len(evidence['products']) == 5 and all(p.get('verified') is True for p in evidence['products']))
        verified = bool(row and evidence)
        deferred = accelerated and bool(queue_data or closed_data or slot.get('validation_deferred'))
        rawfile = RAW / (str(ident) + '.json')
        source = read(rawfile) if rawfile.is_file() else {}
        started_ms = source.get('startedWall')
        pending_send = CACHE/'runs'/(label+'.pending.json')
        if started_ms is None and received:
            try:
                in_flight = read(pending_send)
            except FileNotFoundError:
                in_flight = {}
            if in_flight.get('id') == ident and in_flight.get('label') == label:
                started_ms = in_flight.get('startedWall')

        speakers = [m for m in source.get('history',{}).get('messages',[])
                    if m.get('role') == 'assistant' and m.get('__openclaw',{}).get('runId') == ident]
        first, last = (speakers[0], speakers[-1]) if speakers else ({},{})
        def sample(m):
            timing = m.get('serverGeneration') or {}
            n, ms = timing.get('outputTokens'), timing.get('completionMs')
            return n / (ms / 1000) if n and ms and ms > 0 else None
        final = last.get('stopReason') == 'stop' and sample(last) is not None
        chars = sum(len(b.get('thinking') or '') for b in last.get('content') or []
                    if isinstance(b,dict) and b.get('type') == 'thinking') if final else None
        output = (last.get('serverGeneration') or {}).get('outputTokens') if final else None
        sent = bool(received or verified or source.get('startedWall') or queue_data)
        rec = slot.get('receipt', {})
        provider = sum((r.get('status') == 429) + sum(a.get('status')==429 for a in r.get('attempts',[])) for r in logs)
        details = sum(p.get('http') == 429 for p in evidence['products']) if verified else None
        if slot.get('result')=='presend_failure':
            status = '전송 전 실패'
        elif verified:
            status = ('후검증 ' if deferred else '즉시 검증 ') + ('통과' if valid else '무효')
        elif deferred:
            status = '상세 검증 대기'
        else:
            status = '기록 대기'
        score = row.get('score') if verified else queue_data.get('score',slot.get('score'))
        public_media = (ep.parent / 'original.mp4').is_file() and (ep.parent / 'demo.mp4').is_file()
        full = evidence.get('media',{}).get('attestation',{}).get('full_run') is True and public_media
        for manifest in (directory/'sealed'/str(ident)).glob('*/manifest.json'):
            m = read(manifest)
            if (m.get('complete_full_run') is True and m.get('verification',{}).get('verified_products')==5
                    and m.get('verification',{}).get('raw_digest_checked') is True
                    and all((manifest.parent / n).is_file() for n in ('original.mp4','demo.mp4'))):
                full = True
        result.append(dict(number=number, ident=ident, label=label, status=status, sent=sent, verified=verified,
                           pending=deferred and not verified, deferred=deferred, valid=valid, final=final, chars=chars,
                           output=output, score=score, first=sample(first) if first.get('stopReason')=='toolUse' else None,
                           last=sample(last) if final else None, http=provider, lookup=rec.get('lookup_429_count'),
                           details=details, zero=rec.get('zero_token_429') is True, recording=bool(full),
                           merchant_429=rec.get('merchant_429') is True,
                           first_model_ms=min(received, default=None),
                           last_model_ms=max(received, default=None),
                           cooldown=slot.get('cooldown'), started_ms=started_ms,
                           ended_ms=(source.get('ended') or {}).get('time'), dispatch=slot['dispatch'],
                           products=sum(p.get('verified') is True for p in evidence.get('products',[])) if verified else None,
                           ref=ep if ep.is_file() else closed if closed_data else queue if queue_data else directory/'campaign.json'))
    return result


def first_gap(directory, predecessor):
    if directory in ACCELERATED:
        return 90 if predecessor['merchant_429'] else 5 if predecessor['zero'] else 15
    return 15 if predecessor['zero'] else 45


def render(now, combined=False):
    history = {r['id']:r for r in lines(CACHE/'iterations.jsonl')}
    relay = defaultdict(list)
    for request in lines(CACHE/'relay/logs/requests.jsonl'):
        relay[request.get('run_id')].append(request)
    campaigns = []
    stages = [('기존 단독',PURE),('가속 단독',FAST),('45초·15초 복귀',ORIGINAL),('가속 재개',FAST2)]
    for name,directory in stages:
        p = directory/'campaign.json'
        if not p.is_file():
            continue
        state = read(p)
        snapshots_for_stage = snapshots(directory,state,history,relay)
        start = datetime.fromisoformat(state['started'])
        end = datetime.fromisoformat(state['stopped']) if state.get('stopped') else now
        hours = (min(end,datetime.fromisoformat(state['deadline']))-start).total_seconds()/3600
        campaigns.append((name,state,snapshots_for_stage,hours,p))
    prior = previous_stage = None
    for name,_,rows,_,path in campaigns:
        for r in rows:
            r['stage_name'] = name
            r['applied_gap'] = None
            r['prior_model_gap'] = None
            if prior and r['number'] == prior['number'] + 1:
                r['applied_gap'] = prior['cooldown'] if previous_stage == path.parent else first_gap(path.parent, prior)
                if prior['last_model_ms'] is not None and r['first_model_ms'] is not None:
                    r['prior_model_gap'] = (r['first_model_ms']-prior['last_model_ms']) / 1000
            prior,previous_stage = r,path.parent

    title = '# D5027 최종 실행 결과' if combined else '# D5027 가속 실행 결과'
    output = [title,'',f'{now:%Y-%m-%d %H:%M:%S} KST 집계. 운영 종료는 02:35 KST, 바운티 마감은 03:00 KST다.','',
              '## 캠페인별 처리량','',
              '경과 시간은 감독기 시작부터 중지 또는 집계 시각까지이며 02:35에서 자른다. 전송은 해당 실행의 모델 중계 요청 또는 종료 원본이 확인된 세션 수다. 검증 통과는 상세 상품 5개, 조회별 상품 일치 및 방식 검증을 모두 통과한 세션 수다. 미검증 점수는 최고 기록과 유효 완료율에서 제외한다.','',
              table(['원장','슬롯','전송','확정 유효','확정 무효','검증 대기','경과 분','전송/시간','유효/시간','유효 TPS 중앙값','유효 최고 TPS']),
              table(['---']*11)]
    for name,state,rows,hours,p in campaigns:
        sent = sum(r['sent'] for r in rows)
        valid = [r for r in rows if r['valid']]
        scores = [r['score'] for r in valid if r['score'] is not None]
        peak = max(valid,key=lambda r:r['score']) if scores else None
        output.append(table([link(name,p),len(rows),sent,len(valid),sum(r['verified'] and not r['valid'] for r in rows),
                            sum(r['pending'] for r in rows),fmt(hours*60),fmt(sent/hours if hours>0 else None),
                            fmt(len(valid)/hours if hours>0 else None),fmt(median(scores) if scores else None),
                            f"D{peak['number']} · {fmt(peak['score'])}" if peak else '—']))
    availability = {p.parent for _,_,_,_,p in campaigns}
    for name,directory in stages:
        if directory not in availability:
            output += ['', f'{name} 단계는 캠페인 원장 생성 대기 중이다.']
    if campaigns:
        output += ['', '## 단계별 대기와 상품 검증', '',
                   '실제 대기는 직전 세션의 종료부터 다음 세션이 chat.send를 시작하기까지다. 두 시각 모두 원본에서 읽었다. 동일 단계의 연속 두 세션만 사용하며 단계 간 첫 전송은 별도 표기한다. 가속 단계에서만 1,300 TPS 미만의 상품 상세 검증을 미룬다.', '',
                   table(['단계','예정 최소 대기 초','단계 내 실제 대기 중앙값 초 (범위, 표본)','단계 전환 후 첫 전송 대기 초','즉시 검증','사후 검증 완료','상세 검증 대기']),
                   table(['---'] * 7)]
        previous_end = None
        for name,_,rows,_,p in campaigns:
            intervals = [(r['started_ms'] - prior['ended_ms']) / 1000
                         for prior,r in zip(rows,rows[1:])
                         if prior['ended_ms'] is not None and r['started_ms'] is not None]
            if any(t < 0 for t in intervals):
                raise ValueError('동일 단계의 전송 간격 중첩')
            direction = (rows[0]['started_ms'] - previous_end) / 1000 if rows and rows[0]['started_ms'] is not None and previous_end is not None else None
            interval = f"{fmt(median(intervals))} ({fmt(min(intervals))}~{fmt(max(intervals))}, {len(intervals)}쌍)" if intervals else '—'
            timing = '15 / 5 / 판매처 429 후 90' if p.parent in ACCELERATED else '45 / 0토큰 429 후 15'
            immediate = sum(r['verified'] and not r['deferred'] for r in rows)
            delayed = sum(r['verified'] and r['deferred'] for r in rows)
            output.append(table([name,timing,interval,fmt(direction),immediate,delayed,sum(r['pending'] for r in rows)]))
            if rows:
                previous_end = rows[-1]['ended_ms']
        output += ['', '같은 단계에서 직전 슬롯의 예정 대기별로 관측한 실제 대기는 다음과 같다.', '',
                   table(['단계','직전 슬롯 예정 대기 초','연속 실행 쌍','실제 대기 중앙값 초','최소~최대 초']),table(['---']*5)]
        for name,_,rows,_,_ in campaigns:
            by_gap = defaultdict(list)
            for previous,current in zip(rows,rows[1:]):
                if previous['cooldown'] is not None and previous['ended_ms'] is not None and current['started_ms'] is not None:
                    by_gap[previous['cooldown']].append((current['started_ms']-previous['ended_ms'])/1000)
            for seconds,gaps in sorted(by_gap.items()):
                output.append(table([name,seconds,len(gaps),fmt(median(gaps)),f"{fmt(min(gaps))}~{fmt(max(gaps))}"]))
        output += ['', '아래 표의 예정 대기는 새 단계가 적용하는 값이다. 모델 요청 간격은 중계가 요청 본문 전체를 받은 시각으로 계산하며, Cerebras 도착 시각과는 차이가 있을 수 있다.', '',
                   table(['전환','실행','적용 대기 초','직전 종료 → chat.send 초','직전 종료 → 첫 모델 요청 초','전 세션 마지막 → 다음 첫 모델 요청 초','첫 모델 요청 → 다음 세션 첫 모델 요청 초']),table(['---']*7)]
        for before,after in zip(campaigns,campaigns[1:]):
            old_name,_,old_rows,_,_ = before
            new_name,_,new_rows,_,path = after
            if not old_rows or not new_rows:
                continue
            old, new = old_rows[-1],new_rows[0]
            if new['number'] != old['number'] + 1:
                continue
            # The receiving controller computes the first delay at handoff.
            planned = first_gap(path.parent, old)
            def difference(before_ms, after_ms):
                return fmt((after_ms-before_ms)/1000) if before_ms is not None and after_ms is not None else '—'
            output.append(table([old_name+' → '+new_name, f"D{old['number']} → D{new['number']}", planned,
                                 difference(old['ended_ms'],new['started_ms']),difference(old['ended_ms'],new['first_model_ms']),
                                 difference(old['last_model_ms'],new['first_model_ms']),difference(old['first_model_ms'],new['first_model_ms'])]))
    output += ['','## 최종 응답과 429','',
               '추론 0자·출력 161토큰은 성공한 최종 호출을 기준으로 집계한다. 상품 검증을 마친 유효 세션과 상세 검증 대기 세션을 각각 표시한다. Cerebras 429는 중계 재시도를 포함한 HTTP 응답 수다. 판매처 429는 조회 중 관측된 응답과 상품 상세 검증의 마지막 HTTP 상태를 따로 센다.','',
               table(['캠페인','추론 0자·161토큰 / 유효 최종','추론 0자·161토큰 / 검증 대기 최종','Cerebras 429','확정 0토큰 429 세션','판매처 조회 429','상세 429 / 상세 판정 완료 세션','1,500 초과','전체 영상 있는 유효 최고 TPS']),table(['---']*9)]
    for name,_,rows,_,_ in campaigns:
        finals = [r for r in rows if r['valid'] and r['final']]
        zero = sum(r['chars']==0 and r['output']==161 for r in finals)
        unverified = [r for r in rows if r['pending'] and r['final']]
        pending_zero = sum(r['chars']==0 and r['output']==161 for r in unverified)
        filmed = [r for r in rows if r['valid'] and r['recording']]
        best = max(filmed,key=lambda r:r['score']) if filmed else None
        output.append(table([name,f'{zero}/{len(finals)}'+(f' ({100*zero/len(finals):.1f}%)' if finals else ''),
                             f'{pending_zero}/{len(unverified)}' if unverified else '—',
                             sum(r['http'] for r in rows), sum(r['zero'] for r in rows),
                             sum((r['lookup'] or 0) for r in rows), f"{sum((r['details'] or 0) for r in rows)} / {sum(r['details'] is not None for r in rows)}",
                             sum(r['valid'] and r['score']>1500 for r in rows),f"D{best['number']} · {fmt(best['score'])}" if best else '—']))
    fast_rows = [r for _,_,rows,_,p in campaigns if p.parent in ACCELERATED for r in rows]
    direct=[r for r in fast_rows if r['verified'] and not r['deferred']]
    delayed=[r for r in fast_rows if r['verified'] and r['deferred']]
    pending=[r for r in fast_rows if r['pending']]
    detail_rows = [r for _,_,rows,_,_ in campaigns for r in rows] if combined else fast_rows
    if combined:
        valid = [r for r in detail_rows if r['valid']]
        definitive = sum(r['verified'] for r in detail_rows)
        outstanding = sum(r['pending'] for r in detail_rows)
        output += ['', f"전체 합계는 전송 {sum(r['sent'] for r in detail_rows)}건, 검증 통과 {len(valid)}건, 검증 무효 {definitive-len(valid)}건, 사후 검증 대기 {outstanding}건이다."]
        if valid:
            best = max(valid,key=lambda r:r['score'])
            output += ['', f"전체 유효 최고는 {link('D'+str(best['number']),best['ref'])}의 {fmt(best['score'])} TPS다. 기존 D5027(1,354.66 TPS) 초과 {sum(r['score']>1354.6625976356386 for r in valid)}건, 1,500 TPS 초과 {sum(r['score']>1500 for r in valid)}건이다."]
    output += ['', '## 실행별 결과' if combined else '## 가속 실행별 결과','', 
               f'가속 단계에서 즉시 검증 {len(direct)}건, 사후 검증 완료 {len(delayed)}건, 상세 검증 대기 {len(pending)}건. 1,300 TPS 이상과 생성 토큰이 없는 종료는 즉시 검증 대상이다.','',
               table(['실행','단계','이번 전송의 예정 대기 초','직전 세션 마지막 → 이번 첫 모델 요청 초','판정','첫 TPS','최종 TPS','평균 TPS','상품','최종 추론 글자 / 출력 토큰','Cerebras 429','판매처 조회 / 상세 429']),table(['---']*12)]
    dash=lambda v: '—' if v is None else str(v)
    for r in detail_rows:
        output.append(table([link('D'+str(r['number']),r['ref']),r['stage_name'],dash(r['applied_gap']),fmt(r['prior_model_gap']),r['status'],fmt(r['first']),fmt(r['last']),fmt(r['score']),
                             f"{r['products']}/5" if r['verified'] else '대기',f"{dash(r['chars'])} / {dash(r['output'])}",
                             r['http'],f"{dash(r['lookup'])} / {dash(r['details'])}"]))
    output += ['',f"유효 기록 기준 D5027은 {link('1,354.66 TPS',RUNS/'cd75e5e0-be7c-471f-a9ab-c9e6f0d1bd77/evidence.json')}, 기존 전체 영상 기준 D5009는 {link('1,301.28 TPS',RUNS/'a9530b69-3aed-4ea9-8fd9-9ee1fcb36b51/evidence.json')}다.",
               '',link('기존 단독 실행별 결과',PROJECT/'D5027 단독 실행 결과 - 2026-11-23.md')+' · '+link('중계 HTTP 응답 원장',CACHE/'relay/logs/requests.jsonl')]
    return '\n'.join(output)+'\n'


if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--stdout',action='store_true')
    parser.add_argument('--combined',action='store_true',help='print the combined report when using --stdout')
    args=parser.parse_args()
    now = datetime.now(TZ)
    if args.stdout:
        print(render(now, combined=args.combined),end='')
    else:
        for file,combined in ((TARGET,False),(FINAL_REPORT,True)):
            with NamedTemporaryFile('w',encoding='utf-8',dir=PROJECT,prefix='.d5027-report-',delete=False) as f:
                f.write(render(now, combined))
            Path(f.name).replace(file)
            print(file)
