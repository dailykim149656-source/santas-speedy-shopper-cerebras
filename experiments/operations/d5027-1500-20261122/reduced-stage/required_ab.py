"""Prospectively allocated, bounded D5027 required versus auto experiment."""
from datetime import datetime, timedelta
import hashlib
import json
import math
from pathlib import Path
import re
from statistics import median
import uuid

from cadence import Cadence, stamp

SCREEN = ('AB', 'BA') * 4
CONFIRM = ('BA', 'AB') * 2
ARMS = ''.join(SCREEN + CONFIRM)
MODES = {'A': 'retry-only', 'B': 'first-required'}
HEX = re.compile('[0-9a-f]{64}')


def paired(entries, confirmation=False):
    by_pair = {}
    counts = {'A': 0, 'B': 0}
    for entry in entries:
        arm, result = entry['arm'], entry['outcome']
        counts[arm] += int(result['valid'])
        by_pair.setdefault(entry['pair'], {})[arm] = result
    scored = [pair for pair in by_pair.values()
              if all(arm in pair and pair[arm]['valid'] for arm in 'AB')]
    means = [pair['B']['mean_tps'] - pair['A']['mean_tps'] for pair in scored]
    firsts = [pair['B']['first_tps'] - pair['A']['first_tps'] for pair in scored]
    mean_wins, first_wins = sum(d > 0 for d in means), sum(d > 0 for d in firsts)
    gain = median(means) if means else None
    if confirmation:
        passed = len(means) >= 3 and mean_wins >= 3 and gain > 0
    else:
        passed = (len(means) >= 4 and 4 * mean_wins >= 3 * len(means)
                  and 2 * first_wins > len(means) and gain >= 50)
    return {'n_sent': len(entries), 'valid_counts': counts, 'valid_pairs': len(means),
            'session_wins_B': mean_wins, 'first_wins_B': first_wins,
            'paired_session_deltas': means, 'paired_first_deltas': firsts,
            'median_paired_session_gain': gain, 'pass': passed and counts['B'] >= counts['A']}


class RequiredAB(Cadence):
    """Reuse the cadence ledger's atomic replace, terminal check and dispatch intent."""

    def __init__(self, directory, campaign_cutoff, audit_outcome):
        self.directory = Path(directory)
        self.path = self.directory / 'required-ab-state.json'
        self.audit_outcome = audit_outcome
        config_path = self.directory / 'required-ab-config.json'
        self.config = json.loads(config_path.read_bytes()) if config_path.exists() else None
        self.state = None
        if self.config is None:
            if self.path.exists():
                raise RuntimeError('A/B ledger without A/B opt-in configuration')
            return
        c = self.config
        cutoff = datetime.fromisoformat(c['cutoff'])
        if (c.get('version') != 1 or c.get('enabled') is not True
                or type(c.get('history_start')) is not int or c['history_start'] < 1
                or str(uuid.UUID(c['anchor_id'])) != c['anchor_id']
                or not all(HEX.fullmatch(c[k]) for k in ('relay_sha256', 'previous_relay_sha256'))
                or c['relay_sha256'] == c['previous_relay_sha256']
                or cutoff.tzinfo is None or cutoff.timestamp() > campaign_cutoff):
            raise RuntimeError('A/B configuration invalid')
        self.cutoff = cutoff.timestamp()
        digest = hashlib.sha256(json.dumps(c, sort_keys=True).encode()).hexdigest()
        self.state = json.loads(self.path.read_bytes()) if self.path.is_file() else {
            'version': 1, 'config_sha256': digest, 'config': c, 'assignments': [],
            'screening': None, 'confirmation': None, 'status':'screening'}
        if self.state.get('config_sha256') != digest or self.state.get('version') != 1:
            raise RuntimeError('A/B configuration changed after activation')
        entries = self.state['assignments']
        if len(entries) > len(ARMS):
            raise RuntimeError('A/B exceeds fixed sample size')
        for i, entry in enumerate(entries):
            if (entry['index'] != i + 1 or entry['arm'] != ARMS[i] or entry['pair'] != i // 2 + 1
                    or entry['history_cursor'] != c['history_start'] + i
                    or entry['phase'] not in ('allocated', 'dispatched', 'complete', 'cutoff')
                    or i < len(entries) - 1 and entry['phase'] != 'complete'):
                raise RuntimeError('corrupt A/B assignment ledger')

        cap_path = self.directory / 'required-ab-cap.json'
        self.amendment = json.loads(cap_path.read_bytes()) if cap_path.is_file() else None
        if self.amendment is None:
            if 'reduced_cap' in self.state:
                raise RuntimeError('persisted A/B cap missing its amendment file')
            return
        cap = self.amendment
        registered = datetime.fromisoformat(cap['registered_at'])
        if (type(cap.get('version')) is not int or cap['version'] != 1
                or type(cap.get('max_transmissions')) is not int or cap['max_transmissions'] != 4
                or cap.get('allow_confirmation') is not False
                or cap.get('reason') != 'user_requested_minimum'
                or registered.utcoffset() != timedelta(0)):
            raise RuntimeError('invalid minimum-transmission amendment')
        recorded = self.state.get('cap_amendment')
        if recorded is not None and recorded != cap:
            raise RuntimeError('A/B minimum amendment changed after registration')
        if self.state.get('reduced_cap', 4) != 4 or self.state.get('confirmation') is not None:
            raise RuntimeError('A/B cap conflicts with existing ledger')
        self.state.update(reduced_cap=4, cap_amendment=cap)
        closed_now = self.close_reduced_if_ready()
        if recorded is None or closed_now:
            self.save()

    def close_reduced_if_ready(self):
        entries = self.state['assignments']
        complete = [e for e in entries if e['phase'] == 'complete']
        count = len(complete)
        if count > 4:
            raise RuntimeError('A/B minimum cap exceeded in existing terminal history')
        no_valid_b = count == 3 and not any(e['outcome']['valid'] for e in complete if e['arm'] == 'B')
        if count < 4 and not no_valid_b:
            return False
        pending = self.active()
        if pending and pending['phase'] == 'dispatched':
            if count == 4:
                raise RuntimeError('existing extra A/B dispatch needs operator reconciliation')
            # Consume an already dispatched A4 only when a terminal receipt exists.
            return False
        if self.state['status'] == 'baseline_after_screening' and self.state.get('screening') is not None:
            return False
        if pending:
            pending.update(phase='cutoff', cutoff_at=stamp(), cutoff_reason='user_requested_minimum')
        summary = paired(complete)
        summary.update({'pass': False, 'reduced_cap':4,
                        'end_reason':'no_valid_B_after_three' if no_valid_b else 'four_transmissions_reached',
                        'confirmation_allowed':False})
        self.state.update(status='baseline_after_screening', screening=summary, confirmation=None)
        return True

    def reconcile(self, rows, sealed):
        entry = self.active()
        if entry is None:
            return
        cursor = entry['history_cursor']
        if len(rows) < cursor or rows[cursor-1]['id'] != entry['previous_uuid']:
            raise RuntimeError('A/B history anchor changed')
        if entry['phase'] == 'allocated':
            if len(rows) != cursor:
                raise RuntimeError('unassigned result under A/B allocation')
            return
        attempt = entry['attempts'][-1]
        preflight = set(sealed) - set(attempt['sealed_before'])
        if len(rows) == cursor and len(preflight) == 1:
            attempt.update(phase='proven_presend', run_id=next(iter(preflight)), recorded_at=stamp())
            entry['phase'] = 'allocated'
        elif len(rows) == cursor + 1 and not preflight:
            row = rows[cursor]
            outcome = self.audit_outcome(row, entry, self.config)
            outcome.update(run_id=row['id'], sent=True, history_index=cursor, commit=row['commit'],
                           evidence=f"runs/{row['id']}/evidence.json", recorded_at=stamp())
            attempt.update(phase='terminal', run_id=row['id'])
            entry.update(phase='complete', outcome=outcome)
            self.update_decision()
        else:
            raise RuntimeError('ambiguous A/B dispatch; no automatic retry')
        self.save()

    def dispatch(self, assignment, rows, sealed, command, now):
        expected = ['--once'] + (['--d5027-first-required'] if assignment['arm'] == 'B' else [])
        if '--once' not in command or list(command[command.index('--once'):]) != expected:
            raise RuntimeError('A/B command differs from prospectively allocated arm')
        super().dispatch(assignment, rows, sealed, command, now)

    def update_decision(self):
        if self.amendment is not None:
            self.close_reduced_if_ready()
            return
        entries = self.state['assignments']
        if len(entries) == 16:
            check = paired(entries)
            self.state.update(screening=check, status='confirmation' if check['pass'] else 'baseline_after_screening')
        if len(entries) == 24:
            self.state.update(confirmation=paired(entries[16:], confirmation=True), status='baseline_after_confirmation')

    def select(self, rows, sealed, now, cadence, current_hash):
        if self.state is None:
            return None
        c = self.config
        cursor = c['history_start']
        if len(rows) < cursor or rows[cursor-1]['id'] != c['anchor_id']:
            raise RuntimeError('A/B activation cursor differs from campaign history')
        prior = cadence.state['assignments'] if cadence.state else []
        if (len(prior) != 8 or any(p['phase'] != 'complete' for p in prior)
                or prior[-1]['outcome']['history_index'] >= cursor):
            raise RuntimeError('A/B requires eight completed prior cadence outcomes')
        if current_hash != c['relay_sha256']:
            raise RuntimeError('A/B source hash differs from preregistration')
        self.reconcile(rows, sealed)
        if self.state['status'].startswith('baseline_') or self.state['status'] == 'cutoff':
            return None
        active = self.active()
        if now >= self.cutoff:
            if active:
                active.update(phase='cutoff', cutoff_at=stamp())
            self.state['status'] = 'cutoff'
            self.save()
            return None
        if active:
            return active
        entries = self.state['assignments']
        if len(rows) != cursor + len(entries):
            raise RuntimeError('outside execution appeared during paired A/B')
        i = len(entries)
        e = {'index': i+1, 'pair':i//2+1, 'stage':'screening' if i < 16 else 'confirmation',
             'arm':ARMS[i], 'mode':MODES[ARMS[i]], 'relay_sha256':c['relay_sha256'],
             'history_cursor':len(rows), 'previous_uuid': rows[-1]['id'],
             'phase':'allocated', 'allocated_at':stamp(), 'attempts':[]}
        entries.append(e)
        self.save()
        return e


def sha(data):
    return hashlib.sha256(data).hexdigest()


def check_wire(cache, row, expected_sha, mode, calls):
    """Recompute saved body hashes, strict one-field transformation, and accepted provider timings."""
    ident = row['id']
    requests = []
    with (cache / 'relay/logs/requests.jsonl').open('rb') as source:
        for line in source:
            if line.strip():
                item = json.loads(line)
                if item.get('run_id') == ident:
                    requests.append(item)
    if len(requests) != len(calls) or len(calls) < 2:
        raise RuntimeError('valid A/B does not match accepted request count: ' + ident)
    if calls[0].get('stopReason') != 'toolUse' or calls[-1].get('stopReason') != 'stop':
        raise RuntimeError('valid A/B lacks first tool and final answers')
    proof = []
    for index, (req, call) in enumerate(zip(requests, calls)):
        if (req.get('status') != 200 or req.get('relay_sha256') != expected_sha
                or req.get('nonce') != ident[:8] or req.get('method') != 'POST'
                or any(a.get('status') != 429 for a in req['attempts'])
                or not HEX.fullmatch(req['forwarded_sha256']) or not HEX.fullmatch(req['received_sha256'])
                or type(req['at_ms']) is not int):
            raise RuntimeError('wire identity, timing coverage or retry provenance mismatch: ' + ident)
        directory = cache / 'relay/logs' / ident
        recv, sent = req['received_sha256'], req['forwarded_sha256']
        forwarded = (directory / f"{req['at_ms']}-{sent[:12]}.json").read_bytes()
        payload = json.loads(forwarded)
        generation = call['serverGeneration']
        timing = req['timing']
        late = any(m.get('role') == 'tool' for m in payload['messages'])
        if (sha(forwarded) != sent or late != (index > 0)
                or req.get('retry_schedule') != ('late' if late else 'first')
                or timing['completion_tokens'] != generation['outputTokens']
                or not math.isclose(timing['completion_time'] * 1000, generation['completionMs'], rel_tol=1e-8)):
            raise RuntimeError('wire payload or provider timing differs from scored call: ' + ident)
        if mode == 'first-required' and index == 0:
            original = (directory / f"{req['at_ms']}-{recv[:12]}.received.json").read_bytes()
            change = json.loads(original)
            if (sha(original) != recv or change.get('tool_choice') != 'auto'
                    or payload.get('tool_choice') != 'required'
                    or req.get('phase') != 'first' or req.get('changes') != ['tool_choice_required']):
                raise RuntimeError('bound B first request lacks required-only change: ' + ident)
            change['tool_choice'] = 'required'
            if change != payload:
                raise RuntimeError('B mutated more than tool_choice: ' + ident)
        elif (recv != sent or req.get('changes') != []
                or mode == 'retry-only' and req.get('phase') != 'passthrough'
                or mode == 'first-required' and req.get('phase') not in ('final','repair')):
            raise RuntimeError('passthrough request altered: ' + ident)
        proof.append({'received': recv, 'forwarded': sent, 'phase': req['phase'], 'at_ms': req['at_ms']})
    return proof


def check_plan(plan, anchor, binding, mode, expected_sha):
    ident = plan['id']
    frozen = ('variant','experiment','temperature','thinking','max_completion_tokens','top_p',
              'provider_max_retries','workspace_agents_md','capturePolicy','context_injection',
              'official_commit','official_patch_sha256','benchmark_sha256')
    if (any(plan.get(k) != anchor.get(k) for k in frozen)
            or plan['variant'] != 'synth-five-categories-cap' or plan['temperature'] != .2
            or plan['thinking'] != 'low' or plan['max_completion_tokens'] != 1024
            or plan['provider_max_retries'] != 0 or plan.get('capturePolicy') is not None
            or plan['prompt'].replace(ident[:8], '{nonce}') != anchor['prompt'].replace(anchor['id'][:8], '{nonce}')
            or plan.get('request_relay') != 'relay-v1:' + expected_sha + ':' + mode
            or binding.get('relay_sha256') != expected_sha or binding.get('mode') != mode
            or binding.get('protocol') != 'relay-v1' or binding.get('id') != ident
            or binding.get('nonce') != ident[:8]):
        raise RuntimeError('A/B differs from bound D5027 plan: ' + ident)
    urls = [json.loads(line)['url'] for line in plan['prompt'].splitlines()[1:]]
    if len(set(urls)) != 5 or binding.get('urls') != urls:
        raise RuntimeError('A/B bound merchant URLs differ from plan')
