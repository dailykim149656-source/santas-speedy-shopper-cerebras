"""Private, opt-in cadence allocation ledger; importing never dispatches work."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path

ORDER = [30, 60, 60, 30, 60, 30, 30, 60]


def stamp():
    return datetime.now(timezone.utc).isoformat()


class Cadence:
    def __init__(self, directory, campaign_cutoff, read_record):
        self.directory = Path(directory)
        self.path = self.directory / 'cadence-state.json'
        self.read_record = read_record
        config_path = self.directory / 'cadence-config.json'
        self.config = json.loads(config_path.read_text()) if config_path.exists() else None
        self.state = None
        if self.config is None:
            if self.path.exists():
                raise RuntimeError('cadence config missing for existing allocation ledger')
            return
        config = self.config
        cutoff = datetime.fromisoformat(config['cutoff'])
        if (config.get('version') != 1 or config.get('enabled') is not True
                or config.get('order_seconds') != ORDER
                or type(config.get('history_start')) is not int or config['history_start'] < 1
                or cutoff.tzinfo is None or cutoff.timestamp() > campaign_cutoff):
            raise RuntimeError('invalid opt-in cadence configuration')
        self.cutoff = cutoff.timestamp()
        digest = hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest()
        self.state = json.loads(self.path.read_text()) if self.path.exists() else {
            'version': 1, 'config_sha256': digest, 'config': config, 'assignments': []}
        if self.state.get('version') != 1 or self.state.get('config_sha256') != digest:
            raise RuntimeError('cadence configuration changed after allocation')
        assignments = self.state['assignments']
        if len(assignments) > len(ORDER):
            raise RuntimeError('cadence allocation count exceeds declared order')
        for index, assignment in enumerate(assignments):
            if (assignment['index'] != index + 1 or assignment['requested_seconds'] != ORDER[index]
                    or assignment['phase'] not in ('allocated', 'dispatched', 'complete', 'cutoff')
                    or (index < len(assignments) - 1 and assignment['phase'] != 'complete')):
                raise RuntimeError('invalid cadence allocation ledger')

    def save(self):
        temporary = self.path.with_suffix('.tmp')
        with temporary.open('w') as output:
            json.dump(self.state, output, indent=2)
            output.write('\n')
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, self.path)
        directory_fd = os.open(self.directory, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)

    def active(self):
        assignments = self.state['assignments'] if self.state else []
        return assignments[-1] if assignments and assignments[-1]['phase'] in ('allocated', 'dispatched') else None

    def reconcile_terminal(self, rows):
        assignment = self.active()
        if (assignment and assignment['phase'] == 'dispatched'
                and len(rows) > assignment['history_cursor']):
            # Count committed terminal outcomes even when later campaign checks
            # reject their method or media. Never infer a presend receipt here.
            self.reconcile(rows, assignment['attempts'][-1]['sealed_before'])

    def reconcile(self, rows, sealed):
        assignment = self.active()
        if assignment is None:
            return
        cursor = assignment['history_cursor']
        if len(rows) < cursor or rows[cursor - 1]['id'] != assignment['previous_uuid']:
            raise RuntimeError('cadence history cursor changed')
        if assignment['phase'] == 'allocated':
            if len(rows) != cursor:
                raise RuntimeError('unassigned history result appeared during cadence allocation')
            return
        attempt = assignment['attempts'][-1]
        new_sealed = set(sealed) - set(attempt['sealed_before'])
        if len(rows) == cursor + 1 and not new_sealed:
            row = rows[cursor]
            record = self.read_record(row['id'])
            terminal = record['ended']['terminal']
            if terminal not in ('final', 'error', 'aborted'):
                raise RuntimeError('cadence result has no terminal evidence')
            outcome = {'run_id': row['id'], 'terminal': terminal, 'history_index': cursor,
                       'history_row': row, 'evidence': 'runs/' + row['id'] + '/evidence.json',
                       'commit': row.get('commit'), 'report': str(self.directory / 'trials.json'),
                       'recorded_at': stamp()}
            attempt.update(phase='terminal', outcome=outcome)
            assignment.update(phase='complete', outcome=outcome)
        elif len(rows) == cursor and len(new_sealed) == 1:
            attempt.update(phase='proven_presend', run_id=next(iter(new_sealed)), recorded_at=stamp())
            assignment['phase'] = 'allocated'
        else:
            raise RuntimeError('cadence dispatch unresolved or multiple outcomes; no automatic retry')
        self.save()

    def select(self, rows, sealed, eligible, now):
        if self.state is None:
            return None
        self.reconcile(rows, sealed)
        active = self.active()
        if now >= self.cutoff:
            if active:
                active.update(phase='cutoff', cutoff_at=stamp())
                self.save()
            return None
        if active:
            if not eligible(rows[-1]):
                raise RuntimeError('cadence previous success no longer eligible')
            return active
        assignments = self.state['assignments']
        if (len(assignments) >= len(ORDER) or (assignments and assignments[-1]['phase'] == 'cutoff')
                or len(rows) < self.config['history_start'] or not rows or not eligible(rows[-1])):
            return None
        if any(item['previous_uuid'] == rows[-1]['id'] for item in assignments):
            raise RuntimeError('cadence previous success allocated twice')
        assignment = {'index': len(assignments) + 1, 'previous_uuid': rows[-1]['id'],
                      'requested_seconds': ORDER[len(assignments)], 'history_cursor': len(rows),
                      'allocated_at': stamp(), 'phase': 'allocated', 'attempts': []}
        assignments.append(assignment)
        self.save()
        return assignment

    def dispatch(self, assignment, rows, sealed, command, now):
        if now >= self.cutoff:
            raise RuntimeError('cadence dispatch crossed allocation cutoff')
        if (assignment is not self.active() or assignment['phase'] != 'allocated'
                or len(rows) != assignment['history_cursor']
                or rows[-1]['id'] != assignment['previous_uuid']):
            raise RuntimeError('cadence allocation changed before dispatch')
        assignment['attempts'].append({'phase': 'dispatched', 'dispatched_at': stamp(),
                                       'history_cursor': len(rows), 'sealed_before': sorted(sealed),
                                       'command': command})
        assignment['phase'] = 'dispatched'
        self.save()
