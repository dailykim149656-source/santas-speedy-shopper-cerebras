"""Sequential trials using a private capture spool and a local public-evidence Git history."""
import argparse
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import uuid

from ledger import atomic, prior_verified_mean
from preflight_recovery import seal_unsent
from research_report import (FORMAT_VARIANTS, correct_subtotals, expected_format, first_five_catalog_links,
                             one_per_source_links)
from scoring import recording_required
from variants import (CATEGORY_VARIANTS, CONTEXT_INJECTION_BY_VARIANT, FIRST_FIVE_VARIANTS, LEGACY_WORKSPACE_AGENTS_MD,
                      MAX_TOKENS_BY_VARIANT, TEST_MAX_TOKENS, TOP_P_BY_VARIANT, WORKSPACE_AGENTS_BY_VARIANT, arm_key,
                      choose, choose_target, choose_test, prompt)
from export_bundle import publish

REPO = Path(__file__).resolve().parents[1]
TOOLS = REPO / 'tools'
MAIN_ROOT = Path.home() / 'Library/Caches/cerebras-speed-bounty/2026-11-22'
ROOT = Path(os.environ.get('BOUNTY_ROOT', str(MAIN_ROOT)))
CACHE = ROOT / 'mean-2000'
RUNS = CACHE / 'runs'
HISTORY = CACHE / 'iterations.jsonl'
NODE = ROOT / 'bin/node'
BENCH = json.loads((REPO / 'benchmark.json').read_text())
MAIN_ARCHIVE = Path.home() / 'Library/Application Support/Cerebras Speed Bounty/2026-11-22/raw'
PRIVATE_ARCHIVE = Path(os.environ.get('BOUNTY_RAW_ARCHIVE', str(MAIN_ARCHIVE)))
PUBLIC_DIRECTORY = MAIN_ARCHIVE.parent / 'public'
# A test schedule runs beside the main loop: its own gateway root, raw archive and run numbers, and it never
# refreshes the portable bundle or pushes the public snapshot.
TEST_SCHEDULE = os.environ.get('BOUNTY_SCHEDULE') == 'test'
LABEL_BASE = int(os.environ.get('BOUNTY_LABEL_BASE', '0'))
if TEST_SCHEDULE and (ROOT.resolve() == MAIN_ROOT.resolve() or PRIVATE_ARCHIVE.resolve() == MAIN_ARCHIVE.resolve()
                      or LABEL_BASE < 1000):
    raise SystemExit('Test schedule needs its own BOUNTY_ROOT, BOUNTY_RAW_ARCHIVE and a BOUNTY_LABEL_BASE of 1000+')
PUBLIC_REMOTE = 'https://github.com/dailykim149656-source/santas-speedy-shopper-cerebras.git'

def preserve_raw(file, ident, directory=PRIVATE_ARCHIVE):
    uuid.UUID(ident)
    body = file.read_bytes()
    if json.loads(body)['id'] != ident:
        raise ValueError('Raw run ID does not match the committed plan')
    directory.mkdir(parents=True, mode=0o700, exist_ok=True)
    dest = directory / (ident+'.json')
    if dest.exists() and dest.read_bytes() != body:
        raise ValueError('Private archive already has different bytes for this run')
    if not dest.exists():
        atomic(dest,body)
    digest = hashlib.sha256(body).hexdigest()
    if hashlib.sha256(dest.read_bytes()).hexdigest() != digest:
        raise OSError('Private raw archive failed readback verification')
    return digest

def put(file, value):
    file.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    private = file.with_name(file.name+'.writing')
    private.write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n')
    private.replace(file)

def get(file): return json.loads(file.read_text())

def status(phase, **info):
    info.update(phase=phase, time=datetime.now(timezone.utc).isoformat())
    put(CACHE/'status.json',info)
    print(json.dumps(info,ensure_ascii=False),flush=True)

def ledger(*args):
    done=subprocess.run([sys.executable, str(TOOLS/'ledger.py'), *map(str,args)], text=True,
                        capture_output=True)
    if done.returncode:
        raise RuntimeError('Git ledger: '+done.stderr[-800:])
    if not TEST_SCHEDULE:
        publish(REPO)
    return json.loads(done.stdout)

def update_public_copy():
    if TEST_SCHEDULE:
        return
    approval = PUBLIC_DIRECTORY/'.git/approved-github-remote'
    if not approval.is_file() or approval.read_text().strip() != PUBLIC_REMOTE:
        return
    try:
        upstream = subprocess.check_output(['git','-C',str(PUBLIC_DIRECTORY),'remote','get-url','--push','origin'],text=True).strip()
        if upstream != PUBLIC_REMOTE:
            raise ValueError('Unexpected public GitHub destination')
        subprocess.run([sys.executable,str(TOOLS/'public_snapshot.py'),'--source',str(REPO),'--dest',str(PUBLIC_DIRECTORY)],
                       check=True,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,timeout=300)
        subprocess.run(['git','-C',str(PUBLIC_DIRECTORY),'-c','credential.helper=','-c','credential.helper=!gh auth git-credential',
                        'push','origin','refs/heads/main:refs/heads/main'],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,
                       env=dict(os.environ,GIT_TERMINAL_PROMPT='0'),timeout=50)
        head=subprocess.check_output(['git','-C',str(PUBLIC_DIRECTORY),'rev-parse','HEAD'],text=True).strip()
        put(CACHE/'public-status.json',{'state':'synced','public_commit':head,'at':datetime.now(timezone.utc).isoformat()})
    except (OSError,ValueError,subprocess.SubprocessError) as exc:
        # Local evidence and the trial target remain available during a GitHub outage.
        put(CACHE/'public-status.json',{'state':'retry_next_result','error':type(exc).__name__,'at':datetime.now(timezone.utc).isoformat()})

def append(event):
    with HISTORY.open('a') as output:
        output.write(json.dumps(event,ensure_ascii=False)+'\n')
        output.flush()
        os.fsync(output.fileno())

def past():
    return [json.loads(s) for s in HISTORY.read_text().splitlines() if s] if HISTORY.exists() else []

def next_trial_number():
    highest = 0
    for file in (REPO/'runs').glob('*/plan.json'):
        label = get(file).get('label', '')
        match = re.fullmatch(r'D(\d+)-.+', label)
        if match:
            highest = max(highest, int(match.group(1)))
    return max(highest, LABEL_BASE) + 1

def set_workspace_agents(workspace, text):
    """Make the benchmark workspace's AGENTS.md exactly `text`, or absent for None. OpenClaw rereads it each turn."""
    if Path(workspace).resolve() != (ROOT/'shopper-test/workspace').resolve():
        raise RuntimeError('Benchmark workspace moved; refusing to edit its AGENTS.md')
    target = Path(workspace)/'AGENTS.md'
    if target.is_symlink() or (target.exists() and not target.is_file()):
        raise RuntimeError('Benchmark AGENTS.md must be a regular file')
    # Once AGENTS.md has existed, OpenClaw treats an empty workspace as vanished and refuses the run. This file
    # is not a bootstrap file, so it keeps the workspace non-empty without entering the prompt.
    keep = Path(workspace)/'.benchmark-workspace'
    if not keep.exists():
        keep.write_text('Keeps this benchmark workspace non-empty so OpenClaw does not treat it as vanished '
                        'when AGENTS.md is removed for control trials.\n')
    current = target.read_text() if target.exists() else None
    allowed_agents = (*WORKSPACE_AGENTS_BY_VARIANT.values(), *LEGACY_WORKSPACE_AGENTS_MD)
    if current is not None and current not in allowed_agents:
        raise RuntimeError('Unrecognized AGENTS.md in the benchmark workspace; refusing to replace it')
    if current == text:
        return
    if text is None:
        target.unlink()
    else:
        staged = target.with_name('.AGENTS.md.writing')
        staged.write_text(text)
        staged.replace(target)
    if (target.read_text() if target.exists() else None) != text:
        raise RuntimeError('Benchmark AGENTS.md did not persist')

def configure(temp, top_p, max_tokens, context_injection=None, workspace_agents=None):
    if context_injection not in (None, 'never'):
        raise ValueError('Unsupported benchmark workspace context setting')
    state=ROOT/'shopper-test/openclaw.json'
    config=get(state)
    if config.get('tools',{}).get('toolSearch',{}).get('enabled') is not False:
        raise RuntimeError('Direct web_fetch setting of the dedicated profile changed')
    defaults = config['agents']['defaults']
    if defaults['model']['primary'] != BENCH['model']:
        raise RuntimeError('Dedicated profile no longer uses the Kimi trial model')
    set_workspace_agents(defaults['workspace'], workspace_agents)
    params = dict(defaults.get('params', {}))
    settings = {'temperature': temp, 'topP': top_p, 'maxTokens': max_tokens}
    for key, value in settings.items():
        if value is None:
            params.pop(key, None)
        else:
            params[key] = value
    updated = dict(defaults)
    if params != defaults.get('params', {}):
        updated['params'] = params
    if context_injection is None:
        updated.pop('contextInjection', None)
    else:
        updated['contextInjection'] = context_injection
    if updated == defaults:
        return
    config['agents']['defaults'] = updated
    put(state,config)
    if get(state)['agents']['defaults'] != updated:
        raise RuntimeError('Dedicated profile benchmark configuration did not persist')
    # Configuration is hot-reloaded. This interval exceeds the gateway's default reload debounce.
    time.sleep(3)

def wait_for(file, proc, seconds):
    deadline=time.monotonic()+seconds
    while time.monotonic()<deadline:
        if file.exists(): return
        if proc.poll() is not None:
            raise RuntimeError('Process ended before '+file.name)
        time.sleep(.25)
    raise TimeoutError(file.name)

def stop_child(proc):
    if proc is None or proc.poll() is not None: return
    proc.terminate()
    try: proc.wait(timeout=12)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=5)

def run_trial(idx,arm, *, campaign_1700=False, campaign_2000=False, video_threshold_override=None):
    ident=str(uuid.uuid4())
    nonce=ident[:8]
    label=f'D{idx:04d}-{arm[0]}'
    key='agent:main:shop-'+label.lower()+'-'+nonce
    scratch=CACHE/'capture'/ident
    scratch.mkdir(mode=0o700,parents=True)
    top_p = TOP_P_BY_VARIANT.get(arm[0])
    max_tokens = TEST_MAX_TOKENS if TEST_SCHEDULE else MAX_TOKENS_BY_VARIANT.get(arm[0])
    context_injection = CONTEXT_INJECTION_BY_VARIANT.get(arm[0])
    workspace_agents = WORKSPACE_AGENTS_BY_VARIANT.get(arm[0])
    policy = get(REPO/'benchmark.json')
    video_threshold = (video_threshold_override if video_threshold_override is not None
                       else policy['video_threshold_displayed_mean_inclusive'])
    if type(video_threshold) is not int or video_threshold < 1:
        raise ValueError('Invalid displayed mean video threshold')
    plan={'id':ident,'label':label,'sessionKey':key,'variant':arm[0],'thinking':arm[2],'temperature':arm[1],
          'top_p':top_p,'max_completion_tokens':max_tokens,
          'video_threshold_tps':video_threshold,
          'experiment':arm_key(arm),'prompt':prompt(arm,nonce),'official_commit':BENCH['patch_source_commit'],
          'official_patch_sha256':BENCH['patch_sha256'],
          'benchmark_sha256':hashlib.sha256((REPO/'benchmark.json').read_bytes()).hexdigest(),
          'organizer_reproduction_request':BENCH['organizer_reproduction_request']}
    if context_injection is not None:
        plan['context_injection'] = context_injection
    if workspace_agents is not None:
        plan['workspace_agents_md'] = workspace_agents
    if policy.get('retain_new_verified_record') is True:
        plan['prior_verified_mean_tps'] = prior_verified_mean(REPO)
    p=scratch/'plan.json'; put(p,plan)
    configure(arm[1],top_p,max_tokens,context_injection,workspace_agents)
    plan_commit=ledger('plan','--repo',REPO,'--plan',p)['commit']
    put(scratch/'run.json',dict(plan,readyPath=str(scratch/'ready.json')))
    status('preparing_video',label=label,id=ident,plan_commit=plan_commit)
    agent=recorder=None
    with (scratch/'run.log').open('w') as agent_log, (scratch/'video.log').open('w') as video_log:
        try:
            agent=subprocess.Popen([str(NODE),str(TOOLS/'run.mjs'),str(scratch/'run.json')],
                                   stdout=agent_log,stderr=subprocess.STDOUT)
            wait_for(RUNS/(label+'.session.json'),agent,100)
            video_env=dict(os.environ, RECORDER_AUTH_WRAPPER=os.environ.get('BOUNTY_PROFILE_CLI',str(CACHE/'profile.mjs')))
            if not (campaign_1700 or campaign_2000):
                video_env.setdefault('RECORDER_AUTH_NODE', shutil.which('node') or 'node')
            recorder=subprocess.Popen(['node',str(TOOLS/'record.mjs'),'--session-key',key,'--dir',str(scratch)],
                                      stdout=video_log,stderr=subprocess.STDOUT,env=video_env)
            wait_for(scratch/'ready.json',recorder,260)
            status('recording_trial',label=label,id=ident,plan_commit=plan_commit)
            if agent.wait(timeout=865)!=0: raise RuntimeError('Gateway trial failed; private evidence retained')
            raw=RUNS/(label+'.json')
            preserve_raw(raw,ident)
            validation_path=scratch/'validation.json'
            with validation_path.open('w') as out:
                check=subprocess.run([sys.executable,str(TOOLS/'validate.py'),str(raw)],stdout=out,timeout=100)
            if check.returncode not in (0,1): raise RuntimeError('Validator could not read trial')
            v=get(validation_path); score=v['score'].get('mean_exact_tps')
            ui=v['score'].get('ui_rounded_tps')
            method_valid = None
            if campaign_2000:
                from method_2000 import assess
                method_valid = v['valid'] and assess(plan, get(raw), v)
            elif campaign_1700:
                from method_1700 import assess
                method_valid = v['valid'] and assess(plan, get(raw), v)
            elif v['valid'] and arm[0] in FORMAT_VARIANTS:
                method_valid = expected_format(v['final_text'], arm[0])
            elif v['valid'] and arm[0] in FIRST_FIVE_VARIANTS:
                method_valid = first_five_catalog_links(v)
            elif v['valid'] and arm[0] in CATEGORY_VARIANTS:
                method_valid = one_per_source_links(v)
            elif v['valid'] and arm[0] == 'research-price-total':
                method_valid = correct_subtotals(v) == 5
            qualifying = recording_required(score, ui, v['valid'], video_threshold, plan)
            urls=[r['url'] for r in v['products']]
            put(scratch/'finish.json',{'run_id':ident,'mean':ui,'video_threshold_tps':video_threshold,
                                       'urls':urls,'qualifying':qualifying and v['valid'] and len(urls)==5,
                                       'retain_verified_record': qualifying and ui is not None and ui < video_threshold,
                                       'discard_unverified':not v['valid']})
            if qualifying:
                status('finalizing_video', label=label, id=ident, ui=ui, plan_commit=plan_commit)
            # A long upstream retry can yield a long real-time original even for a short answer.
            recorder_code=recorder.wait(timeout=1800 if qualifying else 150)
            entry=ledger('finish','--repo',REPO,'--raw',raw,'--validation',validation_path,'--media-dir',scratch)
            evidence_status=entry['evidence_status']
            row={'id':ident,'label':label,'arm':arm_key(arm),'score':score,'ui':ui,'valid':v['valid'],
                 'method_valid':method_valid,
                 'call_count':v['score']['call_count'],'p90':v['score']['p90_tps'],'goal':v['target_met'],
                 'recorded_video':evidence_status=='complete','evidence_status':evidence_status,'commit':entry['commit']}
            append(row);status('result',**row)
            update_public_copy()
            if qualifying and v['valid'] and (recorder_code or evidence_status not in ('complete','video_superseded')):
                if row['goal']:
                    raise RuntimeError('Target score crossed; capture is pending verification. Preserve raw spool.')
                print('Recording pending verification for '+ident+'; capture spool retained.',file=sys.stderr)
            if not qualifying and recorder_code: raise RuntimeError('Recorder failed during nonqualifying trial')
            if v['target_met'] and row['recorded_video']: return True
            return False
        except (RuntimeError, TimeoutError, OSError, subprocess.SubprocessError) as exc:
            if not (scratch/'ready.json').exists():
                # Stop both processes before checking the no-send proof. If the
                # recorder became ready at any point, the receipt is refused.
                stop_child(agent); stop_child(recorder)
                state = seal_unsent(REPO, CACHE, ident, type(exc).__name__)
                print(json.dumps(state, ensure_ascii=False), flush=True)
                return False
            raise
        finally:
            stop_child(agent);stop_child(recorder)

def target_met(results):
    """The private trial target requires both measured rates and complete, method-valid evidence."""
    return any(row.get('valid') is True and row.get('method_valid') is True
               and row.get('recorded_video') is True
               and row.get('score') is not None and row['score'] >= 1200
               and row.get('ui') is not None and row['ui'] >= 1200 for row in results)

def main():
    args=argparse.ArgumentParser()
    args.add_argument('--once',action='store_true')
    args.add_argument('--campaign-1700-start', type=int, metavar='D_NUMBER',
                      help='start or resume the bounded test campaign from this trial number')
    args.add_argument('--campaign-2000-start', type=int, metavar='D_NUMBER',
                      help='start or resume the bounded TPS-2000 campaign from this trial number')
    args.add_argument('--fast-probe-2000-start', type=int, metavar='D_NUMBER',
                      help='start or resume the bounded 6-trial TPS-2000 fast probe from this trial number')
    opts=args.parse_args()
    campaign = opts.campaign_1700_start
    campaign_2000 = opts.campaign_2000_start
    fast_probe_2000 = opts.fast_probe_2000_start
    selected_campaigns = [val for val in (campaign, campaign_2000, fast_probe_2000) if val is not None]
    if len(selected_campaigns) > 1:
        args.error('--campaign-1700-start, --campaign-2000-start, and --fast-probe-2000-start are mutually exclusive')
    active_campaign = selected_campaigns[0] if selected_campaigns else None
    if active_campaign is not None and (not TEST_SCHEDULE or active_campaign <= LABEL_BASE):
        args.error('campaign options require the isolated test schedule and a new trial number')
    os.umask(0o077)
    CACHE.mkdir(mode=0o700,parents=True,exist_ok=True); RUNS.mkdir(mode=0o700,exist_ok=True)
    with (CACHE/'loop.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX|fcntl.LOCK_NB)
        while True:
            results=past()
            if campaign is not None:
                from campaign_1700 import decision
                arm, reason = decision(REPO, campaign, results)
                if arm is None:
                    status('campaign_1700_stopped', first=campaign, reason=reason)
                    return
            elif campaign_2000 is not None:
                from campaign_2000 import decision
                arm, reason = decision(REPO, campaign_2000, results)
                if arm is None:
                    status('campaign_2000_stopped', first=campaign_2000, reason=reason)
                    return
            elif fast_probe_2000 is not None:
                from campaign_2000 import fast_decision
                arm, reason = fast_decision(REPO, fast_probe_2000, results)
                if arm is None:
                    status('fast_probe_2000_stopped', first=fast_probe_2000, reason=reason)
                    return
            elif any(r['goal'] and r['recorded_video'] for r in results): return
            focused = TEST_SCHEDULE and (CACHE/'target-1200').exists()
            if active_campaign is None and focused and target_met(results):
                status('target_1200_met');return
            if (CACHE/'stop-requested').exists():
                status('user_stop');return
            reload_marker = CACHE/'reload-after-trial'
            if not opts.once and reload_marker.exists():
                reload_marker.unlink()
                os.execv(sys.executable,[sys.executable,'-u',str(Path(__file__).resolve()), *sys.argv[1:]])
            current = get(CACHE/'status.json') if (CACHE/'status.json').exists() else {}
            if current.get('phase') == 'preflight_aborted':
                remaining = datetime.fromisoformat(current['time']).timestamp() + 45 - time.time()
                if remaining > 0:
                    time.sleep(remaining)
                    continue
            if results:
                latest = get(REPO/'runs'/results[-1]['id']/'evidence.json')
                # Leave one full published token-limit window between this client's trials,
                # or use a faster 15s valid / 30s-60s backoff cadence in fast-probe mode.
                failed = 0
                for row in reversed(results):
                    if row['valid']:
                        break
                    failed += 1
                cooldown = (min(60, 15 * 2 ** min(failed, 2)) if fast_probe_2000 is not None
                            else max(60, 30 * 2 ** min(failed, 4)))
                remaining = latest['ended']['time']/1000 + cooldown - time.time()
                if remaining > 0:
                    time.sleep(remaining)
                    continue
            # Use a unique label even if an earlier preflight ended before a model call.
            n=next_trial_number()
            selector = choose_target if focused else choose_test if TEST_SCHEDULE else choose
            if active_campaign is not None:
                finished = {row['id'] for row in results}
                for path in (REPO/'runs').glob('*/plan.json'):
                    if path.parent.name in finished or path.with_name('preflight.json').is_file():
                        continue
                    label = get(path).get('label', '')
                    number = re.fullmatch(r'D(\d+)-.+', label)
                    if number and int(number[1]) >= active_campaign:
                        status('needs_attention', id=path.parent.name, label=label,
                               error='Reconcile existing campaign run before another send')
                        return
                run_trial(
                    n,
                    arm,
                    campaign_1700=(campaign is not None),
                    campaign_2000=(campaign_2000 is not None or fast_probe_2000 is not None),
                    video_threshold_override=(1350 if fast_probe_2000 is not None else None),
                )
                if opts.once: return
            elif run_trial(n,selector(results)) or opts.once: return

if __name__=='__main__':
    try: main()
    except (RuntimeError,TimeoutError,subprocess.SubprocessError,OSError,ValueError,KeyError) as exc:
        status('needs_attention',error=str(exc)[:800])
        raise
