#!/usr/bin/env python3
"""Describe reasoning length and official speed in verified shopping runs.

Reasoning text length is a separate observation, not a substitute for official
mean tok/s. Near-time control comparisons reduce time separation, but do not
control provider load or establish why a rate changed. This report reads the
private raw transcripts, which retain reasoning text omitted from public evidence.

    python3 tools/reasoning_report.py            # control and reasoning-suppression arms
    python3 tools/reasoning_report.py --all      # every variant in the private archive
No provider calls. Reads OpenClaw's local session report for the reported
AGENTS.md character count; that count cannot prove the file's contents.
"""
import argparse
import json
import os
from pathlib import Path
import sqlite3
from statistics import median
import sys

sys.dont_write_bytecode = True
from research_report import (FORMAT_VARIANTS, category_links_for_plan, correct_subtotals, expected_format,
                             first_five_catalog_links)
from variants import (CATEGORY_VARIANTS, FIRST_FIVE_VARIANTS, PRIORITY_ARMS, PRIORITY_CONTROL, TEST_ARMS,
                      WORKSPACE_AGENTS_BY_VARIANT)

REPO = Path(__file__).resolve().parents[1]
ROOT = Path(os.environ.get('BOUNTY_ROOT', str(Path.home() / 'Library/Caches/cerebras-speed-bounty/2026-11-22')))
RAW = Path(os.environ.get('BOUNTY_RAW_ARCHIVE',
                          str(Path.home() / 'Library/Application Support/Cerebras Speed Bounty/2026-11-22/raw')))
SESSIONS = ROOT / 'shopper-test/agents/main/agent/openclaw-agent.sqlite'
PAIR_WINDOW_MS = 15 * 60 * 1000


def rate(message):
    server = message['serverGeneration']
    return server['outputTokens'] / (server['completionMs'] / 1000)


def reasoning_chars(message):
    return sum(len(part.get('thinking') or '') for part in message.get('content') or []
               if isinstance(part, dict) and part.get('type') == 'thinking')


def agents_injection(db, session_key):
    """Reported AGENTS.md character count, 0 when missing, None when unknown; no content check."""
    if db is None:
        return None
    try:
        # One snapshot row per (session, field); the table has no rowid.
        row = db.execute("select value_json from session_entry_snapshots where session_key=? and field='systemPromptReport'",
                         (session_key,)).fetchone()
    except sqlite3.Error:
        return None
    if not row:
        return None
    for item in json.loads(row[0]).get('injectedWorkspaceFiles') or []:
        if item.get('name') == 'AGENTS.md':
            return 0 if item.get('missing') else item.get('rawChars')
    return None


def load(db):
    runs = []
    for path in sorted(RAW.glob('*.json')):
        raw = json.loads(path.read_bytes())
        ident = raw.get('id')
        calls = [m for m in (raw.get('history') or {}).get('messages') or []
                 if m.get('role') == 'assistant' and (m.get('serverGeneration') or {}).get('completionMs')
                 and (m.get('__openclaw') or {}).get('runId') == ident]
        evidence_path = REPO / 'runs' / str(ident) / 'evidence.json'
        evidence = json.loads(evidence_path.read_bytes()) if evidence_path.exists() else {}
        final = next((m for m in reversed(calls) if m.get('stopReason') == 'stop'), None)
        valid = (evidence.get('validation') or {}).get('valid') is True
        variant = raw.get('variant')
        method_valid = True
        if valid and variant in FIRST_FIVE_VARIANTS:
            method_valid = first_five_catalog_links(evidence)
        elif valid and variant in CATEGORY_VARIANTS:
            method_valid = category_links_for_plan(evidence, raw)
        elif valid and variant in FORMAT_VARIANTS:
            method_valid = expected_format(evidence.get('final_text') or '', variant)
        elif valid and variant == 'research-price-total':
            method_valid = correct_subtotals(evidence) == 5
        runs.append({
            'id': ident, 'label': raw.get('label'), 'variant': raw.get('variant'),
            'arm': f"{raw.get('variant')}|{raw.get('temperature'):g}|{raw.get('thinking')}"
                   if raw.get('temperature') is not None else None,
            'started': raw.get('startedWall'), 'agents_md': raw.get('workspace_agents_md'),
            'valid': valid and method_valid,
            'score': (evidence.get('score') or {}).get('mean_exact_tps'),
            'first': calls[0] if calls else None, 'final': final,
            'injected': agents_injection(db, raw.get('sessionKey')),
        })
    return runs


def pct(values):
    return f'{100 * sum(values) / len(values):.0f}% ({sum(values)}/{len(values)})' if values else '—'


def med(values, digits=0):
    return f'{median(values):,.{digits}f}' if values else '—'


def summarize(rows):
    eligible = [r for r in rows if r['valid'] and r['score'] is not None]
    firsts = [r['first'] for r in eligible if r['first']]
    finals = [r['final'] for r in eligible if r['final']]
    scores = [r['score'] for r in eligible]
    return {
        'runs': len(rows), 'valid': len(scores),
        'first_chars': med([reasoning_chars(m) for m in firsts]),
        'first_zero': pct([reasoning_chars(m) == 0 for m in firsts]),
        'final_zero': pct([reasoning_chars(m) == 0 for m in finals]),
        'first_tps': med([rate(m) for m in firsts]), 'final_tps': med([rate(m) for m in finals]),
        'score': med(scores), 'best': f'{max(scores):,.0f}' if scores else '—',
    }


def paired(treatment, control):
    """Ratio of each valid treatment score to the nearest-in-time valid control score."""
    controls = [r for r in control if r['valid'] and r['score'] and r['started']]
    ratios, chars = [], []
    for row in treatment:
        if not (row['valid'] and row['score'] and row['started'] and controls):
            continue
        near = min(controls, key=lambda c: abs(c['started'] - row['started']))
        if abs(near['started'] - row['started']) > PAIR_WINDOW_MS:
            continue
        ratios.append(row['score'] / near['score'])
        if row['first'] and near['first']:
            chars.append(reasoning_chars(row['first']) - reasoning_chars(near['first']))
    return ratios, chars


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--all', action='store_true', help='report every variant in the private archive')
    parser.add_argument('--test', action='store_true', help='report the test-branch ladder (set BOUNTY_RAW_ARCHIVE)')
    args = parser.parse_args()
    if not RAW.is_dir():
        raise SystemExit('Private raw archive not found: ' + str(RAW))
    db = None
    if SESSIONS.exists():
        try:
            db = sqlite3.connect(f'file:{SESSIONS}?mode=ro', uri=True)
        except sqlite3.Error:
            db = None
    runs = load(db)
    control_key = '|'.join([PRIORITY_CONTROL[0], f'{PRIORITY_CONTROL[1]:g}', PRIORITY_CONTROL[2]])
    focus = [control_key] + ['|'.join([a[0], f'{a[1]:g}', a[2]]) for a in (TEST_ARMS[1:] if args.test else PRIORITY_ARMS)]
    arms = sorted({r['arm'] for r in runs if r['arm']}) if args.all else focus
    print('| 조건 | 실행 / 유효 | 첫 호출 추론 글자 중앙값 | 첫 호출 무추론 | 최종 무추론 | 첫 호출 / 최종 tok/s 중앙값 | 공식 평균 중앙값 / 최고 | 근접 기준 실행 대비 | AGENTS.md 보고 글자 수 |')
    print('|---|---:|---:|---:|---:|---:|---:|---:|---|')
    control = [r for r in runs if r['arm'] == control_key and r['agents_md'] is None]
    for arm in arms:
        name = arm.split('|')[0]
        expected = WORKSPACE_AGENTS_BY_VARIANT.get(name)
        rows = [r for r in runs if r['arm'] == arm and r['agents_md'] == expected]
        if not rows:
            print(f'| {arm.replace("|", "&#124;")} | 0 / 0 | — | — | — | — | — | — | — |')
            continue
        s = summarize(rows)
        pair = '기준'
        if arm != control_key:
            ratios, chars = paired(rows, control)
            if ratios:
                delta = f' · 추론 {median(chars):+,.0f}자' if chars else ''
                pair = f'×{median(ratios):.2f}{delta} (n={len(ratios)})'
            else:
                pair = '쌍 없음'
        injection = '—'
        if expected is not None:
            seen = [r['injected'] for r in rows]
            positive = [value for value in seen if type(value) is int and value > 0]
            injection = f'{len(positive)}/{len(rows)} 양수 · 중앙 {med(positive)}자 (내용 미검증)'
        elif any(r['injected'] for r in rows):
            injection = '예상 밖 양수 길이'
        print(f"| {arm.replace('|', '&#124;')} | {s['runs']} / {s['valid']} | {s['first_chars']} | {s['first_zero']} | {s['final_zero']} | "
              f"{s['first_tps']} / {s['final_tps']} | {s['score']} / {s['best']} | {pair} | {injection} |")
    print()
    print('속도·추론 통계는 쇼핑과 해당 형식 검증을 통과한 실행만 포함한다. 추론 글자 수는 공식 평균을 대체하지 않는다. 근접 실행 비교는 공급자 부하를 통제하지 않는다. AGENTS.md 글자 수는 내용 일치의 증거가 아니다.')


if __name__ == '__main__':
    main()
