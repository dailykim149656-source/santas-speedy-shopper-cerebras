import json,os,time,signal,subprocess
from pathlib import Path
d=Path(__file__).resolve().parent;c=d.parent
def get(p):return json.loads(p.read_bytes())
owner='d5027-supervisor-55646ea2-3100-46f0-bb74-9c5bb303e7c8'
assert not (c/'stop-requested').exists()
started=[json.loads(line) for line in (d/'runner.log').read_text().splitlines() if '"supervisor": "started"' in line][-1]
assert started['owner']==owner
lines=subprocess.check_output(['ps','-axo','pid=,command=']).decode().splitlines()
pids=[int(line.strip().split(maxsplit=1)[0]) for line in lines if line.endswith(' -B -u '+str(d/'supervisor.py'))];assert len(pids)==1
while True:
 if (c/'stop-requested').exists():raise SystemExit('prior supervisor already stopped')
 s=get(c/'status.json')
 if s.get('label','').startswith('D5121-') and s.get('phase') in ('recording_trial','finalizing_video','result'):
  # Once the child has passed its stop check, wait for its terminal append before next dispatch.
  if s.get('phase')=='result' or (c/'runs'/(s['label']+'.pending.json')).exists():break
 time.sleep(.25)
assert subprocess.check_output(['ps','-p',str(pids[0]),'-o','command=']).decode().strip().endswith(' -B -u '+str(d/'supervisor.py'))
os.kill(pids[0],signal.SIGTERM)
print('holding after D5121; no new dispatch until remaining <=2 positions are allocated',flush=True)
