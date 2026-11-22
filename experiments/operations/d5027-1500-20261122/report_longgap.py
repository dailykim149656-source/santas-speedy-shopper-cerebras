"""Read the prospective 60/90 allocation ledger and summarize paired D5027 outcomes."""
from collections import defaultdict
import json
from statistics import median


def number(value, digits=2, signed=False):
    if value is None:
        return '—'
    return format(value, ('+' if signed else '') + ',.' + str(digits) + 'f')


def times(repo, prior, run):
    previous = json.loads((repo / 'runs' / prior['id'] / 'evidence.json').read_bytes())
    current = json.loads((repo / 'runs' / run['id'] / 'evidence.json').read_bytes())
    before, after = previous['startedWall'], current['startedWall']
    previous_end, current_end = previous['ended']['time'], current['ended']['time']
    if not before <= previous_end <= after <= current_end or current_end == previous_end:
        raise ValueError(f"Invalid timing for {prior['label']} and {run['label']}")
    return ((after - previous_end) / 1000, (after - before) / 1000, (current_end - previous_end) / 1000)


def both(run, first, final, digits=2):
    return ' / '.join(number(run.get(key), digits) for key in (first, final))


def amended_section(base, repo, results, original, config):
    path = base / 'longgap-recovery-state.json'
    by_id = {run['id']: run for run in results}
    first = original['assignments'][0]
    if not (config.get('max_total_transmissions') == 4 and first['phase'] == 'complete'
            and first['requested_seconds'] == 60 and first['previous_uuid'] == config['anchor_id']
            and first['outcome']['run_id'] == config['first_id'] and not first['outcome']['valid']):
        raise ValueError('Amendment is missing its original failed 60-second anchor')
    if path.is_file():
        state = json.loads(path.read_bytes())
        assignments = state['assignments']
        status = state['status']
    else:
        assignments = []
        status = 'active'
    if not assignments:
        # The amendment may be registered while slot 2 is still running. Only its
        # known default recovery can be counted before the prospective allocator exists.
        assignments = [dict(first, kind='interval')]
        after_first = next(i+1 for i, row in enumerate(results) if row['id'] == config['first_id'])
        if after_first < len(results):
            run = results[after_first]
            if run['relay_mode'] != 'retry-only':
                raise ValueError('Unexpected relay mode for recovery after original failed interval')
            assignments.append(dict(index=2, previous_uuid=config['first_id'], kind='recovery',
                                    requested_seconds=None, phase='complete', outcome={'run_id': run['id']}))
    if len(assignments) > 4 or assignments[0]['outcome']['run_id'] != config['first_id']:
        raise ValueError('Amendment exceeds send cap or changes first outcome')

    rows = []
    observed = {}
    totals = defaultdict(list)
    previous_id = config['anchor_id']
    for expected, item in enumerate(assignments, 1):
        if item['index'] != expected or item['previous_uuid'] != previous_id:
            raise ValueError('Duplicate or discontinuous amendment slot')
        kind = item['kind']
        arm = item.get('requested_seconds') if kind == 'interval' else None
        if (kind == 'interval' and arm not in (60,90)) or kind not in ('interval','recovery'):
            raise ValueError('Unknown 60/90 amendment exposure')
        condition = '실패 후 기본 대기' if kind == 'recovery' else str(arm)+'초'
        prior = by_id[item['previous_uuid']]
        if item['phase'] != 'complete':
            flag = {'allocated':'대기', 'dispatched':'진행 중', 'cutoff':'마감'}.get(item['phase'],'미확인')
            rows.append(f"| {expected} | {condition} | {prior['label']} → … | {flag} | — | — | — | — | — | — |")
            continue
        receipt = item['outcome']
        run = by_id[receipt['run_id']]
        if receipt.get('valid',run['valid']) != run['valid']:
            raise ValueError('Amended receipt disagrees with committed result ' + run['label'])
        if run['id'] in {r['id'] for _,r in observed.values()}:
            raise ValueError('Duplicate amendment result ' + run['label'])
        previous_id = run['id']
        actual, send_gap, cycle = times(repo,prior,run)
        observed[expected] = (arm,run)
        totals[arm].append((run,cycle))
        flag = '유효' if run['valid'] else ('429 종료' if run['rate_limited'] else '검증 실패')
        evidence = repo / 'runs' / run['id'] / 'evidence.json'
        rows.append(f"| {expected} | {condition} | {prior['label']} → [{run['label']}](<{evidence}>) | {flag} | "
                    f"{actual:.1f} / {send_gap:.1f} | {both(run,'first','final')} | {number(run['score'])} | "
                    f"{both(run,'first_ms','final_ms')} | {both(run,'first_reasoning','final_reasoning',0)} | {run['http429']} |")
    first_label = by_id[config['first_id']]['label']
    n_valid = sum(run['valid'] for _,run in observed.values())
    lines = ['', '## 60초·90초 비교와 실패 후 복구', '',
             f"종료 결과 **{len(observed)}/4회**, 유효 {n_valid}회. 최초 60초 배정 {first_label}은 429로 종료돼 처음 계획한 첫 쌍을 완성하지 못했다. "
             '3회차 전 등록한 변경 계획은 429 종료와 기본 복구 전송도 합쳐 최대 4회로 제한한다. 복구 전송은 60초·90초 조건과 따로 센다.',
             '', '| 전송 | 적용 조건 | 직전 → 이번 실행 | 결과 | 종료→전송 / 전송→전송(초) | 첫 / 최종 TPS | 세션 TPS | 첫 / 최종 생성(ms) | 첫 / 최종 추론 토큰 | HTTP 429 |',
             '|---:|---|---|---|---|---|---:|---|---|---:|', *rows]
    pair = [observed.get(3),observed.get(4)]
    if all(pair) and [arm for arm,_ in pair] == [90,60] and all(run['valid'] for _,run in pair):
        high, low = pair[0][1], pair[1][1]
        change = high['score']-low['score']
        lines += ['', f"3·4회차의 유효 1쌍에서 90초−60초 세션 평균 TPS 차이는 **{number(change,signed=True)} TPS**였다 "
                  f"({high['label']} {number(high['score'])}, {low['label']} {number(low['score'])}). "
                  f"첫·최종 TPS 차이는 각각 {number(high['first']-low['first'],signed=True)}와 {number(high['final']-low['final'],signed=True)}다. "
                  '한 쌍의 관측으로 전송 간격의 효과를 판정하기 어렵다.']
        counts = [(entry.get('outcome') or {}).get('call_count') for entry in state['assignments'][2:4]]
        if len(counts) == 2 and all(type(n) is int for n in counts) and counts[0] != counts[1]:
            lines.append(f"두 세션의 측정 호출 수도 {counts[0]}회와 {counts[1]}회로 달랐다. 공식 세션 평균에는 중간 도구 호출을 포함한 모든 생성이 들어간다.")

    elif status in ('complete','inconclusive','cutoff') or len(observed)==4:
        lines += ['', '판정 보류. 3·4회차에서 유효한 90초·60초 쌍을 확보하지 못해 세션 평균 차이를 산출할 수 없다.']
    else:
        lines += ['', '3·4회차 안에서 유효한 90초·60초 쌍이 완성되면 그 한 쌍의 차이를 표시한다.']
    lines += ['', '| 적용 조건 | 종료 | 유효 | 429 종료 | HTTP 429 합계 | 종료→종료 합계(초) | 시간당 유효 완료 환산 |',
              '|---|---:|---:|---:|---:|---:|---:|']
    for arm,title in ((60,'60초'),(90,'90초'),(None,'실패 후 기본 대기')):
        data = totals[arm]
        count = sum(run['valid'] for run,_ in data)
        elapsed = sum(cycle for _,cycle in data)
        limited = sum(run['rate_limited'] is True for run,_ in data)
        retry = sum(run['http429'] for run,_ in data)
        rate = count*3600/elapsed if elapsed else None
        lines.append(f"| {title} | {len(data)} | {count} | {limited} | {retry} | {elapsed:.1f} | {number(rate)} |")
    links = f"[최초 배정 원장](<{base/'longgap-state.json'}>) · [3회차 전 변경 계획](<{base/'longgap-recovery-config.json'}>)"
    if path.is_file():
        links += f" · [전체 전송 원장](<{path}>)"
    lines += ['', '전송 시각은 원본 startedWall 기준이다. 시간당 값은 해당 조건의 직전 종료→이번 종료 합계 시간에서 환산한다. '+links]
    return lines


def section(base, repo, results):
    state_path = base / 'longgap-state.json'
    lines = ['', '## 정상 종료 뒤 60초·90초 비교', '']
    if not state_path.is_file():
        return lines + ['첫 호출 도구 선택 비교를 마친 뒤 기본 D5027 조건에서 60→90초, 90→60초 순서의 2쌍, 최대 4회를 비교한다. 첫 배정 실패나 429 종료가 발생하면 그 실행을 포함해 비교를 끝낸다.']
    state = json.loads(state_path.read_bytes())
    amendment = base / 'longgap-recovery-config.json'
    if amendment.is_file():
        return amended_section(base, repo, results, state, json.loads(amendment.read_bytes()))
    plan = state['config']['order_seconds']
    if plan != [60, 90, 90, 60] or len(state['assignments']) > 4:
        return lines + ['전송 4회의 사전 배정과 원장이 달라 결과 집계를 보류한다.']
    by_id = {run['id']: run for run in results}
    groups = {60: [], 90: []}
    paired = defaultdict(dict)
    exposure_rows = []
    verdict = {'allocated': '대기', 'dispatched': '실행 중', 'cutoff': '마감'}
    for item in state['assignments']:
        arm = item['requested_seconds']
        key = item['pair']
        prior = by_id[item['previous_uuid']]
        if item['phase'] != 'complete':
            phase = verdict.get(item['phase'], '미확인')
            exposure_rows.append(f"| {key}·{item['slot']} | {arm}초 | {prior['label']} → … | {phase} | — | — | — | — | — | — |")
            continue
        receipt = item['outcome']
        run = by_id[receipt['run_id']]
        if bool(receipt['valid']) != bool(run['valid']):
            raise ValueError(f"Validity mismatch for {run['label']}")
        delay, send_gap, cycle = times(repo, prior, run)
        groups[arm].append((run, cycle))
        paired[key][arm] = run
        phase = '유효' if run['valid'] else ('429 종료' if run['rate_limited'] else '무효')
        evidence_path = repo / 'runs' / run['id'] / 'evidence.json'
        link = f"[{run['label']}](<{evidence_path}>)"
        exposure_rows.append(
            f"| {key}·{item['slot']} | {arm}초 | {prior['label']} → {link} | {phase} | "
            f"{delay:.1f} / {send_gap:.1f} | {both(run,'first','final')} | {number(run['score'])} | "
            f"{both(run,'first_ms','final_ms')} | {both(run,'first_reasoning','final_reasoning',0)} | {run['http429']} |"
        )

    early = state.get('status') == 'inconclusive_after_failure'
    at_cutoff = state.get('status') == 'cutoff'
    complete_pairs = sum(len(arms) == 2 for arms in paired.values())
    deltas = []
    pair_rows = []
    for key in (1, 2):
        order = plan[2*(key-1):2*key]
        arms = paired.get(key, {})
        pair_complete = 60 in arms and 90 in arms
        if pair_complete and all(arms[arm]['valid'] for arm in (60,90)):
            first, final, score = (arms[90][name] - arms[60][name] for name in ('first','final','score'))
            deltas.append(score)
            result = '90초 우위' if score > 0 else '60초 우위' if score < 0 else '동률'
        else:
            first = final = score = None
            result = '한쪽 이상 무효' if pair_complete else '미완료'
            if (early or at_cutoff) and not pair_complete:
                result = '조기 종료로 미완료' if early else '마감으로 미완료'
        pair_rows.append(f"| {key} | {' → '.join(map(str,order))} | {number(first,signed=True)} | "
                         f"{number(final,signed=True)} | {number(score,signed=True)} | {result} |")
    finished = sum(map(len, groups.values()))
    lines.append(f"배정 결과 {finished}/4회 종료, {complete_pairs}/2쌍 종료, 양쪽 모두 유효한 쌍 {len(deltas)}개.")
    if deltas:
        n90 = sum(d > 0 for d in deltas)
        n60 = sum(d < 0 for d in deltas)
        lines += ['', f"유효 쌍에서 세션 평균 TPS 차이(90초−60초)의 중앙값은 **{number(median(deltas), signed=True)} TPS**다. "
                  f"90초 우위 {n90}쌍, 60초 우위 {n60}쌍, 동률 {len(deltas)-n90-n60}쌍이다."]
    if early or at_cutoff:
        failed = by_id.get(state.get('failed_run_id'))
        if early and failed:
            tag = '429 종료' if failed['rate_limited'] else '검증 실패'
            why = f"{failed['label']} {tag}"
        else:
            why = '다음 배정의 유효 선행 실행 부족' if early else '마감'
        lines += ['', f'판정 보류. {why}로 전송 {finished}/4회에서 비교를 종료했다. '
                  f'양쪽 모두 유효한 2쌍을 확보하려면 {2 - len(deltas)}쌍이 더 필요하며, 추가 배정은 종료했다.']
    elif finished == 4:
        if len(deltas) == 2 and (all(d > 0 for d in deltas) or all(d < 0 for d in deltas)):
            faster = '90초' if deltas[0] > 0 else '60초'
            lines += ['', f'두 유효 쌍에서 모두 {faster} 조건의 세션 평균 TPS가 높았다. 이 네 실행에서 관측한 방향이다.']
        else:
            lines += ['', '판정 보류. 유효한 두 쌍에서 같은 방향의 세션 평균 TPS 차이가 확인돼야 한다.']
    lines += ['', '| 쌍 | 배정 순서(초) | 첫 TPS 차이 | 최종 TPS 차이 | 세션 평균 TPS 차이 | 결과 |',
              '|---:|---|---:|---:|---:|---|', *pair_rows, '',
              '| 쌍·순번 | 배정 | 직전 → 이번 실행 | 결과 | 종료→전송 / 전송→전송(초) | 첫 / 최종 TPS | 세션 TPS | 첫 / 최종 생성(ms) | 첫 / 최종 추론 토큰 | HTTP 429 |',
              '|---:|---:|---|---|---|---|---:|---|---|---:|', *exposure_rows, '',
              '| 배정 | 종료 | 유효 | 429 종료 | HTTP 429 합계 | 종료→종료 주기 합계(초) | 시간당 유효 완료 환산 | 최종 출력 161·추론 3인 유효 세션 |',
              '|---:|---:|---:|---:|---:|---:|---:|---|']
    for arm, outcomes in groups.items():
        valid = sum(run['valid'] for run, _ in outcomes)
        limited = sum(run.get('rate_limited') is True for run, _ in outcomes)
        count_429 = sum(run['http429'] for run, _ in outcomes)
        elapsed = sum(duration for _, duration in outcomes)
        rate = valid * 3600 / elapsed if elapsed else None
        matched = [run['label'] for run, _ in outcomes if run['valid'] and run.get('final_output_tokens') == 161
                   and run.get('final_reasoning') == 3]
        lines.append(f"| {arm}초 | {len(outcomes)}/2 | {valid} | {limited} | {count_429} | {elapsed:.1f} | {number(rate)} | "
                     + (', '.join(matched) if matched else '—') + ' |')
    lines += ['', '전송 시각은 원본의 startedWall이다. 종료→전송에는 녹화 준비 시간이 포함된다. '
              '시간당 값은 해당 배정에서 종료된 세션의 유효 건수를 직전 종료부터 이번 종료까지의 합계 시간으로 나눠 환산했다. '
              '429 종료·상품 검증 실패도 그 시간과 배정 횟수에 포함한다. 배정된 실행이 처음 실패하면 해당 결과에서 비교를 마친다.',
              '', '표본은 최대 2쌍이며 시간대별 제공사 부하와 추론량의 영향이 남을 수 있다. '
              f'[배정 및 결과 원장](<{state_path}>)']
    return lines
