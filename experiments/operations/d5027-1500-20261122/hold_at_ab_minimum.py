import datetime, json, os, signal, subprocess, time
from pathlib import Path
d=Path(__file__).resolve().parent
cache=d.parent
owner='d5027-supervisor-02120495-78c3-454d-9dd5-f496ff34f638'
def read(p): return json.loads(p.read_bytes())
def cmd(p):return subprocess.check_output(['ps','-p',str(p),'-o','command=']).decode().strip()
assert not (cache/'stop-requested').exists()
lines=subprocess.check_output(['ps','-axo','pid=,command=']).decode().splitlines()
pids=[int(line.strip().split(maxsplit=1)[0]) for line in lines if line.endswith(' -B -u '+str(d/'supervisor.py'))]
if len(pids)!=1:raise RuntimeError('unexpected active supervisor')
pid=pids[0]
started=[row for line in (d/'runner.log').read_text().splitlines() if '"supervisor": "started"' in line for row in [json.loads(line)]][-1]
assert started['owner']==owner
with (d/'required-ab-cap.json').open('x') as f:
 json.dump({'version':1,'max_transmissions':4,'allow_confirmation':False,'registered_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'reason':'user_requested_minimum'},f,indent=2);f.write('\n')
while True:
 if (cache/'stop-requested').exists(): raise SystemExit('supervisor already stopped')
 a=read(d/'required-ab-state.json')['assignments']
 s=read(cache/'status.json')
 if len(a)>4:raise RuntimeError('unexpected assignment beyond amended cap')
 if len(a)>=3 and a[2]['phase']=='complete' and not a[2]['outcome']['valid'] and not a[1]['outcome']['valid']:
  reason='neither B gave valid measurement';break
 if len(a)==4:
  if a[-1]['phase']=='complete':
   reason='fourth outcome committed';break
  if a[-1]['phase']=='dispatched' and s.get('phase') in ('recording_trial','finalizing_video') and s.get('id')!=a[-1]['previous_uuid']:
   # Child has already passed its own stop gate. Parent will await the one trial.
   reason='fourth child running; finish this child and stop';break
 time.sleep(.25)
if not cmd(pid).endswith(' -B -u '+str(d/'supervisor.py')):raise RuntimeError('owner changed')
os.kill(pid,signal.SIGTERM)
print(reason,flush=True)
