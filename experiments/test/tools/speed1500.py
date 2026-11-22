"""Balanced, resumable 18-session shopping comparison and independent confirmation."""
import argparse
from contextlib import ExitStack
from datetime import datetime, timedelta, timezone
import fcntl
import json
import os
from pathlib import Path
import re
from statistics import median
import subprocess
import sys
import time


TOOLS = Path(__file__).resolve().parent
REPO = TOOLS.parent
BASE = Path.home() / 'Library/Caches/cerebras-speed-bounty/2026-11-22-test/mean-2000'
ORDER = 'AFP PFA FPA APF PAF FAP'.split()
RECORD = 1354.6625976356386
KST = timezone(timedelta(hours=9))


def read(path):
    return json.loads(path.read_text())


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix('.writing')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    temp.replace(path)


def protocol():
    return dict(order=ORDER, pairs_required=4, wins_required=4, median_gain_required=100,
                product_success='at least control count', goal=1500, previous_record=RECORD,
                confirmation=['A', 'winner', 'winner', 'A'], cooldown_after_terminal_seconds=60,
                confirmation_window='later KST clock hour, at least 15 min after exploration')


def selection(exploration):
    groups = [exploration[i:i + 3] for i in range(0, 18, 3)]
    options = {}
    for arm in 'PF':
        differences = []
        for group in groups:
            pair = {r['arm']: r for r in group}
            a, b = pair.get('A'), pair.get(arm)
            if a and b and a['valid'] and b['valid']:
                differences.append(b['score'] - a['score'])
        wins = sum(d > 0 for d in differences)
        gain = median(differences) if differences else None
        products = sum(r['product_valid'] for r in exploration if r['arm'] == arm)
        controls = sum(r['product_valid'] for r in exploration if r['arm'] == 'A')
        passed = (len(exploration) == 18 and len(differences) >= 4 and wins >= 4 and
                  gain >= 100 and products >= controls)
        options[arm] = dict(paired_differences=differences, pairs=len(differences), wins=wins,
                            median_gain=gain, product_successes=products, promoted=passed)
    qualified = [arm for arm in 'PF' if options[arm]['promoted']]
    # P is the preregistered first priority if both ranking fields tie.
    winner = max(qualified, key=lambda a: (options[a]['median_gain'], options[a]['product_successes']),
                 default=None)
    return options, winner


def rows(home):
    results = []
    for slot in range(1, 23):
        path = home / 'slots' / f'{slot:03d}' / 'summary.json'
        if not path.exists():
            break
        row = read(path)
        if row['slot'] != slot or (slot <= 18 and row['arm'] != ''.join(ORDER)[slot-1]):
            raise ValueError(f'Unexpected result for slot {slot}')
        results.append(row)
    return results


def report(home):
    outcomes = rows(home)
    options, winner = selection(outcomes[:18])
    valid = [r for r in outcomes if r['valid'] and r['score'] is not None]
    best = max(valid, key=lambda r: r['score'], default=None)
    confirmation = []
    for offset in (18, 20):
        pair = outcomes[offset:offset + 2]
        if len(pair) == 2:
            a, b = sorted(pair, key=lambda r: r['arm'] != 'A')
            if a['arm'] != 'A' or b['arm'] != winner:
                raise ValueError('Unexpected confirmation pair')
            confirmation.append(b['score'] - a['score'] if a['valid'] and b['valid'] else None)
    groups = {}
    for arm in 'APF':
        group = [r for r in outcomes[:18] if r['arm'] == arm]
        scores = [r['score'] for r in group if r['valid']]
        groups[arm] = dict(sent=len(group), valid=len(scores), median=median(scores) if scores else None,
                           best=max(scores, default=None), products=sum(r['product_valid'] for r in group))
    return dict(completed=len(outcomes), groups=groups, candidates=options, winner=winner,
                confirmation_differences=confirmation,
                confirmation_pass=len(confirmation) == 2 and all(x is not None and x > 0 for x in confirmation),
                best=({key: best[key] for key in ('label', 'arm', 'score', 'ui', 'id')} if best else None),
                records=[r['label'] for r in valid if r['score'] > RECORD],
                targets=[r['label'] for r in valid if r['goal']],
                targets_pending_ui=[r['label'] for r in valid if r['score'] >= 1500
                                    and r['ui'] >= 1500 and not r['goal']])


def safe_profile(base, home, restore):
    cfg = base.parent / 'shopper-test/openclaw.json'
    profile = read(cfg)
    backup = home / 'plugins-before.json'
    installed = home / 'plugins-during.json'
    if restore:
        prior = read(backup)
        if profile.get('plugins') == prior['before']:
            return
        if profile.get('plugins') != read(installed):
            raise RuntimeError('Plugin configuration changed externally; check before restoring')
        if prior['present']:
            profile['plugins'] = prior['before']
        else:
            profile.pop('plugins', None)
        save(cfg, profile)
        return
    if profile['agents']['defaults']['model']['primary'] != 'cerebras/moonshotai-kimi-k3.1-pro-trial':
        raise RuntimeError('Unexpected benchmark model')
    receipts = home / 'receipts'
    receipts.mkdir(parents=True, exist_ok=True)
    if backup.exists():
        if profile.get('plugins') == read(installed):
            return
        if profile.get('plugins') != read(backup)['before']:
            raise RuntimeError('Cannot replace external plugin edits')
    else:
        save(backup, {'present': 'plugins' in profile, 'before': profile.get('plugins')})
    plugins = profile.setdefault('plugins', {})
    plugins['enabled'] = True
    allow = plugins.get('allow')
    if allow and 'speed1500' not in allow:
        allow.append('speed1500')
    paths = plugins.setdefault('load', {}).setdefault('paths', [])
    source = str(TOOLS / 'speed1500-plugin')
    if source not in paths:
        paths.append(source)
    plugins.setdefault('entries', {})['speed1500'] = {
        'enabled': True, 'config': {'root': str(receipts)},
        'hooks': {'allowPromptInjection': True, 'allowConversationAccess': True,
                  'timeouts': {'before_prompt_build': 60000}}}
    save(installed, plugins)
    save(cfg, profile)


def campaign(base, home):
    schedule = protocol()
    path = home / 'protocol.json'
    if path.exists() and read(path) != schedule:
        raise RuntimeError('The registered protocol changed')
    save(path, schedule)
    env = dict(os.environ, BOUNTY_ROOT=str(base.parent), BOUNTY_GATEWAY_PORT='19863',
               BOUNTY_LABEL_BASE='5000', BOUNTY_SCHEDULE='test',
               BOUNTY_RAW_ARCHIVE=str(Path.home() / 'Library/Application Support/Cerebras Speed Bounty/2026-11-22/raw-test'))
    with ExitStack() as stack:
        location = base.parent.parent
        for root in (location / '2026-11-22', location / '2026-11-22-exp2000', base.parent):
            lock = stack.enter_context((root / 'mean-2000/loop.lock').open('rb'))
            fcntl.flock(lock, (fcntl.LOCK_EX if root == base.parent else fcntl.LOCK_SH) | fcntl.LOCK_NB)
        while True:
            existing = rows(home)
            current = report(home)
            save(home / 'report.json', current)
            order = ''.join(ORDER)
            if current['winner']:
                order += 'A' + current['winner'] * 2 + 'A'
            if len(existing) == len(order):
                print(json.dumps(current, ensure_ascii=False), flush=True)
                return
            if existing:
                previous_end = existing[-1]['ended_wall'] / 1000
                start_after = previous_end + 60
                if len(existing) == 18:
                    hour = datetime.fromtimestamp(previous_end, KST).replace(minute=0, second=0, microsecond=0)
                    start_after = max(previous_end + 900, (hour + timedelta(hours=1)).timestamp())
                while time.time() < start_after:
                    time.sleep(min(5, max(0, start_after - time.time())))
            slot = len(existing) + 1
            print(f'Slot {slot}: {order[slot-1]}', flush=True)
            subprocess.run([sys.executable, '-B', str(TOOLS / 'run_speed1500.py'), '--root', str(base),
                            '--campaign', home.name, '--slot', str(slot), '--arm', order[slot-1]], env=env, check=True)
            if len(rows(home)) != slot:
                raise RuntimeError(f'Slot {slot} finished without a summary')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('install', 'restore', 'run', 'report'))
    parser.add_argument('--campaign', default='speed1500-20261122')
    args = parser.parse_args()
    if not re.fullmatch(r'speed1500-[A-Za-z0-9-]+', args.campaign):
        parser.error('Invalid campaign name')
    home = BASE / args.campaign
    os.umask(0o077)
    if args.action == 'report':
        print(json.dumps(report(home), ensure_ascii=False, indent=2))
        return
    branch = subprocess.check_output(['git', '-C', str(REPO), 'branch', '--show-current'], text=True).strip()
    if branch != 'test':
        parser.error('Use the test worktree')
    if args.action == 'run':
        campaign(BASE, home)
    else:
        safe_profile(BASE, home, args.action == 'restore')


if __name__ == '__main__':
    main()
