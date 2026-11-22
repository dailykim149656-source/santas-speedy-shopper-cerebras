import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from unittest.mock import patch

repo = Path.cwd()
sys.path.insert(0, str(repo / 'tools'))
import variants as v
import loop
old = {}
exec(compile(subprocess.check_output(['git', 'show', 'HEAD:tools/variants.py'], text=True), 'baseline_variants.py', 'exec'), old)
for name in old['VARIANTS']:
    assert v.prompt((name, .2, 'low'), 'qa-nonce') == old['prompt']((name, .2, 'low'), 'qa-nonce'), name
assert v.ARMS == old['ARMS']
assert v.TEST_ARMS == old['TEST_ARMS']
assert v.EXACT_ARGS_VARIANTS == old['EXACT_ARGS_VARIANTS']
assert v.CATEGORY_VARIANTS == old['CATEGORY_VARIANTS']
history = []
for _ in range(100):
    assert v.choose(history) == old['choose'](history)
    assert v.choose_test(history) == old['choose_test'](history)
    history.append({'arm':v.arm_key(v.choose_test(history)), 'valid':True, 'method_valid':True, 'score':1000})
print('PASS: all existing prompts, arms, exact-args shapes, and 100 scheduling turns unchanged')
a, b = v.TARGET_ARMS[3], v.TARGET_ARMS[2]
original = v.prompt(a, 'qa-nonce').splitlines()
changed = v.prompt(b, 'qa-nonce').splitlines()
assert len(original) == len(changed) == 2
assert json.loads(changed[1]) == {'url':original[1], 'extractMode':'text', 'maxChars':20000}
assert changed[0] == original[0].replace('web_fetch this live catalog', 'call web_fetch with the exact argument object below')
assert v.VARIANTS[a[0]][:-1] == v.VARIANTS[b[0]][:-1]
assert v.WORKSPACE_AGENTS_BY_VARIANT[a[0]] == v.WORKSPACE_AGENTS_BY_VARIANT[b[0]]
assert a[1:] == b[1:] == (.2, 'low')
assert all(arm[0] in v.FIRST_FIVE_VARIANTS for arm in (a,b))
assert all(arm[0] not in v.CATEGORY_VARIANTS for arm in (a,b))
assert all(json.loads(line).keys() == {'url'} for line in v.prompt(('synth-five-categories-cap',0,'low'),'qa').splitlines()[1:])
print('PASS: single-catalog prompt is the only experimental difference; old five-category objects remain url-only')
history = []
for n in range(20):
    selected = v.choose_target(history)
    assert selected == v.TARGET_ARMS[n % 4]
    history.append({'arm':v.arm_key(selected), 'valid':False})
assert v.choose_target([{'arm':v.arm_key(a)}]*5) == v.TARGET_ARMS[0]
assert v.choose_target([{'arm':v.arm_key(v.TARGET_ARMS[0])}]*5) == v.TARGET_ARMS[1]
assert v.choose_target([{'arm':v.arm_key((a[0],0,'low'))}]*5) == v.TARGET_ARMS[0]
assert v.TARGET_ARMS[:2] == (('synth-five-categories-cap',.2,'low'),('synth-five-categories-cap',0.0,'low'))
assert v.prompt(v.TARGET_ARMS[0], 'qa') == v.prompt(v.TARGET_ARMS[1], 'qa')
assert all(arm[0] in v.CATEGORY_VARIANTS and arm[0] not in v.FIRST_FIVE_VARIANTS for arm in v.TARGET_ARMS[:2])
print('PASS: four-arm balanced cycle prioritizes category temperatures, includes failed attempts, preserves method separation')
good = {'id':'fixture', 'arm':v.arm_key(a),'goal':False,'valid':True,'method_valid':True,'recorded_video':True,'score':1200,'ui':1200}
assert loop.target_met([good])
assert loop.target_met([dict(good,score=1300,ui=1300)])
assert not loop.target_met([])
for field in ('valid','method_valid','recorded_video'):
    for value in (False,None,1):
        assert not loop.target_met([dict(good,**{field:value})]), (field,value)
for field in ('score','ui'):
    for value in (1199.99,None):
        assert not loop.target_met([dict(good,**{field:value})]), (field,value)
print('PASS: both inclusive thresholds and all three explicit true flags required')
# Invoke the real main path with only filesystem state and trial execution isolated.
for test_schedule, marker, rows, expected in (
    (False,False,[],v.choose([])), (False,True,[good],v.choose([good])),
    (True,False,[good],v.choose_test([good])), (True,True,[],v.TARGET_ARMS[0]),
    (True,True,[dict(good,score=1199)],v.TARGET_ARMS[0]), (True,True,[good],None)):
    with tempfile.TemporaryDirectory() as temp:
        cache = Path(temp)
        if marker:
            (cache/'target-1200').touch()
        calls = []
        with patch.multiple(loop,CACHE=cache,RUNS=cache/'runs',TEST_SCHEDULE=test_schedule), \
             patch.object(sys,'argv',['loop.py','--once']), \
             patch.object(loop,'past',return_value=rows), \
             patch.object(loop,'get',return_value={'ended':{'time':0}}), \
             patch.object(loop,'next_trial_number',return_value=5009), \
             patch.object(loop,'status') as status, \
             patch.object(loop,'run_trial',side_effect=lambda n,arm:calls.append((n,arm)) or False):
            loop.main()
        assert calls == ([] if expected is None else [(5009,expected)]), (test_schedule,marker,calls)
        if expected is None:
            status.assert_called_once_with('target_1200_met')
print('PASS: real main path selects/stops only for opted-in test schedule; no trial starts after qualifying history')
