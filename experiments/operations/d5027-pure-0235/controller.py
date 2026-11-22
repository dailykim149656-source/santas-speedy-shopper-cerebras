"""Serial, recorded D5027 campaign, bounded by the local operations cutoff."""
from contextlib import ExitStack
from datetime import datetime
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
from zoneinfo import ZoneInfo

os.umask(0o077)
work = Path(__file__).resolve().parent
cache = work.parent
root = cache.parent
repo = Path(os.environ.get("BOUNTY_TEST_REPO", Path.cwd()))
old = cache/'merchant45-20261123'
marker = cache/'stop-requested'
journal = work/'campaign.json'
tz = ZoneInfo('Asia/Seoul')
cutoff = datetime(2026,11,23,2,35,tzinfo=tz).timestamp()
sys.path.insert(0, str(repo/'tools'))
os.environ.update(BOUNTY_SCHEDULE='test', BOUNTY_ROOT=str(root), BOUNTY_LABEL_BASE='5000',
                  BOUNTY_GATEWAY_PORT='19863', BOUNTY_RELAY_PORT='19871', BOUNTY_PROFILE_CLI=str(cache/'profile.mjs'),
                  BOUNTY_RAW_ARCHIVE=str(Path.home()/'Library/Application Support/Cerebras Speed Bounty/2026-11-22/raw-test'),
                  PYTHONDONTWRITEBYTECODE='1')
import loop
from variants import FOCUS_D5027, MERCANTILE_ARM

def now():
    return datetime.now(tz).isoformat(timespec='milliseconds')

def guard(done):
    if done.wait(max(0,cutoff-30-time.time())):
        return
    while not done.is_set() and time.time() < cutoff:
        # Stop a still-unsent preflight at the boundary without touching another session.
        st = loop.get(journal)
        if st['slots']:
            slot = st['slots'][-1]
            status = loop.get(cache/'status.json')
            if status.get('label') == f"D{slot['number']}-{slot['arm']}" and status.get('phase') == 'preparing_video':
                scratch = cache/'capture'/status['id']
                for raw in subprocess.check_output(['ps','-axo','pid=,ppid=,command='],text=True).splitlines():
                    parts = raw.strip().split(None,2)
                    if len(parts) == 3 and int(parts[1]) == os.getpid() and str(repo/'tools/run.mjs') in parts[2] and str(scratch/'run.json') in parts[2] and not (scratch/'ready.json').exists():
                        try:
                            os.kill(int(parts[0]),signal.SIGTERM)
                        except ProcessLookupError:
                            pass
        done.wait(min(1,max(0,cutoff-time.time())))
    if not done.is_set():
        with (work/'deadline-guard.log').open('a') as out:
            subprocess.run([str(root/'bin/node'),str(work/'abort_active.mjs')],stdout=out,stderr=out,timeout=23)

def record(st, info, history_size):
    from receipt import assess
    label = f"D{info['number']}-{info['arm']}"
    rows = loop.past()[history_size:]
    if not rows:
        files = [p for p in (repo/'runs').glob('*/preflight.json') if loop.get(p.with_name('plan.json')).get('label')==label]
        if len(files)!=1:
            raise RuntimeError('terminal/preflight reconciliation needed')
        info.update(id=files[0].parent.name,result='presend_failure',valid=False,method_valid=False,ended=round(time.time()*1000),cooldown=45)
        return
    if len(rows) != 1 or rows[0]['label'] != label:
        raise RuntimeError('unexpected ledger rows')
    row = rows[0]
    evidence = loop.get(repo/'runs'/row['id']/'evidence.json')
    rec = assess(row)
    end = evidence['ended']['time']
    delay = loop.exploit_wait_seconds(zero_token_429=rec['zero_token_429'] is True,
             retry_after_seconds=max(0,(rec.get('retry_after_until') or 0)-end/1000))
    info.update(id=row['id'],result='terminal',valid=row['valid'],method_valid=row['method_valid'],
                ended=end,score=row['score'],context_clean=row.get('context_clean'),
                rate_limited=row.get('rate_limited'),receipt=rec,cooldown=delay)
    if info['arm']==FOCUS_D5027[0] and 'aisynthesis.com' in rec['merchant_429_hosts']:
        st['fallback_from']=label
    if row['valid'] and row['method_valid'] and row['score'] and row['score'] > st['record_tps']:
        st['record_tps']=row['score']
        info['new_record']=True
    if row['valid'] and row['method_valid'] and row.get('recorded_video') and row['score'] > st['filmed_record_tps']:
        st['filmed_record_tps']=row['score']
        info['new_full_video_record']=True

def main():
    if time.time() >= cutoff or journal.exists():
        raise SystemExit('campaign cutoff passed or existing journal')
    with ExitStack() as stack:
        fds=[]
        for path,kind in ((cache/'d5027-1500-20261122/supervisor.lock',fcntl.LOCK_EX),
                          (loop.MAIN_ROOT/'mean-2000/loop.lock',fcntl.LOCK_SH),
                          (root.parent/'2026-11-22-exp2000/mean-2000/loop.lock',fcntl.LOCK_SH),
                          (cache/'loop.lock',fcntl.LOCK_EX)):
            fd=stack.enter_context(path.open('rb'));fcntl.flock(fd,kind|fcntl.LOCK_NB);fds.append(fd.fileno())
        last=loop.get(old/'campaign.json')
        prev=loop.get(marker)
        if prev.get('reason')!='handoff to D5027-only campaign at terminal slot per user' or prev.get('owner')!=old.name or last['phase']!='external_stop':
            raise RuntimeError('another reservation')
        if subprocess.check_output(['git','-C',str(repo),'branch','--show-current'],text=True).strip()!='test':
            raise RuntimeError('wrong branch')
        if not loop.d5027_control_active() or loop.next_trial_number()!=5130:
            raise RuntimeError('unexpected arm or sequence')
        sha=loop.relay_health()['relay_sha256']
        if sha!=last['relay_sha256'] or sha!=hashlib.sha256(loop.RELAY_SOURCE.read_bytes()).hexdigest():
            raise RuntimeError('relay hash diverged')
        base=loop.get(repo/'runs/cd75e5e0-be7c-471f-a9ab-c9e6f0d1bd77/evidence.json')['score']['mean_exact_tps']
        state={'owner':work.name,'phase':'running','started':now(),'deadline':'2026-11-23T02:35:00+09:00',
               'record_tps':base,'filmed_record_tps':loop.get(repo/'runs/a9530b69-3aed-4ea9-8fd9-9ee1fcb36b51/evidence.json')['score']['mean_exact_tps'],'relay_sha256':sha,'fallback_from':None,'slots':[]}
        loop.put(journal,state)
        loop.put(marker,{'owner':work.name,'reason':'exclusive D5027 through 02:35 KST','time':now()})
        hold=marker.read_bytes()
        done=threading.Event()
        threading.Thread(target=guard,args=(done,),daemon=True).start()
        next_time=last['slots'][-1]['ended']/1000+45
        try:
            while time.time() < cutoff-30:
                while time.time()<min(next_time,cutoff-30) and marker.is_file() and marker.read_bytes()==hold:
                    time.sleep(min(1.0,max(.01,min(next_time,cutoff-30)-time.time())))
                if not marker.is_file() or marker.read_bytes()!=hold:
                    state['phase']='external_stop'
                    break
                if time.time()>=cutoff-30:
                    break
                if not loop.d5027_control_active() or loop.relay_health()['relay_sha256']!=sha:
                    raise RuntimeError('selector/relay configuration changed')
                n=loop.next_trial_number()
                if n!=5130+len(state['slots']):
                    raise RuntimeError('another writer has allocated a slot')
                arm=MERCANTILE_ARM if state['fallback_from'] else FOCUS_D5027
                info={'slot':len(state['slots'])+1,'number':n,'arm':arm[0],'dispatch':now()}
                before=len(loop.past())
                state['slots'].append(info)
                loop.put(journal,state)
                loop.run_trial(n,arm,lock_fds=tuple(fds))
                record(state,info,before)
                loop.put(journal,state)
                next_time=info['ended']/1000+info['cooldown']
                if info.get('new_record') or info.get('new_full_video_record'):
                    with (work/'seal.log').open('a') as out:
                        seal=subprocess.run([sys.executable,'-B',str(work/'seal.py'),info['id']],stdout=out,stderr=out)
                    info['seal_exit']=seal.returncode
                    loop.put(journal,state)
            if state['phase']=='running':
                state['phase']='completed'
        except BaseException as exc:
            state['phase']='interrupted'
            state['error']=type(exc).__name__
            raise
        finally:
            done.set()
            state['stopped']=now()
            loop.put(journal,state)
            if marker.exists() and marker.read_bytes()==hold:
                loop.put(marker,{'owner':work.name,'reason':'campaign '+state['phase'],'time':now(),'slots':len(state['slots'])})

if __name__=='__main__':
    main()
