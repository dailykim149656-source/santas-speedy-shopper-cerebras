"""Install the approved first-required comparison between terminal runs, with rollback."""
import fcntl, hashlib, json, os, shutil, signal, subprocess, sys, tempfile, time, urllib.request
from contextlib import ExitStack
from datetime import datetime, timezone
from pathlib import Path

D = Path(__file__).resolve().parent
C = D.parent
R = Path(os.environ.get("BOUNTY_TEST_REPO", Path.cwd()))
STAGE = D / 'required-stage'
OLD = '788fe1f6f9b8dd32322202fa63510d97e5400a940098b9e502ff715d3a69c5fd'
NEW = 'a0106af362e080f62f67dcf0a89d2fb187db99063c8e329a5c787f4f244ee1dd'
NODE = Path.home() / '.nvm/versions/node/v24.20.0/bin/node'
STOP = C / 'stop-requested'
HOLD = D / 'required-deployment'
OWNER = 'd5027-supervisor-53625892-be31-4b98-a60d-e53bfc71a859'
PORT = 19871


def load(path):
    return json.loads(path.read_bytes())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def history():
    return [json.loads(x) for x in (C/'iterations.jsonl').read_bytes().splitlines() if x.strip()]


def free(path):
    with path.open('rb') as f:
        try:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return False
    return True


def fileinstall(src, dest):
    with tempfile.NamedTemporaryFile(dir=dest.parent, delete=False) as tmp:
        name=Path(tmp.name)
    try:
        shutil.copy2(src,name)
        os.replace(name,dest)
    finally:
        name.unlink(missing_ok=True)


def health(port):
    with urllib.request.urlopen(f'http://127.0.0.1:{port}/health',timeout=3) as r:
        assert r.status==200
        return json.load(r)


def listen_pid():
    cp=subprocess.run(['lsof','-nP','-tiTCP:'+str(PORT),'-sTCP:LISTEN'],capture_output=True,text=True)
    return int(cp.stdout.strip()) if cp.returncode==0 else None


def proc(pid):
    return subprocess.check_output(['ps','-p',str(pid),'-o','command=']).decode().strip()


def launch_relay(expected):
    if listen_pid() is not None:
        raise RuntimeError('relay port already owned')
    args=[str(NODE),str(R/'tools/request_relay.mjs'),'--root='+str(C/'relay'),'--port='+str(PORT)]
    env={'PATH':'/usr/bin:/bin:/usr/sbin:/sbin','HOME':str(Path.home())}
    with (C/'relay/relay.log').open('ab') as stream:
        child=subprocess.Popen(args,cwd=R,stdout=stream,stderr=stream,stdin=subprocess.DEVNULL,
                               env=env,start_new_session=True)
    for _ in range(70):
        if child.poll() is not None:
            raise RuntimeError('relay exited during startup')
        try:
            ok=health(PORT)
            if ok.get('relay_sha256')==expected and ok.get('upstream')=='https://api.cerebras.ai' and ok.get('ok'):
                return child.pid
        except OSError:
            pass
        time.sleep(.15)
    child.terminate()
    child.wait(timeout=5)
    raise RuntimeError('relay health did not match installed source')


def exclusive_json(path, data):
    with path.open('x') as file:
        json.dump(data,file,indent=2);file.write('\n');file.flush();os.fsync(file.fileno())


def check_staged():
    if sha(STAGE/'request_relay.mjs') != NEW or sha(R/'tools/request_relay.mjs') != OLD:
        raise RuntimeError('source version changed')
    original_test=subprocess.check_output(['git','-C',str(R),'show','HEAD:tools/request_relay.test.mjs'])
    if original_test != (R/'tools/request_relay.test.mjs').read_bytes():
        raise RuntimeError('shared relay tests changed before deployment')
    for name in ('supervisor.py','required_ab.py'):
        compile((STAGE/name).read_bytes(),str(STAGE/name),'exec')
    expected=load(STAGE/'root-verified-release.json')
    if any(sha(STAGE / name)!=digest for name,digest in expected.items()):
        raise RuntimeError('staged release differs from verified source')


def main():
    os.umask(0o077)
    check_staged()
    if (D/'required-ab-config.json').exists() or STOP.exists() or HOLD.exists():
        raise RuntimeError('activation already attempted or stopped')
    live=subprocess.check_output(['ps','-axo','pid=,command=']).decode().splitlines()
    oldpids=[int(line.strip().split(maxsplit=1)[0]) for line in live if line.endswith(' -B -u '+str(D/'supervisor.py'))]
    if len(oldpids)!=1 or free(D/'supervisor.lock'):
        raise RuntimeError('unexpected supervisor ownership')
    oldpid=oldpids[0]
    deadline=datetime.fromisoformat(load(D/'campaign.json')['deadline']).timestamp()-420
    while time.time()<deadline:
        if STOP.exists() or free(D/'supervisor.lock') or not proc(oldpid).endswith(' -B -u '+str(D/'supervisor.py')):
            raise RuntimeError('original supervisor controls changed')
        assignments=load(D/'cadence-state.json')['assignments']
        state=load(C/'status.json')
        if len(assignments)==8 and all(a['phase']=='complete' for a in assignments) and state.get('phase')=='result' and free(C/'loop.lock'):
            rows=history()
            if rows[-1]['id']==state['id'] and not (rows[-1].get('score') or 0)>1500:
                end=load(R/'runs'/state['id']/'evidence.json')['ended']['time']/1000
                if time.time()<end+57:
                    break
        time.sleep(.5)
    else:
        raise RuntimeError('comparison cutoff reached')
    check_staged()
    oldrelay=listen_pid()
    relcmd=proc(oldrelay)
    if (oldrelay!=62559 or '--root='+str(C/'relay') not in relcmd or str(R/'tools/request_relay.mjs') not in relcmd
            or health(PORT).get('relay_sha256')!=OLD or not health(19863).get('ok')):
        raise RuntimeError('relay/gateway ownership or health changed')
    if not all(free(C.parent.parent/name/'mean-2000/loop.lock') for name in ['2026-11-22','2026-11-22-exp2000']):
        raise RuntimeError('other campaign holds gateway reservation')
    HOLD.mkdir()
    for name,src in [('request_relay.mjs',R/'tools/request_relay.mjs'),('request_relay.test.mjs',R/'tools/request_relay.test.mjs'),('supervisor.py',D/'supervisor.py')]:
        shutil.copy2(src,HOLD/name)
    print('handoff after',state['label'],'with 8 completed cadence assignments',flush=True)
    os.kill(oldpid,signal.SIGTERM)
    for _ in range(120):
        if free(D/'supervisor.lock'):
            break
        time.sleep(.15)
    else:
        raise RuntimeError('original supervisor did not release lock')
    receipt=load(STOP)
    if receipt.get('owner')!=OWNER or receipt.get('reason')!='supervisor signal 15' or history()[-1]['id']!=state['id']:
        raise RuntimeError('unexpected handoff receipt')
    newpid=None
    with ExitStack() as locks:
        for root in (C,C.parent.parent/'2026-11-22/mean-2000',C.parent.parent/'2026-11-22-exp2000/mean-2000'):
            f=locks.enter_context((root/'loop.lock').open('rb'));fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if listen_pid()!=oldrelay or health(PORT).get('relay_sha256')!=OLD:
            raise RuntimeError('listener changed at handoff')
        os.kill(oldrelay,signal.SIGTERM)
        for _ in range(80):
            if listen_pid() is None:break
            time.sleep(.1)
        else: raise RuntimeError('old relay failed to release port')
        try:
            for name in ['request_relay.mjs','request_relay.test.mjs']:
                fileinstall(STAGE/name,R/'tools'/name)
            newpid=launch_relay(NEW)
            fileinstall(STAGE/'required_ab.py',D/'required_ab.py')
            fileinstall(STAGE/'supervisor.py',D/'supervisor.py')
            config={'version':1,'enabled':True,'history_start':len(rows),'anchor_id':state['id'],'relay_sha256':NEW,
                    'previous_relay_sha256':OLD,'cutoff':'2026-11-23T02:53:00+09:00'}
            exclusive_json(D/'required-ab-config.json',config)
            exclusive_json(HOLD/'deployed.json',{'time':datetime.now(timezone.utc).isoformat(),'previous_pid':oldrelay,
                     'relay_pid':newpid,'previous_sha':OLD,'relay_sha':NEW,'anchor':state['label'],'stage_sha256':load(STAGE/'root-verified-release.json')})
        except Exception:
            if newpid is not None and listen_pid()==newpid:
                os.kill(newpid,signal.SIGTERM)
                for _ in range(70):
                    if listen_pid() is None: break
                    time.sleep(.15)
            for name in ['request_relay.mjs','request_relay.test.mjs']:
                fileinstall(HOLD/name,R/'tools'/name)
            fileinstall(HOLD/'supervisor.py',D/'supervisor.py')
            if listen_pid() is None: launch_relay(OLD)
            raise
        os.link(STOP,HOLD/'old-supervisor-stop.json')
        STOP.unlink()
    print('new relay healthy at',PORT,'starting A/B supervisor',flush=True)
    os.execv(sys.executable,[sys.executable,'-B','-u',str(D/'supervisor.py')])


if __name__=='__main__':
    main()
