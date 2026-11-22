"""Offline safety checks for committed plans abandoned before chat.send."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import uuid

import preflight_recovery as recovery
import supervise


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value) if isinstance(value, dict) else value)


class UnsentPreflightTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name) / 'repo'
        self.cache = Path(self.temp.name) / 'cache'
        self.repo.mkdir()
        (self.cache / 'runs').mkdir(parents=True)
        (self.cache / 'loop.lock').touch()
        (self.cache / 'iterations.jsonl').touch()
        self.ident = str(uuid.uuid4())
        self.label = 'D9999-direct-fetch'
        self.key = 'agent:main:shop-d9999-direct-fetch-' + self.ident[:8]
        self.run_dir = self.repo / 'runs' / self.ident
        self.scratch = self.cache / 'capture' / self.ident
        self.plan = {'id': self.ident, 'label': self.label, 'sessionKey': self.key,
                     'prompt': 'Fetch a live catalog? _run=' + self.ident[:8]}
        write(self.run_dir / 'plan.json', self.plan)
        write(self.repo / 'tools' / 'run.mjs',
              "if(!ready)throw Error('Recorder not ready; no chat request sent');\n"
              "await req('chat.send',{sessionKey,message:prompt});\n")
        subprocess.run(['git', '-C', str(self.repo), 'init', '-q'], check=True)
        subprocess.run(['git', '-C', str(self.repo), 'config', 'user.name', 'Offline Test'], check=True)
        subprocess.run(['git', '-C', str(self.repo), 'config', 'user.email', 'test@example.invalid'], check=True)
        subprocess.run(['git', '-C', str(self.repo), 'add', '.'], check=True)
        subprocess.run(['git', '-C', str(self.repo), 'commit', '-qm', 'Commit plan and runner'], check=True)
        write(self.scratch / 'run.json', dict(self.plan, readyPath=str(self.scratch / 'ready.json')))
        write(self.scratch / 'error.json', {'error': 'CDP unavailable', 'sessionKey': self.key})
        write(self.scratch / 'run.log', '')
        write(self.scratch / 'video.log', '')
        write(self.cache / 'status.json', {'phase': 'needs_attention', 'error': 'ready.json'})

    def test_seals_without_score_and_supervisor_resumes(self):
        state = recovery.seal_unsent(self.repo, self.cache, self.ident, 'TimeoutError')
        self.assertEqual(state['phase'], 'preflight_aborted')
        receipt = recovery.verify_preflight(self.repo, self.cache, self.ident)
        self.assertEqual(receipt['status'], 'aborted_before_send')
        self.assertFalse((self.run_dir / 'evidence.json').exists())
        self.assertEqual((self.cache / 'iterations.jsonl').read_text(), '')
        self.assertTrue((self.repo / 'evidence.bundle').is_file())
        older = dict(state, time='2000-01-01T00:00:00+00:00')
        write(self.cache / 'status.json', older)
        with patch.object(supervise, 'gateway_ready', return_value=True):
            self.assertEqual(supervise.next_action(self.repo, self.cache)[0], 'resume')

    def test_rejects_every_possible_send_marker(self):
        forbidden = [self.scratch / 'ready.json', self.scratch / 'finish.json',
                     self.cache / 'runs' / (self.label + '.pending.json'),
                     self.cache / 'runs' / (self.label + '.json'),
                     self.run_dir / 'evidence.json']
        for path in forbidden:
            with self.subTest(path=path.name):
                write(path, '{}')
                with self.assertRaises(ValueError):
                    recovery.unsent_inputs(self.repo, self.cache, self.ident)
                path.unlink()

    def test_rejects_live_child_or_uncommitted_plan(self):
        with patch.object(recovery, 'active_children', return_value=['live run.mjs']):
            with self.assertRaises(ValueError):
                recovery.unsent_inputs(self.repo, self.cache, self.ident)
        write(self.run_dir / 'plan.json', dict(self.plan, prompt='changed'))
        with self.assertRaises(ValueError):
            recovery.unsent_inputs(self.repo, self.cache, self.ident)

    def test_tampered_receipt_blocks_supervisor(self):
        recovery.seal_unsent(self.repo, self.cache, self.ident, 'TimeoutError')
        receipt_path = self.run_dir / 'preflight.json'
        receipt = json.loads(receipt_path.read_text())
        receipt['cause_class'] = 'tampered'
        write(receipt_path, receipt)
        with self.assertRaises(ValueError):
            recovery.verify_preflight(self.repo, self.cache, self.ident)
        with patch.object(supervise, 'gateway_ready', return_value=True):
            action, reason = supervise.next_action(self.repo, self.cache)
        self.assertEqual(action, 'wait')
        self.assertIn('receipt needs review', reason)


if __name__ == '__main__':
    unittest.main()
