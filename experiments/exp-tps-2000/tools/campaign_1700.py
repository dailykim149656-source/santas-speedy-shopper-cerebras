"""Offline, resumable AB/BA campaign scheduling; never sends requests or writes markers."""
import argparse
import json
import math
from pathlib import Path
import re
from statistics import median

from variants import arm_key

CONTROL = 'synth-five-categories-cap'
PHASES = ((CONTROL, 'synth-five-categories-cap-4000'),
          ('synth-six-sorted', 'synth-six-sorted-pages'))
ORDER = 'ABBABAAB'


def _arm(name):
    return (name, .2, 'low')


def _number(row):
    match = re.fullmatch(r'D(\d+)-.+', row.get('label', ''))
    return int(match[1]) if match else None


def _finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def _valid(row):
    return row.get('valid') is True and row.get('method_valid') is True and _finite(row.get('score'))


def _target(row):
    return (_valid(row) and row.get('recorded_video') is True
            and _finite(row.get('ui')) and row['score'] >= 1700 and row['ui'] >= 1700)


def _candidates(repo, row):
    """Order actual results by planned URL, independent of parallel completion order."""
    ident = row.get('id', '')
    if not isinstance(ident, str) or not ident or Path(ident).name != ident:
        return None, 'invalid run id'
    try:
        directory = repo / 'runs' / ident
        plan = json.loads((directory / 'plan.json').read_text())
        evidence = json.loads((directory / 'evidence.json').read_text())
        urls = []
        for line in plan['prompt'].splitlines():
            if line.strip().startswith('{'):
                urls.append(json.loads(line)['url'])
        expected_lengths = [6] if row['arm'] == arm_key(_arm(PHASES[1][0])) else [3, 3]
        sources = evidence['retail_sources']
        if len(urls) != len(expected_lengths) or len(set(urls)) != len(urls) or len(sources) != len(urls):
            return None, 'unexpected planned or actual page count'
        result = []
        for url, size in zip(urls, expected_lengths):
            matches = [source for source in sources if source.get('url') == url]
            if len(matches) != 1 or matches[0].get('accepted') is not True:
                return None, 'missing, duplicate, or rejected planned source'
            products = matches[0].get('products')
            if not isinstance(products, list) or len(products) != size:
                return None, 'actual page does not contain expected candidate count'
            if any(not isinstance(product, str) or not product.startswith('https://') for product in products):
                return None, 'nonconcrete candidate URL'
            result.extend(products)
        if len(result) != 6 or len(set(result)) != 6:
            return None, 'candidate list is not six distinct products'
        return result, None
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return None, 'unreadable candidate evidence or plan'


def _phase_summary(repo, rows, phase):
    names = PHASES[phase]
    counts = {side: sum(row.get('valid') is True for row in rows
                        if row.get('arm') == arm_key(_arm(names[index])))
              for index, side in enumerate('AB')}
    pairs = []
    for offset in range(0, len(rows) - 1, 2):
        first, second = rows[offset:offset + 2]
        a, b = (first, second) if ORDER[offset] == 'A' else (second, first)
        pair = {'a': a['label'], 'b': b['label'], 'valid': _valid(a) and _valid(b),
                'difference_tps': None, 'audit': []}
        if phase == 1:
            ca, ea = _candidates(repo, a)
            cb, eb = _candidates(repo, b)
            pair['candidates_a'], pair['candidates_b'] = ca, cb
            if ea or eb or ca != cb:
                pair['valid'] = False
                pair['audit'] = [reason for reason in (ea, eb, 'ordered candidates differ' if ca != cb else None) if reason]
        if pair['valid']:
            pair['difference_tps'] = b['score'] - a['score']
        pairs.append(pair)
    differences = [pair['difference_tps'] for pair in pairs if pair['valid']]
    advantage = median(differences) if differences else None
    wins = sum(value > 0 for value in differences)
    reasons = []
    if len(rows) != 8:
        reasons.append('phase incomplete')
    if len(differences) < 3:
        reasons.append('fewer than three valid pairs')
    if wins < 3:
        reasons.append('fewer than three wins')
    if advantage is None or advantage < 100:
        reasons.append('median paired advantage below 100 TPS')
    if counts['B'] < counts['A']:
        reasons.append('shopping validity count below control')
    return {'phase': phase + 1, 'candidate': names[1], 'pairs': pairs,
            'valid_pairs': len(differences), 'wins': wins, 'median_advantage_tps': advantage,
            'shopping_valid_counts': counts, 'qualified': not reasons, 'reasons': reasons}


def summary(repo: Path, start: int, rows: list[dict]):
    """Completed rows include failed outcomes; preflight-only plans are not rows."""
    selected = sorted((row for row in rows if _number(row) is not None and _number(row) >= start),
                      key=_number)
    result = {'start': start, 'completed': len(selected), 'phases': [], 'promotion': None,
              'next_arm': None, 'reason': ''}
    numbers = [_number(row) for row in selected]
    if len(numbers) != len(set(numbers)):
        result['reason'] = 'stop: duplicate completed trial number'
        return result
    for index, row in enumerate(selected[:16]):
        expected = _arm(PHASES[index // 8]['AB'.index(ORDER[index % 8])])
        if row.get('arm') != arm_key(expected):
            result['reason'] = f"stop: unexpected arm at {row['label']}; expected {arm_key(expected)}"
            return result
    result['phases'] = [_phase_summary(repo, selected[p * 8:(p + 1) * 8], p) for p in range(2)]
    qualified = [phase for phase in result['phases'] if phase['qualified']]
    if qualified:
        result['promotion'] = max(qualified, key=lambda phase: phase['median_advantage_tps'])['candidate']
    for index, row in enumerate(selected[16:]):
        if index >= 4 or result['promotion'] is None:
            result['reason'] = 'stop: unexpected rows beyond campaign allocation'
            return result
        expected = _arm(CONTROL if ORDER[index] == 'A' else result['promotion'])
        if row.get('arm') != arm_key(expected):
            result['reason'] = f"stop: unexpected arm at {row['label']}; expected {arm_key(expected)}"
            return result
    target = next((row for row in selected if _target(row)), None)
    if target:
        result['reason'] = f"stop: target recorded at {target['label']}; final raw/hash/video verification required"
    elif len(selected) < 16:
        index = len(selected)
        result['next_arm'] = _arm(PHASES[index // 8]['AB'.index(ORDER[index % 8])])
        result['reason'] = f'phase {index // 8 + 1}, slot {index % 8 + 1}/8'
    elif result['promotion'] is None:
        result['reason'] = 'stop: neither changed arm meets promotion criteria'
    elif len(selected) < 20:
        index = len(selected) - 16
        result['next_arm'] = _arm(CONTROL if ORDER[index] == 'A' else result['promotion'])
        result['reason'] = f'phase 3, slot {index + 1}/4; promoted {result["promotion"]}'
    else:
        result['reason'] = 'stop: completed maximum 20 trials'
    return result


def decision(repo: Path, start: int, rows: list[dict]):
    result = summary(repo, start, rows)
    return result['next_arm'], result['reason']


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--start', type=int, required=True)
    parser.add_argument('--rows', type=Path, required=True, help='completed iterations JSONL')
    args = parser.parse_args()
    rows = [json.loads(line) for line in args.rows.read_text().splitlines() if line.strip()]
    print(json.dumps(summary(args.repo, args.start, rows), indent=2))
