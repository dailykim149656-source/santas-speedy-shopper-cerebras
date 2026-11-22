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
old = cache/'d5027-original-0235'
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
from variants import FOCUS_D5027
from traffic import next_slot_at
from competition import competing_senders

def now():
    return datetime.now(tz).isoformat(timespec='milliseconds')

def guard_other_sender(done, held):
    while not done.wait(3):
        other=competing_senders()
        if not other:
            continue
        if not marker.is_file() or marker.read_bytes()!=held:
            return
        loop.put(work/'competing-sender.json',{'at':now(),'senders':other})
        loop.put(marker,{'owner':work.name,'reason':'competing active benchmark sender','time':now()})
        with (work/'competition.log').open('a') as out:
            subprocess.run([str(root/'bin/node'),str(work/'abort_active.mjs')],stdout=out,stderr=out,timeout=22)
        return

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

def record(st, info, history_size, returned):
    from receipt import assess
    label = f"D{info['number']}-{info['arm']}"
    rows = loop.past()[history_size:]
    pending = isinstance(returned, dict) and returned.get('result') == 'pending_validation'
    if pending:
        if rows or returned['label'] != label:
            raise RuntimeError('accelerated pending result disagrees with ledger')
        row = returned
        end = row['ended']
        if row.get('valid') is not None or not 0 <= row['score'] < 1300:
            raise RuntimeError('unexpected score or premature validation')
    elif rows:
        if len(rows)!=1 or rows[0]['label']!=label:
            raise RuntimeError('unexpected formal entries')
        row=rows[0]
        end=loop.get(repo/'runs'/row['id']/'evidence.json')['ended']['time']
    else:
        files=[f for f in (repo/'runs').glob('*/preflight.json') if loop.get(f.with_name('plan.json')).get('label')==label]
        if len(files)!=1:
            raise RuntimeError('terminal/preflight reconciliation needed')
        info.update(id=files[0].parent.name,result='presend_failure',valid=False,method_valid=False,
                    ended=round(time.time()*1000),cooldown=45 if st['rolled_back'] else 15)
        return
    rec = assess(row)
    info.update(id=row['id'], result='pending_validation' if pending else 'terminal', validation_deferred=pending,
                valid=row.get('valid'), method_valid=row.get('method_valid'), ended=end, score=row['score'],
                context_clean=row.get('context_clean'), rate_limited=row.get('rate_limited'), receipt=rec)
    stamp=end/1000
    # Count affected slots, not the number of requests rejected in one batch.
    if 'aisynthesis.com' in rec['merchant_429_hosts']:
        st['merchant_hits'].append(stamp)
        if sum(stamp-600 <= t <= stamp for t in st['merchant_hits']) >= 2:
            st['rolled_back']=True
    info['cooldown']=loop.exploit_wait_seconds(zero_token_429=rec['zero_token_429'] is True,
                       retry_after_seconds=max(0,(rec.get('retry_after_until') or 0)-stamp),
                       accelerated=True, merchant_429=rec['merchant_429'] is True)
    if st['rolled_back']:
        info['cooldown']=max(45,info['cooldown'])
    if row.get('valid') and row.get('method_valid') and row['score'] and row['score']>st['record_tps']:
        st['record_tps']=row['score']
        info['new_record']=True
    if row.get('valid') and row.get('method_valid') and row.get('recorded_video') and row['score']>st['filmed_record_tps']:
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
        if prev.get('reason')!='return to accelerated 15s D5027 at terminal slot per user' or prev.get('owner')!=old.name or last['phase']!='external_stop':
            raise RuntimeError('another reservation')
        if subprocess.check_output(['git','-C',str(repo),'branch','--show-current'],text=True).strip()!='test':
            raise RuntimeError('wrong branch')
        if not loop.d5027_control_active() or not last['slots'] or loop.next_trial_number()!=last['slots'][-1]['number']+1:
            raise RuntimeError('unexpected arm or sequence')
        if competing_senders():
            raise RuntimeError('independent sending process detected')
        sha=loop.relay_health()['relay_sha256']
        if sha!=last['relay_sha256'] or sha!=hashlib.sha256(loop.RELAY_SOURCE.read_bytes()).hexdigest():
            raise RuntimeError('relay hash diverged')
        start_number=last['slots'][-1]['number']+1
        base=loop.get(repo/'runs/cd75e5e0-be7c-471f-a9ab-c9e6f0d1bd77/evidence.json')['score']['mean_exact_tps']
        state={'owner':work.name,'phase':'running','started':now(),'deadline':'2026-11-23T02:35:00+09:00',
               'start_number':start_number,'rolled_back':False,'merchant_hits':[],'record_tps':max(base,last['record_tps']),'filmed_record_tps':last['filmed_record_tps'],'relay_sha256':sha,'fallback_from':None,'slots':[]}
        prior_fast=loop.get(cache/'d5027-fast-0235/campaign.json')
        if prior_fast['phase']!='external_stop' or prior_fast['owner']!='d5027-fast-0235':
            raise RuntimeError('initial accelerated process still active')
        state['merchant_hits']=prior_fast.get('merchant_hits',[]) + [s['ended']/1000 for s in last['slots'] if 'aisynthesis.com' in s.get('receipt',{}).get('merchant_429_hosts',[])]
        state['rolled_back']=prior_fast.get('rolled_back',False) or sum(t >= time.time()-600 for t in state['merchant_hits'])>=2
        loop.put(journal,state)
        loop.put(marker,{'owner':work.name,'reason':'exclusive accelerated D5027 through 02:35 KST','time':now()})
        hold=marker.read_bytes()
        done=threading.Event()
        threading.Thread(target=guard,args=(done,),daemon=True).start()
        threading.Thread(target=guard_other_sender,args=(done,hold),daemon=True).start()
        previous=last['slots'][-1]
        prev_receipt=previous.get('receipt',{})
        next_time=previous['ended']/1000+loop.exploit_wait_seconds(zero_token_429=prev_receipt.get('zero_token_429') is True,accelerated=True,merchant_429=prev_receipt.get('merchant_429') is True)
        try:
            while time.time() < cutoff-30:
                next_time=max(next_time,next_slot_at())
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
                if n!=start_number+len(state['slots']):
                    raise RuntimeError('another writer has allocated a slot')
                arm=FOCUS_D5027
                info={'slot':len(state['slots'])+1,'number':n,'arm':arm[0],'dispatch':now()}
                before=len(loop.past())
                state['slots'].append(info)
                loop.put(journal,state)
                returned=loop.run_trial(n,arm,lock_fds=tuple(fds),defer_below_tps=1300)
                record(state,info,before,returned)
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
