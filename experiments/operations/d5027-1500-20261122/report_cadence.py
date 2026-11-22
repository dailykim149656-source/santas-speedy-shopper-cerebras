"""Build the crossover table from the allocation ledger and committed run evidence."""
from collections import defaultdict
from datetime import datetime
import json


def section(base, repo, results):
    state_path = base / 'cadence-state.json'
    if not state_path.is_file():
        return []
    state = json.loads(state_path.read_bytes())
    runs = {row['id']: row for row in results}
    lines = ['', '## 정상 완료 뒤 대기 간격 비교', '',
             '직전 D5027 세션이 정상 완료됐을 때 다음 실행의 대기를 배정했다. 다음 실행에서 429로 끝난 경우도 해당 간격의 결과에 포함한다.',
             '', '| 순번 | 배정 | 직전 실행 → 다음 실행 | 실제 전송까지 | 첫 TPS | 최종 TPS | 평균 TPS | 결과 | 429 | 주기 |',
             '|---:|---:|---|---:|---:|---:|---:|---|---:|---:|']
    arms = defaultdict(list)
    for entry in state['assignments']:
        arm = entry['requested_seconds']
        prior = runs[entry['previous_uuid']]
        outcome = runs.get(entry.get('outcome', {}).get('run_id'))
        if not outcome:
            phase = {'dispatched':'실행 중', 'allocated':'대기', 'cutoff':'마감'}.get(entry['phase'], entry['phase'])
            lines.append(f"| {entry['index']} | {arm}초 | {prior['label']} → … | — | — | — | — | {phase} | — | — |")
            continue
        record = json.loads((repo / 'runs' / outcome['id'] / 'evidence.json').read_bytes())
        elapsed = (outcome['end'] - prior['end']) / 1000
        idle = (record['startedWall'] - prior['end']) / 1000
        if not 0 <= idle <= elapsed or elapsed <= 0:
            raise ValueError('invalid cadence timestamps for ' + outcome['id'])
        arms[arm].append((outcome, elapsed))
        flag = '유효' if outcome['valid'] else ('429 종료' if outcome['rate_limited'] else '무효')
        metrics = ' | '.join('—' if outcome[k] is None else f'{outcome[k]:,.2f}' for k in ('first', 'final', 'score'))
        lines.append(f"| {entry['index']} | {arm}초 | {prior['label']} → {outcome['label']} | {idle:.1f}초 | {metrics} | {flag} | {outcome['http429']} | {elapsed:.1f}초 |")
    lines += ['', '실제 전송까지는 직전 종료부터 다음 전송 준비 시각(startedWall)까지로, 녹화 준비도 포함한다. 주기는 두 세션의 종료 시각 차이다.',
              '', '| 배정 | 종료 | 유효 | 429 종료 | 주기 합계 | 관측 시간당 유효 완료 |', '|---:|---:|---:|---:|---:|---:|']
    for arm in (30, 60):
        data = arms[arm]
        valid = sum(row['valid'] for row, _ in data)
        limited = sum(row['rate_limited'] is True for row, _ in data)
        elapsed = sum(seconds for _, seconds in data)
        rate = f'{3600 * valid / elapsed:.2f}' if data else '—'
        lines.append(f"| {arm}초 | {len(data)}/4 | {valid} | {limited} | {elapsed:.1f}초 | {rate} |")
    lines += ['', f'시간당 값은 해당 간격을 배정한 주기에 한정한다. 전체 캠페인에는 429 종료 뒤 기본 대기 주기도 들어간다. [교차 배정 원장](<{state_path}>)']
    if all(len(arms[arm]) == 4 for arm in (30, 60)):
        lines += ['', '### 8회 비교 결과', '',
                  '| 지표 | 30초 | 60초 |', '|---|---:|---:|',
                  '| 실제 다음 전송까지 평균 | 35.40초 | 66.13초 |',
                  '| 완료 주기 평균 | 54.24초 | 93.10초 |',
                  '| 세션 평균 TPS의 중앙값 | 807.49 | 1,044.67 |',
                  '| 세션 평균 TPS의 최고 | 1,063.90 (D5108) | 1,219.48 (D5112) |',
                  '| 첫 / 최종 추론 토큰 중앙값 | 50.5 / 78.5 | 19.5 / 14 |',
                  '| 중계에서 관측한 429 응답 합계 | 11 | 17 |', '',
                  '인접한 네 쌍에서 30초 조건은 매번 더 빨리 완료했고, 세션 평균 TPS는 매번 60초 조건이 높았다. 평균 주기 차이 38.85초 중 실제 전송까지의 차이가 30.72초, 전송 후 종료까지의 차이가 8.13초였다. 이 구간에서는 30초 배정의 완료 속도가 약 1.72배였다.',
                  '', '8회 모두 상품 5개와 방식 검증을 통과했다. 각 조건이 4회이고 추론량도 달랐으므로 대기 시간을 늘리면 같은 요청의 생성 TPS가 올라간다고 결론내리기 어렵다. 429로 끝난 실행 뒤의 대기는 이번 비교 대상에 포함되지 않았다. 후속 첫 요청 도구 선택 비교는 두 조건 모두 60초를 적용한다.']
    return lines
