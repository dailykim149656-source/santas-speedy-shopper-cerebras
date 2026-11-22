"""One-time approved handoff for the crossover at a completed trial boundary."""
import fcntl
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone


base = Path(__file__).resolve().parent
cache = base.parent
repo = Path(os.environ.get("BOUNTY_TEST_REPO", Path.cwd()))
stop = cache / 'stop-requested'
owner = 'd5027-supervisor-ca1d5947-c445-4139-9f62-f1b29e640ddf'
pid = 69026


def read(path):
    return json.loads(path.read_bytes())


def held(path):
    with path.open('rb') as file:
        try:
            fcntl.flock(file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return True
    return False


def history():
    return [json.loads(row) for row in (cache / 'iterations.jsonl').read_bytes().splitlines() if row.strip()]


def main():
    if stop.exists() or (base / 'cadence-config.json').exists():
        raise RuntimeError('unexpected incumbent control')
    for unused in range(1800):
        if stop.exists() or not held(base/'supervisor.lock'):
            raise RuntimeError('control changed while waiting')
        phase = read(cache/'status.json')
        if phase.get('phase') == 'result' and not held(cache/'loop.lock'):
            rows = history()
            if rows[-1]['id'] == phase['id']:
                end = read(repo / 'runs' / phase['id'] / 'evidence.json')['ended']['time'] / 1000
                # The active baseline parent cannot dispatch during this window.
                if time.time() < end + 57 and not (rows[-1].get('score') or 0) > 1500:
                    break
        time.sleep(.5)
    else:
        raise RuntimeError('no completed boundary in 15 minutes')
    live = subprocess.check_output(['ps','-p',str(pid),'-o','command=']).decode().strip()
    if not live.endswith(' -B -u ' + str(base/'supervisor.py')):
        raise RuntimeError('incumbent process identity changed')
    print('handoff boundary', phase['label'], len(rows), flush=True)
    os.kill(pid, signal.SIGTERM)
    for unused in range(100):
        if not held(base/'supervisor.lock'):
            break
        time.sleep(.2)
    else:
        raise RuntimeError('old supervisor still owns lock')
    receipt = read(stop)
    if receipt['owner'] != owner or receipt['reason'] != 'supervisor signal 15' or held(cache/'loop.lock'):
        raise RuntimeError('stop receipt or loop owner changed')
    if history()[-1]['id'] != phase['id']:
        raise RuntimeError('history moved during handoff')
    with (base/'cadence-config.json').open('x') as file:
        json.dump({'version':1, 'enabled':True, 'order_seconds':[30,60,60,30,60,30,30,60],
                   'history_start':len(rows), 'cutoff':'2026-11-23T02:53:00+09:00',
                   'activated_at':datetime.now(timezone.utc).isoformat(), 'anchor_id':phase['id']},file,indent=2)
        file.write('\n')
        file.flush()
        os.fsync(file.fileno())
    receipt_copy = base/'cadence-handoff-stop.json'
    os.link(stop, receipt_copy)
    stop.unlink()
    print('starting crossover supervisor', flush=True)
    os.execv(sys.executable, [sys.executable,'-B','-u',str(base/'supervisor.py')])


if __name__ == '__main__':
    main()
