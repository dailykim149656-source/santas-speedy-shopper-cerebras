"""Prospectively paired 60/90-second test after the required/auto experiment."""
from datetime import datetime, timezone
import hashlib
import json
import os
import tempfile
from pathlib import Path
import uuid

from cadence import Cadence, stamp
from required_ab import HEX, RequiredAB


def reduced_ab_last_index(directory, state, rows):
    """Cross-check the user's shorter comparison against its approved cap and sent rows."""
    cap_file = directory / 'required-ab-cap.json'
    cap = json.loads(cap_file.read_bytes()) if cap_file.is_file() else {}
    screening = state.get('screening') or {}
    entries = state['assignments']
    completed = [e for e in entries if e['phase'] == 'complete']
    n = len(completed)
    if (cap.get('version') != 1 or cap.get('max_transmissions') != 4
            or cap.get('allow_confirmation') is not False or cap.get('reason') != 'user_requested_minimum'
            or state['reduced_cap'] != 4 or state['status'] != 'baseline_after_screening'
            or state.get('confirmation') is not None or screening.get('pass') is not False
            or screening.get('n_sent') != n or n not in (3, 4)
            or screening.get('confirmation_allowed') is not False
            or screening.get('end_reason') != ('no_valid_B_after_three' if n == 3 else 'four_transmissions_reached')
            or [e['arm'] for e in completed] != list('ABBA'[:n])
            or entries[:n] != completed):
        raise RuntimeError('reduced A/B lacks cap or complete terminal evidence')
    tail = entries[n:]
    if (len(tail) > 1 or any(e.get('phase') != 'cutoff' or e.get('cutoff_reason') != 'user_requested_minimum'
                             or 'outcome' in e or any(a['phase'] != 'proven_presend' for a in e['attempts'])
                             for e in tail)):
        raise RuntimeError('reduced A/B contains an uncertain trailing assignment')
    for entry in completed:
        result = entry['outcome']
        i = result['history_index']
        if (type(i) is not int or i < 0 or i >= len(rows) or rows[i]['id'] != result['run_id']
                or entry['history_cursor'] != i or result.get('sent') is not True):
            raise RuntimeError('reduced A/B sent row differs from committed run history')
    if n == 3 and not all(e['outcome'].get('valid') is False for e in completed if e['arm'] == 'B'):
        raise RuntimeError('reduced A/B stopped before four without two invalid B sends')
    return completed[-1]['outcome']['history_index']


def activate_pending(directory, cutoff, rows, ab, source_hash, eligible, now):
    """At the next eligible baseline boundary, atomically publish the root opt-in."""
    directory = Path(directory)
    path = directory / 'longgap-config.json'
    if path.exists():
        return True
    approval = directory / 'longgap-approved-pending.json'
    if not approval.is_file() or now >= cutoff or not rows:
        return False
    pending = json.loads(approval.read_bytes())
    prereg_bytes = (directory / 'longgap-prereg.json').read_bytes()
    if (pending.get('version') != 1 or pending.get('wait_for_eligible_baseline') is not True
            or hashlib.sha256(prereg_bytes).hexdigest() != pending.get('prereg_sha256')):
        raise RuntimeError('pending 60/90 approval differs from preregistration')
    state = ab.state
    if not state or state.get('status') != 'baseline_after_screening' or state.get('reduced_cap') != 4:
        return False
    last_ab = reduced_ab_last_index(directory, state, rows)
    if last_ab >= len(rows) or ab.config['relay_sha256'] != source_hash:
        raise RuntimeError('pending 60/90 baseline or relay changed')
    if not eligible(rows[-1]):
        return False
    prereg = json.loads(prereg_bytes)
    registered = datetime.fromisoformat(prereg['created'])
    if (prereg.get('version') != 1 or prereg.get('max_assignments') != 4
            or prereg.get('order_seconds') != [60,90,90,60] or prereg.get('pairs') != [[60,90],[90,60]]
            or registered.tzinfo is None or registered.timestamp() > now):
        raise RuntimeError('pending 60/90 preregistration is invalid')
    config = {'version':1, 'enabled':True, 'registered_at':prereg['created'],
              'cutoff':datetime.fromtimestamp(cutoff, timezone.utc).isoformat(), 'history_start':len(rows),
              'anchor_id':rows[-1]['id'], 'order_seconds':prereg['order_seconds'], 'relay_sha256':source_hash}
    # A complete inode is linked with exclusive creation; a restart can observe
    # either no config or all of it. Existing activation is never overwritten.
    tmp = None
    try:
        with tempfile.NamedTemporaryFile(dir=directory, prefix='.longgap-config-', delete=False, mode='w') as out:
            tmp = Path(out.name)
            json.dump(config,out,indent=2);out.write('\n');out.flush();os.fsync(out.fileno())
        try:
            os.link(tmp, path)
        except FileExistsError:
            return True
        dirfd = os.open(directory, os.O_RDONLY)
        try:
            os.fsync(dirfd)
        finally:
            os.close(dirfd)
    finally:
        if tmp is not None:
            tmp.unlink(missing_ok=True)
    return True


class LongGap(RequiredAB):
    # The shared A/B reconciliation method counts every audited terminal send,
    # preserves prepared-but-unsent assignments and halts on an uncertain send.
    def __init__(self, directory, campaign_cutoff, audit_outcome):
        self.directory = Path(directory)
        self.path = self.directory / 'longgap-state.json'
        self.audit_outcome = audit_outcome
        source = self.directory / 'longgap-config.json'
        self.config = json.loads(source.read_bytes()) if source.is_file() else None
        self.state = None
        if self.config is None:
            if self.path.exists():
                raise RuntimeError('long-gap ledger exists without its activation config')
            return
        config = self.config
        prereg = json.loads((self.directory / 'longgap-prereg.json').read_bytes())
        order = config['order_seconds']
        pairs = [order[i:i + 2] for i in range(0, len(order), 2)]
        registered = datetime.fromisoformat(config['registered_at'])
        cutoff = datetime.fromisoformat(config['cutoff'])
        if (config.get('version') != 1 or config.get('enabled') is not True
                or type(config.get('history_start')) is not int or config['history_start'] < 1
                or str(uuid.UUID(config['anchor_id'])) != config['anchor_id']
                or not HEX.fullmatch(config['relay_sha256'])
                or order != [60, 90, 90, 60] or not all(type(v) is int for v in order)
                or prereg.get('version') != 1 or prereg.get('max_assignments') != 4 or prereg.get('order_seconds') != order
                or prereg.get('pairs') != pairs or prereg.get('created') != config['registered_at']
                or registered.tzinfo is None or cutoff.tzinfo is None
                or registered.timestamp() >= cutoff.timestamp() or cutoff.timestamp() > campaign_cutoff):
            raise RuntimeError('invalid preregistered 60/90 comparison')
        self.cutoff = cutoff.timestamp()
        digest = hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest()
        self.state = json.loads(self.path.read_bytes()) if self.path.exists() else {
            'version': 1, 'config_sha256': digest, 'config': config, 'status': 'active', 'assignments': []}
        if self.state.get('version') != 1 or self.state.get('config_sha256') != digest:
            raise RuntimeError('long-gap configuration changed after allocation')
        entries = self.state['assignments']
        if len(entries) > len(order) or self.state.get('status') not in ('active', 'complete', 'cutoff', 'inconclusive_after_failure'):
            raise RuntimeError('corrupt long-gap ledger')
        last_cursor = config['history_start'] - 1
        for index, entry in enumerate(entries):
            if (entry['index'] != index + 1 or entry['pair'] != index // 2 + 1 or entry['slot'] != index % 2 + 1
                    or entry['requested_seconds'] != order[index] or entry['mode'] != 'retry-only'
                    or entry['relay_sha256'] != config['relay_sha256'] or entry['history_cursor'] <= last_cursor
                    or entry['phase'] not in ('allocated', 'dispatched', 'complete', 'cutoff')
                    or index < len(entries) - 1 and entry['phase'] != 'complete'):
                raise RuntimeError('corrupt long-gap assignment')
            last_cursor = entry['history_cursor']
        if self.state['status'] == 'inconclusive_after_failure':
            if (not entries or entries[-1]['phase'] != 'complete'
                    or self.state.get('failed_run_id') != entries[-1]['outcome']['run_id']):
                raise RuntimeError('inconsistent early stop for long-gap comparison')
        elif (self.state['status'] == 'complete') != (len(entries) == len(order) and all(
                entry['phase'] == 'complete' and entry['outcome']['valid'] for entry in entries)):
            raise RuntimeError('long-gap completion status disagrees with assigned outcomes')

    def update_decision(self):
        entries = self.state['assignments']
        outcome = entries[-1]['outcome']
        if not outcome['valid'] or outcome.get('rate_limited') is True:
            self.finish_after_failure(outcome['run_id'], 'assigned session failed; two valid pairs cannot be completed')
        elif len(entries) == len(self.config['order_seconds']):
            self.state['status'] = 'complete'

    def finish_after_failure(self, ident, reason):
        self.state.update(status='inconclusive_after_failure', failed_run_id=ident, reason=reason)

    def select(self, rows, sealed, now, ab, source_hash, eligible):
        if self.state is None:
            return None
        self.reconcile(rows, sealed)
        if self.state['status'] != 'active':
            return None
        active = self.active()
        if now >= self.cutoff:
            if active:
                active.update(phase='cutoff', cutoff_at=stamp())
            self.state['status'] = 'cutoff'
            self.save()
            return None
        if not ab.state or ab.state.get('status') not in ('baseline_after_screening', 'baseline_after_confirmation'):
            if self.state['assignments']:
                raise RuntimeError('prior A/B changed during long-gap comparison')
            return None
        prior = ab.state['assignments']
        after_confirmation = ab.state['status'] == 'baseline_after_confirmation'
        if 'reduced_cap' in ab.state:
            last_ab_index = reduced_ab_last_index(self.directory, ab.state, rows)
        else:
            n = 24 if after_confirmation else 16
            if (len(prior) != n or any(entry['phase'] != 'complete' for entry in prior)
                    or not ab.state.get('screening') or ab.state['screening'].get('pass') is not after_confirmation
                    or after_confirmation and not ab.state.get('confirmation')):
                raise RuntimeError('prior A/B does not have the promised terminal decision')
            last_ab_index = prior[-1]['outcome']['history_index']
        config = self.config
        anchor = config['history_start']
        if (len(rows) < anchor or rows[anchor-1]['id'] != config['anchor_id']
                or last_ab_index >= anchor
                or source_hash != config['relay_sha256'] or source_hash != ab.config['relay_sha256']):
            raise RuntimeError('long-gap activation history or deployed relay differs')
        if now < datetime.fromisoformat(config['registered_at']).timestamp():
            raise RuntimeError('long-gap registration time is in the future')
        entries = self.state['assignments']
        cursor = len(rows)
        completed = sum(e['phase'] == 'complete' for e in entries)
        if cursor != anchor + completed:
            raise RuntimeError('unexpected execution during the four-transmission comparison')
        if not eligible(rows[-1]):
            if active or not entries:
                raise RuntimeError('long-gap activation or allocated predecessor lacks eligible A evidence')
            self.finish_after_failure(rows[-1]['id'], 'previous session cannot enter the next paired interval')
            self.save()
            return None
        if active:
            return active
        index = len(entries)
        entry = {'index': index + 1, 'pair': index // 2 + 1, 'slot': index % 2 + 1,
                 'requested_seconds': config['order_seconds'][index], 'history_cursor': cursor,
                 'previous_uuid': rows[-1]['id'], 'mode': 'retry-only', 'relay_sha256': source_hash,
                 'phase': 'allocated', 'allocated_at': stamp(), 'attempts': []}
        entries.append(entry)
        self.save()
        return entry

    def dispatch(self, assignment, rows, sealed, command, now):
        expected = ['--once', '--d5027-post-success-seconds', str(assignment['requested_seconds'])]
        if '--once' not in command or list(command[command.index('--once'):]) != expected:
            raise RuntimeError('long-gap dispatch does not match preregistered baseline interval')
        Cadence.dispatch(self, assignment, rows, sealed, command, now)
