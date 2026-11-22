"""Offline checks for D5027 selection at the loop's trial-dispatch boundary."""
from contextlib import ExitStack
from pathlib import Path
import json
import shutil
import sys
import tempfile
import unittest
from unittest.mock import ANY, Mock, call, patch
from urllib.parse import parse_qs, urlsplit

import loop


D5027 = ('synth-five-categories-cap', 0.2, 'low')
RUN_TRIAL = loop.run_trial


class D5027Fixture(unittest.TestCase):
    def setUp(self):
        stack = ExitStack()
        self.addCleanup(stack.close)
        root = Path(stack.enter_context(tempfile.TemporaryDirectory()))
        self.cache = root / 'cache'
        self.cache.mkdir()
        stack.enter_context(patch.multiple(
            loop, TEST_SCHEDULE=True, REPO=root / 'repo', CACHE=self.cache,
            RUNS=self.cache / 'runs', HISTORY=self.cache / 'iterations.jsonl',
        ))
        stack.enter_context(patch.object(sys, 'argv', ['loop.py', '--once']))
        stack.enter_context(patch.object(loop.os, 'umask'))
        self.trial = stack.enter_context(patch.object(loop, 'run_trial', return_value=False))

    def mark(self, *names):
        for name in names:
            (self.cache / name).touch()

    def record_qualified_result(self, ident):
        loop.put(loop.REPO / 'runs' / ident / 'evidence.json', {'ended': {'time': 0}})
        loop.append({'id': ident, 'arm': loop.arm_key(D5027), 'score': 1354.66, 'ui': 1355,
                     'valid': True, 'method_valid': True, 'recorded_video': True, 'goal': False})


class D5027FocusTests(D5027Fixture):
    def test_focus_repeats_d5027_ahead_of_other_selectors(self):
        self.mark('focus-d5027', 'focus-relay', 'focus-categories', 'target-1200')
        loop.main()
        self.record_qualified_result('prior-one')
        loop.main()
        self.record_qualified_result('prior-two')
        loop.main()
        self.assertEqual(self.trial.call_args_list, [call(ANY, D5027)] * 3)

    def test_focus_bypasses_target_stop_without_other_focus_markers(self):
        self.mark('focus-d5027', 'target-1200')
        self.record_qualified_result('prior')
        loop.main()
        self.trial.assert_called_once_with(ANY, D5027)

    def test_target_alone_still_stops(self):
        self.mark('target-1200')
        self.record_qualified_result('prior')
        loop.main()
        self.trial.assert_not_called()
        self.assertEqual(loop.get(self.cache / 'status.json')['phase'], 'target_1200_met')

    def test_stop_request_still_stops_with_focus(self):
        self.mark('focus-d5027', 'target-1200', 'stop-requested')
        self.record_qualified_result('prior')
        loop.main()
        self.trial.assert_not_called()
        self.assertEqual(loop.get(self.cache / 'status.json')['phase'], 'user_stop')

    def test_main_schedule_ignores_test_focus(self):
        self.mark('focus-d5027')
        with patch.object(loop, 'TEST_SCHEDULE', False):
            loop.main()
        self.trial.assert_called_once_with(ANY, loop.choose([]))


class CooldownReached(Exception):
    pass


class D5027DeferredCaptureTests(D5027Fixture):
    def test_requires_explicit_recorded_control_configuration(self):
        with self.assertRaisesRegex(ValueError, 'Deferred validation'):
            RUN_TRIAL(9999, D5027, defer_below_tps=1300)
        self.mark('focus-d5027', 'relay-control')
        for options in ({'score_first': True}, {'first_required': True}, {'first5027': True},
                        {'campaign_1700': True}, {'defer_below_tps': 1500}):
            with self.subTest(options=options), self.assertRaisesRegex(ValueError, 'Deferred validation'):
                RUN_TRIAL(9999, D5027, **dict({'defer_below_tps': 1300}, **options))
        self.assertFalse((self.cache / 'capture').exists())

    def test_pending_receipt_returns_without_committing_a_validation_result(self):
        self.mark('focus-d5027', 'relay-control')
        loop.REPO.mkdir()
        shutil.copyfile(loop.TOOLS.parent / 'benchmark.json', loop.REPO / 'benchmark.json')
        ident = '12345678-1234-4abc-8def-123456789abc'
        label = 'D9999-synth-five-categories-cap'
        raw = loop.RUNS / (label + '.json')
        loop.put(raw, {'id': ident, 'history': {'messages': []}})
        pending = {'result': 'pending_validation', 'id': ident, 'label': label, 'valid': None, 'score': 900}
        deferred = Mock()
        deferred.deferred_capture.return_value = pending
        with ExitStack() as stack:
            stack.enter_context(patch.dict(sys.modules, deferred_helpers=deferred))
            stack.enter_context(patch.object(loop.uuid, 'uuid4', return_value=ident))
            stack.enter_context(patch.object(loop, 'prior_verified_mean', return_value=1354.66))
            for name in ('configure', 'bind_relay', 'wait_for', 'stop_child'):
                stack.enter_context(patch.object(loop, name))
            stack.enter_context(patch.object(loop, 'RELAY_ROOT', self.cache / 'relay'))
            ledger = stack.enter_context(patch.object(loop, 'ledger', return_value={'commit': 'plan'}))
            archive = stack.enter_context(patch.object(loop, 'preserve_raw'))
            process = Mock()
            process.wait.return_value = 0
            stack.enter_context(patch.object(loop.subprocess, 'Popen', return_value=process))
            validate = stack.enter_context(patch.object(loop.subprocess, 'run'))
            reported = RUN_TRIAL(9999, D5027, defer_below_tps=1300)
        archive.assert_called_once_with(raw, ident)
        deferred.deferred_capture.assert_called_once()
        self.assertEqual(deferred.deferred_capture.call_args.args[0], raw)
        self.assertIs(reported['valid'], None)
        self.assertEqual(reported['result'], 'pending_validation')
        self.assertEqual(reported['relay_phases'], [])
        self.assertEqual(ledger.call_args_list, [call('plan', '--repo', loop.REPO, '--plan',
                                                      self.cache/'capture'/ident/'plan.json')])
        self.assertFalse(loop.HISTORY.exists())
        validate.assert_not_called()


class D5027FirstRequiredTests(D5027Fixture):
    def test_control_and_treatment_dispatch(self):
        self.mark('focus-d5027', 'relay-control', 'focus-relay', 'target-1200')
        self.record_qualified_result('prior')
        loop.main()
        with patch.object(sys, 'argv', ['loop.py', '--once', '--d5027-first-required']):
            loop.main()
        self.assertEqual(self.trial.call_args_list, [call(ANY, D5027), call(ANY, D5027, first_required=True)])

    def test_flag_requires_isolated_single_control_trial(self):
        cases = [(False, ['--once'], ['focus-d5027', 'relay-control']),
                 (True, [], ['focus-d5027', 'relay-control']),
                 (True, ['--once'], ['focus-relay', 'relay-control']),
                 (True, ['--once'], ['focus-d5027']),
                 (True, ['--once', '--campaign-1700-start', '9999'], ['focus-d5027', 'relay-control']),
                 (True, ['--once', '--d5027-post-success-seconds', '30'], ['focus-d5027', 'relay-control']),
                 (True, ['--once', '--d5027-post-success-seconds', '90'], ['focus-d5027', 'relay-control'])]
        for test_schedule, flags, markers in cases:
            with self.subTest(flags=flags, markers=markers, test=test_schedule), \
                    patch.object(loop, 'TEST_SCHEDULE', test_schedule), \
                    patch.object(sys, 'argv', ['loop.py', '--d5027-first-required', *flags]), \
                    patch('sys.stderr'):
                self.mark(*markers)
                with self.assertRaises(SystemExit) as error:
                    loop.main()
                self.assertEqual(error.exception.code, 2)
                for marker in markers:
                    (self.cache / marker).unlink()
        self.trial.assert_not_called()

    def test_marker_rechecked_at_dispatch(self):
        with self.assertRaisesRegex(ValueError, 'isolated D5027'):
            RUN_TRIAL(9999, D5027, first_required=True)
        self.mark('focus-d5027', 'relay-control')
        for arm, kwargs in [(('synth-five-categories-cap', 0.0, 'low'), {}),
                            (D5027, {'campaign_1700': True}), (D5027, {'score_first': True}),
                            (D5027, {'first5027': True})]:
            with self.subTest(arm=arm, kwargs=kwargs), self.assertRaisesRegex(ValueError, 'isolated D5027'):
                RUN_TRIAL(9999, arm, first_required=True, **kwargs)
        self.assertFalse((self.cache / 'capture').exists())

    def test_single_trial_comparisons_write_matching_plans_and_bindings(self):
        # Exercise the real trial entry through its plan, binding and recorder-input writes.
        class BeforeRecording(Exception):
            pass

        benchmark = loop.TOOLS.parent / 'benchmark.json'
        loop.REPO.mkdir()
        shutil.copyfile(benchmark, loop.REPO / 'benchmark.json')
        ident = '12345678-1234-4abc-8def-123456789abc'
        stamp = 'a' * 64
        snapshots = []
        for case, arm, mode in (('control', D5027, 'retry-only'), ('required', D5027, 'first-required'),
                                ('mercantile', loop.MERCANTILE_ARM, 'retry-only')):
            cache = self.cache / case
            cache.mkdir()
            if case != 'mercantile':
                for marker in ('focus-d5027', 'relay-control'):
                    (cache / marker).touch()
            with patch.multiple(loop, CACHE=cache, RELAY_ROOT=cache/'relay', PROVIDER_MAX_RETRIES=0), \
                    patch.object(loop.uuid, 'uuid4', return_value=ident), \
                    patch.object(loop, 'relay_sha256', return_value=stamp), \
                    patch.object(loop, 'prior_verified_mean', return_value=1354.66), \
                    patch.object(loop, 'configure') as configure, \
                    patch.object(loop, 'ledger', return_value={'commit': 'plan'}) as ledger, \
                    patch.object(loop, 'status', side_effect=BeforeRecording), \
                    patch.object(loop.subprocess, 'Popen') as start:
                with self.assertRaises(BeforeRecording):
                    RUN_TRIAL(9999, arm, first_required=(mode == 'first-required'))
                start.assert_not_called()
                scratch = cache/'capture'/ident
                ledger.assert_called_once_with('plan', '--repo', loop.REPO, '--plan', scratch/'plan.json')
                plan = loop.get(scratch/'plan.json')
                inputs = loop.get(scratch/'run.json')
                self.assertEqual(inputs.pop('readyPath'), str(scratch/'ready.json'))
                self.assertEqual(inputs, plan)
                self.assertEqual(plan.pop('request_relay'), f'relay-v1:{stamp}:{mode}')
                binding = loop.get(cache/'relay'/'bindings'/'12345678.json')
                self.assertEqual(binding.pop('mode'), mode)
                self.assertEqual(binding['relay_sha256'], stamp)
                self.assertEqual(len(binding['urls']), 5)
                self.assertNotIn('relay_system_prompt', plan)
                self.assertNotIn('system_prompt', binding)
                self.assertEqual(plan['provider_max_retries'], 0)
                self.assertEqual(plan['experiment'], loop.arm_key(arm))
                self.assertEqual(configure.call_args.kwargs, {'relay': True})
                self.assertEqual(binding['urls'], [json.loads(line)['url'] for line in plan['prompt'].splitlines()[1:]])
                snapshots.append((plan, binding, configure.call_args))
        self.assertEqual(snapshots[0], snapshots[1])
        control, control_binding, control_config = snapshots[0]
        candidate, candidate_binding, candidate_config = snapshots[2]
        self.assertEqual(control_config, candidate_config)
        self.assertEqual(candidate['max_completion_tokens'], 1024)
        self.assertEqual(candidate['temperature'], .2)
        self.assertEqual(candidate['thinking'], 'low')
        self.assertIn('Think in at most 5 words.', candidate['workspace_agents_md'])
        different = {key for key in control.keys() | candidate.keys() if control.get(key) != candidate.get(key)}
        self.assertEqual(different, {'label', 'sessionKey', 'variant', 'experiment', 'prompt'})
        self.assertEqual(control['prompt'].splitlines()[0], candidate['prompt'].splitlines()[0])
        self.assertEqual({key for key in control_binding if control_binding[key] != candidate_binding[key]}, {'urls'})
        for url, keyword in zip(candidate_binding['urls'], ('shirt', 'hoodie', 'mug', 'tumbler', 'golf')):
            parsed = urlsplit(url)
            self.assertEqual((parsed.scheme, parsed.netloc, parsed.path),
                             ('https', 'mercantile.wordpress.org', '/wp-json/wc/store/v1/products'))
            self.assertEqual(parse_qs(parsed.query), {'search': [keyword], 'per_page': ['1'],
                             'stock_status': ['instock'], '_fields': ['name,permalink'], '_run': [ident[:8]]})


class D5027MercantileTests(D5027Fixture):
    def test_explicit_single_trial_then_default_and_stop(self):
        self.mark('target-1200')
        self.record_qualified_result('prior')
        flags = ['loop.py', '--once', '--d5027-mercantile']
        with patch.object(sys, 'argv', flags):
            loop.main()
        self.mark('focus-d5027', 'relay-control')
        loop.main()
        self.mark('stop-requested')
        with patch.object(sys, 'argv', flags):
            loop.main()
        self.assertEqual(self.trial.call_args_list, [call(ANY, loop.MERCANTILE_ARM), call(ANY, D5027)])
        self.assertEqual(loop.get(self.cache / 'status.json')['phase'], 'user_stop')

    def test_isolated_once_only_and_no_other_comparison(self):
        self.mark('focus-d5027', 'relay-control')
        cases = [(False, ['--once']), (True, []), (True, ['--once', '--d5027-first-required']),
                 (True, ['--once', '--campaign-1700-start', '9999']),
                 (True, ['--once', '--d5027-post-success-seconds', '30']),
                 (True, ['--once', '--d5027-post-success-seconds', '90'])]
        for test_schedule, flags in cases:
            with self.subTest(test_schedule=test_schedule, flags=flags), \
                    patch.object(loop, 'TEST_SCHEDULE', test_schedule), \
                    patch.object(sys, 'argv', ['loop.py', '--d5027-mercantile', *flags]), \
                    patch('sys.stderr'), self.assertRaises(SystemExit) as error:
                loop.main()
            self.assertEqual(error.exception.code, 2)
        self.trial.assert_not_called()


class D5027CooldownTests(D5027Fixture):
    def test_exploit_gap_shortens_only_for_a_confirmed_zero_token_429(self):
        for classified, expected in [(True, 15), (False, 45), (None, 45)]:
            with self.subTest(classified=classified):
                self.assertEqual(loop.exploit_wait_seconds(zero_token_429=classified), expected)

    def test_exploit_gap_honors_server_retry_after(self):
        for classified, minimum, expected in [(True, 7, 15), (True, 18.5, 18.5),
                                               (False, 30, 45), (False, 120, 120)]:
            with self.subTest(classified=classified, minimum=minimum):
                actual = loop.exploit_wait_seconds(zero_token_429=classified, retry_after_seconds=minimum)
                self.assertEqual(actual, expected)

    def test_accelerated_gap_applies_only_when_explicit(self):
        for zero, merchant, minimum, expected in [(False, False, 0, 15), (True, False, 0, 5),
                                                 (False, True, 0, 90), (True, True, 0, 90),
                                                 (True, False, 19, 19), (True, True, 120, 120)]:
            with self.subTest(zero=zero, merchant=merchant, minimum=minimum):
                self.assertEqual(loop.exploit_wait_seconds(zero_token_429=zero, merchant_429=merchant,
                                                           retry_after_seconds=minimum, accelerated=True), expected)
        self.assertEqual(loop.exploit_wait_seconds(zero_token_429=False, merchant_429=True), 45)

    def result(self, ident='latest', **changes):
        row = {'id': ident, 'arm': loop.arm_key(D5027), 'score': 1354.66, 'ui': 1355,
               'valid': True, 'method_valid': True, 'recorded_video': True, 'goal': False,
               'rate_limited': False, 'call_count': 2}
        row.update(changes)
        loop.put(loop.REPO / 'runs' / ident / 'evidence.json', {'ended': {'time': 1000000}})
        loop.append(row)
        return row

    def assert_cooldown(self, seconds, *options):
        with patch.object(sys, 'argv', ['loop.py', '--once', *options]), \
                patch.object(loop.time, 'time', return_value=1000), \
                patch.object(loop.time, 'sleep', side_effect=CooldownReached) as sleep:
            with self.assertRaises(CooldownReached):
                loop.main()
        sleep.assert_called_once_with(seconds)
        self.trial.assert_not_called()

    def test_valid_prior_default_and_opt_in(self):
        self.mark('focus-d5027')
        self.result()
        self.assert_cooldown(60)
        self.assert_cooldown(60, '--d5027-post-success-seconds', '60')
        self.assert_cooldown(30, '--d5027-post-success-seconds', '30')

    def test_mercantile_and_control_keep_same_cooldown_in_both_orders(self):
        self.mark('focus-d5027', 'relay-control')
        self.result('control')
        self.assert_cooldown(60, '--d5027-mercantile')
        self.result('mercantile', arm=loop.arm_key(loop.MERCANTILE_ARM))
        self.assert_cooldown(60)

    def test_opt_in_dispatches_only_after_full_30_seconds(self):
        self.mark('focus-d5027')
        self.result()
        with patch.object(sys, 'argv', ['loop.py', '--once', '--d5027-post-success-seconds', '30']), \
                patch.object(loop.time, 'time', return_value=1029), \
                patch.object(loop.time, 'sleep', side_effect=CooldownReached) as sleep:
            with self.assertRaises(CooldownReached):
                loop.main()
            sleep.assert_called_once_with(1)
            self.trial.assert_not_called()
        with patch.object(sys, 'argv', ['loop.py', '--once', '--d5027-post-success-seconds', '30']), \
                patch.object(loop.time, 'time', return_value=1030), \
                patch.object(loop.time, 'sleep') as sleep:
            loop.main()
            sleep.assert_not_called()
            self.trial.assert_called_once_with(ANY, D5027)

    def test_failures_keep_backoff_after_older_success(self):
        self.mark('focus-d5027')
        self.result('success')
        self.result('failed-one', valid=False, method_valid=False)
        self.assert_cooldown(60, '--d5027-post-success-seconds', '30')
        self.result('failed-two', valid=False, method_valid=False)
        self.assert_cooldown(120, '--d5027-post-success-seconds', '30')

    def test_zero_token_429_keeps_existing_windows(self):
        self.mark('focus-d5027')
        self.result('success')
        for index in range(3):
            self.result(f'limited-{index}', valid=False, method_valid=False,
                        rate_limited=True, call_count=0, score=None, ui=None)
            self.assert_cooldown(60 if index < 2 else 120, '--d5027-post-success-seconds', '30')

    def test_main_and_other_selectors_keep_default(self):
        self.result()
        for marker in (None, 'focus-relay', 'focus-categories'):
            with self.subTest(marker=marker):
                if marker:
                    self.mark(marker)
                self.assert_cooldown(60, '--d5027-post-success-seconds', '30')
                if marker:
                    (self.cache / marker).unlink()
        self.mark('focus-d5027')
        with patch.object(loop, 'TEST_SCHEDULE', False):
            self.assert_cooldown(60, '--d5027-post-success-seconds', '30')

    def test_campaign_keeps_default(self):
        self.mark('focus-d5027')
        self.result()
        with patch('campaign_1700.decision', return_value=(D5027, 'fixture')):
            self.assert_cooldown(60, '--d5027-post-success-seconds', '30',
                                 '--campaign-1700-start', str(loop.LABEL_BASE + 1))

    def test_d5102_retry_only_passthrough_allows_opt_in(self):
        self.mark('focus-d5027', 'relay-control')
        row = self.result('8cc80670-9e66-4a59-9e74-fd3bfeadcf7e',
                          label='D5102-synth-five-categories-cap',
                          score=1053.7211993078274, ui=1054, recorded_video=False,
                          evidence_status='video_superseded',
                          relay_phases=['passthrough', 'passthrough'],
                          context_clean=True, errors_before_first_call=0)
        self.assertNotIn('capturePolicy', row)
        self.assertTrue(loop.prior_d5027_success(row))
        self.assert_cooldown(60)
        self.assert_cooldown(30, '--d5027-post-success-seconds', '30')
        self.assert_cooldown(90, '--d5027-post-success-seconds', '90')

    def test_90_seconds_dispatches_once_at_deadline(self):
        self.mark('focus-d5027', 'relay-control')
        self.result(relay_phases=['passthrough', 'passthrough'])
        with patch.object(sys, 'argv', ['loop.py', '--once', '--d5027-post-success-seconds', '90']), \
                patch.object(loop.time, 'time', side_effect=[1089, 1090]), \
                patch.object(loop.time, 'sleep') as sleep:
            loop.main()
        sleep.assert_called_once_with(1)
        self.trial.assert_called_once_with(ANY, D5027)

    def test_90_seconds_falls_back_after_treatment_or_incomplete_phase_evidence(self):
        self.mark('focus-d5027', 'relay-control')
        for changes in ({'relay_phases': ['first', 'final']},
                        {'relay_phases': ['passthrough', 'passthrough'],
                         'request_relay': 'relay-v1:' + 'a' * 64 + ':first-required'},
                        {'relay_phases': []}):
            with self.subTest(changes=changes):
                self.result(**changes)
                self.assert_cooldown(60, '--d5027-post-success-seconds', '90')

    def test_90_seconds_preserves_failure_backoff(self):
        self.mark('focus-d5027', 'relay-control')
        self.result('success', relay_phases=['passthrough', 'passthrough'])
        for index in range(3):
            self.result(f'limited-{index}', valid=False, method_valid=False,
                        rate_limited=True, call_count=0, score=None, ui=None)
            self.assert_cooldown(60 if index < 2 else 120, '--d5027-post-success-seconds', '90')

    def test_90_seconds_requires_once_and_active_baseline_control(self):
        self.mark('focus-d5027', 'relay-control')
        for flags in ([], ['--once', '--campaign-1700-start', '9999']):
            with self.subTest(flags=flags), \
                    patch.object(sys, 'argv', ['loop.py', *flags, '--d5027-post-success-seconds', '90']), \
                    patch('sys.stderr'), self.assertRaises(SystemExit):
                loop.main()
        (self.cache / 'focus-d5027').unlink()
        with patch.object(sys, 'argv', ['loop.py', '--once', '--d5027-post-success-seconds', '90']), \
                patch('sys.stderr'), self.assertRaises(SystemExit):
            loop.main()
        self.trial.assert_not_called()

    def test_ineligible_prior_results_keep_default(self):
        self.mark('focus-d5027')
        for changes in ({'arm': 'synth-five-categories-cap|0|low'},
                        {'arm': 'synth-five-categories-cap-4000|0.2|low'},
                        {'method_valid': False}, {'method_valid': None},
                        {'rate_limited': True}, {'rate_limited': None},
                        {'call_count': 0}, {'call_count': 1}, {'call_count': 3}, {'call_count': None},
                        {'call_count': True}, {'relay_phases': ['sent']},
                        {'relay_phases': ['rewrite', 'passthrough']},
                        {'relay_phases': ['prewarm', 'passthrough']},
                        {'relay_phases': ['suppressed', 'passthrough']},
                        {'relay_phases': ['passthrough', 'error']},
                        {'capturePolicy': 'score-first'}):
            with self.subTest(changes=changes):
                self.result(**changes)
                self.assert_cooldown(60, '--d5027-post-success-seconds', '30')

    def test_manual_stop_precedes_override(self):
        self.mark('focus-d5027', 'stop-requested')
        self.result()
        with patch.object(sys, 'argv', ['loop.py', '--once', '--d5027-post-success-seconds', '30']), \
                patch.object(loop.time, 'sleep') as sleep:
            loop.main()
        sleep.assert_not_called()
        self.trial.assert_not_called()
        self.assertEqual(loop.get(self.cache / 'status.json')['phase'], 'user_stop')

    def test_cli_rejects_unbounded_values(self):
        for value in ('0', '29', '31', '59', '61', '120'):
            with self.subTest(value=value), \
                    patch.object(sys, 'argv', ['loop.py', '--d5027-post-success-seconds', value]), \
                    patch('sys.stderr'):
                with self.assertRaises(SystemExit) as raised:
                    loop.main()
                self.assertEqual(raised.exception.code, 2)
        self.trial.assert_not_called()


if __name__ == '__main__':
    unittest.main()
