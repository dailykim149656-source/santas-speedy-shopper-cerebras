"""Offline observer exemption cases; no live processes or provider requests changed."""
import copy
import json
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'tools'))
import preflight_recovery as recovery

checks = []
with tempfile.TemporaryDirectory() as temp:
    repo = Path(temp).resolve() / 'repo with spaces'
    cache = Path(temp).resolve() / 'private root' / 'mean-2000'
    ident = 'e668c558-7718-4125-ac0d-5a6cd93788dd'
    label = 'D5037-first5027-extract-text'
    plan = dict(id=ident, label=label, variant='first5027-extract-text',
                sessionKey='agent:main:shop-' + label.lower() + '-' + ident[:8],
                prompt='offline fixture', capturePolicy='score-first')
    run_dir = repo / 'runs' / ident
    scratch = cache / 'capture' / ident
    film = cache / 'film-first5027-5037' / ident / 'attempt-01'
    for folder in (run_dir, scratch, cache / 'runs', film):
        folder.mkdir(parents=True)
    plan_path = run_dir / 'plan.json'
    config_path = scratch / 'run.json'
    original_bytes = json.dumps(plan).encode()
    plan_path.write_bytes(original_bytes)
    config_path.write_bytes(original_bytes)
    source = (recovery.INTENT_GUARD + '\n' + recovery.GUARD + '\n' + recovery.SEND).encode()
    committed = original_bytes
    def git(repo, *args):
        if args[0] == 'log':
            return b'fixture-commit\n'
        return source if args[-1].endswith(':tools/run.mjs') else committed
    command = f'{cache.parent / "bin/node"} {repo / "tools/record.mjs"} --session-key {plan["sessionKey"]} --dir {film}'
    def check(name, children, expected):
        with patch.object(recovery, 'git', side_effect=git), patch.object(recovery, 'active_children', return_value=children):
            try:
                recovery.unsent_inputs(repo, cache, ident)
                actual = True
            except ValueError:
                actual = False
        checks.append(dict(scenario=name, expected=expected, actual=actual, passed=expected == actual))
        assert actual == expected, name

    check('exact independent observer permits proven score-first preflight', [command], True)
    check('no observer permits proven score-first preflight', [], True)
    for name, changed in [
        ('sender always blocks', command.replace('/tools/record.mjs ', '/tools/run.mjs ')),
        ('different recorder checkout blocks', command.replace(str(repo), str(repo) + '-other')),
        ('different node path blocks', command.replace('/bin/node ', '/bin/other-node ')),
        ('wrong session blocks', command.replace(plan['sessionKey'], plan['sessionKey'] + '-other')),
        ('wrong film root blocks', command.replace('film-first5027-5037', 'film-first5027-5038')),
        ('wrong UUID directory blocks', command.replace('/' + ident + '/', '/another-run/')),
        ('unrecognized attempt directory blocks', command.replace('attempt-01', 'attempt-other')),
        ('extra arguments block', command + ' --rehearsal'),
        ('shell wrapper blocks', 'sh -c ' + command),
        ('unknown child blocks', 'unrecognized recorder command'),
        ('legacy readiness recorder blocks', command.replace(str(film), str(scratch))),
    ]:
        check(name, [changed], False)
    check('observer plus sender still blocks', [command, command.replace('/tools/record.mjs ', '/tools/run.mjs ')], False)
    check('observer plus unknown child still blocks', [command, 'unknown'], False)
    config_path.write_text(json.dumps(dict(plan, readyPath=str(scratch / 'ready.json'))))
    check('score-first config with readyPath blocks observer exemption', [command], False)
    config_path.write_bytes(original_bytes)
    forbidden = [scratch / 'ready.json', scratch / 'finish.json', run_dir / 'evidence.json']
    forbidden += [cache / 'runs' / (label + suffix) for suffix in
                  ('.send-intent.json', '.pending.json', '.ack.json', '.terminal.json', '.json')]
    for file in forbidden:
        file.write_text('{}')
        check('send marker blocks despite observer: ' + file.name, [command], False)
        file.unlink()
    plan_path.write_text(json.dumps(dict(plan, prompt='uncommitted')))
    check('uncommitted plan blocks despite observer', [command], False)
    plan_path.write_bytes(original_bytes)
    config_path.write_text(json.dumps(dict(plan, prompt='mismatch')))
    check('mismatching private config blocks despite observer', [command], False)
    config_path.write_bytes(original_bytes)
    saved_source = source
    source = recovery.SEND.encode()
    check('missing committed presend guard blocks despite observer', [command], False)
    source = saved_source
    legacy = copy.deepcopy(plan)
    legacy.pop('capturePolicy')
    committed = json.dumps(legacy).encode()
    plan_path.write_bytes(committed)
    config_path.write_text(json.dumps(dict(legacy, readyPath=str(scratch / 'ready.json'))))
    check('legacy readiness-gated run cannot exempt observer', [command], False)
    check('legacy run without observer still passes', [], True)

result = dict(invocation='python3 .omo/evidence/first5027-preflight-observer/verify.py',
              binary_observable='exit 0; every checks[].passed true', checks=checks,
              passed=len(checks), failed=0, scope='Offline temporary fixtures; no live process changes or provider calls.')
out = Path(__file__).with_name('results.json')
out.write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps(dict(passed=len(checks), failed=0, artifact=str(out))))
