"""Offline method scenarios; independent product GETs are stubbed, never claimed live."""
from pathlib import Path
from copy import deepcopy
import hashlib
import json
import sys
sys.path.insert(0, str(Path.cwd() / 'tools'))
import validate
import method_1700 as method
from variants import prompt

OUT = Path('.omo/evidence/exp17-method')
RUN = 'a9530b69-3aed-4ea9-8fd9-9ee1fcb36b51'
raw_path = Path.home() / 'Library/Application Support/Cerebras Speed Bounty/2026-11-22/raw-test' / (RUN + '.json')
raw_bytes = raw_path.read_bytes()
raw = json.loads(raw_bytes)
plan = json.loads((Path('runs') / RUN / 'plan.json').read_text())
archived = json.loads((Path('runs') / RUN / 'evidence.json').read_text())
assert hashlib.sha256(raw_bytes).hexdigest() == archived['private_raw_sha256']
validate.verify_product = lambda item: dict(item, verified=True, reasons=[], offline_get_stub=True)
rows = []


def check(name, p, r, want, mutate_validation=None):
    v = validate.validate(r)
    if mutate_validation:
        mutate_validation(v)
    actual = method.assess(p, r, v)
    row = dict(scenario=name, expected=want, observed=actual, passed=actual is want,
               validator_valid=v['valid'], call_count=v['score']['call_count'],
               mean_exact_tps=v['score']['mean_exact_tps'],
               ordered_candidates=method.ordered_candidates(p, v))
    rows.append(row)
    assert actual is want, row
    return v


def payload(message):
    return message.get('details') or validate.unwrap_json(validate.text_content(message))


def fixture(variant):
    p, r = deepcopy(plan), deepcopy(raw)
    p['variant'] = variant
    p['prompt'] = prompt((variant, .2, 'low'), RUN[:8])
    args = [json.loads(x) for x in p['prompt'].splitlines() if x.startswith('{')]
    catalogs = [validate.unwrap_json(payload(x)['text'])[0] for x in r['history']['messages'][2:7]]
    catalogs.append({'name': 'Synthetic sixth fixture', 'permalink': 'https://aisynthesis.com/product/synthetic-sixth-fixture/'})
    sizes = method.ARMS[variant]
    batch, final = deepcopy(r['history']['messages'][1]), deepcopy(r['history']['messages'][-1])
    batch['content'] = []
    results, slot = [], 0
    for i, (arg, size) in enumerate(zip(args, sizes)):
        batch['content'].append(dict(type='toolCall', id=f'fixture-{i}', name='web_fetch', arguments=arg))
        result = deepcopy(r['history']['messages'][2])
        result['toolCallId'] = f'fixture-{i}'
        value = payload(result)
        value.update(url=arg['url'], finalUrl=arg['url'], text=json.dumps(catalogs[slot:slot+size]))
        result['content'] = [{'type':'text', 'text':json.dumps(value)}]
        results.append(result)
        slot += size
    r['history']['messages'] = [r['history']['messages'][0], batch, *results, final]
    return p, r

check('real D5009 raw and exact baseline score', plan, raw, True)
assert rows[-1]['mean_exact_tps'] == archived['score']['mean_exact_tps']
for variant in method.ARMS:
    p, r = fixture(variant)
    check('positive '+variant, p, r, True)
    r['history']['messages'][2:-1] = reversed(r['history']['messages'][2:-1])
    check('out of order results '+variant, p, r, True)

for variant in ('synth-six-sorted', 'synth-six-sorted-pages'):
    p, r = fixture(variant)
    for part in r['history']['messages'][1]['content']:
        part['arguments'].update(extractMode='text', maxChars=4000)
    check('native optional fetch arguments '+variant, p, r, True)

p, r = fixture('synth-five-categories-cap')
r['history']['messages'][1]['content'].append({'type':'text','text':'Fetching now.'})
check('batch may include explanatory text', p, r, True)
extra = deepcopy(r['history']['messages'][-1])
extra['responseId'] = 'extra-measured-response'
extra['content'] = [{'type':'text','text':'Preparing final answer.'}]
extra['serverGeneration'] = {'completionMs':1000, 'outputTokens':100}
r['history']['messages'].insert(-1, extra)
v = check('extra non-tool timed turn retained in official mean', p, r, True)
assert v['score']['call_count'] == 3
assert v['score']['mean_exact_tps'] == sum(c['tokensPerSecond'] for c in v['calls']) / 3

for variant in ('synth-five-categories-cap', 'synth-five-categories-cap-4000'):
    p, r = fixture(variant)
    r['history']['messages'][1]['content'][0]['arguments']['maxChars'] = 8000
    check('wrong category arguments '+variant, p, r, False)

p, r = fixture('synth-five-categories-cap')
extra = deepcopy(r['history']['messages'][1])
extra['responseId'] = 'split-batch-response'
extra['content'] = [r['history']['messages'][1]['content'].pop()]
r['history']['messages'].insert(2, extra)
check('split timed fetch batches', p, r, False)

p, r = fixture('synth-six-sorted-pages')
r['history']['messages'].pop(3)
check('missing page result', p, r, False)
p, r = fixture('synth-six-sorted-pages')
r['history']['messages'].insert(3, deepcopy(r['history']['messages'][2]))
check('duplicate page result', p, r, False)
p, r = fixture('synth-six-sorted-pages')
value = payload(r['history']['messages'][3])
products = json.loads(value['text'])
products[-1] = json.loads(payload(r['history']['messages'][2])['text'])[0]
value['text'] = json.dumps(products)
r['history']['messages'][3]['content'][0]['text'] = json.dumps(value)
check('duplicate sixth product across pages', p, r, False)

for name in ('truncated', 'cached', 'missing sixth product', 'invalid extra catalog record', 'wrong final order', 'cross-run batch', 'rejected source', 'missing measured call', 'wrong tool URL', 'missing sort query'):
    p, r = fixture('synth-six-sorted')
    mutation = None
    if name in ('truncated','cached','missing sixth product','invalid extra catalog record'):
        value = payload(r['history']['messages'][2])
        if name in ('truncated', 'cached'):
            value[name] = True
        else:
            products = json.loads(value['text'])
            if name == 'missing sixth product': products.pop()
            else: products.append({'name':'invalid'})
            value['text'] = json.dumps(products)
        r['history']['messages'][2]['content'][0]['text'] = json.dumps(value)
    elif name == 'wrong final order':
        lines = r['history']['messages'][-1]['content'][0]['text'].splitlines()
        lines[0], lines[1] = lines[1], lines[0]
        r['history']['messages'][-1]['content'][0]['text'] = '\n'.join(lines)
    elif name == 'cross-run batch':
        r['history']['messages'][1]['__openclaw']['runId'] = 'another-run'
    elif name == 'rejected source':
        mutation = lambda v: v['retail_sources'][0].update(accepted=False)
    elif name == 'missing measured call':
        mutation = lambda v: v['calls'].pop(0)
    elif name == 'wrong tool URL':
        r['history']['messages'][1]['content'][0]['arguments']['url'] += '&extra=1'
    elif name == 'missing sort query':
        p['prompt'] = p['prompt'].replace('&orderby=id','')
    check(name, p, r, False, mutation)

p, r = fixture('synth-six-sorted-pages')
v = validate.validate(r)
v['retail_sources'].reverse()
assert method.ordered_candidates(p,v) == [u for s in reversed(v['retail_sources']) for u in s['products']]
assert method.ordered_candidates({}, {}) is None
assert method.assess({}, {}, {}) is False
report = {'invocation':'python3 -B .omo/evidence/exp17-method/check.py',
          'offline_only':True, 'network_product_gets':'stubbed; no independent live product verification claimed',
          'raw_path':str(raw_path), 'raw_sha256':hashlib.sha256(raw_bytes).hexdigest(),
          'source_file_sha256':hashlib.sha256(Path('tools/method_1700.py').read_bytes()).hexdigest(),
          'scenario_count':len(rows),'passed':all(x['passed'] for x in rows),'scenarios':rows}
(OUT/'results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'passed':report['passed'],'scenario_count':len(rows),'artifact':str(OUT/'results.json')}))
