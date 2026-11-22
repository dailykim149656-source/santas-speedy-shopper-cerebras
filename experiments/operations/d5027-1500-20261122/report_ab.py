"""Render the fixed first-required paired comparison from the allocation ledger."""
import json
from statistics import median


def fmt(val):
    return '—' if val is None else f'{val:,.2f}'


def section(base, runs):
    path = base / 'required-ab-state.json'
    lines = ['', '## 첫 요청 도구 선택 방식 비교', '',
             '[실행 수와 사전 판정 기준](<첫 호출 required 교차 비교.md>)']
    if not path.exists():
        return lines + ['', '30초·60초 비교가 종료된 후 새 중계 버전에서 시작한다.']
    state = json.loads(path.read_bytes())
    by_id = {run['id']: run for run in runs}
    entries = state['assignments']
    done = [e for e in entries if e['phase'] == 'complete']
    lines += ['', f"기록된 전송 결과 {len(done)}/최대 4회. 순서는 AB, BA이며 A는 auto, B는 첫 요청만 required다. 두 B가 모두 실패하면 3회에서 끝난다.",
              '', '| 쌍 | 순서 | A 실행·평균 | B 실행·평균 | B−A 첫 TPS | B−A 최종 TPS | B−A 세션 TPS |',
              '|---:|---|---|---|---:|---:|---:|']
    for pair_id in sorted({e['pair'] for e in entries}):
        assigned = [e for e in entries if e['pair'] == pair_id]
        data = {e['arm']: by_id[e['outcome']['run_id']] for e in assigned if e['phase'] == 'complete'}
        def cell(arm):
            if arm in data:
                row = data[arm]
                suffix = fmt(row['score']) if row['valid'] else ('429 종료' if row['rate_limited'] else '무효')
                return f"[{row['label']}](<speed-bounty-evidence-test/runs/{row['id']}/evidence.json>) {suffix}"
            return '진행 중' if any(e['arm']==arm for e in assigned) else '—'
        paired = len(data) == 2 and all(r['valid'] for r in data.values())
        diffs = [data['B'][k] - data['A'][k] if paired else None for k in ('first','final','score')]
        lines.append(f"| {pair_id} | {''.join(e['arm'] for e in assigned)} | {cell('A')} | {cell('B')} | "+
                     ' | '.join(fmt(d) for d in diffs)+' |')
    for stage, title in [('screening','탐색'),('confirmation','재확인')]:
        decision=state.get(stage)
        if decision:
            valid=decision['valid_counts']
            lines += ['', f"{title} 결과는 유효 A {valid['A']}회·B {valid['B']}회, 완전한 쌍 {decision['valid_pairs']}개다. "+
                      f"세션 평균 B 승리는 {decision['session_wins_B']}쌍, 첫 TPS B 승리는 {decision['first_wins_B']}쌍이며 "+
                      f"쌍별 세션 차이 중앙값은 {fmt(decision['median_paired_session_gain'])} TPS다. "+
                      ('사용자 요청대로 소수 표본의 관측 결과로 마무리했다.' if state.get('reduced_cap') else ('사전 기준 통과.' if decision['pass'] else '사전 기준 미충족.'))]
    lines += ['', f'[배정·본문 검산 원장](<{path}>)']
    return lines
