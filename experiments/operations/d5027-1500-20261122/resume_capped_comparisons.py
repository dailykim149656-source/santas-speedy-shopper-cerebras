"""Resume after the committed three-request capped result, with fixed four-request longgap opt-in."""
import os, sys, json, hashlib, fcntl, subprocess, shutil, urllib.request
from pathlib import Path
from contextlib import ExitStack

d=Path(__file__).resolve().parent
c=d.parent
repo=Path(os.environ.get("BOUNTY_TEST_REPO", Path.cwd()))
def read(p):return json.loads(p.read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def health(port):
 with urllib.request.urlopen(f'http://127.0.0.1:{port}/health',timeout=3) as res:return json.load(res)
def write_exclusive(p,obj):
 with p.open('x') as out:json.dump(obj,out,indent=2);out.write('\n');out.flush();os.fsync(out.fileno())
def main():
 os.umask(0o077)
 stop=c/'stop-requested';receipt=read(stop)
 if receipt['owner']!='d5027-supervisor-02120495-78c3-454d-9dd5-f496ff34f638' or receipt['reason']!='supervisor signal 15':
  raise RuntimeError('foreign stop marker')
 with ExitStack() as stack:
  for lock in [d/'supervisor.lock', c/'loop.lock',c.parent.parent/'2026-11-22/mean-2000/loop.lock',c.parent.parent/'2026-11-22-exp2000/mean-2000/loop.lock']:
   f=stack.enter_context(lock.open('rb'));fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
  ab=read(d/'required-ab-state.json');pr=read(d/'longgap-prereg.json')
  assert ab['status']=='baseline_after_screening' and ab['reduced_cap']==4 and ab['screening']['n_sent']==3 and not ab['screening']['pass'] and ab['confirmation'] is None
  assert pr['max_assignments']==4 and pr['order_seconds']==[60,90,90,60]
  assert read(c/'status.json')['id']==ab['assignments'][2]['outcome']['run_id']
  assert health(19863)['ok'] and health(19871)['relay_sha256']==sha(repo/'tools/request_relay.mjs')==ab['config']['relay_sha256']
  assert subprocess.check_output(['git','-C',str(repo),'branch','--show-current']).decode().strip()=='test'
  staged=d/'longgap-stage'
  manifest=read(staged/'root-verified-release.json')
  for n in ['longgap.py','supervisor.py']:
   assert manifest[n]==sha(staged/n);compile((staged/n).read_bytes(),str(staged/n),'exec')
  assert manifest['required_ab.py']==sha(d/'required_ab.py')
  for n in ['longgap.py','supervisor.py']:
   t=d/(n+'.install');shutil.copy2(staged/n,t);os.replace(t,d/n)
  write_exclusive(d/'longgap-approved-pending.json',{'version':1,'prereg_sha256':sha(d/'longgap-prereg.json'),'wait_for_eligible_baseline':True})
  os.link(stop,staged/'previous-supervisor-stop.json');stop.unlink()
 print('capped B closure verified; waiting for a valid default A before any 60/90 assignment',flush=True)
 os.execv(sys.executable,[sys.executable,'-B','-u',str(d/'supervisor.py')])
if __name__=='__main__':main()
