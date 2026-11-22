"""Fresh Shopify prefetch and one official-patch generation per isolated OpenClaw session."""
import argparse
from contextlib import ExitStack
from datetime import datetime
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import tempfile
import time
from urllib.request import urlopen
from uuid import uuid4
import run_category_trials as core

SOURCE = '121842981f3214db7066de4f12540d51195bcc36'
PROMPT = 'Find 5 real Christmas gifts for my husband under $50:\n- collapsible coffee dripper\n- cast iron skillet\n- enamel camp mug\n- leather pocket journal\n- leather keychain'
TOOLS=Path(__file__).resolve().parent

def read(p):
    return json.loads(p.read_bytes())

def trial(n):
    ident=str(uuid4())
    return dict(id=ident,label=f'slot-{n:03}-shopify',slot=n,arm='shopify-prefetch',variant='shopify-one-generation',
                sessionKey=f'agent:main:shopify-one-{ident}',prompt=PROMPT,model=core.MODEL,
                thinking='low',temperature=.1,max_completion_tokens=2400)

def criteria(raw,pref):
    assistants=[m for m in raw.get('history',{}).get('messages',[]) if m.get('role')=='assistant']
    if not pref or not pref.get('valid') or len(assistants)!=1 or raw.get('ended',{}).get('terminal')!='final':
        return False
    answer='\n'.join(c.get('text','') for c in assistants[0].get('content',[]) if c.get('type')=='text')
    gen=assistants[0].get('serverGeneration',{})
    return (raw.get('official') or {}).get('calls')==1 and (gen.get('completionMs') or 0)>0 and all(p['url'] in answer for p in pref['products'])

def previous_pause(directory):
    """Continue the last documented merchant/provider backoff across an approved time extension."""
    if directory is None:
        return 0, 0
    records = sorted(directory.glob('slot-*-shopify.json'))
    if not records:
        return 0, 0
    streak = 0
    for path in records:
        raw = read(path)
        if not raw.get('ended'):
            raise RuntimeError('preceding raw result still pending')
        folder = directory / raw['id']
        prefile, tracefile = folder/'prefetch.json', folder/'transport/trace.json'
        pre = read(prefile) if prefile.is_file() else {}
        tr = read(tracefile) if tracefile.is_file() else {}
        provider = tr.get('status') == 429 or any(e.get('status') == 429 for e in raw.get('providerFailures',[]))
        retailer = any(e.get('status') == 429 for e in pre.get('lookups',[]))
        streak = streak+1 if provider else 0
        wait = 90 if retailer else min(90,30*streak) if provider else 15
        finish = folder/'finish.json'
        last = max(raw['ended']['time']/1000, finish.stat().st_mtime if finish.is_file() else 0)
    return streak, last + wait

def run(args):
    cutoff=datetime.fromisoformat(args.deadline)
    if not cutoff.tzinfo:raise ValueError('time zone required')
    until=cutoff.timestamp()
    runtime=core.DEFAULT_RUNTIME
    out=args.out.resolve()
    if out.exists() or time.time()>=until:raise ValueError('new directory and future cutoff required')
    with ExitStack() as stack:
        core.campaign_locks(stack,runtime)
        info=core.runtime_info(runtime)
        for port in (args.port,args.relay_port):
            with socket.socket() as sock:sock.bind(('127.0.0.1',port))
        key=core.provider_key(runtime)
        out.mkdir(mode=0o700,parents=True)
        root=runtime.parent/'simethan-private-states'
        root.mkdir(mode=0o700,exist_ok=True)
        state=Path(tempfile.mkdtemp(prefix='shopify-',dir=root))
        core.save(out/'review-state.json',{'state':str(state)})
        if args.continue_from:
            core.save(out/'post-run-video-only.json', {'reason':'continuation of user-approved post-run capture', 'previous':str(args.continue_from.resolve())})
        slots=[trial(n) for n in range(1,61)]
        core.save(out/'plan.json',dict(protocol='simethan-shopify-v1',runtime=info,source=SOURCE,
                  deadline=cutoff.isoformat(),pauseSeconds=15,trials=slots,continuedFrom=str(args.continue_from.resolve()) if args.continue_from else None))
        core.prepare_state(runtime,state,args.port,out)
        conf=read(state/'openclaw.json')
        route=conf['models']['providers']['cerebras']
        route['baseUrl']=f'http://127.0.0.1:{args.relay_port}/v1'
        route['models'][0].setdefault('compat',{}).update(supportsStore=False,supportsUsageInStreaming=False)
        conf['agents']['defaults']['params'].update(temperature=.1,maxTokens=2400)
        conf['plugins']={'enabled':True,'allow':['cerebras']}
        conf['tools']={'allow':['web_fetch'],'toolSearch':{'enabled':False}}
        (state/'workspace/AGENTS.md').write_text('Use the shopping request in the current session.\n')
        (state/'openclaw.json').write_text(json.dumps(conf))
        with (out/'transport.log').open('xb') as tlog:
            relay=subprocess.Popen([runtime/'bin/node',TOOLS/'simethan_transport.mjs',f'--root={out}',f'--port={args.relay_port}'],start_new_session=True,stdout=tlog,stderr=tlog)
            stack.callback(core.stop_process_group,relay)
            timeout=min(time.time()+15,until)
            while time.time()<timeout:
                try:
                    with urlopen(f'http://127.0.0.1:{args.relay_port}/health',timeout=.6) as r:
                        if r.status==200:break
                except OSError:pass
                if relay.poll() is not None:raise RuntimeError('transport failed to start')
                time.sleep(.15)
            else:raise RuntimeError('transport readiness timeout')
            gw=core.start_gateway(stack,runtime,state,args.port,out/'gateway.log',key,cutoff)
            streak, earliest = previous_pause(args.continue_from)
            if earliest:
                core.save(out/'handoff.json', {'previous':str(args.continue_from.resolve()),'providerStreak':streak,'earliestNextSlot':earliest})
                time.sleep(max(0,min(earliest,until)-time.time()))
            for s in slots:
                if time.time()>=until:break
                if gw.poll() is not None or relay.poll() is not None:raise RuntimeError('owned gateway or transport stopped')
                with (out/'events.jsonl').open('a') as events:
                    print(json.dumps({'slot':s['label'],'id':s['id'],'dispatch':time.time()}),file=events,flush=True)
                with (out/(s['label']+'.log')).open('xb') as log:
                    child=subprocess.Popen([runtime/'bin/node','--experimental-transform-types',TOOLS/'category_query_session.mjs',runtime/'openclaw',state,str(args.port),out,s['label']],start_new_session=True,stdout=log,stderr=log)
                    try:child.wait(timeout=max(2,min(300,until-time.time()+65)))
                    finally:core.stop_process_group(child)
                rawfile=out/(s['label']+'.json')
                if not rawfile.exists():raise RuntimeError('missing actual session receipt')
                raw=read(rawfile)
                pf=out/s['id']/'prefetch.json'; pref=read(pf) if pf.is_file() else {}
                if raw.get('unconfirmedTermination'):raise RuntimeError('session termination not acknowledged')
                if child.returncode and not ('Shopify lookup failed' in raw.get('error','') or 'Deadline' in raw.get('error','')):raise RuntimeError('session failed before a terminal receipt')
                trace=out/s['id']/'transport/trace.json';tr=read(trace) if trace.exists() else {}
                provider=tr.get('status')==429 or bool(any(e.get('status')==429 for e in raw.get('providerFailures',[])))
                retailer=any(x.get('status')==429 for x in pref.get('lookups',[]))
                if tr.get('status') in (401,403):raise RuntimeError('upstream authentication failed')
                streak=streak+1 if provider else 0
                pause=90 if retailer else min(90,30*streak) if provider else 15
                print(json.dumps({'slot':s['label'],'shop':pref.get('valid'), 'provider429':provider,'merchant429':retailer,
                          'calls':(raw.get('official') or {}).get('calls'), 'score':(raw.get('official') or {}).get('meanTokensPerSecond'),'pause':pause}), flush=True)
                ok=criteria(raw,pref)
                folder=out/s['id']
                if folder.is_dir():
                    core.save(folder/'finish.json',{'run_id':s['id'],'mean':round((raw.get('official') or {}).get('meanTokensPerSecond') or 0),
                            'sentAt':raw.get('sentAt'),'urls':[p['url'] for p in pref.get('products',[])], 'video_threshold_tps':1,'qualifying':ok})
                time.sleep(max(0,min(pause,until-time.time())))
        print('Campaign closed at '+datetime.now().astimezone().isoformat(),flush=True)

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--out',type=Path,required=True);ap.add_argument('--deadline',required=True)
    ap.add_argument('--continue-from',type=Path)
    ap.add_argument('--relay-port',type=int,default=19872);ap.add_argument('--port',type=int,default=19873)
    os.umask(0o077)
    run(ap.parse_args())
