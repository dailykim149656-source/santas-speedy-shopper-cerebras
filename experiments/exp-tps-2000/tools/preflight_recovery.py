#!/usr/bin/env python3
"""Seal a committed trial that failed before the recorder allowed chat.send.

This is deliberately separate from a scored result. A missing or uncertain
send acknowledgement must never be converted into a zero-score trial.
"""
import argparse
from datetime import datetime, timezone
import fcntl
import hashlib
import json
from pathlib import Path
import re
import subprocess
import uuid

from export_bundle import publish
from ledger import atomic, commit


REPO = Path(__file__).resolve().parents[1]
CACHE = Path.home() / 'Library/Caches/cerebras-speed-bounty/2026-11-22/mean-2000'
GUARD = "if(!ready)throw Error('Recorder not ready; no chat request sent')"
SEND = "req('chat.send'"


def read(path):
    return json.loads(path.read_bytes())


def git(repo, *args):
    return subprocess.check_output(['git', '-C', str(repo), *args], stderr=subprocess.PIPE)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def active_children(ident):
    """Inspect live processes rather than trusting a stale lock or status file."""
    listing = subprocess.check_output(['ps', '-A', '-o', 'command='], text=True)
    return [line for line in listing.splitlines()
            if ident in line and ('/tools/run.mjs ' in line or '/tools/record.mjs ' in line)]


def paths(repo, cache, ident):
    uuid.UUID(ident)
    if str(uuid.UUID(ident)) != ident:
        raise ValueError('Noncanonical preflight run ID')
    plan = repo / 'runs' / ident / 'plan.json'
    if not plan.is_file() or plan.is_symlink():
        raise ValueError('Committed plan is missing or unsafe')
    detail = read(plan)
    label = detail.get('label')
    if detail.get('id') != ident or not isinstance(label, str) or not re.fullmatch(r'D\d{4,}-[a-z0-9-]+', label):
        raise ValueError('Preflight plan identity mismatch')
    scratch = cache / 'capture' / ident
    return plan, detail, label, scratch


def source_guard(repo, plan_commit):
    source = git(repo, 'show', f'{plan_commit}:tools/run.mjs')
    before, send = source.find(GUARD.encode()), source.find(SEND.encode())
    if before < 0 or send < 0 or before >= send:
        raise ValueError('Committed runner does not prove recorder readiness gates chat.send')
    return sha(source)


def unsent_inputs(repo, cache, ident):
    plan_path, plan, label, scratch = paths(repo, cache, ident)
    relative = f'runs/{ident}/plan.json'
    plan_commit = git(repo, 'log', '-1', '--format=%H', '--', relative).decode().strip()
    if not plan_commit or git(repo, 'show', f'{plan_commit}:{relative}') != plan_path.read_bytes():
        raise ValueError('Preflight plan is not the committed version')
    runner_sha = source_guard(repo, plan_commit)
    run_config = scratch / 'run.json'
    if not run_config.is_file() or run_config.is_symlink():
        raise ValueError('Private runner inputs are missing or unsafe')
    config = read(run_config)
    if any(config.get(key) != plan.get(key) for key in ('id', 'label', 'sessionKey', 'prompt')):
        raise ValueError('Private runner inputs differ from the committed plan')
    if config.get('readyPath') != str(scratch / 'ready.json'):
        raise ValueError('Private runner readiness path differs from the recorder path')
    forbidden = (scratch / 'ready.json', scratch / 'finish.json',
                 cache / 'runs' / f'{label}.pending.json', cache / 'runs' / f'{label}.json',
                 repo / 'runs' / ident / 'evidence.json')
    if any(path.exists() or path.is_symlink() for path in forbidden):
        raise ValueError('Readiness, pending request, result, or scored evidence exists; send state needs review')
    if active_children(ident):
        raise ValueError('Runner or recorder remains live; send state needs review')
    return plan_path, plan, label, scratch, plan_commit, runner_sha, run_config


def private_digests(scratch, run_config):
    files = {'run.json': run_config}
    for name in ('run.log', 'video.log', 'error.json', 'status.json'):
        path = scratch / name
        if path.exists():
            if not path.is_file() or path.is_symlink():
                raise ValueError('Unsafe private preflight source: ' + name)
            files[name] = path
    return {name: sha(path.read_bytes()) for name, path in files.items()}


def verify_preflight(repo, cache, ident):
    plan_path, plan, label, scratch, plan_commit, runner_sha, run_config = unsent_inputs(repo, cache, ident)
    receipt_path = plan_path.with_name('preflight.json')
    if not receipt_path.is_file() or receipt_path.is_symlink():
        raise ValueError('Committed preflight receipt is missing or unsafe')
    receipt_bytes = receipt_path.read_bytes()
    if git(repo, 'show', f'HEAD:runs/{ident}/preflight.json') != receipt_bytes:
        raise ValueError('Preflight receipt differs from Git')
    receipt = json.loads(receipt_bytes)
    if (receipt.get('schema_version') != 1 or receipt.get('status') != 'aborted_before_send'
            or receipt.get('id') != ident or receipt.get('label') != label
            or receipt.get('sessionKey') != plan['sessionKey']
            or receipt.get('plan_commit') != plan_commit
            or receipt.get('runner_sha256') != runner_sha
            or receipt.get('private_sources_sha256') != private_digests(scratch, run_config)):
        raise ValueError('Preflight receipt content does not match private no-send proof')
    return receipt


def seal_unsent(repo, cache, ident, cause):
    plan_path, plan, label, scratch, plan_commit, runner_sha, run_config = unsent_inputs(repo, cache, ident)
    receipt_path = plan_path.with_name('preflight.json')
    if receipt_path.exists():
        receipt = verify_preflight(repo, cache, ident)
    else:
        receipt = {
            'schema_version': 1, 'status': 'aborted_before_send',
            'id': ident, 'label': label, 'sessionKey': plan['sessionKey'],
            'plan_commit': plan_commit, 'runner_sha256': runner_sha,
            'private_sources_sha256': private_digests(scratch, run_config),
            'cause_class': cause, 'sealed_at': datetime.now(timezone.utc).isoformat(),
        }
        atomic(receipt_path, (json.dumps(receipt, ensure_ascii=False, indent=2) + '\n').encode())
        commit(repo, [receipt_path], 'Seal unsent preflight ' + ident)
        verify_preflight(repo, cache, ident)
    publish(repo)
    state = {'phase': 'preflight_aborted', 'id': ident, 'label': label,
             'receipt_commit': git(repo, 'log', '-1', '--format=%H', '--', f'runs/{ident}/preflight.json').decode().strip(),
             'time': datetime.now(timezone.utc).isoformat()}
    atomic(cache / 'status.json', (json.dumps(state, ensure_ascii=False, indent=2) + '\n').encode())
    return state


def controller_active(cache):
    with (cache / 'loop.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return True
    return False


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    parser.add_argument('--repo', type=Path, default=REPO)
    parser.add_argument('--cache', type=Path, default=CACHE)
    args = parser.parse_args()
    if controller_active(args.cache):
        raise SystemExit('Controller is still live; do not seal an uncertain preflight')
    state = read(args.cache / 'status.json')
    if state.get('phase') not in ('needs_attention', 'preflight_aborted'):
        raise SystemExit('Controller status is not an ended preflight')
    print(json.dumps(seal_unsent(args.repo, args.cache, args.run_id, 'recorder_preflight_error')))


if __name__ == '__main__':
    main()
