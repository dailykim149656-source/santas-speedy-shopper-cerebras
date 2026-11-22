import fcntl,hashlib,json,os,shutil,sys,urllib.request
from contextlib import ExitStack
from pathlib import Path
d=Path(__file__).resolve().parent
c=d.parent
stage=d/'longgap-recovery-stage'
read=lambda p:json.loads(p.read_bytes())
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 os.umask(0o077)
 assert read(d/'stop-after-longgap')['max_total_transmissions_after_D5119']==4
 assert read(d/'longgap-recovery-config.json')['max_total_transmissions']==4
 s=read(c/'stop-requested')
 assert s['owner']=='d5027-supervisor-55646ea2-3100-46f0-bb74-9c5bb303e7c8' and s['reason']=='supervisor signal 15'
 with ExitStack() as stack:
  for path in (d/'supervisor.lock', c/'loop.lock', c.parent.parent/'2026-11-22/mean-2000/loop.lock',c.parent.parent/'2026-11-22-exp2000/mean-2000/loop.lock'):
   f=stack.enter_context(path.open('rb'));fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
  history=[json.loads(line) for line in (c/'iterations.jsonl').read_bytes().splitlines() if line.strip()]
  anchor=read(d/'longgap-config.json')['history_start']
  assert len(history)==anchor+2 and [r['label'].split('-')[0] for r in history[anchor:]]==['D5120','D5121']
  assert read(c/'status.json')['id']==history[-1]['id']
  expected=read(stage/'root-verified-release.json')
  for name in ['gap_recovery.py','supervisor.py']:
   assert sha(stage/name)==expected[name];compile((stage/name).read_bytes(),str(stage/name),'exec')
  for port in (19863,19871):
   with urllib.request.urlopen('http://127.0.0.1:%s/health'%port,timeout=3) as res:
    state=json.load(res);assert state['ok']
    if port==19871:assert state['relay_sha256']==read(d/'required-ab-config.json')['relay_sha256']
  for name in ['gap_recovery.py','supervisor.py']:
   tmp=d/(name+'.install');shutil.copy2(stage/name,tmp);os.replace(tmp,d/name)
  os.link(c/'stop-requested',stage/'previous-supervisor-stop.json');(c/'stop-requested').unlink()
 print('two slots used; final runner has max four total and stop-after-comparison',flush=True)
 os.execv(sys.executable,[sys.executable,'-B','-u',str(d/'supervisor.py')])
if __name__=='__main__': main()
