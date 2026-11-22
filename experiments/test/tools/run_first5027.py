"""Run the approved first-call comparison while reserving the other two local campaigns."""
import argparse
from contextlib import ExitStack, contextmanager
from datetime import datetime
import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import loop
from first5027 import summary


def event(path, kind, **values):
    record = dict(event=kind, at_ms=time.time_ns() // 1_000_000, pid=os.getpid(), **values)
    with path.open('a') as out:
        out.write(json.dumps(record) + '\n')
        out.flush()
        os.fsync(out.fileno())
    print(json.dumps(record), flush=True)


def exp_finished(cache):
    state_path = cache / 'status.json'
    state = loop.get(state_path) if state_path.exists() else {}
    if state.get('phase') == 'user_stop':
        return True
    if state.get('phase') == 'campaign_2000_stopped' and state.get('first') == 6001:
        return True
    # A --once driver may leave its last status at result. Use its own read-only scheduler.
    history = cache / 'iterations.jsonl'
    if state.get('phase') != 'result' or not history.exists():
        return False
    rows = [json.loads(line) for line in history.read_text().splitlines() if line.strip()]
    if len(rows) < 20 and not any((r.get('score') or 0) > 2000 and r.get('recorded_video') for r in rows):
        return False
    repo = loop.REPO.parent / 'speed-bounty-evidence-2000'
    output = subprocess.check_output([sys.executable, '-B', str(repo / 'tools/campaign_2000.py'),
                                      '--repo', str(repo), '--start', '6001', '--rows', str(history)])
    result = json.loads(output)
    return result['next_arm'] is None and result['reason'].startswith(
        ('stop: completed maximum 20 trials', 'stop: >2000 TPS target recorded'))


@contextmanager
def reservation(locks, receipt, *, exp_ready=None):
    """Main and exp use exclusive flock for the entire model run, including retries."""
    previous = None
    while True:
        exp_cache = next((path.parent for name, path, _ in locks if name == 'exp-tps-2000'), None)
        if exp_ready is not None and exp_cache is not None and not exp_ready(exp_cache):
            if previous != 'exp campaign completion':
                event(receipt, 'waiting', owner='exp campaign completion')
            previous = 'exp campaign completion'
            time.sleep(10)
            continue
        with ExitStack() as stack:
            descriptors = []
            for name, path, mode in locks:
                lock = stack.enter_context(path.open('rb'))
                try:
                    fcntl.flock(lock, mode | fcntl.LOCK_NB)
                except BlockingIOError:
                    if previous != name:
                        event(receipt, 'waiting', owner=name)
                    previous = name
                    break
                if name == 'exp-tps-2000' and exp_ready is not None and not exp_ready(path.parent):
                    if previous != 'exp campaign completion':
                        event(receipt, 'waiting', owner='exp campaign completion')
                    previous = 'exp campaign completion'
                    break
                descriptors.append(lock.fileno())
            else:
                event(receipt, 'reserved', locks=[str(p) for _, p, _ in locks])
                try:
                    yield tuple(descriptors)
                finally:
                    event(receipt, 'releasing')
                return
        time.sleep(3)


def foreign_end(cache):
    """Refuse a new send if a previous foreign send has no terminal evidence."""
    target = cache / 'runs'
    for pending in target.glob('*.pending.json'):
        label = pending.name.removesuffix('.pending.json')
        ident = loop.get(pending)['id']
        files = (target / (label + '.json'), target / (label + '.terminal.json'))
        if not any(p.is_file() and loop.get(p).get('id') == ident and
                   loop.get(p).get('ended', {}).get('terminal') in ('final', 'aborted', 'error')
                   for p in files):
            raise RuntimeError('Foreign send needs reconciliation before test: ' + label)
    latest = 0
    for path in target.glob('*.json'):
        if path.name.count('.') != 1 and not path.name.endswith('.terminal.json'):
            continue
        ended = loop.get(path).get('ended', {})
        latest = max(latest, ended.get('time') or 0)
    return latest / 1000


def unfinished(start, completed):
    for path in (loop.REPO / 'runs').glob('*/plan.json'):
        plan = loop.get(path)
        if not plan['label'].startswith('D') or int(plan['label'].split('-')[0][1:]) < start:
            continue
        if plan['id'] not in completed and not path.with_name('preflight.json').exists():
            return plan
    return None


def run(start, locks, receipt):
    prefix = f'first5027-{start}'
    state_path = loop.CACHE / (prefix + '-backoff.json')
    pool = [p.parent for name, p, _ in locks if name != 'test']
    with reservation(locks, receipt, exp_ready=exp_finished) as fds:
        latest_foreign = max(foreign_end(cache) for cache in pool)
        while True:
            rows = loop.past()
            data = summary(loop.REPO, start, rows)
            arm = data['next_arm']
            if arm is None:
                loop.status('first5027_stopped', first=start, reason=data['reason'])
                return
            if (loop.CACHE / 'stop-requested').exists():
                loop.status('user_stop', first=start)
                return
            orphan = unfinished(start, {r['id'] for r in rows})
            if orphan:
                raise RuntimeError('Reconcile the existing test plan before a new send: ' + orphan['label'])
            latest = rows[-1] if rows else None
            deadline = latest_foreign + 60
            if latest:
                last_end = loop.get(loop.REPO / 'runs' / latest['id'] / 'evidence.json')['ended']['time'] / 1000
                failures = 0
                for row in reversed(rows):
                    if row['valid']:
                        break
                    failures += 1
                deadline = max(deadline, last_end + max(60, 30 * 2 ** min(failures, 4)))
                number = data['completed']
                backoff = loop.get(state_path) if state_path.exists() else {}
                if (data['terminal_429_streak'] >= 2 and
                        number - backoff.get('after_slot', 0) >= 2):
                    backoff = dict(after_slot=number, last_id=latest['id'], until=last_end + 600)
                    loop.put(state_path, backoff)
                    event(receipt, 'terminal_429_pause', **backoff)
                deadline = max(deadline, backoff.get('until', 0))
            status_path = loop.CACHE / 'status.json'
            status = loop.get(status_path) if status_path.exists() else {}
            if status.get('phase') == 'preflight_aborted':
                deadline = max(deadline, datetime.fromisoformat(status['time']).timestamp() + 45)
            remaining = deadline - time.time()
            if remaining > 0:
                time.sleep(min(remaining, 30))
                continue
            n = loop.next_trial_number()
            event(receipt, 'trial_reserved', number=n, slot=data['completed'] + 1, arm=arm[0])
            loop.run_trial(n, arm, score_first=True, first5027=True, lock_fds=fds)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--start', required=True, type=int)
    args = parser.parse_args()
    if (not loop.TEST_SCHEDULE or args.start <= loop.LABEL_BASE
            or loop.ROOT != loop.MAIN_ROOT.with_name('2026-11-22-test')
            or os.environ.get('BOUNTY_GATEWAY_PORT') != '19863'
            or subprocess.check_output(['git', '-C', str(loop.REPO), 'branch', '--show-current'],
                                       text=True).strip() != 'test'):
        parser.error('Use the isolated test branch, cache and gateway')
    os.umask(0o077)
    exp = loop.MAIN_ROOT.with_name('2026-11-22-exp2000') / 'mean-2000'
    locks = [('exp-tps-2000', exp / 'loop.lock', fcntl.LOCK_SH),
             ('main', loop.MAIN_ROOT / 'mean-2000/loop.lock', fcntl.LOCK_SH),
             ('test', loop.CACHE / 'loop.lock', fcntl.LOCK_EX)]
    receipt = loop.CACHE / f'first5027-{args.start}-reservation.jsonl'
    try:
        run(args.start, locks, receipt)
    except (RuntimeError, OSError, ValueError, subprocess.SubprocessError) as error:
        event(receipt, 'needs_attention', reason=str(error)[:500])
        raise


if __name__ == '__main__':
    main()
