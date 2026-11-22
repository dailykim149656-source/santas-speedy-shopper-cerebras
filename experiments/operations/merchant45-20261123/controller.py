"""Bounded deadline-aware 45-second AB test. Every dispatch is journaled before sending."""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time
from contextlib import ExitStack
from datetime import datetime
from zoneinfo import ZoneInfo

os.umask(0o077)
work=Path(__file__).resolve().parent
cache=work.parent
root=cache.parent
repo=Path(os.environ.get("BOUNTY_TEST_REPO", Path.cwd()))
sys.path.insert(0,str(repo/'tools'))
os.environ.update(BOUNTY_SCHEDULE='test',BOUNTY_ROOT=str(root),BOUNTY_LABEL_BASE='5000',BOUNTY_GATEWAY_PORT='19863',
                  BOUNTY_RELAY_PORT='19871',BOUNTY_PROFILE_CLI=str(cache/'profile.mjs'),PYTHONDONTWRITEBYTECODE='1',
                  BOUNTY_RAW_ARCHIVE=str(Path.home()/'Library/Application Support/Cerebras Speed Bounty/2026-11-22/raw-test'))
import loop
from variants import FOCUS_D5027,MERCANTILE_ARM
kst=ZoneInfo('Asia/Seoul')
deadline=datetime(2026,11,23,3,tzinfo=kst).timestamp()
now=lambda:datetime.now(kst).isoformat(timespec='milliseconds')
state=work/'campaign.json'
marker=cache/'stop-requested'
owner=work.name
arms=(FOCUS_D5027,MERCANTILE_ARM)
def put(p,v):loop.put(p,v)
def interrupted(s,f):raise SystemExit('controller interrupted')
signal.signal(signal.SIGTERM,interrupted)

def guard_deadline(finished):
    # Suppress a non-sent preflight before deadline and cancel only our still-active last run at cutoff.
    if finished.wait(max(0,deadline-30-time.time())):return
    def stop_preflight():
        meta=loop.get(state)
        if not meta['slots']:return
        slot=meta['slots'][-1]; status=loop.get(cache/'status.json')
        label=f"D{slot['number']:04d}-{slot['arm']}"
        if status.get('label')!=label or status.get('phase')!='preparing_video' or not status.get('id'):return
        ident=status['id']; scratch=cache/'capture'/ident
        if (scratch/'ready.json').exists():return
        for raw in subprocess.check_output(['ps','-axo','pid=,ppid=,command='],text=True).splitlines():
            pid,ppid,cmd=raw.strip().split(None,2)
            if int(ppid)==os.getpid() and str(scratch/'run.json') in cmd and str(repo/'tools/run.mjs') in cmd:
                if not (scratch/'ready.json').exists():os.kill(int(pid),signal.SIGTERM)
    try:stop_preflight()
    except (OSError,ValueError,KeyError):pass
    if finished.wait(max(0,deadline-time.time())):return
    try:
        with (work/'deadline-guard.log').open('a') as out:
            subprocess.run([str(root/'bin/node'),str(work/'abort_active.mjs')],stdout=out,stderr=out,timeout=25)
    except (OSError,subprocess.TimeoutExpired):pass

def main():
    if time.time()>=deadline:raise SystemExit('deadline passed')
    with ExitStack() as stack:
        locks=[]
        for p,kind in ((cache/'d5027-1500-20261122/supervisor.lock',fcntl.LOCK_EX),(loop.MAIN_ROOT/'mean-2000/loop.lock',fcntl.LOCK_SH),(root.parent/'2026-11-22-exp2000/mean-2000/loop.lock',fcntl.LOCK_SH),(cache/'loop.lock',fcntl.LOCK_EX)):
            f=stack.enter_context(p.open('rb'));fcntl.flock(f,kind|fcntl.LOCK_NB);locks.append(f)
        if state.exists():raise RuntimeError('existing campaign journal: inspect before resuming')
        if not loop.d5027_control_active() or loop.next_trial_number()!=5128:raise RuntimeError('baseline or sequence changed')
        prev=loop.get(marker)
        if prev.get('owner')!='mercantile-abba-d5124' or prev.get('reason')!='four-slot comparison completed':raise RuntimeError('other reservation')
        if subprocess.check_output(['git','-C',str(repo),'branch','--show-current'],text=True).strip()!='test':raise RuntimeError('test checkout changed')
        sha=loop.relay_health()['relay_sha256']
        st={'owner':owner,'phase':'running','started':now(),'deadline':'2026-11-23T03:00:00+09:00','arms':[a[0] for a in arms],'cadence_seconds':45,'max_probe_sends':5,'probe_status':'pending','relay_sha256':sha,'slots':[]}
        put(work/'previous-stop.json',prev);put(state,st)
        put(marker,{'owner':owner,'reason':'exclusive serial A/B campaign through 03:00 KST','time':now()})
        reserved=marker.read_bytes()
        done=threading.Event();threading.Thread(target=guard_deadline,args=(done,),daemon=True).start()
        end=0
        try:
            while time.time()<deadline:
                if not marker.exists() or marker.read_bytes()!=reserved:st['phase']='external_stop';break
                if not loop.d5027_control_active() or loop.relay_health()['relay_sha256']!=sha:raise RuntimeError('control/relay configuration changed')
                # Run the separately-approved five diagnostics only between terminal official sessions.
                # The ready marker is created by the root after offline review of the exact script.
                if st['slots'] and st['probe_status']=='pending' and (work/'probe-approved-ready').is_file() and time.time()<deadline-300:
                    st['probe_status']='started';put(state,st)
                    with (work/'probe-process.log').open('ab') as out:
                        result=subprocess.run([str(root/'bin/node'),str(work/'probe.mjs')],stdout=out,stderr=out,timeout=310)
                    st['probe_status']='finished' if result.returncode==0 else 'needs_review';put(state,st)
                while time.time()<min(end+45,deadline-30):
                    if not marker.exists() or marker.read_bytes()!=reserved:break
                    time.sleep(min(2,max(.02,min(end+45,deadline-30)-time.time())))
                if not marker.exists() or marker.read_bytes()!=reserved:st['phase']='external_stop';break
                if time.time()>=deadline-30:break
                slot=len(st['slots'])+1;arm=arms[(slot-1)%2];n=loop.next_trial_number()
                if n != 5127+slot:raise RuntimeError('unexpected trial number')
                info={'slot':slot,'number':n,'arm':arm[0],'dispatch':now()};st['slots'].append(info);put(state,st)
                before=len(loop.past())
                loop.run_trial(n,arm,lock_fds=tuple(f.fileno() for f in locks))
                rows=loop.past()[before:];label=f'D{n:04d}-{arm[0]}'
                if len(rows)==1 and rows[0]['label']==label:
                    row=rows[0];ident=row['id'];e=loop.get(repo/'runs'/ident/'evidence.json')
                    end=e['ended']['time']/1000
                    info.update(id=ident,result='terminal',valid=row['valid'],method_valid=row['method_valid'],ended=e['ended']['time'],score=row['score'])
                elif not rows:
                    pres=[p for p in (repo/'runs').glob('*/preflight.json') if loop.get(p.with_name('plan.json')).get('label')==label]
                    if len(pres)!=1:raise RuntimeError('missing terminal/preflight receipt')
                    end=time.time()
                    info.update(id=pres[0].parent.name,result='presend_failure',valid=False)
                else:raise RuntimeError('unexpected ledger entries')
                put(state,st)
            if st['phase']=='running':st['phase']='completed'
        except BaseException as exc:
            st['phase']='interrupted';st['exception_type']=type(exc).__name__;raise
        finally:
            done.set();st['stopped']=now();put(state,st)
            if marker.exists() and marker.read_bytes()==reserved:
                put(marker,{'owner':owner,'reason':'campaign '+st['phase'],'time':now(),'slots':len(st['slots'])})

if __name__=='__main__':main()
