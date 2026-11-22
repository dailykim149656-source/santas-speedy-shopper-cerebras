#!/usr/bin/env python3
"""Bounded sequential D5027 supervisor. Importing this module never starts work.

Only main() dispatches real loop.py --once. Existing stop markers are never
removed. A seven-minute preparation margin covers the runner's 3 s reload,
100 s session wait and 260 s recorder wait; cooldown is completed here first.
run.mjs has no stop-before-send check: already-dispatched work is allowed to
finish and an uncertain send always returns control to the human/root agent.
"""
from contextlib import ExitStack
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import threading
import time
import uuid

sys.dont_write_bytecode = True
from cadence import Cadence
from longgap import LongGap, activate_pending
from required_ab import RequiredAB, check_plan, check_wire

REPO = Path(os.environ.get("BOUNTY_TEST_REPO", Path.cwd()))
CAMPAIGN_DIR = Path(__file__).resolve().parent
CACHE = CAMPAIGN_DIR.parent
ROOT = CACHE.parent
RAW = Path.home() / 'Library/Application Support/Cerebras Speed Bounty/2026-11-22/raw-test'
PREPARATION_MARGIN = 420
POLL_SECONDS = 0.5


def read(path):
    return json.loads(path.read_bytes())


def event(kind, **fields):
    print(json.dumps(dict(time=datetime.now(timezone.utc).isoformat(), supervisor=kind, **fields)), flush=True)


def git(*args):
    return subprocess.check_output(['git', '--no-optional-locks', '-C', str(REPO), *args], stderr=subprocess.PIPE, timeout=30)


def owned_stop(path, owner, reason):
    """Exclusive creation preserves foreign markers, including dangling symlinks."""
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        return False
    with os.fdopen(fd, 'w') as out:
        json.dump({'owner': owner, 'reason': reason, 'time': datetime.now(timezone.utc).isoformat()}, out)
        out.write('\n')
        out.flush()
        os.fsync(out.fileno())
    return True


def controls(cache, cutoff, now=None):
    if os.path.lexists(cache / 'stop-requested'):
        return 'stop-requested'
    if not all((cache / name).is_file() for name in ('focus-d5027', 'relay-control')):
        return 'required focus-d5027/relay-control marker changed'
    if (time.time() if now is None else now) >= cutoff:
        return 'deadline preparation cutoff'
    return None


def monitor(cache, cutoff, owner, done, stopped):
    """Runs independently of blocking child, verification, or cooldown operations."""
    while not done.is_set():
        reason = controls(cache, cutoff)
        if reason:
            owned_stop(cache / 'stop-requested', owner, reason)
            stopped.set()
            return
        done.wait(POLL_SECONDS)


def history():
    return [json.loads(line) for line in (CACHE / 'iterations.jsonl').read_text().splitlines() if line.strip()]


def cooldown_until(rows, status, post_success_seconds=None):
    until = 0
    if status.get('phase') == 'preflight_aborted':
        until = datetime.fromisoformat(status['time']).timestamp() + 45
    if rows:
        failed = limited = 0
        for row in reversed(rows):
            if row['valid']:
                break
            if row.get('rate_limited'):
                limited += 1
            else:
                failed += 1
        cooldown = max(60, 30 * 2 ** min(failed, 4))
        if rows[-1].get('rate_limited'):
            cooldown = max(60 if limited < 3 else 120, 30 * 2 ** min(failed, 4) if failed else 0)
        if post_success_seconds is not None:
            if post_success_seconds not in (30, 60, 90) or not cadence_eligible(rows[-1]):
                raise RuntimeError('ineligible post-success cadence override')
            cooldown = post_success_seconds
        last = read(REPO / 'runs' / rows[-1]['id'] / 'evidence.json')
        until = max(until, last['ended']['time'] / 1000 + cooldown)
    return until


def cadence_eligible(row):
    if not (row.get('arm') == 'synth-five-categories-cap|0.2|low'
            and row.get('valid') is True and row.get('method_valid') is True
            and row.get('rate_limited') is False
            and type(row.get('call_count')) is int and row['call_count'] == 2
            and row.get('relay_phases') == ['passthrough', 'passthrough']):
        return False
    plan = read(REPO / 'runs' / row['id'] / 'plan.json')
    record = committed_record(row['id'])
    return (plan.get('variant') == 'synth-five-categories-cap'
            and plan.get('experiment') == 'synth-five-categories-cap|0.2|low'
            and plan.get('capturePolicy') is None
            and plan.get('request_relay') == 'relay-v1:' + hashlib.sha256(
                (REPO / 'tools/request_relay.mjs').read_bytes()).hexdigest() + ':retry-only'
            and record['ended']['terminal'] == 'final' and record['validation']['valid'] is True
            and len(record['calls']) == 2 and all(call.get('timed_sample') is True for call in record['calls']))


def strict_candidate(row, record, threshold):
    score = record['score']['mean_exact_tps']
    return (type(score) in (int, float) and math.isfinite(score) and score > threshold
            and row.get('valid') is True and row.get('method_valid') is True
            and record['validation']['valid'] is True)


def committed_record(ident):
    name = f'runs/{ident}/evidence.json'
    payload = git('show', 'HEAD:' + name)
    if payload != (REPO / name).read_bytes():
        raise RuntimeError('working evidence differs from committed result: ' + ident)
    return json.loads(payload)


def committed_plan(ident):
    name = f'runs/{ident}/plan.json'
    data = git('show', 'HEAD:' + name)
    if data != (REPO / name).read_bytes():
        raise RuntimeError('working plan differs from committed A/B plan: ' + ident)
    return json.loads(data)


def audit_ab_outcome(row, entry, config):
    ident = row['id']
    plan, anchor = committed_plan(ident), committed_plan(config['anchor_id'])
    binding = read(CACHE / 'relay/bindings' / (ident[:8] + '.json'))
    check_plan(plan, anchor, binding, entry['mode'], config['relay_sha256'])
    record = committed_record(ident)
    if record['ended']['terminal'] not in ('final', 'error', 'aborted'):
        raise RuntimeError('A/B result is not terminal: ' + ident)
    valid = (row.get('valid') is True and row.get('method_valid') is True
             and record['validation']['valid'] is True)
    products = sum(p.get('verified') is True for p in record.get('products', []))
    calls = [c for c in record['calls'] if c.get('timed_sample')]
    wire = []
    if valid:
        if products != 5 or len(calls) != row['call_count']:
            raise RuntimeError('A/B score coverage or product count mismatch: ' + ident)
        wire = check_wire(CACHE, row, config['relay_sha256'], entry['mode'], calls)
    def rate(reason):
        for c in calls:
            if c.get('stopReason') == reason:
                g = c['serverGeneration']
                return 1000 * g['outputTokens'] / g['completionMs']
        return None
    return {'valid':valid, 'product_valid':row.get('valid'), 'method_valid':row.get('method_valid'),
            'verified_products':products, 'first_tps':rate('toolUse'), 'final_tps':rate('stop'),
            'mean_tps':record['score']['mean_exact_tps'], 'terminal':record['ended']['terminal'],
            'mode':entry['mode'], 'relay_sha256':config['relay_sha256'], 'wire':wire,
            'rate_limited':row.get('rate_limited'), 'call_count':len(calls)}


def audit_longgap_outcome(row, entry, config):
    outcome = audit_ab_outcome(row, entry, config)
    previous = committed_record(entry['previous_uuid'])
    record = committed_record(row['id'])
    started = record.get('startedWall')
    prior_started = previous.get('startedWall')
    ended = record['ended']['time']
    prior_end = previous['ended']['time']
    def seconds(later, earlier):
        if type(later) not in (int, float) or type(earlier) not in (int, float):
            return None
        return (later - earlier) / 1000
    outcome.update(actual_wait_seconds=seconds(started, prior_end),
                   start_to_start_seconds=seconds(started, prior_started),
                   cycle_seconds=seconds(ended, prior_end))
    return outcome


def current_source_hash():
    return hashlib.sha256((REPO / 'tools/request_relay.mjs').read_bytes()).hexdigest()


def candidate_arm(ident, index, ab):
    if ab is None or ab.config is None:
        return 'retry-only', current_source_hash()
    cfg = ab.config
    if index < cfg['history_start']:
        return 'retry-only', cfg['previous_relay_sha256']
    for entry in ab.state['assignments']:
        if (entry['phase'] == 'cutoff' and entry.get('cutoff_reason') == 'user_requested_minimum'
                and not entry.get('outcome') and all(a['phase'] == 'proven_presend' for a in entry['attempts'])):
            continue
        if entry['history_cursor'] == index:
            if entry.get('outcome', {}).get('run_id') != ident:
                raise RuntimeError('A/B candidate lacks reconciled assignment: ' + ident)
            return entry['mode'], cfg['relay_sha256']
    return 'retry-only', cfg['relay_sha256']


def candidate_context(plan, record, raw, binding, relay_sha, deadline, mode='retry-only'):
    if not (plan.get('variant') == 'synth-five-categories-cap'
            and plan.get('experiment') == 'synth-five-categories-cap|0.2|low'
            and plan.get('capturePolicy') is None
            and mode in ('retry-only', 'first-required')
            and plan.get('request_relay') == 'relay-v1:' + relay_sha + ':' + mode
            and binding.get('mode') == mode and binding.get('protocol') == 'relay-v1'
            and binding.get('id') == plan['id'] and binding.get('nonce') == plan['id'][:8]
            and binding.get('relay_sha256') == relay_sha):
        raise RuntimeError('candidate is not the bound D5027 arm')
    planned_urls = [json.loads(line)['url'] for line in plan['prompt'].splitlines()[1:]]
    if binding.get('urls') != planned_urls or len(planned_urls) != 5:
        raise RuntimeError('candidate relay binding URLs differ from committed plan')
    final = [m for m in raw['history']['messages']
             if m.get('role') == 'assistant' and m.get('stopReason') == 'stop']
    if not final or raw.get('id') != plan['id']:
        raise RuntimeError('candidate final transcript missing or wrong identity')
    times = [record['ended']['time'], raw['ended']['time'],
             final[-1].get('__openclaw', {}).get('recordTimestampMs', final[-1].get('timestamp'))]
    if not all(type(t) in (int, float) and math.isfinite(t) for t in times):
        raise RuntimeError('candidate final timestamp is unavailable')
    return all(t <= deadline * 1000 for t in times)


def verify_candidate(row, record, threshold):
    ident = row['id']
    result = subprocess.run([sys.executable, '-B', str(REPO / 'tools/verify_run.py'), ident,
                             '--repo', str(REPO), '--raw', str(RAW / (ident + '.json'))],
                            capture_output=True, text=True, timeout=180)
    artifact = CAMPAIGN_DIR / ('verify-' + ident + '.json')
    artifact.write_text(json.dumps({'argv': result.args, 'returncode': result.returncode,
                                    'stdout': result.stdout, 'stderr': result.stderr}, indent=2) + '\n')
    if result.returncode:
        raise RuntimeError('candidate verification failed; preserve candidate: ' + str(artifact))
    verified = json.loads(result.stdout)
    calls = record['calls']
    expected_media = {'original.mp4', 'demo.mp4', 'final.png', 'viewport-evidence.json'}
    if not (record['evidence_status'] == 'complete' and row.get('recorded_video') is True
            and verified['evidence_status'] == 'complete' and verified['mean'] > threshold
            and verified['raw_digest_checked'] is True and verified['verified_products'] == 5
            and verified['samples'] == len(calls) > 0
            and all(call.get('timed_sample') is True for call in calls)
            and isinstance(verified['checked_media'], list)
            and len(verified['checked_media']) == len(expected_media)
            and set(verified['checked_media']) == expected_media
            and math.isclose(row['score'], verified['mean'], rel_tol=1e-12)):
        raise RuntimeError('candidate missing complete media or 100% timing coverage: ' + ident)
    sys.path.insert(0, str(REPO / 'tools'))
    from research_report import one_per_source_links
    if not one_per_source_links(record):
        raise RuntimeError('candidate method does not independently validate: ' + ident)
    event('success', id=ident, mean=verified['mean'], verification=str(artifact))
    return True


def reconcile(campaign, baseline, ab=None):
    """Only campaign plans are new; historical unresolved runs remain untouched."""
    rows = history()
    if len(rows) < campaign['history_start']:
        raise RuntimeError('history truncated')
    selected = rows[campaign['history_start']:]
    by_id = {row['id']: row for row in selected}
    index_by_id = {r['id']: i for i, r in enumerate(rows)}
    if len(by_id) != len(selected):
        raise RuntimeError('duplicate campaign history run ID')
    plans = {p.parent.name: read(p) for p in (REPO / 'runs').glob('*/plan.json')
             if p.parent.name not in baseline or p.parent.name in by_id}
    if not set(by_id).issubset(plans):
        raise RuntimeError('history has no matching plan')
    sealed = set()
    for ident, plan in plans.items():
        if str(uuid.UUID(ident)) != ident or plan['id'] != ident:
            raise RuntimeError('unsafe plan ID')
        directory = REPO / 'runs' / ident
        label = plan['label']
        if not re.fullmatch(r'D\d+-[a-z0-9-]+', label):
            raise RuntimeError('unsafe plan label')
        if (CACHE / 'runs' / (label + '.pending.json')).exists():
            raise RuntimeError('unresolved send/pending run: ' + ident)
        if not (directory / 'evidence.json').exists():
            if not (directory / 'preflight.json').exists():
                raise RuntimeError('unsealed preparation or uncertain send: ' + ident)
            sys.path.insert(0, str(REPO / 'tools'))
            from preflight_recovery import verify_preflight
            verify_preflight(REPO, CACHE, ident)
            sealed.add(ident)
            continue
        record = committed_record(ident)
        if ident not in by_id:
            raise RuntimeError('committed result missing history append: ' + ident)
        row = by_id[ident]
        if record['ended']['terminal'] not in ('final', 'error', 'aborted'):
            raise RuntimeError('run lacks terminal evidence: ' + ident)
        if strict_candidate(row, record, campaign['threshold']):
            mode, trusted_sha = candidate_arm(ident, index_by_id[ident], ab)
            plan = committed_plan(ident)
            check_wire(CACHE, row, trusted_sha, mode, [c for c in record['calls'] if c.get('timed_sample')])
            on_time = candidate_context(plan, record, read(RAW / (ident + '.json')),
                                        read(CACHE / 'relay/bindings' / (ident[:8] + '.json')),
                                        trusted_sha, datetime.fromisoformat(campaign['deadline']).timestamp(), mode)
            if not on_time:
                event('late_result_retained', id=ident, mean=record['score']['mean_exact_tps'])
                continue
            if record['evidence_status'] != 'complete':
                raise RuntimeError('candidate video pending; preserve session: ' + ident)
            if verify_candidate(row, record, campaign['threshold']):
                return rows, True, sealed
        elif record['validation']['valid'] and (record['score']['mean_exact_tps'] or 0) > campaign['threshold']:
            raise RuntimeError('above-threshold candidate requires method reconciliation: ' + ident)
    return rows, False, sealed


def lock_free(path):
    with path.open('rb') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return False
    return True


def report():
    script = CAMPAIGN_DIR / 'report_trials.py'
    if script.is_file():
        try:
            result = subprocess.run([sys.executable, '-B', str(script)], cwd=CAMPAIGN_DIR, timeout=120)
            event('report', returncode=result.returncode)
        except (OSError, subprocess.TimeoutExpired) as exc:
            event('report_error', error=str(exc))


def main():
    os.umask(0o077)
    owner = 'd5027-supervisor-' + str(uuid.uuid4())
    campaign = read(CAMPAIGN_DIR / 'campaign.json')
    deadline = datetime.fromisoformat(campaign['deadline'])
    if deadline.tzinfo is None or campaign['threshold'] != 1500 or campaign['history_start'] < 0:
        raise RuntimeError('unexpected campaign settings')
    cutoff = deadline.timestamp() - PREPARATION_MARGIN
    if git('branch', '--show-current').decode().strip() != 'test':
        raise RuntimeError('expected isolated test branch')
    baseline = {line.split('/')[1] for line in git('ls-tree', '-r', '--name-only', campaign['initial_head'], '--', 'runs').decode().splitlines()
                if line.endswith('/plan.json')}
    env = dict(os.environ, BOUNTY_SCHEDULE='test', BOUNTY_ROOT=str(ROOT), BOUNTY_RAW_ARCHIVE=str(RAW),
               BOUNTY_LABEL_BASE='5000', BOUNTY_GATEWAY_PORT='19863', BOUNTY_RELAY_PORT='19871',
               BOUNTY_PROFILE_CLI=str(CACHE / 'profile.mjs'), PYTHONDONTWRITEBYTECODE='1')
    with ExitStack() as outer:
        supervisor_lock = outer.enter_context((CAMPAIGN_DIR / 'supervisor.lock').open('a'))
        fcntl.flock(supervisor_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        log = outer.enter_context((CAMPAIGN_DIR / 'runner.log').open('a', buffering=1))
        # Send supervisor and child diagnostics to the single campaign log.
        os.dup2(log.fileno(), 1)
        os.dup2(log.fileno(), 2)
        done, stopped = threading.Event(), threading.Event()
        def stop_signal(signum, frame):
            owned_stop(CACHE / 'stop-requested', owner, 'supervisor signal ' + str(signum))
            stopped.set()
        signal.signal(signal.SIGTERM, stop_signal)
        signal.signal(signal.SIGINT, stop_signal)
        watcher = threading.Thread(target=monitor, args=(CACHE, cutoff, owner, done, stopped), daemon=True)
        watcher.start()
        event('started', owner=owner, deadline=deadline.isoformat(), cutoff=datetime.fromtimestamp(cutoff, timezone.utc).isoformat())
        try:
            cadence = Cadence(CAMPAIGN_DIR, cutoff, committed_record)
            ab = RequiredAB(CAMPAIGN_DIR, cutoff, audit_ab_outcome)
            longgap = LongGap(CAMPAIGN_DIR, cutoff, audit_longgap_outcome)
            while True:
                if not lock_free(CACHE / 'loop.lock'):
                    event('return_control', reason='test loop lock is held; no automatic takeover')
                    return 2
                if cadence.state is not None:
                    cadence.reconcile_terminal(history())
                if ab.state is not None:
                    ab.reconcile_terminal(history())
                if longgap.state is not None:
                    longgap.reconcile_terminal(history())
                rows, success, sealed = reconcile(campaign, baseline, ab)
                longgap.reconcile(rows, sealed)
                ab.reconcile(rows, sealed)
                cadence.reconcile(rows, sealed)
                if success:
                    owned_stop(CACHE / 'stop-requested', owner, 'verified mean >1500')
                    report()
                    return 0
                reason = controls(CACHE, cutoff)
                if stopped.is_set() or reason:
                    if reason:
                        owned_stop(CACHE / 'stop-requested', owner, reason)
                    event('stopped', reason=reason or 'monitor stop')
                    return 0
                state = read(CACHE / 'status.json')
                if state.get('phase') not in ('result', 'preflight_aborted'):
                    raise RuntimeError('launcher state requires root reconciliation: ' + str(state.get('phase')))
                if state['phase'] == 'preflight_aborted' and state.get('id') not in sealed:
                    raise RuntimeError('latest preflight receipt not verified')
                if state['phase'] == 'result' and (not rows or state.get('id') != rows[-1]['id']):
                    raise RuntimeError('latest result/history mismatch')
                assignment = cadence.select(rows, sealed, cadence_eligible, time.time())
                source_hash = current_source_hash()
                treatment = ab.select(rows, sealed, time.time(), cadence, source_hash)
                if (longgap.state is None and activate_pending(CAMPAIGN_DIR, cutoff, rows, ab,
                        source_hash, cadence_eligible, time.time())):
                    longgap = LongGap(CAMPAIGN_DIR, cutoff, audit_longgap_outcome)
                interval = longgap.select(rows, sealed, time.time(), ab, source_hash, cadence_eligible)
                if sum(item is not None for item in (assignment, treatment, interval)) > 1:
                    raise RuntimeError('two campaigns claimed the same dispatch')
                interval_entry = interval or assignment
                remaining = cooldown_until(rows, state, interval_entry['requested_seconds'] if interval_entry else None) - time.time()
                if remaining > 0:
                    stopped.wait(max(0, min(remaining, cutoff - time.time())))
                    continue
                with ExitStack() as reservations:
                    fds = [supervisor_lock.fileno()]
                    for name in ('2026-11-22', '2026-11-22-exp2000'):
                        path = ROOT.parent / name / 'mean-2000/loop.lock'
                        lock = reservations.enter_context(path.open('rb'))
                        try:
                            fcntl.flock(lock, fcntl.LOCK_SH | fcntl.LOCK_NB)
                        except BlockingIOError:
                            event('competing_lock', path=str(path))
                            break
                        fds.append(lock.fileno())
                    else:
                        if controls(CACHE, cutoff) or stopped.is_set():
                            continue
                        before = (len(rows), frozenset(sealed))
                        command = [sys.executable, '-B', '-u', str(REPO / 'tools/loop.py'), '--once']
                        if interval_entry:
                            command += ['--d5027-post-success-seconds', str(interval_entry['requested_seconds'])]
                            allocator = longgap if interval else cadence
                            allocator.dispatch(interval_entry, rows, sealed, command, time.time())
                        if treatment:
                            if treatment['arm'] == 'B':
                                command += ['--d5027-first-required']
                            ab.dispatch(treatment, rows, sealed, command, time.time())
                        event('dispatch', command=command)
                        child = subprocess.Popen(command, cwd=REPO, env=env, stdout=log, stderr=subprocess.STDOUT,
                                                 pass_fds=tuple(fds))
                        # Never kill/restart a child whose send may have happened.
                        code = child.wait()
                        event('child_exit', returncode=code)
                        if cadence.state is not None:
                            cadence.reconcile_terminal(history())
                        if ab.state is not None:
                            ab.reconcile_terminal(history())
                        if longgap.state is not None:
                            longgap.reconcile_terminal(history())
                        after, success, sealed_after = reconcile(campaign, baseline, ab)
                        longgap.reconcile(after, sealed_after)
                        ab.reconcile(after, sealed_after)
                        cadence.reconcile(after, sealed_after)
                        report()
                        if success:
                            owned_stop(CACHE / 'stop-requested', owner, 'verified mean >1500')
                            return 0
                        if code or before == (len(after), frozenset(sealed_after)):
                            raise RuntimeError('launcher failed or made no terminal progress; no automatic retry')
                        continue
                stopped.wait(5)
        except Exception as exc:
            owned_stop(CACHE / 'stop-requested', owner, 'root reconciliation required')
            event('needs_root_reconciliation', error=str(exc)[:1200])
            return 2
        finally:
            done.set()
            watcher.join(timeout=2)


if __name__ == '__main__':
    raise SystemExit(main())
