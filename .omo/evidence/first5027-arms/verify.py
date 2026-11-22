"""Offline method regression: historical product GET records are explicit fixtures."""
import copy
import hashlib
import json
from pathlib import Path
import socket
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'tools'))
import method_1700 as method
import validate
import variants

OUT = Path(__file__).resolve().parent
IDENT = 'cd75e5e0-be7c-471f-a9ab-c9e6f0d1bd77'
RAW = Path.home() / 'Library/Application Support/Cerebras Speed Bounty/2026-11-22/raw-test' / (IDENT + '.json')
raw_bytes = RAW.read_bytes()
raw = json.loads(raw_bytes)
plan = json.loads((ROOT / 'runs' / IDENT / 'plan.json').read_text())
evidence = json.loads((ROOT / 'runs' / IDENT / 'evidence.json').read_text())
recorded = json.loads((Path.home() / 'Library/Caches/cerebras-speed-bounty/2026-11-22-test/mean-2000/capture' / IDENT / 'validation.json').read_text())
checks = []

def check(name, actual, expected=True):
    checks.append({'scenario': name, 'actual': actual, 'expected': expected, 'passed': actual == expected})
    assert actual == expected, name

check('original raw SHA256 matches committed evidence and validation',
      hashlib.sha256(raw_bytes).hexdigest() == evidence['private_raw_sha256'] == recorded['input_sha256'])
check('original raw size matches committed evidence', len(raw_bytes) == evidence['private_raw_bytes'])
products = {p['url']: p for p in recorded['products']}

def product_fixture(item):
    product = copy.deepcopy(products[item['url']])
    assert product['catalog_name'] == item['catalog_name']
    assert product['source_tool_call_id'] == item['source_tool_call_id']
    return product

def recalculate(data):
    with patch.object(socket.socket, 'connect', side_effect=AssertionError('offline: no network')), patch.object(validate, 'verify_product', side_effect=product_fixture):
        return validate.validate(data)

original = recalculate(raw)
check('original raw source checks and full score recomputed offline',
      original['valid'] and original['calls'] == recorded['calls']
      and original['retail_sources'] == recorded['retail_sources']
      and original['score']['mean_exact_tps'] == recorded['score']['mean_exact_tps'])
check('actual D5027 passes first5027 method', method.assess_first5027(plan, raw, original))
check('original baseline prompt byte parity', variants.prompt((variants.FIRST5027_VARIANTS[0], .2, 'low'), IDENT[:8]) == plan['prompt'])
check('original baseline workspace byte parity', variants.WORKSPACE_AGENTS_BY_VARIANT[variants.FIRST5027_VARIANTS[0]] == plan['workspace_agents_md'])

fixtures = {}
for name in variants.FIRST5027_VARIANTS:
    p, r = copy.deepcopy(plan), copy.deepcopy(raw)
    p['variant'] = name
    p['prompt'] = variants.prompt((name, .2, 'low'), IDENT[:8])
    p['workspace_agents_md'] = variants.WORKSPACE_AGENTS_BY_VARIANT[name]
    for key in ('variant', 'prompt', 'workspace_agents_md'):
        r[key] = p[key]
    calls = [part for part in r['history']['messages'][1]['content'] if part.get('type') == 'toolCall']
    arguments = [json.loads(line) for line in p['prompt'].splitlines()[1:]]
    for call, args in zip(calls, arguments):
        call['arguments'] = args
    v = recalculate(r)
    fixtures[name] = (p, r, v)
    before = json.dumps(v, sort_keys=True)
    check(name + ': method positive and full validation unmodified',
          method.assess_first5027(p, r, v) and before == json.dumps(v, sort_keys=True))
    check(name + ': exact settings and arm registration',
          (name, .2, 'low') in variants.ARMS and variants.TEST_MAX_TOKENS == 1024
          and name not in variants.TOP_P_BY_VARIANT and name in variants.CATEGORY_VARIANTS)
    check(name + ': exact URL/category order and argument keys',
          [a['url'] for a in arguments] == [a['url'] for a in method._requests(plan)]
          and all(set(a) == ({'url', 'extractMode'} if name == 'first5027-extract-text' else {'url'}) for a in arguments))
check('C changes only the specified conditional workspace line and preserves A prompt',
      fixtures['first5027-defer-answer'][0]['prompt'] == plan['prompt']
      and fixtures['first5027-defer-answer'][0]['workspace_agents_md'] == plan['workspace_agents_md'] + variants.FIRST5027_DEFER_LINE + '\n')
check('B changes only the five argument objects',
      fixtures['first5027-extract-text'][0]['prompt'].replace(',"extractMode":"text"', '') == plan['prompt']
      and fixtures['first5027-extract-text'][0]['workspace_agents_md'] == plan['workspace_agents_md'])

def negative(name, arm, mutate):
    p, r, v = copy.deepcopy(fixtures[arm])
    mutate(p, r, v)
    check(name, method.assess_first5027(p, r, v), False)

A, B, C = variants.FIRST5027_VARIANTS
negative('B rejects actual maxChars option', B, lambda p,r,v: r['history']['messages'][1]['content'][-1]['arguments'].update(maxChars=4000))
negative('B rejects planned maxChars option', B, lambda p,r,v: p.update(prompt=p['prompt'].replace('"extractMode":"text"', '"extractMode":"text","maxChars":4000')))
negative('C rejects vca final category', C, lambda p,r,v: p.update(prompt=p['prompt'].replace('search=cable', 'search=vca')))
negative('C rejects missing conditional instruction', C, lambda p,r,v: p.update(workspace_agents_md=plan['workspace_agents_md']))
negative('reject wrong run binding', A, lambda p,r,v: r.update(id='another-run'))
negative('reject measured response mismatch', A, lambda p,r,v: v['calls'][0].update(response_id='another-response'))
negative('reject measured tokens mismatch', A, lambda p,r,v: v['calls'][0].update(outputTokens=448))
negative('reject reordered tool calls', A, lambda p,r,v: r['history']['messages'][1]['content'].reverse())
negative('reject invalid source', A, lambda p,r,v: v['retail_sources'][0].update(accepted=False))
negative('reject cached source', A, lambda p,r,v: v['retail_sources'][0].update(cached=True))
negative('reject invalid product verification', A, lambda p,r,v: v['products'][0].update(verified=False))
negative('reject product binding mismatch', A, lambda p,r,v: v['products'][0].update(source_tool_call_id='another-call'))
negative('reject final answer mismatch', A, lambda p,r,v: v.update(final_text='different answer'))

for position, label, expected in [(1, 'earlier measured assistant before five-call batch', False), (7, 'additional measured assistant after tool results', True)]:
    p, r, v = copy.deepcopy(fixtures[A])
    extra = copy.deepcopy(r['history']['messages'][-1])
    extra['responseId'] = 'extra-measured-response'
    extra['content'] = [{'type': 'text', 'text': 'Checking the results.'}]
    extra['serverGeneration'] = {'completionMs': 200, 'outputTokens': 50}
    r['history']['messages'].insert(position, extra)
    v = recalculate(r)
    check(label + ': full validator and legacy method pass', v['valid'] and method.assess(p, r, v))
    check(label + ': first-response check', method.assess_first5027(p, r, v), expected)
    check(label + ': all three measurements remain in mean',
          len(v['calls']) == 3 and v['score']['call_count'] == 3
          and v['score']['mean_exact_tps'] == sum(c['tokensPerSecond'] for c in v['calls']) / 3)

report = {'invocation': 'python3 .omo/evidence/first5027-arms/verify.py',
          'binary_observable': 'exit 0 and every checks[].passed true',
          'raw_path': str(RAW), 'raw_sha256': hashlib.sha256(raw_bytes).hexdigest(),
          'scope': 'Offline method/config verification. Historical independent product GET records are fixtures; source validity, arguments, raw binding and all server metrics are recomputed. No current product availability or provider performance claim.',
          'checks': checks, 'passed': len(checks), 'failed': 0}
(OUT / 'results.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps({'passed': len(checks), 'failed': 0, 'artifact': str(OUT / 'results.json')}))
