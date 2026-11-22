"""Offline, resumable AB/BA campaign scheduler for the TPS-2000 target."""
import argparse
import json
import math
from pathlib import Path
import re
from statistics import median

from method_2000 import call_diagnostics
from variants import arm_key


PHASE1_ARMS = (
    ('synth-five-categories-cap-4000', 0.2, 'low'),
    ('exp2k-call0-zero-think', 0.2, 'low'),
)
PHASE2_ARMS = (
    ('exp2k-call0-zero-think', 0.2, 'low'),
    ('exp2k-verbatim-cards', 0.2, 'low'),
)
PHASE3A_CHALLENGER = ('exp2k-verbatim-cards-topp03', 0.15, 'low')
PHASE3B_CHALLENGER = ('exp2k-three-call-verify', 0.2, 'low')
FAST_PROBE_BASE_ARMS = (
    PHASE2_ARMS[1],
    PHASE3A_CHALLENGER,
    PHASE3B_CHALLENGER,
)
# Symmetric ABCCBA schedule gives every arm one slot in trials 1-3, 2 trials total, and equal mean position.
FAST_PROBE_ARMS = FAST_PROBE_BASE_ARMS + tuple(reversed(FAST_PROBE_BASE_ARMS))
ORDER6 = 'ABBABA'
ORDER4 = 'ABBA'
TOTAL_BUDGET = 20


def _number(row):
    match = re.fullmatch(r'D(\d+)-.+', row.get('label', ''))
    return int(match[1]) if match else None


def _finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def _valid(row):
    return row.get('valid') is True and row.get('method_valid') is True and _finite(row.get('score'))


def _target(row):
    return (_valid(row) and row.get('recorded_video') is True
            and _finite(row.get('ui')) and row['score'] > 2000 and row['ui'] > 2000)


def _pair_summary(rows, arm_a, arm_b, order):
    key_a, key_b = arm_key(arm_a), arm_key(arm_b)
    counts = {
        'A': sum(_valid(row) for row in rows if row.get('arm') == key_a),
        'B': sum(_valid(row) for row in rows if row.get('arm') == key_b),
    }
    pairs = []
    for offset in range(0, len(rows) - 1, 2):
        first, second = rows[offset:offset + 2]
        a, b = (first, second) if order[offset] == 'A' else (second, first)
        valid_pair = _valid(a) and _valid(b)
        pairs.append({
            'a': a.get('label'),
            'b': b.get('label'),
            'score_a': a.get('score'),
            'score_b': b.get('score'),
            'valid': valid_pair,
            'difference_tps': (b['score'] - a['score']) if valid_pair else None,
        })
    diffs = [pair['difference_tps'] for pair in pairs if pair['valid']]
    scores_a = [row['score'] for row in rows if row.get('arm') == key_a and _valid(row)]
    scores_b = [row['score'] for row in rows if row.get('arm') == key_b and _valid(row)]
    return {
        'arm_a': key_a,
        'arm_b': key_b,
        'completed': len(rows),
        'expected': len(order),
        'valid_counts': counts,
        'median_a': median(scores_a) if scores_a else None,
        'median_b': median(scores_b) if scores_b else None,
        'pairs': pairs,
        'valid_pairs': len(diffs),
        'wins_b': sum(value > 0 for value in diffs),
        'median_advantage_tps': median(diffs) if diffs else None,
    }


def _choose_phase2_winner(phase2_rows, phase2_stats):
    """Deterministically select Phase-2 winner once all 6 Phase-2 slots complete."""
    if len(phase2_rows) < len(ORDER6):
        return None
    diffs = [pair['difference_tps'] for pair in phase2_stats['pairs'] if pair['valid']]
    if diffs:
        adv = median(diffs)
        if adv > 0 or (adv == 0 and phase2_stats['wins_b'] > len(diffs) / 2):
            return PHASE2_ARMS[1]
        return PHASE2_ARMS[0]
    med_a = phase2_stats['median_a']
    med_b = phase2_stats['median_b']
    if med_b is not None and (med_a is None or med_b > med_a):
        return PHASE2_ARMS[1]
    return PHASE2_ARMS[0]


def _slot_arm(index, phase2_winner):
    if index < 6:
        return PHASE1_ARMS[0 if ORDER6[index] == 'A' else 1]
    if index < 12:
        return PHASE2_ARMS[0 if ORDER6[index - 6] == 'A' else 1]
    if index < 16:
        return phase2_winner if ORDER4[index - 12] == 'A' else PHASE3A_CHALLENGER
    return phase2_winner if ORDER4[index - 16] == 'A' else PHASE3B_CHALLENGER


def summary(repo: Path, start: int, rows: list[dict]):
    """Compute resumable state and next arm for the 20-trial TPS-2000 campaign."""
    del repo  # signature mirrors campaign_1700.summary
    selected = sorted((row for row in rows if _number(row) is not None and _number(row) >= start),
                      key=_number)
    result = {
        'start': start,
        'completed': len(selected),
        'budget': TOTAL_BUDGET,
        'phase2_winner': None,
        'phases': [],
        'next_arm': None,
        'reason': '',
    }
    numbers = [_number(row) for row in selected]
    if len(numbers) != len(set(numbers)):
        result['reason'] = 'stop: duplicate completed trial number'
        return result

    for index, row in enumerate(selected[:12]):
        expected = _slot_arm(index, None)
        if row.get('arm') != arm_key(expected):
            result['reason'] = f"stop: unexpected arm at {row.get('label')}; expected {arm_key(expected)}"
            return result

    p1_rows = selected[:6]
    p2_rows = selected[6:12]
    p1_stats = _pair_summary(p1_rows, PHASE1_ARMS[0], PHASE1_ARMS[1], ORDER6)
    p1_stats['phase'] = '1_call0_zero_think'
    p2_stats = _pair_summary(p2_rows, PHASE2_ARMS[0], PHASE2_ARMS[1], ORDER6)
    p2_stats['phase'] = '2_verbatim_cards'
    result['phases'] = [p1_stats, p2_stats]

    phase2_winner = _choose_phase2_winner(p2_rows, p2_stats)
    result['phase2_winner'] = arm_key(phase2_winner) if phase2_winner else None

    for index, row in enumerate(selected[12:], start=12):
        if index >= TOTAL_BUDGET or phase2_winner is None:
            result['reason'] = 'stop: unexpected rows beyond campaign allocation'
            return result
        expected = _slot_arm(index, phase2_winner)
        if row.get('arm') != arm_key(expected):
            result['reason'] = f"stop: unexpected arm at {row.get('label')}; expected {arm_key(expected)}"
            return result

    if phase2_winner is not None:
        p3a_stats = _pair_summary(selected[12:16], phase2_winner, PHASE3A_CHALLENGER, ORDER4)
        p3a_stats['phase'] = '3a_low_top_p'
        p3b_stats = _pair_summary(selected[16:20], phase2_winner, PHASE3B_CHALLENGER, ORDER4)
        p3b_stats['phase'] = '3b_three_call_verify'
        result['phases'].extend([p3a_stats, p3b_stats])

    target = next((row for row in selected if _target(row)), None)
    if target:
        result['reason'] = (f"stop: >2000 TPS target recorded at {target['label']} "
                            f"({target['score']:.1f} tok/s)")
        return result

    if len(selected) < TOTAL_BUDGET:
        idx = len(selected)
        result['next_arm'] = _slot_arm(idx, phase2_winner)
        phase_tag = ('1' if idx < 6 else '2' if idx < 12 else '3a' if idx < 16 else '3b')
        slot_num = (idx % 6 + 1 if idx < 12 else (idx - 12) % 4 + 1)
        slot_total = 6 if idx < 12 else 4
        result['reason'] = f'phase {phase_tag}, slot {slot_num}/{slot_total}'
    else:
        result['reason'] = 'stop: completed maximum 20 trials'
    return result


def decision(repo: Path, start: int, rows: list[dict]):
    result = summary(repo, start, rows)
    return result['next_arm'], result['reason']


def _append_diagnostics_table(lines: list[str], selected: list[dict], raw_dir: Path | None) -> None:
    if not selected:
        return
    lines.extend(['', '## Per-Trial Call Diagnostics', '',
                  '| Trial | Arm | Mean TPS | Valid/Method | Calls (tps / tok / ms / think_chars) |',
                  '|---|---|---:|---|---|'])
    for row in selected:
        diag_str = '—'
        if raw_dir is not None:
            raw_path = raw_dir / f"{row.get('id')}.json"
            if raw_path.is_file():
                diags = call_diagnostics(json.loads(raw_path.read_text()))
                diag_str = ' ; '.join(
                    f"{d['stopReason']}[{d['tps']:.0f} t/s, {d['outputTokens']}t/{d['completionMs']:.0f}ms, th={d['think_chars']}c]"
                    if d['tps'] is not None else f"{d['stopReason']}[unscored]"
                    for d in diags
                )
        score_str = f"{row['score']:.1f}" if _finite(row.get('score')) else '—'
        lines.append(f"| {row.get('label')} | `{row.get('arm')}` | {score_str} | "
                     f"{row.get('valid')}/{row.get('method_valid')} | {diag_str} |")


def format_report(repo: Path, start: int, rows: list[dict], raw_dir: Path | None = None) -> str:
    data = summary(repo, start, rows)
    lines = [
        f"# Campaign 2000 Report (start=D{start:04d})",
        f"- Completed: {data['completed']}/{data['budget']} | Status: {data['reason']}",
    ]
    if data['phase2_winner']:
        lines.append(f"- Phase-2 winner carried into Phase 3: `{data['phase2_winner']}`")
    lines.extend(['', '| Phase | Arm A | Arm B | Done | Med A | Med B | Paired Med (B-A) | Wins B |',
                  '|---|---|---|---:|---:|---:|---:|---:|'])
    for ph in data['phases']:
        med_a = f"{ph['median_a']:.1f}" if ph['median_a'] is not None else '—'
        med_b = f"{ph['median_b']:.1f}" if ph['median_b'] is not None else '—'
        adv = f"{ph['median_advantage_tps']:+.1f}" if ph['median_advantage_tps'] is not None else '—'
        lines.append(f"| {ph['phase']} | `{ph['arm_a']}` | `{ph['arm_b']}` | "
                     f"{ph['completed']}/{ph['expected']} | {med_a} | {med_b} | {adv} | "
                     f"{ph['wins_b']}/{ph['valid_pairs']} |")

    selected = sorted((row for row in rows if _number(row) is not None and _number(row) >= start),
                      key=_number)
    _append_diagnostics_table(lines, selected, raw_dir)
    return '\n'.join(lines) + '\n'


def fast_summary(repo: Path, start: int, rows: list[dict]):
    """Compute resumable state and next arm for the 6-trial TPS-2000 fast probe."""
    del repo  # signature mirrors summary
    selected = sorted((row for row in rows if _number(row) is not None and _number(row) >= start),
                      key=_number)
    result = {
        'start': start,
        'completed': len(selected),
        'budget': len(FAST_PROBE_ARMS),
        'arms': [],
        'best_arm': None,
        'next_arm': None,
        'reason': '',
    }
    numbers = [_number(row) for row in selected]
    if len(numbers) != len(set(numbers)):
        result['reason'] = 'stop: duplicate completed trial number'
        return result

    for index, row in enumerate(selected):
        if index >= len(FAST_PROBE_ARMS):
            result['reason'] = 'stop: unexpected rows beyond fast-probe budget'
            return result
        expected = FAST_PROBE_ARMS[index]
        if row.get('arm') != arm_key(expected):
            result['reason'] = f"stop: unexpected arm at {row.get('label')}; expected {arm_key(expected)}"
            return result

    arm_stats = []
    for base_arm in FAST_PROBE_BASE_ARMS:
        key = arm_key(base_arm)
        arm_rows = [row for row in selected if row.get('arm') == key]
        valid_scores = [row['score'] for row in arm_rows if _valid(row)]
        arm_stats.append({
            'arm': key,
            'attempts': len(arm_rows),
            'valid_count': len(valid_scores),
            'median_tps': median(valid_scores) if valid_scores else None,
            'best_tps': max(valid_scores) if valid_scores else None,
        })
    result['arms'] = arm_stats
    measured = [item for item in arm_stats if item['median_tps'] is not None]
    if measured:
        result['best_arm'] = max(measured, key=lambda item: (item['median_tps'], item['best_tps']))['arm']

    target = next((row for row in selected if _target(row)), None)
    if target:
        result['reason'] = (f"stop: >2000 TPS target recorded at {target['label']} "
                            f"({target['score']:.1f} tok/s)")
        return result

    if len(selected) < len(FAST_PROBE_ARMS):
        idx = len(selected)
        result['next_arm'] = FAST_PROBE_ARMS[idx]
        result['reason'] = f'fast-probe slot {idx + 1}/{len(FAST_PROBE_ARMS)}'
    else:
        result['reason'] = f'stop: completed fast-probe schedule ({len(FAST_PROBE_ARMS)} trials)'
    return result


def fast_decision(repo: Path, start: int, rows: list[dict]):
    result = fast_summary(repo, start, rows)
    return result['next_arm'], result['reason']


def format_fast_report(repo: Path, start: int, rows: list[dict], raw_dir: Path | None = None) -> str:
    data = fast_summary(repo, start, rows)
    lines = [
        f"# Fast Probe 2000 Report (start=D{start:04d})",
        f"- Completed: {data['completed']}/{data['budget']} | Status: {data['reason']}",
    ]
    if data['best_arm']:
        lines.append(f"- Current median leader: `{data['best_arm']}`")
    lines.extend(['', '| Arm | Done | Valid | Med TPS | Best TPS |', '|---|---:|---:|---:|---:|'])
    for item in data['arms']:
        med = f"{item['median_tps']:.1f}" if item['median_tps'] is not None else '—'
        best = f"{item['best_tps']:.1f}" if item['best_tps'] is not None else '—'
        lines.append(f"| `{item['arm']}` | {item['attempts']}/2 | {item['valid_count']} | {med} | {best} |")

    selected = sorted((row for row in rows if _number(row) is not None and _number(row) >= start),
                      key=_number)
    _append_diagnostics_table(lines, selected, raw_dir)
    return '\n'.join(lines) + '\n'


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--start', type=int, required=True)
    parser.add_argument('--rows', type=Path, required=True, help='completed iterations JSONL')
    parser.add_argument('--report', action='store_true', help='print Markdown report instead of JSON')
    parser.add_argument('--fast', action='store_true', help='summarize/report the 6-trial fast-probe schedule')
    parser.add_argument('--raw-dir', type=Path, help='optional raw archive directory for call diagnostics')
    args = parser.parse_args()
    rows = [json.loads(line) for line in args.rows.read_text().splitlines() if line.strip()] if args.rows.exists() else []
    if args.fast:
        if args.report:
            print(format_fast_report(args.repo, args.start, rows, args.raw_dir), end='')
        else:
            print(json.dumps(fast_summary(args.repo, args.start, rows), indent=2))
    elif args.report:
        print(format_report(args.repo, args.start, rows, args.raw_dir), end='')
    else:
        print(json.dumps(summary(args.repo, args.start, rows), indent=2))
