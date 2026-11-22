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
from research_report import (FORMAT_VARIANTS, category_links_for_plan, correct_subtotals, expected_format,
                             first_five_catalog_links)
from scoring import recording_required
from variants import (CATEGORY_VARIANTS, CONTEXT_INJECTION_BY_VARIANT, FIRST_FIVE_VARIANTS, MAX_TOKENS_BY_VARIANT,
                      MERCANTILE_ARM, MERCANTILE_VARIANT,
                      TEST_MAX_TOKENS, TOP_P_BY_VARIANT, WORKSPACE_AGENTS_BY_VARIANT, arm_key, choose,
                      choose_category_focus, choose_d5027, choose_relay_focus, choose_target, choose_test,
                      prompt, RELAY_SYSTEM_PROMPT, RELAY_VARIANTS)
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
# Test schedule only: no same-model provider retries. OpenClaw otherwise retries a 429 up to nine times in the
# same run, 30 s apart, and the retried request carries recovery context into the first measured call (15 of 19
# runs after the 1,355 record). A provider error now ends the run, and the next trial starts in a fresh session.
PROVIDER_MAX_RETRIES = 0 if TEST_SCHEDULE else None
AGENT_SETTINGS = ROOT/'shopper-test/agents/main/agent/settings.json'
# Largest clean first-call prompt (uncached + cached tokens) seen for a variant; above it the context grew.
# Internal retries leave no error message in history, so the prompt size is the evidence. Clean runs of the
# D5027 family were 2,862-3,026 tokens; retried ones 3,428-7,679.
# Use the same diagnostic cutoff for the Mercantile comparison.
CLEAN_FIRST_PROMPT_MAX = {name: 3300 for name in (
    'synth-five-categories-cap', MERCANTILE_VARIANT, 'synth-five-categories-cap-4000',
    'first5027-extract-text', 'first5027-defer-answer')}
RATE_LIMIT_TEXT = ('needs a short break', 'high traffic', 'rate limit', '429')
# Relay arms reach Cerebras through tools/request_relay.mjs; every other arm talks to Cerebras directly.
DIRECT_BASE_URL = 'https://api.cerebras.ai/v1'
RELAY_PORT = int(os.environ.get('BOUNTY_RELAY_PORT', '19871'))
RELAY_BASE_URL = f'http://127.0.0.1:{RELAY_PORT}/v1'
RELAY_ROOT = CACHE/'relay'
RELAY_SOURCE = TOOLS/'request_relay.mjs'
# OpenClaw shapes requests for api.cerebras.ai without `store` or streaming usage options. A loopback URL would
# turn both on, so they are pinned off while the relay URL is set; only the relay's own rewrite then differs.
RELAY_COMPAT = {'supportsStore': False, 'supportsUsageInStreaming': False}

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
    if current is not None and current not in WORKSPACE_AGENTS_BY_VARIANT.values():
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

def set_provider_retries(count):
    """Pin retry.provider.maxRetries in the benchmark agent's settings.json, read by OpenClaw on every run."""
    if count is None:
        return
    if AGENT_SETTINGS.resolve().parent != (ROOT/'shopper-test/agents/main/agent').resolve():
        raise RuntimeError('Benchmark agent directory moved; refusing to edit its settings')
    settings = get(AGENT_SETTINGS) if AGENT_SETTINGS.exists() else {}
    if settings.get('retry', {}).get('provider', {}).get('maxRetries') == count:
        return
    retry = dict(settings.get('retry', {}))
    retry['provider'] = dict(retry.get('provider', {}), maxRetries=count)
    put(AGENT_SETTINGS, dict(settings, retry=retry))
    if get(AGENT_SETTINGS)['retry']['provider']['maxRetries'] != count:
        raise RuntimeError('Provider retry setting did not persist')

def context_metrics(raw, variant):
    """Whether the first measured call saw only the committed request, and whether the run hit a rate limit."""
    messages = [m for m in raw['history']['messages'] if m.get('role') == 'assistant']
    errors_before, first = 0, None
    for m in messages:
        if m.get('serverGeneration'):
            first = m
            break
        if m.get('stopReason') == 'error':
            errors_before += 1
    def text(m):
        return ' '.join(b.get('text', '') for b in m.get('content') or [] if isinstance(b, dict)).lower()
    rate_limited = any(m.get('stopReason') == 'error' and any(s in text(m) for s in RATE_LIMIT_TEXT)
                       for m in messages)
    usage = (first or {}).get('usage') or {}
    prompt_tokens = (usage.get('input') or 0) + (usage.get('cacheRead') or 0) + (usage.get('cacheWrite') or 0)
    limit = CLEAN_FIRST_PROMPT_MAX.get(variant)
    clean = None
    if first is not None:
        clean = errors_before == 0 and (limit is None or prompt_tokens <= limit)
    return {'first_prompt_tokens': prompt_tokens if first else None, 'errors_before_first_call': errors_before,
            'context_clean': clean, 'rate_limited': rate_limited}

def relay_sha256():
    return hashlib.sha256(RELAY_SOURCE.read_bytes()).hexdigest()

def relay_health():
    import urllib.request
    try:
        with urllib.request.urlopen(f'http://127.0.0.1:{RELAY_PORT}/health', timeout=3) as response:
            health = json.loads(response.read())
    except (OSError, ValueError) as exc:
        raise RuntimeError(f'Request relay is not running on port {RELAY_PORT}') from exc
    if health.get('relay_sha256') != relay_sha256():
        raise RuntimeError('Running request relay differs from tools/request_relay.mjs; restart it')
    return health

def bind_relay(plan, mode='rewrite'):
    """Write the binding the relay looks up by the request's _run= nonce. No binding, no rewrite."""
    urls = [json.loads(line)['url'] for line in plan['prompt'].splitlines()[1:]]
    nonce = plan['id'][:8]
    if len(urls) != 5 or any(f'_run={nonce}' not in url for url in urls):
        raise RuntimeError('Relay binding needs the five committed fetch URLs')
    binding = {'protocol': 'relay-v1', 'mode': mode, 'id': plan['id'], 'nonce': nonce, 'urls': urls,
               'relay_sha256': relay_sha256()}
    if mode == 'rewrite':
        binding['system_prompt'] = plan['relay_system_prompt']
    target = RELAY_ROOT/'bindings'/(nonce+'.json')
    if target.exists():
        raise RuntimeError('Relay binding already exists for this nonce')
    put(target, binding)

def relay_phases(ident):
    log = RELAY_ROOT/'logs'/'requests.jsonl'
    if not log.exists():
        return []
    rows = [json.loads(line) for line in log.read_text().splitlines() if line.strip()]
    return [row.get('phase') if not row.get('error') else 'error' for row in rows if row.get('run_id') == ident]

def set_provider_route(config, relay):
    """Point the cerebras provider at the relay or directly at Cerebras. Returns True when it changed."""
    provider = config['models']['providers']['cerebras']
    models = [m for m in provider['models'] if m['id'] == BENCH['model'].split('/', 1)[1]]
    if len(models) != 1:
        raise RuntimeError('Dedicated profile no longer lists the Kimi trial model once')
    before = json.dumps(provider, sort_keys=True)
    compat = {k: v for k, v in models[0].get('compat', {}).items() if k not in RELAY_COMPAT}
    if relay:
        relay_health()
        compat.update(RELAY_COMPAT)
    models[0]['compat'] = compat
    provider['baseUrl'] = RELAY_BASE_URL if relay else DIRECT_BASE_URL
    return json.dumps(provider, sort_keys=True) != before

def configure(temp, top_p, max_tokens, context_injection=None, workspace_agents=None, relay=False):
    set_provider_retries(PROVIDER_MAX_RETRIES)
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
    route_changed = set_provider_route(config, relay)
    if updated == defaults and not route_changed:
        return
    config['agents']['defaults'] = updated
    put(state,config)
    if get(state)['agents']['defaults'] != updated:
        raise RuntimeError('Dedicated profile benchmark configuration did not persist')
    if get(state)['models']['providers']['cerebras']['baseUrl'] != (RELAY_BASE_URL if relay else DIRECT_BASE_URL):
        raise RuntimeError('Provider route did not persist')
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

def d5027_control_active():
    return TEST_SCHEDULE and (CACHE/'focus-d5027').is_file() and (CACHE/'relay-control').is_file()

def run_trial(idx,arm, *, campaign_1700=False, score_first=False, first5027=False, lock_fds=(), first_required=False,
              defer_below_tps=None):
    if defer_below_tps is not None:
        if (defer_below_tps != 1300 or not d5027_control_active() or arm not in (choose_d5027([]), MERCANTILE_ARM)
                or campaign_1700 or score_first or first5027 or first_required):
            raise ValueError('Deferred validation needs a recorded retry-only control trial and a 1300 TPS cutoff')
        from deferred_helpers import deferred_capture
    if arm[0] == MERCANTILE_VARIANT and (not TEST_SCHEDULE or arm != MERCANTILE_ARM or campaign_1700
                                         or score_first or first5027):
        raise ValueError('Mercantile comparison needs the isolated test schedule and D5027 settings')
    if first_required and (not d5027_control_active() or arm != choose_d5027([])
                           or campaign_1700 or score_first or first5027):
        raise ValueError('First-required needs the isolated D5027 control trial')
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
    video_threshold = policy['video_threshold_displayed_mean_inclusive']
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
    if score_first:
        plan['capturePolicy'] = 'score-first'
    if PROVIDER_MAX_RETRIES is not None:
        plan['provider_max_retries'] = PROVIDER_MAX_RETRIES
    relay_mode = None
    if arm[0] in RELAY_VARIANTS:
        relay_mode = 'rewrite'
        plan['request_relay'] = 'relay-v1:' + relay_sha256()
        plan['relay_system_prompt'] = RELAY_SYSTEM_PROMPT
    elif first_required:
        relay_mode = 'first-required'
    elif arm == MERCANTILE_ARM or (TEST_SCHEDULE and arm[0] == 'synth-five-categories-cap'
                                   and (CACHE/'relay-control').exists()):
        relay_mode = 'retry-only'
    if relay_mode in ('retry-only', 'first-required'):
        plan['request_relay'] = 'relay-v1:' + relay_sha256() + ':' + relay_mode
    p=scratch/'plan.json'; put(p,plan)
    configure(arm[1],top_p,max_tokens,context_injection,workspace_agents,relay=bool(relay_mode))
    plan_commit=ledger('plan','--repo',REPO,'--plan',p)['commit']
    if relay_mode:
        bind_relay(plan, relay_mode)
    inputs = plan if score_first else dict(plan, readyPath=str(scratch/'ready.json'))
    put(scratch/'run.json', inputs)
    status('measuring_tps' if score_first else 'preparing_video', label=label, id=ident, plan_commit=plan_commit)
    agent=recorder=None
    with (scratch/'run.log').open('w') as agent_log, (scratch/'video.log').open('w') as video_log:
        try:
            agent=subprocess.Popen([str(NODE),str(TOOLS/'run.mjs'),str(scratch/'run.json')],
                                   stdout=agent_log,stderr=subprocess.STDOUT,pass_fds=lock_fds)
            if not score_first:
                wait_for(RUNS/(label+'.session.json'),agent,100)
                video_env=dict(os.environ, RECORDER_AUTH_WRAPPER=os.environ.get('BOUNTY_PROFILE_CLI',str(CACHE/'profile.mjs')))
                if not campaign_1700:
                    video_env.setdefault('RECORDER_AUTH_NODE', shutil.which('node') or 'node')
                recorder=subprocess.Popen(['node',str(TOOLS/'record.mjs'),'--session-key',key,'--dir',str(scratch)],
                                          stdout=video_log,stderr=subprocess.STDOUT,env=video_env)
                wait_for(scratch/'ready.json',recorder,260)
                status('recording_trial',label=label,id=ident,plan_commit=plan_commit)
            if agent.wait(timeout=865)!=0: raise RuntimeError('Gateway trial failed; private evidence retained')
            raw=RUNS/(label+'.json')
            preserve_raw(raw,ident)
            if defer_below_tps is not None:
                pending = deferred_capture(raw, plan, scratch, video_threshold, recorder)
                if pending is not None:
                    pending.update(context_metrics(get(raw), arm[0]), relay_phases=relay_phases(ident))
                    status('pending_validation', **pending)
                    return pending
            validation_path=scratch/'validation.json'
            with validation_path.open('w') as out:
                check=subprocess.run([sys.executable,str(TOOLS/'validate.py'),str(raw)],stdout=out,timeout=100)
            if check.returncode not in (0,1): raise RuntimeError('Validator could not read trial')
            v=get(validation_path); score=v['score'].get('mean_exact_tps')
            ui=v['score'].get('ui_rounded_tps')
            recorded_run = get(raw)
            method_valid = None
            if first5027:
                from method_1700 import assess_first5027
                method_valid = v['valid'] and assess_first5027(plan, recorded_run, v)
            elif campaign_1700:
                from method_1700 import assess
                method_valid = v['valid'] and assess(plan, recorded_run, v)
            elif v['valid'] and arm[0] in FORMAT_VARIANTS:
                method_valid = expected_format(v['final_text'], arm[0])
            elif v['valid'] and arm[0] in FIRST_FIVE_VARIANTS:
                method_valid = first_five_catalog_links(v)
            elif v['valid'] and arm[0] in CATEGORY_VARIANTS:
                method_valid = category_links_for_plan(v, recorded_run)
            elif v['valid'] and arm[0] == 'research-price-total':
                method_valid = correct_subtotals(v) == 5
            media_args = []
            if recorder is not None:
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
                media_args = ['--media-dir', scratch]
            entry=ledger('finish','--repo',REPO,'--raw',raw,'--validation',validation_path,*media_args)
            evidence_status=entry['evidence_status']
            row={'id':ident,'label':label,'arm':arm_key(arm),'score':score,'ui':ui,'valid':v['valid'],
                 'method_valid':method_valid,
                 'call_count':v['score']['call_count'],'p90':v['score']['p90_tps'],'goal':v['target_met'],
                 'recorded_video':evidence_status=='complete','evidence_status':evidence_status,'commit':entry['commit']}
            if score_first:
                row['capturePolicy'] = plan['capturePolicy']
            row.update(context_metrics(recorded_run, arm[0]))
            if first_required or arm == MERCANTILE_ARM:
                row['request_relay'] = plan['request_relay']
            if relay_mode:
                row['relay_phases'] = relay_phases(ident)
            if first5027:
                from first5027 import metrics
                row.update(metrics(plan, recorded_run, v, ROOT/'gateway.log'))
            append(row);status('result',**row)
            update_public_copy()
            if recorder is not None and qualifying and v['valid'] and (recorder_code or evidence_status not in ('complete','video_superseded')):
                if row['goal']:
                    raise RuntimeError('Target score crossed; capture is pending verification. Preserve raw spool.')
                print('Recording pending verification for '+ident+'; capture spool retained.',file=sys.stderr)
            if recorder is not None and not qualifying and recorder_code: raise RuntimeError('Recorder failed during nonqualifying trial')
            if v['target_met'] and row['recorded_video']: return True
            return False
        except (RuntimeError, TimeoutError, OSError, subprocess.SubprocessError) as exc:
            send_intent = RUNS/(label+'.send-intent.json')
            if not (scratch/'ready.json').exists() and not send_intent.exists():
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

def trial_selector():
    if not TEST_SCHEDULE:
        return choose
    for marker, selector in (('focus-d5027', choose_d5027), ('focus-relay', choose_relay_focus),
                             ('focus-categories', choose_category_focus), ('target-1200', choose_target)):
        if (CACHE / marker).exists():
            return selector
    return choose_test

def exploit_wait_seconds(*, zero_token_429: bool, retry_after_seconds: float = 0,
                         accelerated: bool = False, merchant_429: bool = False) -> float:
    """Minimum gap from the preceding terminal timestamp for the D5027-only campaign."""
    base_seconds = 15 if zero_token_429 is True else 45
    if accelerated:
        base_seconds = 90 if merchant_429 is True else (5 if zero_token_429 is True else 15)
    return max(base_seconds, retry_after_seconds)

def prior_d5027_success(row, *, retry_only=False):
    phases = row.get('relay_phases')
    if retry_only and (phases != ['passthrough', 'passthrough']
                       or ('request_relay' in row and not str(row['request_relay']).endswith(':retry-only'))):
        return False
    return (row.get('arm') == arm_key(choose_d5027([]))
            and row.get('valid') is True and row.get('method_valid') is True
            and row.get('rate_limited') is False
            and type(row.get('call_count')) is int and row['call_count'] == 2
            and phases in (None, [], ['passthrough', 'passthrough'])
            and row.get('capturePolicy') is None)

def main():
    args=argparse.ArgumentParser()
    args.add_argument('--once',action='store_true')
    comparison = args.add_mutually_exclusive_group()
    comparison.add_argument('--d5027-mercantile', action='store_true',
                            help='select the Mercantile five-search arm for a single retry-only test trial')
    comparison.add_argument('--d5027-first-required', action='store_true',
                            help='set only the first request tool_choice to required for one D5027 control trial')
    args.add_argument('--d5027-post-success-seconds', type=int, choices=(30, 60, 90), default=60,
                      help='cooldown after a successful normal test focus-d5027 trial (default: 60)')
    args.add_argument('--campaign-1700-start', type=int, metavar='D_NUMBER',
                      help='start or resume the bounded test campaign from this trial number')
    opts=args.parse_args()
    campaign = opts.campaign_1700_start
    if opts.d5027_mercantile and (not TEST_SCHEDULE or not opts.once or campaign is not None
                                  or opts.d5027_post_success_seconds != 60):
        args.error('--d5027-mercantile needs test --once and the default 60-second cadence')
    long_gap = opts.d5027_post_success_seconds == 90
    if long_gap and (not opts.once or campaign is not None):
        args.error('a 90-second cadence needs a single D5027 control trial (--once)')
    if opts.d5027_first_required and (not opts.once or not d5027_control_active()
                                     or campaign is not None or opts.d5027_post_success_seconds != 60):
        args.error('--d5027-first-required needs test --once, focus-d5027, relay-control and a 60-second cadence')
    if campaign is not None and (not TEST_SCHEDULE or campaign <= LABEL_BASE):
        args.error('--campaign-1700-start requires the isolated test schedule and a new trial number')
    os.umask(0o077)
    CACHE.mkdir(mode=0o700,parents=True,exist_ok=True); RUNS.mkdir(mode=0o700,exist_ok=True)
    with (CACHE/'loop.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX|fcntl.LOCK_NB)
        while True:
            results=past()
            if long_gap and not d5027_control_active():
                args.error('a 90-second cadence needs the test focus-d5027 and relay-control markers')
            if campaign is not None:
                from campaign_1700 import decision
                arm, reason = decision(REPO, campaign, results)
                if arm is None:
                    status('campaign_1700_stopped', first=campaign, reason=reason)
                    return
            elif any(r['goal'] and r['recorded_video'] for r in results): return
            selector = trial_selector()
            if campaign is None and not opts.d5027_mercantile and selector is choose_target and target_met(results):
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
                # Leave one full published token-limit window between this client's trials.
                failed = limited = 0
                for row in reversed(results):
                    if row['valid']:
                        break
                    if row.get('rate_limited'):
                        limited += 1
                    else:
                        failed += 1
                cooldown = max(60, 30 * 2 ** min(failed, 4))
                # A 429 now ends the run at once and uses no tokens, so restart in a fresh session after one
                # token-limit window instead of backing off exponentially; slow to 2 minutes in a long 429 run.
                if results[-1].get('rate_limited'):
                    cooldown = max(60 if limited < 3 else 120, 30 * 2 ** min(failed, 4) if failed else 0)
                if (TEST_SCHEDULE and campaign is None and selector is choose_d5027
                        and prior_d5027_success(results[-1], retry_only=long_gap)):
                    cooldown = opts.d5027_post_success_seconds
                remaining = latest['ended']['time']/1000 + cooldown - time.time()
                if remaining > 0:
                    time.sleep(remaining)
                    continue
            # Use a unique label even if an earlier preflight ended before a model call.
            n=next_trial_number()
            if campaign is not None:
                finished = {row['id'] for row in results}
                for path in (REPO/'runs').glob('*/plan.json'):
                    if path.parent.name in finished or path.with_name('preflight.json').is_file():
                        continue
                    label = get(path).get('label', '')
                    number = re.fullmatch(r'D(\d+)-.+', label)
                    if number and int(number[1]) >= campaign:
                        status('needs_attention', id=path.parent.name, label=label,
                               error='Reconcile existing campaign run before another send')
                        return
                score_first = (CACHE/f'score-first-{campaign}').is_file()
                run_trial(n, arm, campaign_1700=True, score_first=score_first)
                if opts.once: return
            elif opts.d5027_mercantile:
                run_trial(n, MERCANTILE_ARM)
                return
            elif opts.d5027_first_required:
                run_trial(n, selector(results), first_required=True)
                return
            elif run_trial(n,selector(results)) or opts.once: return

if __name__=='__main__':
    try: main()
    except (RuntimeError,TimeoutError,subprocess.SubprocessError,OSError,ValueError,KeyError) as exc:
        status('needs_attention',error=str(exc)[:800])
        raise
