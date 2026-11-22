#!/usr/bin/env python3
"""Print a Korean Markdown comparison of recorded shopping experiments.

From the repository root: python3 tools/research_report.py > RESEARCH.md
Only committed-evidence formats under runs/ are needed. No provider calls.
"""
import argparse
import json
import math
from pathlib import Path
import re
from statistics import median
import sys

sys.dont_write_bytecode = True
from validate import MARKDOWN_TOKEN, answer_links, merchant

COMPARISONS = (
    ('판매처 1곳', (('WordPress','wordpress-links'),('AI Synthesis','synth-links'))),
    ('판매처 2곳', (('WordPress + RaspberryPi.dk','source-order'),('WordPress + AI Synthesis','source-order-synth'))),
    ('답변 형식', (('표','research-table'),('문장','research-prose'))),
    ('가격 계산', (('문장','research-prose'),('가격 합계','research-price-total'))),
    ('카탈로그 크기', (('4개씩','paired-links-small'),('8개씩','paired-links'))),
    ('추론 수준', (('기준 설정','source-order'),('최대 추론 요청','research-reasoning-max'))),
    ('최대 출력 토큰', (('기본 설정','source-order'),('2,048','source-order-max-2048'),('4,096','research-cap-4096'))),
    ('샘플링 top_p', (('0.80','source-order-top-p-080'),('0.45','source-order-top-p-045'))),
)
RUN_ID = re.compile(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}')


def number(value):
    return type(value) in (int,float) and math.isfinite(value) and value >= 0


def load_runs(repo):
    groups = {variant:[] for _, arms in COMPARISONS for _, variant in arms}
    for plan_path in sorted((repo/'runs').glob('*/plan.json')):
        plan = json.loads(plan_path.read_bytes())
        variant = plan.get('variant')
        if variant not in groups or plan.get('temperature') != 0.2:
            continue
        if variant != 'research-reasoning-max' and plan.get('thinking') != 'low':
            continue
        ident = plan_path.parent.name
        if not RUN_ID.fullmatch(ident) or plan.get('id') != ident:
            raise ValueError('plan identity differs from run folder')
        evidence_path = plan_path.with_name('evidence.json')
        evidence = json.loads(evidence_path.read_bytes()) if evidence_path.exists() else None
        if evidence is not None and evidence.get('id') != ident:
            raise ValueError('evidence identity differs from plan')
        groups[variant].append((plan,evidence))
    return groups


def measurements(evidence):
    valid, scores, tool, final, output, usage = [], [], [], [], [], []
    for record in evidence:
        if not record['validation']['valid']:
            continue
        mean = record['score']['mean_exact_tps']
        if not number(mean):
            raise ValueError('validated run lacks a finite official score')
        valid.append(record)
        scores.append(mean)
        for call in record['calls']:
            timing = call['serverGeneration']
            ms, tokens = timing.get('completionMs'), timing.get('outputTokens')
            if not number(ms) or ms == 0 or not number(tokens) or tokens < 1:
                raise ValueError('validated run lacks server generation timing')
            output.append(tokens)
            if call.get('stopReason') == 'toolUse':
                tool.append(tokens*1000/ms)
            if call.get('stopReason') == 'stop':
                final.append(tokens*1000/ms)
            counters = call.get('usage',{})
            keys = ('input','cacheRead','cacheWrite')
            if all(number(counters.get(k)) for k in keys):
                usage.append(tuple(counters[k] for k in keys))
    return valid, scores, tool, final, output, usage


def fmt_median(values):
    return f'{median(values):,.1f}' if values else '—'


def references(group, valid):
    finished = sorted((e for _,e in group if e is not None),key=lambda r:r.get('startedWall',0))
    selected = []
    if valid:
        selected.append(max(valid,key=lambda r:r['score']['mean_exact_tps'])['id'])
    if finished and finished[-1]['id'] not in selected:
        selected.append(finished[-1]['id'])
    planned = sorted(p['id'] for p,e in group if e is None)
    links = [f'[{i[:8]}](runs/{i}/evidence.json)' for i in selected]
    if planned:
        links.append(f'[계획](runs/{planned[-1]}/plan.json)')
    return ' · '.join(links) or '—'


def expected_format(text, variant):
    urls, misleading = answer_links(text)
    if misleading or len(set(urls)) != 5 or len(urls) != 5 or not all(merchant(url,product=True) for url in urls):
        return False
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if variant == 'research-table':
        if len(lines) != 7:
            return False
        rows = [[c.strip() for c in re.split(r'(?<!\\)\|',line.strip('|'))] for line in lines]
        return (all(len(row) == 2 for row in rows) and [c.strip('*_').casefold() for c in rows[0]] == ['gift','price']
                and all(re.fullmatch(r':?-{3,}:?',c) for c in rows[1])
                and all(len(answer_links(gift)[0]) == 1 and bool(price) for gift,price in rows[2:]))
    if any(re.match(r'^(?:[-+*]\s|\d+[.)]\s|[|>#`]|~{3})',line) or '|' in line for line in lines):
        return False
    # Temporarily mask URLs and Markdown links to avoid treating dots in domains or product names as sentence boundaries.
    masked = MARKDOWN_TOKEN.sub(lambda m: ' LINK ' if not m[1] and not m[2] else '', text)
    for url in sorted(urls,key=len,reverse=True):
        masked = masked.replace(url,' LINK ')
    parts = [part for part in re.split(r'[.!?]+(?=\s|$)|\n+',masked) if part.strip()]
    return len(parts) == 5 and all(part.count(' LINK ') == 1 for part in parts)


def format_count(group, variant):
    texts = [e['final_text'] for _,e in group if e and isinstance(e.get('final_text'),str) and e['final_text'].strip()]
    return f'{sum(expected_format(text,variant) for text in texts)}/{len(texts)}' if texts else '미측정'



def render(repo):
    groups = load_runs(repo)
    lines = [
        '# 실시간 선물 쇼핑 TPS 실험', '',
        '같은 Cerebras Kimi K3.1 Pro로 실제 판매처에서 선물 다섯 개를 고른 요청을 비교했다. '
        '각 조건의 속도와 토큰 통계에는 쇼핑 검증을 통과한 실행만 포함한다.', '',
        '| 실험 | 조건 | 유효/실행 확인 | 계획만 | 공식 평균 TPS 중앙값 / 최고 | 도구 / 최종 호출 TPS 중앙값 | 입력 / 캐시 읽기 / 캐시 쓰기 / 출력 토큰 합계 | 기록 |',
        '|---|---|---:|---:|---:|---:|---:|---|',
    ]
    cache_hits = cache_known = measured_calls = 0
    cache_counted = set()
    for experiment, arms in COMPARISONS:
        for name, variant in arms:
            group = groups[variant]
            evidence = [e for _,e in group if e is not None]
            valid, scores, tool, final, output, usage = measurements(evidence)
            if variant not in cache_counted:
                cache_hits += sum(read > 0 for _,read,_ in usage)
                cache_known += len(usage)
                measured_calls += len(output)
                cache_counted.add(variant)
            n = len(valid)
            official = f'{fmt_median(scores)} / {max(scores):,.1f}' if scores else '—'
            stage = f'{fmt_median(tool)} / {fmt_median(final)}' if n else '—'
            totals = ' / '.join(f'{sum(col):,}' for col in zip(*usage)) if usage else '— / — / —'
            tokens = f'{totals} / {sum(output):,}' if output else '—'
            if usage and len(usage) < len(output):
                tokens += f' (입력·캐시 {len(usage)}/{len(output)}호출)'
            if variant == 'research-reasoning-max':
                levels = sorted({p.get('thinking','') for p,_ in group})
                observed = [x for x in levels if x in ('none','off','low','medium','high','xhigh','max')]
                if observed:
                    name += ' ('+', '.join(observed)+')'
            lines.append(f'| {experiment} | {name} | {n}/{len(evidence)} | {len(group)-len(evidence)} | {official} | {stage} | {tokens} | {references(group,valid)} |')

    table = format_count(groups['research-table'],'research-table')
    prose = format_count(groups['research-prose'],'research-prose')
    lines += ['', f'요청한 형식에 맞은 최종 응답은 표 **{table}**, 문장 **{prose}**로 집계했다. '
              '분모는 최종 답변이 남은 해당 형식의 실행 수다. 표는 Gift·Price 두 열과 서로 다른 상품 링크가 하나씩 든 다섯 행, '
              '문장은 목록·표 표식 없이 상품 링크가 하나씩 든 다섯 문장 또는 줄을 확인한다.',
              '', '온도는 0.2이며 추론 수준 비교군을 제외한 행은 모두 low 설정이다. '
              '실행 확인 수는 결과가 남은 요청 수이며 검증 실패도 포함한다. 계획만 남은 요청은 전송 여부를 알 수 없다. '
              '표의 대시는 미측정이고 0은 관측값이다. 반복해서 표시한 기준 행은 같은 실행을 참조한다.', '',
              '공식 평균은 한 실행에서 각 모델 호출의 서버 출력 토큰 수를 생성 시간으로 나눈 값의 산술평균이다. '
              '도구·최종 열은 각각 도구를 요청한 호출과 최종 답변 호출의 중앙값이다. '
              '입력·캐시는 사용량이 기록된 호출의 합계이고 출력은 서버 생성 토큰 합계다. 기록 링크는 조건별 최고 유효 실행과 최근 결과를 가리킨다.',
              '', '## 캐시와 프리필', '']
    if cache_known:
        lines.append(f'표의 중복 조건을 한 번씩 집계한 결과, 유효 호출 {measured_calls}개 중 {cache_known}개에 입력·캐시 사용량이 남았다. '
                     f'그중 {cache_hits}개에서 캐시 읽기가 기록됐다.')
    else:
        lines.append('표의 유효 실행에는 아직 입력·캐시 사용량을 함께 기록한 호출이 없다.')
    lines += ['', '프리필 시간과 첫 토큰 지연은 이 기록의 측정 항목에서 빠져 있다. '
              '캐시 읽기가 입력 처리 시간을 줄였는지는 이 표로 추정할 수 없다. '
              '각 비교에 충분한 대조·실험 반복 쌍이 쌓이기 전에는 관측된 TPS 차이의 원인을 특정할 수 없다.']
    return '\n'.join(lines)+'\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo',type=Path,default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    if not (args.repo/'runs').is_dir():
        parser.error('runs directory not found')
    print(render(args.repo),end='')


if __name__ == '__main__':
    main()
