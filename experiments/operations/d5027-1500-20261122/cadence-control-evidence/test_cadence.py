import copy
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

CAMPAIGN = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(CAMPAIGN))
import cadence
import supervisor


def row(ident, valid=True):
    return {'id': ident, 'valid': valid, 'method_valid': valid, 'rate_limited': False,
            'arm': 'synth-five-categories-cap|0.2|low', 'call_count': 2,
            'relay_phases': ['passthrough', 'passthrough'], 'commit': 'fixture'}


def record(ident):
    return {'ended': {'terminal': 'error' if ident.startswith('failed') else 'final', 'time': 0},
            'validation': {'valid': not ident.startswith('failed')},
            'calls': [{'timed_sample': True}, {'timed_sample': True}]}


class CadenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.config = {'version': 1, 'enabled': True, 'order_seconds': cadence.ORDER,
                       'history_start': 1, 'cutoff': '2100-01-01T00:00:00+00:00'}
        self.write_config()
        self.rows = [row('previous')]

    def write_config(self):
        (self.directory / 'cadence-config.json').write_text(json.dumps(self.config))

    def manager(self):
        return cadence.Cadence(self.directory, 4102444800, record)

    def select(self, manager, sealed=()):
        return manager.select(self.rows, sealed, lambda r: r['valid'] and r['method_valid'] and not r['rate_limited'], 1)

    def dispatch(self, manager, assignment, sealed=()):
        manager.dispatch(assignment, self.rows, sealed, ['loop.py', '--once', '--d5027-post-success-seconds', str(assignment['requested_seconds'])], 2)

    def test_disabled_has_no_ledger_or_override(self):
        (self.directory / 'cadence-config.json').unlink()
        manager = self.manager()
        self.assertIsNone(self.select(manager))
        self.assertFalse(manager.path.exists())

    def test_balanced_eight_failure_counted_then_default(self):
        manager = self.manager()
        observed = []
        for index, seconds in enumerate(cadence.ORDER):
            assignment = self.select(manager)
            observed.append(assignment['requested_seconds'])
            self.assertEqual(assignment['history_cursor'], len(self.rows))
            self.dispatch(manager, assignment)
            ident = 'failed-1' if index == 1 else 'result-' + str(index)
            self.rows.append(row(ident, index != 1))
            manager = self.manager()
            manager.reconcile(self.rows, ())
            self.assertEqual(manager.state['assignments'][-1]['outcome']['run_id'], ident)
            if index == 1:
                self.assertEqual(manager.state['assignments'][-1]['outcome']['terminal'], 'error')
                self.assertIsNone(self.select(manager))
                self.rows.append(row('recovery-success'))
        self.assertEqual(observed, [30,60,60,30,60,30,30,60])
        self.assertIsNone(self.select(manager))
        self.assertEqual(len(manager.state['assignments']), 8)

    def test_presend_does_not_consume_assignment(self):
        manager = self.manager()
        assignment = self.select(manager)
        self.dispatch(manager, assignment)
        manager = self.manager()
        manager.reconcile(self.rows, {'presend-1'})
        assignment = self.select(manager, {'presend-1'})
        self.assertEqual(assignment['index'], 1)
        self.assertEqual(assignment['attempts'][0]['phase'], 'proven_presend')
        self.dispatch(manager, assignment, {'presend-1'})
        self.rows.append(row('result'))
        manager.reconcile(self.rows, {'presend-1'})
        self.assertEqual(len(manager.state['assignments']), 1)
        self.assertEqual(len(assignment['attempts']), 2)

    def test_allocated_restart_is_same_intent(self):
        manager = self.manager()
        initial = copy.deepcopy(self.select(manager))
        manager = self.manager()
        self.assertEqual(self.select(manager), initial)
        self.assertEqual(len(manager.state['assignments']), 1)

    def test_ambiguous_dispatch_never_retries(self):
        manager = self.manager()
        self.dispatch(manager, self.select(manager))
        for rows, sealed in [(self.rows, ()), (self.rows, ('p1','p2')),
                             (self.rows + [row('r1'),row('r2')], ())]:
            with self.subTest(rows=rows, sealed=sealed):
                with self.assertRaisesRegex(RuntimeError, 'no automatic retry'):
                    self.manager().reconcile(rows, sealed)

    def test_cutoff_cancels_unsent_intent(self):
        manager = self.manager()
        assignment = self.select(manager)
        self.assertIsNone(manager.select(self.rows, (), lambda r: True, manager.cutoff))
        self.assertEqual(assignment['phase'], 'cutoff')
        self.assertEqual(assignment['attempts'], [])
        self.assertIsNone(self.select(self.manager()))

    def test_cutoff_dispatch_rejected_and_config_immutable(self):
        manager = self.manager()
        assignment = self.select(manager)
        with self.assertRaisesRegex(RuntimeError, 'cutoff'):
            manager.dispatch(assignment, self.rows, (), [], manager.cutoff)
        self.config['history_start'] = 2
        self.write_config()
        with self.assertRaisesRegex(RuntimeError, 'configuration changed'):
            self.manager()

    def test_external_cooldown_and_failed_backoff_unchanged(self):
        with patch.object(supervisor, 'read', side_effect=lambda p: record(p.parent.name)), patch.object(supervisor, 'cadence_eligible', return_value=True):
            self.assertEqual(supervisor.cooldown_until(self.rows, {}), 60)
            self.assertEqual(supervisor.cooldown_until(self.rows, {}, 30), 30)
            self.assertEqual(supervisor.cooldown_until(self.rows, {}, 60), 60)
            for count, expected in [(1,60),(2,120),(3,240),(4,480),(5,480)]:
                self.assertEqual(supervisor.cooldown_until([row('failed-'+str(i),False) for i in range(count)], {}), expected)
            limited = [dict(row('limited-'+str(i),False), rate_limited=True) for i in range(3)]
            self.assertEqual(supervisor.cooldown_until(limited[:1], {}), 60)
            self.assertEqual(supervisor.cooldown_until(limited, {}), 120)
            self.assertEqual(supervisor.cooldown_until(self.rows, {'phase':'preflight_aborted','time':'1970-01-01T00:00:00+00:00'}, 30), 45)

    def test_terminal_method_failure_counted_before_campaign_checks(self):
        manager = self.manager()
        assignment = self.select(manager)
        self.dispatch(manager, assignment)
        self.rows.append(dict(row('method-failed'), method_valid=False))
        manager.reconcile_terminal(self.rows)
        self.assertEqual(assignment['phase'], 'complete')
        self.assertFalse(assignment['outcome']['history_row']['method_valid'])

    def test_ineligible_prior_results_cannot_allocate(self):
        for changes in ({'valid':False}, {'method_valid':False}, {'rate_limited':True}):
            with self.subTest(changes=changes):
                self.rows = [dict(row('previous'), **changes)]
                self.assertIsNone(self.select(self.manager()))
        self.assertFalse((self.directory/'cadence-state.json').exists())

    def test_supervisor_dispatches_flag_and_records_before_report(self):
        root = self.directory / '2026-test'
        cache = root / 'mean'
        campaign = cache / 'campaign'
        campaign.mkdir(parents=True)
        (campaign / 'campaign.json').write_text(json.dumps({'deadline':'2100-01-01T00:07:00+00:00', 'threshold':1500, 'history_start':0, 'initial_head':'fixture'}))
        (campaign / 'cadence-config.json').write_text(json.dumps(self.config))
        (cache / 'status.json').write_text(json.dumps({'phase':'result','id':'previous'}))
        (cache / 'loop.lock').touch()
        for name in ('2026-11-22','2026-11-22-exp2000'):
            lock = self.directory / name / 'mean-2000/loop.lock'
            lock.parent.mkdir(parents=True)
            lock.touch()
        commands = []
        complete = []
        class Child:
            def wait(inner):
                self.rows.append(row('failed-outcome',False))
                complete.append(True)
                return 0
        def launch(command, **kwargs):
            commands.append(command)
            ledger = json.loads((campaign/'cadence-state.json').read_text())
            self.assertEqual(ledger['assignments'][0]['phase'], 'dispatched')
            return Child()
        def report():
            ledger = json.loads((campaign/'cadence-state.json').read_text())
            self.assertEqual(ledger['assignments'][0]['outcome']['run_id'], 'failed-outcome')
        with patch.multiple(supervisor, ROOT=root, CACHE=cache, CAMPAIGN_DIR=campaign), \
             patch.object(supervisor, 'git', side_effect=lambda *args: b'test\n' if args[0]=='branch' else b''), \
             patch.object(supervisor, 'reconcile', side_effect=lambda *args:(list(self.rows),False,set())), \
             patch.object(supervisor, 'history', side_effect=lambda:list(self.rows)), \
             patch.object(supervisor, 'committed_record', side_effect=record), \
             patch.object(supervisor, 'cadence_eligible', return_value=True), \
             patch.object(supervisor, 'cooldown_until', return_value=0) as cooldown, \
             patch.object(supervisor, 'controls', side_effect=lambda *args:'fixture complete' if complete else None), \
             patch.object(supervisor, 'owned_stop'), patch.object(supervisor.os, 'dup2'), \
             patch.object(supervisor.subprocess, 'Popen', side_effect=launch), \
             patch.object(supervisor, 'report', side_effect=report):
            self.assertEqual(supervisor.main(),0)
        self.assertEqual(len(commands),1)
        self.assertEqual(commands[0][-3:],['--once','--d5027-post-success-seconds','30'])
        self.assertEqual(cooldown.call_args.args[-1],30)


if __name__ == '__main__':
    unittest.main(verbosity=2)
