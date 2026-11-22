"""Keep the sequential benchmark running in this macOS login session."""
import argparse
from datetime import datetime, timezone
import fcntl
import http.client
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

from preflight_recovery import verify_preflight


REPO = Path(__file__).resolve().parents[1]
CACHE = Path.home() / 'Library/Caches/cerebras-speed-bounty/2026-11-22/mean-2000'
LABEL = 'local.cerebras.speed-bounty.20261122'
LAUNCHCTL = '/bin/launchctl'


def read(path):
    return json.loads(path.read_bytes())


def controller_active(cache):
    with (cache / 'loop.lock').open('rb') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return True
        return False


def gateway_ready():
    client = http.client.HTTPConnection('127.0.0.1', 19862, timeout=3)
    try:
        client.request('GET', '/health')
        response = client.getresponse()
        return response.status == 200 and json.loads(response.read(512)).get('ok') is True
    except (OSError, ValueError, http.client.HTTPException):
        return False
    finally:
        client.close()


def next_action(repo, cache):
    if (cache / 'stop-requested').exists():
        return 'stop', 'user stop requested'
    if controller_active(cache):
        return 'wait', 'existing controller owns the run lock'
    # A run may have ended between the Git commit and the history append.
    # Check both stores before allowing any new provider request.
    status = read(cache / 'status.json')
    history = [json.loads(line) for line in (cache / 'iterations.jsonl').read_text().splitlines() if line]
    if any(row.get('goal') and row.get('recorded_video') for row in history):
        return 'stop', 'target recorded in iteration history'
    closed = set()
    sealed = set()
    waiting = None
    latest_plan_number, latest_plan_id = -1, None
    for plan in (repo / 'runs').glob('*/plan.json'):
        directory = plan.parent
        label = read(plan).get('label', '')
        match = re.fullmatch(r'D(\d+)-[a-z0-9-]+', label)
        if match and int(match[1]) > latest_plan_number:
            latest_plan_number, latest_plan_id = int(match[1]), directory.name
        evidence = directory / 'evidence.json'
        if not evidence.is_file():
            receipt = directory / 'preflight.json'
            if receipt.is_file():
                try:
                    verify_preflight(repo, cache, directory.name)
                except (OSError, ValueError, subprocess.SubprocessError):
                    waiting = 'preflight no-send receipt needs review: ' + directory.name
                else:
                    sealed.add(directory.name)
                continue
            waiting = 'committed trial awaits final evidence: ' + directory.name
            continue
        record = read(evidence)
        validation = record['validation']
        if validation.get('target_met'):
            if record['evidence_status'] == 'complete':
                return 'stop', 'verified target in Git evidence: ' + directory.name
            waiting = 'target recording awaits verification: ' + directory.name
        if not record['historical']:
            closed.add(record['id'])
    if waiting:
        return 'wait', waiting
    if closed != {row['id'] for row in history}:
        return 'wait', 'Git and private history have not been reconciled'
    if next((cache / 'runs').glob('*.pending.json'), None):
        return 'wait', 'gateway run has no recorded terminal acknowledgement'
    phase = status.get('phase')
    if (phase == 'result' and (not history or status.get('id') != history[-1]['id'])) or (
            phase == 'preflight_aborted' and (status.get('id') not in sealed or status.get('id') != latest_plan_id)) or (
            phase not in ('result', 'preflight_aborted')):
        return 'wait', 'last controller state needs review: ' + str(status.get('phase'))
    failures = 0
    for row in reversed(history):
        if row['valid']:
            break
        failures += 1
    if failures:
        raw = read(cache / 'runs' / (history[-1]['label'] + '.json'))
        messages = [m for m in raw['history']['messages'] if m.get('stopReason') == 'error']
        errors = ' '.join(json.dumps(m.get(k, '')).lower() for m in messages for k in ('errorMessage', 'content'))
        if any(term in errors for term in ('insufficient_quota', 'insufficient quota', 'billing', 'daily limit', 'daily quota', 'payment required', 'quota exceeded', 'quota exhausted', 'unauthorized', 'invalid api key', 'permission denied')):
            return 'wait', 'last provider response requires account or quota review'
    cooldown = 45 if phase == 'preflight_aborted' else (30 * 2 ** min(failures, 4) if failures else 15)
    ended = datetime.fromisoformat(status['time'])
    if (datetime.now(timezone.utc) - ended).total_seconds() < cooldown:
        return 'wait', 'controller cooldown is still in effect'
    if not gateway_ready():
        return 'wait', 'dedicated local gateway is offline'
    return 'resume', 'previous trial finalized and gateway ready'


def submit():
    domain = f'gui/{os.getuid()}/{LABEL}'
    if subprocess.run([LAUNCHCTL, 'print', domain], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0:
        print('Already registered: ' + domain)
        return
    bins = []
    for name in ('node', 'ffmpeg', 'ffprobe', 'git'):
        binary = shutil.which(name)
        if not binary:
            raise SystemExit('Missing runtime executable: ' + name)
        bins.append(str(Path(binary).absolute().parent))
    runtime_path = ':'.join(dict.fromkeys([*bins, '/usr/bin', '/bin', '/usr/sbin', '/sbin']))
    log = CACHE / 'supervisor.log'
    log.touch(mode=0o600, exist_ok=True)
    subprocess.run([LAUNCHCTL, 'submit', '-l', LABEL, '-o', str(log), '-e', str(log), '--',
                    sys.executable, '-u', str(Path(__file__).resolve()), '--runtime-path', runtime_path], check=True)
    print('Registered: ' + domain)


def supervise():
    with (CACHE / 'supervisor.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return
        last = None
        while True:
            try:
                action, reason = next_action(REPO, CACHE)
            except (OSError, ValueError, KeyError, IndexError, TypeError) as exc:
                action, reason = 'wait', 'evidence unavailable: ' + type(exc).__name__
            if (action, reason) != last:
                print(datetime.now(timezone.utc).isoformat(), action, reason, flush=True)
                last = (action, reason)
            if action == 'stop':
                return
            if action == 'resume':
                subprocess.run([sys.executable, '-u', str(REPO / 'tools/loop.py')], cwd=REPO)
            time.sleep(45)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--submit', action='store_true', help='register this supervisor in the current macOS login')
    parser.add_argument('--status', action='store_true', help='display the decision without submitting or starting trials')
    parser.add_argument('--runtime-path', help=argparse.SUPPRESS)
    args = parser.parse_args()
    os.umask(0o077)
    if args.runtime_path:
        os.environ['PATH'] = args.runtime_path
    if args.submit:
        submit()
    elif args.status:
        print(*next_action(REPO, CACHE))
    else:
        supervise()
