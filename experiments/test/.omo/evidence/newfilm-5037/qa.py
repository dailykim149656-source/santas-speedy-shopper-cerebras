"""Synthetic offline fixtures only: does not capture a browser or send any model request."""
from pathlib import Path
from unittest.mock import patch
import importlib.util
import copy
import json
import io
from contextlib import redirect_stdout
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / 'tools'))
import first5027_film as f
EVIDENCE = Path(__file__).parent
ARTIFACTS = EVIDENCE / 'fixtures'
if ARTIFACTS.exists(): shutil.rmtree(ARTIFACTS)
ARTIFACTS.mkdir(exist_ok=True)
f.REPO = ARTIFACTS / 'repo'
f.CACHE = ARTIFACTS / 'cache'
f.FILMS = f.CACHE / 'film-first5027-5037'
f.SENTINEL = f.CACHE / 'recording-complete-5037'
f.FILMS.mkdir(parents=True, exist_ok=True)
if f.SENTINEL.exists(): f.SENTINEL.unlink()
ident = '12345678-abcd-1234-abcd-123456789012'
label = 'D5037-synth-five-categories-cap'
session = {'id': ident, 'sessionKey': 'agent:main:shop-' + label.lower() + '-' + ident[:8]}
plan = dict(session, label=label, variant='synth-five-categories-cap', capturePolicy='score-first', prompt='synthetic offline fixture')
private = f.CACHE / 'capture' / ident
private.mkdir(parents=True, exist_ok=True)
(f.REPO / 'runs' / ident).mkdir(parents=True, exist_ok=True)
f.put(private / 'plan.json', plan)
(f.CACHE / 'runs').mkdir(parents=True, exist_ok=True)
run = lambda suffix: f.CACHE / 'runs' / (label + suffix)
start = 1700000000000
stamp = lambda ms: datetime.fromtimestamp(ms / 1000, timezone.utc).isoformat()
f.put(run('.session.json'), session)
f.put(run('.send-intent.json'), dict(session, startedWall=start + 100))
f.put(run('.terminal.json'), dict(session, ended={'time': start + 5000}))
f.put(run('.json'), dict(session, startedWall=start + 100, ended={'time': start + 5100}))
urls = [f'https://example.com/product/{i}' for i in range(5)]
validation = dict(run_id=ident, valid=True, score={'ui_rounded_tps': 1700}, products=[dict(url=u, verified=True) for u in urls])
f.put(private / 'validation.json', validation)
d = f.FILMS / ident / 'attempt-01'
d.mkdir(parents=True, exist_ok=True)
ready = dict(sessionKey=session['sessionKey'], ready=True, readyAt=stamp(start), initialSummary='', rehearsal=False, capture='owned-local-viewport')
metadata = dict(run_id=ident, sessionKey=session['sessionKey'], readyAt=stamp(start), rehearsal=False, authless=True, full_run=True, qualifying=True, final_ui_tps=1700, urls=urls, durationSeconds=6)
timeline = dict(durationSeconds=6, frames=[dict(file=f'frame-{i}.jpg', seconds=i) for i in range(6)])
interval = dict(originalFromSeconds=1, originalToSeconds=5.5, clipFromSeconds=1, clipToSeconds=5.5, firstFrameSha256='a'*64, lastFrameSha256='b'*64)
proof = dict(schema_version=1, verified=True, finishSeconds=.5, demoStartSeconds=0, score=dict(interval, mean=1700), links=[dict(interval, url=u) for u in urls])
for name, value in [('ready.json', ready), ('recording.json', metadata), ('capture-timeline.json', timeline), ('viewport-evidence.json', proof)]: f.put(d / name, value)
subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-y','-f','lavfi','-i','color=c=black:s=16x16:r=25','-t','6','-c:v','libx264','-pix_fmt','yuv420p',str(d / 'original.mp4')], check=True)
shutil.copyfile(d / 'original.mp4', d / 'demo.mp4')
results = []
def check(name, condition, actual=None):
    if not condition: raise AssertionError((name, actual))
    results.append(dict(scenario=name, passed=True, observable=actual))
def inspect(name):
    result = f.inspect(label, session, d)
    f.put(EVIDENCE / (name + '.json'), result)
    return result

r = inspect('full-fixture')
check('same-run pre-send complete fixture', r['full_run_verified'] and r['target_1700_verified'] and r['real_time_verified'], r['classification'])
check('all timing and evidence sources have hashes and ages', len(r['source_provenance']) == 9 and all(v['bytes'] > 0 and v['modified_ns'] > 0 and len(v['sha256']) == 64 for v in r['source_provenance'].values()), list(r['source_provenance']))
for name, time_ms, expected in [('late', start+200, 'first_frame_during_run'), ('post-run', start+6000, 'first_frame_after_terminal')]:
    f.put(d/'ready.json', dict(ready, readyAt=stamp(time_ms)))
    f.put(d/'recording.json', dict(metadata, readyAt=stamp(time_ms)))
    r = inspect(name)
    check(name+' cannot claim full run', not r['full_run_verified'] and not r['target_1700_verified'] and r['timing'] == expected, r['classification'])
f.put(d/'ready.json', ready)
f.put(d/'recording.json', metadata)
for name, file, base, changes in [
    ('rehearsal', 'recording.json', metadata, {'rehearsal': True}),
    ('stale-ui', 'ready.json', ready, {'initialSummary': 'mean 1700 tok/s'}),
    ('stale-ready', 'recording.json', metadata, {'readyAt': stamp(start-1000)}),
    ('retimed', 'capture-timeline.json', timeline, {'durationSeconds': 12}),
]:
    f.put(d/file, dict(base, **changes)); r = inspect(name)
    check(name+' rejected as full-run', not r['full_run_verified'], r['classification'])
    f.put(d/file, base)
f.put(run('.json'), dict(session, startedWall=start+101, ended={'time': start+5100}))
r = inspect('raw-time-mismatch'); check('raw/send disagreement rejected', not r['full_run_verified'])
f.put(run('.json'), dict(session, startedWall=start+100, ended={'time': start+5100}))
f.put(run('.session.json'), dict(session, id='wrong'))
try: f.inspect(label, session, d)
except ValueError: check('cross-session timing identity rejected', True, 'ValueError')
else: raise AssertionError('cross-session identity accepted')
f.put(run('.session.json'), session)
f.put(private/'validation.json', dict(validation, score={'ui_rounded_tps': 1699}))
f.put(d/'recording.json', dict(metadata, final_ui_tps=1699))
f.put(d/'viewport-evidence.json', dict(proof, score=dict(interval, mean=1699)))
r = inspect('below-threshold'); check('1699 retained without target qualification', r['playable'] and r['full_run_verified'] and r['viewportVerified'] and not r['target_1700_verified'])
f.put(private/'validation.json', dict(validation, run_id=None))
try: f.state(label, session)
except ValueError: check('valid result missing run identity rejected', True)
else: raise AssertionError('missing validation identity accepted')
f.put(private/'validation.json', validation); f.put(d/'recording.json', metadata); f.put(d/'viewport-evidence.json', proof)
for name, change in [('wrong-score', {'score':dict(interval, mean=1701)}), ('duplicate-url', {'links':[dict(interval, url=urls[0])]*5})]:
    f.put(d/'viewport-evidence.json', dict(proof, **change)); r = inspect(name)
    check(name+' viewport rejected', not r['viewportVerified'] and not r['target_1700_verified'])
f.put(d/'viewport-evidence.json', proof)
f.put(private/'validation.json', dict(validation, valid=False))
r = inspect('invalid-shopping'); check('invalid shopping does not verify viewport/target', not r['viewportVerified'] and not r['target_1700_verified'])
f.put(private/'validation.json', validation)
subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-y','-f','lavfi','-i','color=c=black:s=16x16:r=1','-t','61','-c:v','libx264','-pix_fmt','yuv420p',str(d/'demo.mp4')], check=True)
r = inspect('overlong-demo'); check('demo over 60 seconds rejected', not r['playable'])
shutil.copyfile(d/'original.mp4', d/'demo.mp4')
(d/'demo.mp4').write_bytes(b'not a movie')
r = inspect('corrupt-demo'); check('corrupt media rejected', not r['playable'])
shutil.copyfile(d/'original.mp4', d/'demo.mp4')
for variant in f.VARIANTS:
    p = dict(plan, variant=variant, label='D5037-'+variant, sessionKey='agent:main:shop-d5037-'+variant+'-'+ident[:8])
    check('allowed arm '+variant, f.eligible(p))
for name, p in [('old label', dict(plan, label='D5036-synth-five-categories-cap')), ('other arm', dict(plan, variant='synth-other')), ('uncommitted policy', dict(plan, capturePolicy='blocking')), ('session mismatch', dict(plan, sessionKey='other'))]:
    check('reject '+name, not f.eligible(p))
class Git:
    returncode = 0
    stdout = json.dumps(plan).encode()
with patch.object(f.subprocess, 'run', return_value=Git()):
    f.put(f.CACHE/'status.json', {'phase':'campaign_1700_stopped'})
    queue = f.watch_queue(5037)
    check('prior controller stopped status does not block plan discovery', len(queue) == 1)
    run('.session.json').unlink()
    check('pre-send plan discovered before session file exists', len(f.watch_queue(5037)) == 1)
    f.put(run('.session.json'), session)
    f.put(private/'plan.json', dict(plan, prompt='different'))
    check('uncommitted altered plan excluded', f.watch_queue(5037) == [])
    f.put(private/'plan.json', plan)
    f.put(f.REPO/'runs'/ident/'preflight.json', {'aborted':True})
    check('preflight-only plan excluded', f.watch_queue(5037) == [])
    (f.REPO/'runs'/ident/'preflight.json').unlink()
    f.put(f.FILMS/ident/'receipt.json', {})
    with patch.object(f.subprocess, 'run', side_effect=AssertionError('receipted session invoked git')):
        check('already inspected session excluded before git subprocess', f.watch_queue(5037) == [])
    (f.FILMS/ident/'receipt.json').unlink()

class IdleObserved(Exception): pass
with patch.object(sys,'argv',['first5027_film.py']), patch.object(f.subprocess,'check_output',return_value='test\n'), patch.object(f,'watch_queue',return_value=[]), patch.object(f.time,'sleep',side_effect=IdleObserved):
    try: f.main()
    except IdleObserved: check('watcher waits while controller has not started', True, 'idle sleep reached')
    else: raise AssertionError('idle watcher exited')
f.SENTINEL.write_text('done\n')
with patch.object(sys,'argv',['first5027_film.py']), patch.object(f.subprocess,'check_output',return_value='test\n'), patch.object(f,'watch_queue',return_value=[]):
    f.main(); check('sentinel ends empty watcher', True, 'main returned')
f.SENTINEL.unlink()
launch = {}
class FakeProc:
    pid = 999999
    def poll(self): return 0
    def wait(self, **kwargs): return 0

def fake_popen(command, **kwargs):
    launch.update(command=command, BOUNTY_ROOT=kwargs['env']['BOUNTY_ROOT'], gateway=kwargs['env']['BOUNTY_GATEWAY_PORT'], wrapper=kwargs['env']['RECORDER_AUTH_WRAPPER'])
    return FakeProc()
with patch.object(f.subprocess, 'Popen', side_effect=fake_popen), patch.object(f,'inspect',return_value={'offline_launcher_fixture':True}):
    output = f.FILMS/ident/'launcher-fixture'
    if output.exists(): shutil.rmtree(output)
    f.record(label,session,output)
check('launcher has real non-rehearsal session and isolated gateway', '--rehearsal' not in launch['command'] and launch['gateway'] == '19863' and '--session-key' in launch['command'])
f.put(EVIDENCE/'launcher.json', launch)
state = f.state(label, session)
check('retention independent from official score threshold', state['video_threshold_tps'] == 1700 and state['retain_verified_record'] is True and state['discard_unverified'] is False)
with tempfile.TemporaryDirectory(prefix='first5027-private-permissions-') as local:
    secured = Path(local) / 'inspection.json'
    f.put(secured, {'fixture': True})
    check('private inspection permissions on local filesystem', secured.stat().st_mode & 0o777 == 0o600, oct(secured.stat().st_mode & 0o777))
real_check_output = subprocess.check_output
for mode in ('--inspect', '--retry'):
    with patch.object(sys, 'argv', ['first5027_film.py', mode, '5037']), patch.object(f.subprocess, 'check_output', side_effect=lambda cmd, **kw: 'test\n' if cmd[0] == 'git' else real_check_output(cmd, **kw)), patch.object(f, 'sessions', return_value=[(5037, label, session)]), redirect_stdout(io.StringIO()) as output:
        if mode == '--inspect':
            f.main()
            summary = json.loads(output.getvalue())
            check('inspect CLI recomputes receipt', summary['full_run_verified'] and (f.FILMS/ident/'receipt.json').is_file())
        else:
            with patch.object(f, 'process') as process:
                f.main()
                process.assert_called_once_with(label, session, retry=True)
                check('retry CLI selects same session explicitly', True)
for branch, isolated in [('main', True), ('test', False)]:
    with patch.object(sys, 'argv', ['first5027_film.py']), patch.object(f.subprocess, 'check_output', return_value=branch+'\n'), patch.object(f, 'ROOT', f.ROOT if isolated else f.MAIN_ROOT), redirect_stdout(io.StringIO()), patch.object(sys, 'stderr', io.StringIO()):
        try: f.main()
        except SystemExit as exc: check('reject unsafe runtime '+branch+str(isolated), exc.code == 2)
        else: raise AssertionError('unsafe runtime accepted')
f.put(EVIDENCE/'results.json', dict(kind='synthetic offline tests; no live recorder/model executed', passed=len(results), scenarios=results))
print(json.dumps(dict(passed=len(results), artifact=str(EVIDENCE/'results.json'))))
