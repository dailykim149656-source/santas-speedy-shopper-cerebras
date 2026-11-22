import ast
import json
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
before = {}
current = {}
before_source = (OUT / 'variants.before.py').read_text()
current_source = (ROOT / 'tools/variants.py').read_text()
exec(compile(before_source, 'variants.before.py', 'exec'), before)
exec(compile(current_source, 'tools/variants.py', 'exec'), current)
checks = []

def check(name, passed):
    assert passed, name
    checks.append({'scenario': name, 'observable': 'PASS'})

nonce = 'exp17-local-a'
new_names = current['EXPERIMENT_1700_VARIANTS']
all_names = ('synth-five-categories-cap',) + new_names
rendered = {name: current['prompt']((name, .2, 'low'), nonce) for name in all_names}

def args(name):
    return [json.loads(line) for line in rendered[name].splitlines()[1:]]

def queries(name):
    return [parse_qs(urlparse(arg['url']).query) for arg in args(name)]

check('Every preexisting rendered prompt is unchanged', all(
    current['prompt']((name, .2, 'low'), nonce) == before['prompt']((name, .2, 'low'), nonce)
    for name in before['VARIANTS']))
baseline = json.loads((ROOT / 'runs/a9530b69-3aed-4ea9-8fd9-9ee1fcb36b51/plan.json').read_text())
check('Phase 1 A reproduces stored D5009 request exactly', current['prompt'](
    ('synth-five-categories-cap', .2, 'low'), 'a9530b69') == baseline['prompt'])
check('Phase 1 B instruction is identical to A', rendered[all_names[0]].splitlines()[0] == rendered[all_names[1]].splitlines()[0])
check('Phase 1 B changes only extractMode and maxChars', args(all_names[1]) == [
    dict(arg, extractMode='text', maxChars=4000) for arg in args(all_names[0])])
check('Phase 1 preserves five category order and one in-stock item per category',
      [q['search'][0] for q in queries(all_names[1])] == list(current['SYNTH_CATEGORIES'])
      and all(q['per_page'] == ['1'] and q['stock_status'] == ['instock'] for q in queries(all_names[1])))
single, pages = new_names[1:]
check('Phase 2 instruction is exactly identical', rendered[single].splitlines()[0] == rendered[pages].splitlines()[0])
check('Phase 2 explicitly chooses ordered first five distinct live products and parallel multiple fetches',
      all(text in rendered[single].splitlines()[0] for text in (
          'first five distinct products', 'live ordered catalog',
          'numbered [exact name](exact product URL) links', 'preserving catalog order',
          'processing pages in the order listed', 'in parallel when there is more than one')))
check('Phase 2 uses URL-only JSON arguments', all(set(arg) == {'url'} for name in (single, pages) for arg in args(name)))
check('Phase 2 queries preserve search, order, fields, freshness and stock', all(
    q['search'] == ['eurorack'] and q['orderby'] == ['id'] and q['order'] == ['asc']
    and q['_fields'] == ['name,permalink'] and q['_run'] == [nonce]
    and q['stock_status'] == ['instock'] for name in (single, pages) for q in queries(name)))
check('Phase 2 control fetches six candidates once', len(args(single)) == 1
      and queries(single)[0]['per_page'] == ['6'] and 'offset' not in queries(single)[0])
check('Phase 2 treatment fetches three candidates at explicit offsets 0 and 3', len(args(pages)) == 2
      and [q['offset'] for q in queries(pages)] == [['0'], ['3']]
      and all(q['per_page'] == ['3'] for q in queries(pages)))
base_query = {k: v for k, v in queries(single)[0].items() if k != 'per_page'}
check('Phase 2 query difference is limited to page size and offset', all(
    {k: v for k, v in q.items() if k not in ('per_page', 'offset')} == base_query for q in queries(pages)))
check('Phase 2 logical candidate positions match', list(range(6)) == [
    i for q in queries(pages) for i in range(int(q['offset'][0]), int(q['offset'][0]) + int(q['per_page'][0]))])
check('Every new arm carries caller-provided fresh nonce', all(
    all(parse_qs(urlparse(json.loads(line)['url']).query)['_run'] == ['exp17-local-b']
        for line in current['prompt']((name, .2, 'low'), 'exp17-local-b').splitlines()[1:]) for name in new_names))
check('New arms inherit D5009 workspace instructions', all(
    current['WORKSPACE_AGENTS_BY_VARIANT'][name] == baseline['workspace_agents_md'] for name in new_names))
check('New arms registered at temperature .2 and low with runner token cap 1024',
      all((name, .2, 'low') in current['ARMS'] for name in new_names)
      and current['TEST_MAX_TOKENS'] == baseline['max_completion_tokens'] == 1024
      and all(name not in current['MAX_TOKENS_BY_VARIANT'] for name in new_names))
check('Category and first-five validation families include new arms', new_names[0] in current['CATEGORY_VARIANTS']
      and all(name in current['FIRST_FIVE_VARIANTS'] for name in new_names[1:]))

def scheduler_ast(source):
    return {node.name: ast.dump(node) for node in ast.parse(source).body
            if isinstance(node, ast.FunctionDef) and node.name not in ('catalogs', 'prompt')}
check('All existing scheduling and selection functions are unchanged', scheduler_ast(before_source) == scheduler_ast(current_source))
check('Focus scheduler configuration unchanged', current['FOCUS_CATEGORY_CYCLE'] == before['FOCUS_CATEGORY_CYCLE'])
(OUT / 'rendered-prompts.json').write_text(json.dumps({
    name: {'prompt': prompt, 'temperature': .2, 'thinking': 'low',
           'max_completion_tokens': current['TEST_MAX_TOKENS'],
           'workspace_agents_md': current['WORKSPACE_AGENTS_BY_VARIANT'][name]}
    for name, prompt in rendered.items()}, indent=2) + '\n')
(OUT / 'verification.json').write_text(json.dumps({
    'invocation': 'python3 -B .omo/evidence/exp17-arms/verify.py',
    'scope': 'Offline rendered prompts and configuration only; no provider calls or live catalog claims.',
    'checks': checks, 'result': 'PASS',
    'artifacts': ['rendered-prompts.json', 'verification.json', 'validation.log', 'variants.before.py', 'preexisting.diff']
}, indent=2) + '\n')
print(f'PASS: {len(checks)} prompt/configuration checks; rendered-prompts.json and verification.json recorded')
