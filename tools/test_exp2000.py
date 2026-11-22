"""Offline tests for the isolated exp-tps-2000 branch, methods, scheduler, and runtime."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import unittest
import uuid

import campaign_2000
import method_2000
import validate
import variants


TOOLS_DIR = Path(__file__).resolve().parent


def _fake_product(slot, pid, slug):
    return {
        'id': pid,
        'name': f'AI Synth Module {slot}',
        'slug': slug,
        'type': 'variable',
        'permalink': f'https://aisynthesis.com/product/{slug}/',
        'prices': {'price': '1500', 'currency_code': 'USD', 'currency_minor_unit': 2},
        'stock_availability': {'text': '10 in stock' if slot != 2 else '', 'class': 'in-stock'},
        'variations': [
            {'id': pid * 10 + i, 'attributes': [{'name': 'Type', 'value': f'var-{slot}-{i}'}]}
            for i in range(6)
        ],
    }


def _verbatim_text(products):
    blocks = []
    for idx, prod in enumerate(products, 1):
        stock = prod['stock_availability']['text'] or prod['stock_availability']['class']
        vstr = ', '.join(
            f"{v['id']}:{','.join(a['value'] for a in v['attributes'])}"
            for v in prod['variations']
        )
        blocks.append(
            f"{idx}. [{prod['name']}]({prod['permalink']})\n"
            f"- ID: {prod['id']} | Slug: {prod['slug']} | Type: {prod['type']} | "
            f"Price: {prod['prices']['price']} {prod['prices']['currency_code']} | Stock: {stock}\n"
            f"- Variations: {vstr}"
        )
    return '\n'.join(blocks)


def _tool_result_msg(run_id, call_id, url, payload_obj):
    return {
        'role': 'toolResult',
        'toolCallId': call_id,
        'isError': False,
        '__openclaw': {'runId': run_id, 'resultContentSource': 'network'},
        'details': {
            'url': url,
            'finalUrl': url,
            'status': 200,
            'cached': False,
            'truncated': False,
            'text': json.dumps(payload_obj),
        },
    }


def _make_two_call_fixtures(variant_name):
    run_id = str(uuid.uuid4())
    nonce = run_id[:8]
    arm = (variant_name, 0.2, 'low')
    prompt_text = variants.prompt(arm, nonce)
    reqs = [json.loads(line) for line in prompt_text.splitlines() if line.lstrip().startswith('{')]
    products = [_fake_product(i + 1, 21000 + i, f'ai-mod-{i + 1}') for i in range(5)]
    plan = {'id': run_id, 'variant': variant_name, 'prompt': prompt_text}
    final_text = (_verbatim_text(products) if variant_name in method_2000.VERBATIM_ARMS
                  else '\n'.join(f"{i}. [{p['name']}]({p['permalink']})" for i, p in enumerate(products, 1)))
    messages = [
        {
            'role': 'assistant',
            '__openclaw': {'runId': run_id},
            'stopReason': 'toolUse',
            'responseId': 'resp-0',
            'serverGeneration': {'completionMs': 320.0, 'outputTokens': 420},
            'usage': {'input': 700, 'cacheRead': 2048},
            'content': [
                {'type': 'toolCall', 'id': f'call_{i}', 'name': 'web_fetch', 'arguments': req}
                for i, req in enumerate(reqs)
            ],
        },
        *[_tool_result_msg(run_id, f'call_{i}', req['url'], [prod])
          for i, (req, prod) in enumerate(zip(reqs, products))],
        {
            'role': 'assistant',
            '__openclaw': {'runId': run_id},
            'stopReason': 'stop',
            'responseId': 'resp-1',
            'serverGeneration': {'completionMs': 180.0, 'outputTokens': 380},
            'usage': {'input': 3100, 'cacheRead': 2048},
            'content': [{'type': 'text', 'text': final_text}],
        },
    ]
    raw = {'id': run_id, 'history': {'messages': messages}}
    validation = {
        'run_id': run_id,
        'valid': True,
        'calls': [
            {'message_index': 0, 'response_id': 'resp-0', 'completionMs': 320.0, 'outputTokens': 420},
            {'message_index': 6, 'response_id': 'resp-1', 'completionMs': 180.0, 'outputTokens': 380},
        ],
        'final_text': final_text,
    }
    return plan, raw, validation, products


def _make_three_call_fixtures():
    run_id = str(uuid.uuid4())
    nonce = run_id[:8]
    arm = ('exp2k-three-call-verify', 0.2, 'low')
    prompt_text = variants.prompt(arm, nonce)
    json_lines = [json.loads(line) for line in prompt_text.splitlines() if line.lstrip().startswith('{')]
    step1_reqs = [item for item in json_lines if '<ID>' not in item['url']]
    products = [_fake_product(i + 1, 22000 + i, f'ai-mod3-{i + 1}') for i in range(5)]
    step1_payloads = [[{'id': p['id'], 'name': p['name'], 'permalink': p['permalink']}] for p in products]
    step2_reqs = [
        {
            'url': (f'https://aisynthesis.com/wp-json/wc/store/v1/products?include={p["id"]}'
                    f'&_fields={variants.SYNTH_RICH_FIELDS}&_run={nonce}'),
            'extractMode': 'text',
            'maxChars': 4000,
        }
        for p in products
    ]
    final_text = _verbatim_text(products)
    plan = {'id': run_id, 'variant': 'exp2k-three-call-verify', 'prompt': prompt_text}
    messages = [
        {
            'role': 'assistant',
            '__openclaw': {'runId': run_id},
            'stopReason': 'toolUse',
            'responseId': 'resp-0',
            'serverGeneration': {'completionMs': 310.0, 'outputTokens': 390},
            'content': [
                {'type': 'toolCall', 'id': f's1_{i}', 'name': 'web_fetch', 'arguments': req}
                for i, req in enumerate(step1_reqs)
            ],
        },
        *[_tool_result_msg(run_id, f's1_{i}', req['url'], pay)
          for i, (req, pay) in enumerate(zip(step1_reqs, step1_payloads))],
        {
            'role': 'assistant',
            '__openclaw': {'runId': run_id},
            'stopReason': 'toolUse',
            'responseId': 'resp-1',
            'serverGeneration': {'completionMs': 240.0, 'outputTokens': 500},
            'content': [
                {'type': 'toolCall', 'id': f's2_{i}', 'name': 'web_fetch', 'arguments': req}
                for i, req in enumerate(step2_reqs)
            ],
        },
        *[_tool_result_msg(run_id, f's2_{i}', req['url'], [prod])
          for i, (req, prod) in enumerate(zip(step2_reqs, products))],
        {
            'role': 'assistant',
            '__openclaw': {'runId': run_id},
            'stopReason': 'stop',
            'responseId': 'resp-2',
            'serverGeneration': {'completionMs': 220.0, 'outputTokens': 510},
            'content': [{'type': 'text', 'text': final_text}],
        },
    ]
    raw = {'id': run_id, 'history': {'messages': messages}}
    validation = {
        'run_id': run_id,
        'valid': True,
        'calls': [
            {'message_index': 0, 'response_id': 'resp-0', 'completionMs': 310.0, 'outputTokens': 390},
            {'message_index': 6, 'response_id': 'resp-1', 'completionMs': 240.0, 'outputTokens': 500},
            {'message_index': 12, 'response_id': 'resp-2', 'completionMs': 220.0, 'outputTokens': 510},
        ],
        'final_text': final_text,
    }
    return plan, raw, validation, products


class Exp2000Tests(unittest.TestCase):
    def test_prompts_and_workspace_agents(self):
        nonce = 'abcd1234'
        for name in variants.EXP2000_VARIANTS:
            with self.subTest(variant=name):
                p = variants.prompt((name, 0.2, 'low'), nonce)
                self.assertIn(f'_run={nonce}', p)
                self.assertNotIn('__NONCE__', p)
                self.assertNotIn('aisynthesis.com/product/', p)
                json_lines = [json.loads(line) for line in p.splitlines() if line.lstrip().startswith('{')]
                if name == 'exp2k-three-call-verify':
                    self.assertEqual(len(json_lines), 6)
                    self.assertIn('<ID>', json_lines[0]['url'])
                    for req in json_lines[1:]:
                        self.assertEqual(req['extractMode'], 'text')
                        self.assertEqual(req['maxChars'], 2000)
                else:
                    self.assertEqual(len(json_lines), 5)
                    for req in json_lines:
                        self.assertEqual(req['extractMode'], 'text')
                        self.assertEqual(req['maxChars'], 4000)
                agents_md = variants.WORKSPACE_AGENTS_BY_VARIANT.get(name, '')
                self.assertTrue(agents_md.strip())
                self.assertLessEqual(len(agents_md), 4000)
                self.assertIn('Think in at most 5 words.', agents_md)
                self.assertNotIn('Emit zero reasoning tokens', agents_md)

        self.assertEqual(len(variants.LEGACY_WORKSPACE_AGENTS_MD), 2)
        for legacy in variants.LEGACY_WORKSPACE_AGENTS_MD:
            self.assertIn('Emit zero reasoning tokens', legacy)

        # Ensure existing 1700 prompt remained identical in format
        p1700 = variants.prompt(('synth-five-categories-cap-4000', 0.2, 'low'), nonce)
        j1700 = [json.loads(line) for line in p1700.splitlines() if line.lstrip().startswith('{')]
        self.assertEqual(len(j1700), 5)
        self.assertIn('search=cable', j1700[4]['url'])

    def test_answer_links_on_verbatim_cards(self):
        products = [_fake_product(i + 1, 21000 + i, f'ai-mod-{i + 1}') for i in range(5)]
        text = _verbatim_text(products)
        urls, misleading = validate.answer_links(text)
        self.assertFalse(misleading)
        self.assertEqual(urls, [p['permalink'] for p in products])
        extra_urls, _ = validate.answer_links(text + '\nhttps://docs.google.com/extra')
        self.assertEqual(len(extra_urls), 6)

    def test_method_2000_two_call_and_rejects(self):
        for name in ('exp2k-call0-zero-think', 'exp2k-verbatim-cards', 'exp2k-verbatim-cards-topp03'):
            plan, raw, validation, _ = _make_two_call_fixtures(name)
            self.assertTrue(method_2000.assess(plan, raw, validation), msg=name)

        # Reject wrong link order
        plan, raw, validation, products = _make_two_call_fixtures('exp2k-verbatim-cards')
        swapped = _verbatim_text([products[1], products[0], *products[2:]])
        raw['history']['messages'][-1]['content'][0]['text'] = swapped
        validation['final_text'] = swapped
        self.assertFalse(method_2000.assess(plan, raw, validation))

        # Reject missing variation verbatim copy
        plan, raw, validation, products = _make_two_call_fixtures('exp2k-verbatim-cards')
        short_text = '\n'.join(
            f"{i}. [{p['name']}]({p['permalink']})\n- ID: {p['id']} | Slug: {p['slug']}"
            for i, p in enumerate(products, 1)
        )
        raw['history']['messages'][-1]['content'][0]['text'] = short_text
        validation['final_text'] = short_text
        self.assertFalse(method_2000.assess(plan, raw, validation))

        # Reject wrong maxChars in tool call
        plan, raw, validation, _ = _make_two_call_fixtures('exp2k-call0-zero-think')
        raw['history']['messages'][0]['content'][0]['arguments']['maxChars'] = 20000
        self.assertFalse(method_2000.assess(plan, raw, validation))

        diags = method_2000.call_diagnostics(raw)
        self.assertEqual(len(diags), 2)
        self.assertEqual(diags[0]['tool_count'], 5)
        self.assertEqual(diags[1]['think_chars'], 0)

    def test_method_2000_three_call_and_rejects(self):
        plan, raw, validation, _ = _make_three_call_fixtures()
        self.assertTrue(method_2000.assess(plan, raw, validation))

        # Reject mismatched Step-2 include ID
        plan, raw, validation, _ = _make_three_call_fixtures()
        bad_url = raw['history']['messages'][6]['content'][0]['arguments']['url'].replace('22000', '99999')
        raw['history']['messages'][6]['content'][0]['arguments']['url'] = bad_url
        self.assertFalse(method_2000.assess(plan, raw, validation))

        # Reject extra URL in final_text
        plan, raw, validation, _ = _make_three_call_fixtures()
        extra = validation['final_text'] + '\nhttps://aisynthesis.com/extra'
        raw['history']['messages'][-1]['content'][0]['text'] = extra
        validation['final_text'] = extra
        self.assertFalse(method_2000.assess(plan, raw, validation))

    def test_campaign_2000_schedule_and_early_stop(self):
        repo = TOOLS_DIR.parent
        rows = []
        # Walk all 20 slots cleanly where Phase 2 B (verbatim cards) beats A
        for idx in range(20):
            arm, reason = campaign_2000.decision(repo, 6001, rows)
            self.assertIsNotNone(arm, msg=f'slot {idx}: {reason}')
            score = 1550.0 if 'verbatim' in arm[0] or 'three-call' in arm[0] else 1100.0
            rows.append({
                'id': f'id-{idx}',
                'label': f'D{6001 + idx}-{arm[0]}',
                'arm': variants.arm_key(arm),
                'score': score,
                'ui': round(score),
                'valid': True,
                'method_valid': True,
                'recorded_video': True,
            })
        s = campaign_2000.summary(repo, 6001, rows)
        self.assertEqual(s['phase2_winner'], 'exp2k-verbatim-cards|0.2|low')
        self.assertIsNone(s['next_arm'])
        self.assertIn('20 trials', s['reason'])
        self.assertEqual(s['phases'][2]['arm_a'], 'exp2k-verbatim-cards|0.2|low')
        self.assertEqual(s['phases'][2]['arm_b'], 'exp2k-verbatim-cards-topp03|0.15|low')
        self.assertEqual(s['phases'][3]['arm_b'], 'exp2k-three-call-verify|0.2|low')

        # Early stop strictly > 2000 for both score and ui
        arm0, _ = campaign_2000.decision(repo, 6001, [])
        row_2000_exact = {
            'id': 'id-0',
            'label': f'D6001-{arm0[0]}',
            'arm': variants.arm_key(arm0),
            'score': 2000.0,
            'ui': 2000,
            'valid': True,
            'method_valid': True,
            'recorded_video': True,
        }
        arm1, _ = campaign_2000.decision(repo, 6001, [row_2000_exact])
        self.assertIsNotNone(arm1)

        row_over = dict(row_2000_exact, score=2001.4, ui=2001)
        arm_stop, stop_reason = campaign_2000.decision(repo, 6001, [row_over])
        self.assertIsNone(arm_stop)
        self.assertIn('>2000', stop_reason)

    def test_fast_probe_2000_schedule_and_early_stop(self):
        repo = TOOLS_DIR.parent
        rows = []
        seen_arms = []
        scores_by_arm = {
            'exp2k-verbatim-cards|0.2|low': 1420.0,
            'exp2k-verbatim-cards-topp03|0.15|low': 1610.0,
            'exp2k-three-call-verify|0.2|low': 1510.0,
        }
        for idx in range(6):
            arm, reason = campaign_2000.fast_decision(repo, 6008, rows)
            self.assertIsNotNone(arm, msg=f'slot {idx}: {reason}')
            arm_str = variants.arm_key(arm)
            seen_arms.append(arm_str)
            score = scores_by_arm[arm_str]
            rows.append({
                'id': f'fast-{idx}',
                'label': f'D{6008 + idx}-{arm[0]}',
                'arm': arm_str,
                'score': score,
                'ui': round(score),
                'valid': True,
                'method_valid': True,
                'recorded_video': True,
            })
        self.assertEqual(len(seen_arms), 6)
        for key in scores_by_arm:
            self.assertEqual(seen_arms.count(key), 2)
        self.assertEqual(len(set(seen_arms[:3])), 3)

        fs = campaign_2000.fast_summary(repo, 6008, rows)
        self.assertIsNone(fs['next_arm'])
        self.assertEqual(fs['best_arm'], 'exp2k-verbatim-cards-topp03|0.15|low')
        self.assertIn('6 trials', fs['reason'])

        report = campaign_2000.format_fast_report(repo, 6008, rows)
        self.assertIn('Fast Probe 2000 Report (start=D6008)', report)
        self.assertIn('exp2k-verbatim-cards-topp03|0.15|low', report)

        # Early stop strictly > 2000 for both score and ui
        arm0, _ = campaign_2000.fast_decision(repo, 6008, [])
        row_exact = {
            'id': 'fast-0',
            'label': f'D6008-{arm0[0]}',
            'arm': variants.arm_key(arm0),
            'score': 2000.0,
            'ui': 2000,
            'valid': True,
            'method_valid': True,
            'recorded_video': True,
        }
        arm1, _ = campaign_2000.fast_decision(repo, 6008, [row_exact])
        self.assertIsNotNone(arm1)

        row_over = dict(row_exact, score=2001.2, ui=2001)
        arm_stop, stop_reason = campaign_2000.fast_decision(repo, 6008, [row_over])
        self.assertIsNone(arm_stop)
        self.assertIn('>2000', stop_reason)

    def test_runtime_root_and_launcher_syntax(self):
        launcher = TOOLS_DIR / 'run_exp2000.sh'
        self.assertTrue(launcher.is_file())
        self.assertTrue(os.access(launcher, os.X_OK))
        subprocess.run(['bash', '-n', str(launcher)], check=True)
        help_launcher = subprocess.run([str(launcher), '--help'], check=True, capture_output=True, text=True)
        self.assertIn('--fast-probe', help_launcher.stdout)
        self.assertIn('--fast-report', help_launcher.stdout)
        help_loop = subprocess.run(['python3', '-B', str(TOOLS_DIR / 'loop.py'), '--help'],
                                   check=True, capture_output=True, text=True)
        self.assertIn('--fast-probe-2000-start', help_loop.stdout)

        exp_root = Path.home() / 'Library/Caches/cerebras-speed-bounty/2026-11-22-exp2000'
        if exp_root.exists():
            cfg = json.loads((exp_root / 'shopper-test/openclaw.json').read_text())
            self.assertEqual(cfg['gateway']['port'], 19864)
            self.assertEqual(cfg['agents']['defaults']['model']['primary'], 'cerebras/moonshotai-kimi-k3.1-pro-trial')
            self.assertEqual(Path(cfg['agents']['defaults']['workspace']), exp_root / 'shopper-test/workspace')
            node_bin = shutil.which('node')
            if node_bin:
                subprocess.run([node_bin, '--check', str(exp_root / 'mean-2000/profile.mjs')], check=True)


if __name__ == '__main__':
    unittest.main()
