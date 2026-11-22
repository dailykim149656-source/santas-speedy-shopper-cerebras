"""Run repeated query-only five-category sessions on a dedicated official-patch gateway."""
import argparse
import contextlib
from datetime import datetime
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import re
import secrets
import signal
import socket
import subprocess
import tempfile
import time
from urllib.request import urlopen
from uuid import uuid4

from variants import DIRECT_TOOL_CAP_AGENTS_MD, SYNTH_CATEGORIES, prompt

TOOLS = Path(__file__).resolve().parent
DEFAULT_RUNTIME = Path.home() / 'Library/Caches/cerebras-speed-bounty/2026-11-22'
BASE_VARIANT = 'synth-five-categories-cap'
PATCHED_TREE = 'aec08de95dc279d3c2a5ef46c641ae31b7a0e219'
MODEL = 'cerebras/moonshotai-kimi-k3.1-pro-trial'
PLUGIN = 'category-query'


def workspace_rules():
    return DIRECT_TOOL_CAP_AGENTS_MD.replace('URLs to fetch', 'queries to search').replace(
        'web_fetch calls for those exact URLs', 'search_category calls for those exact queries')


def make_trials(count):
    trials = []
    for slot in range(1, count + 1):
        ident = str(uuid4())
        baseline = prompt((BASE_VARIANT, .2, 'low'), ident[:8])
        first_line = baseline.splitlines()[0].replace('web_fetch', 'search_category')
        arguments = [json.dumps({'query': query}, separators=(',', ':')) for query in SYNTH_CATEGORIES]
        trials.append(dict(id=ident, arm='B', label=f'slot-{slot:03}-B', slot=slot,
                           sessionKey=f'agent:main:category-ab-b-{ident}',
                           prompt='\n'.join([first_line, *arguments]), variant='synth-category-query',
                           model=MODEL, thinking='low', temperature=.2, max_completion_tokens=1024,
                           workspace_agents_md=workspace_rules()))
    return trials


def save(path, payload):
    with path.open('x', encoding='utf8') as stream:
        stream.write(json.dumps(payload, ensure_ascii=False, indent=2) + '\n')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def runtime_info(runtime):
    repo = runtime / 'openclaw'
    bench = json.loads((TOOLS.parent / 'benchmark.json').read_text())
    tree = subprocess.check_output(['git', '-C', repo, 'rev-parse', 'HEAD^{tree}'], text=True).strip()
    dirty = subprocess.check_output(['git', '-C', repo, 'status', '--porcelain', '--untracked-files=no'])
    patch_hash = digest(runtime / 'official.patch')
    if tree != PATCHED_TREE or patch_hash != bench['patch_sha256'] or dirty or bench['model'] != MODEL:
        raise ValueError('Runtime source tree or official patch differs from the recorded benchmark.')
    return dict(model=MODEL, officialPatch=bench['patch_source_commit'], patchSha256=patch_hash, tree=tree,
                runnerSha256=digest(Path(__file__)), clientSha256=digest(TOOLS / 'category_query_session.mjs'),
                pluginSha256=digest(TOOLS / 'category-query-plugin/index.cjs'))


def provider_key(runtime):
    if os.environ.get('CEREBRAS_API_KEY'):
        return os.environ['CEREBRAS_API_KEY']
    # Resolve through the locally configured provider without persisting or logging the credential.
    script = """
import fs from 'node:fs'; import os from 'node:os'; import path from 'node:path'; import {pathToFileURL} from 'node:url';
const {resolveApiKeyForProvider} = await import(pathToFileURL(process.argv[1]));
const base = path.join(os.homedir(),'.openclaw');
const cfg = JSON.parse(fs.readFileSync(path.join(base,'openclaw.json'),'utf8'));
const key = await resolveApiKeyForProvider({provider:'cerebras', modelId:'moonshotai-kimi-k3.1-pro-trial',
  cfg, agentDir:path.join(base,'agents/main/agent')});
if (typeof key.apiKey !== 'string' || !key.apiKey) process.exit(1);
process.stdout.write(key.apiKey);
"""
    result = subprocess.run([runtime / 'bin/node', '--input-type=module', '-e', script,
                             runtime / 'openclaw/dist/plugin-sdk/provider-auth-runtime.js'],
                            capture_output=True, timeout=35)
    if result.returncode or not result.stdout.strip() or b'\n' in result.stdout.strip():
        raise RuntimeError('Cerebras credential unavailable in the environment or local OpenClaw profile')
    return result.stdout.decode().strip()


def campaign_locks(stack, runtime):
    for root, mode in [(runtime.with_name(runtime.name + '-exp2000'), fcntl.LOCK_SH),
                       (runtime, fcntl.LOCK_SH), (runtime.with_name(runtime.name + '-test'), fcntl.LOCK_EX)]:
        lock = stack.enter_context((root / 'mean-2000/loop.lock').open('rb'))
        try:
            fcntl.flock(lock, mode | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError(f'An existing experiment owns {lock.name}. No query trials were started.') from exc


def gateway_config(runtime, state, port, receipts):
    checkout = runtime / 'openclaw'
    base = json.loads((checkout / 'dev/cerebras-kimi/openclaw.json').read_text())
    provider = base['models']['providers']['cerebras']
    if provider['baseUrl'] != 'https://api.cerebras.ai/v1' or provider['apiKey'] != '${CEREBRAS_API_KEY}':
        raise ValueError('Expected the standard direct Cerebras provider')
    plugins = {'enabled': True, 'allow': ['cerebras', PLUGIN],
               'load': {'paths': [str(TOOLS / 'category-query-plugin')]},
               'entries': {PLUGIN: {'enabled': True, 'config': {'receiptDir': str(receipts),
                                                                'openclawRoot': str(checkout)}}}}
    return {'models': {'mode': 'merge', 'providers': {'cerebras': provider}},
            'agents': {'defaults': {'model': {'primary': MODEL}, 'workspace': str(state / 'workspace'),
                                   'skipBootstrap': True, 'thinkingDefault': 'low', 'timeoutSeconds': 180,
                                   'params': {'temperature': .2, 'maxTokens': 1024}}},
            'plugins': plugins, 'tools': {'allow': ['search_category'], 'web': {'fetch': {'enabled': True}},
                                         'toolSearch': {'enabled': False}},
            'gateway': {'mode':'local','bind':'loopback','port':port,'auth':{'mode':'token','token':'${OPENCLAW_GATEWAY_TOKEN}'}},
            'meta': {'migrations': {'modelPolicyAllowlist':True,'utilityModelSeparation':True},'lastTouchedVersion':'2026.10.9'}}


def stop_process_group(proc):
    if proc.poll() is not None:
        return
    try:
        os.killpg(proc.pid, signal.SIGTERM)
        proc.wait(timeout=10)
    except (ProcessLookupError, subprocess.TimeoutExpired):
        if proc.poll() is None:
            os.killpg(proc.pid, signal.SIGKILL)
            proc.wait(timeout=10)


def prepare_state(runtime, state, port, out):
    workspace = state / 'workspace'
    workspace.mkdir(parents=True)
    (workspace / 'AGENTS.md').write_text(workspace_rules())
    token = secrets.token_hex(32)
    (state / 'gateway-token').write_text(token)
    agent = state / 'agents/main/agent'
    agent.mkdir(parents=True)
    save(agent / 'settings.json', {'retry': {'provider': {'maxRetries': 0}}})
    cfg = gateway_config(runtime, state, port, out / 'receipts')
    save(state / 'openclaw.json', cfg)


def start_gateway(stack, runtime, state, port, log_path, key, deadline):
    token = (state / 'gateway-token').read_text().strip()
    env = dict(os.environ, OPENCLAW_STATE_DIR=str(state), OPENCLAW_CONFIG_PATH=str(state / 'openclaw.json'),
               OPENCLAW_GATEWAY_TOKEN=token, OPENCLAW_GATEWAY_PORT=str(port), CEREBRAS_API_KEY=key,
               OPENCLAW_SKIP_CHANNELS='1', OPENCLAW_SKIP_CRON='1',
               PATH=str(runtime / 'bin') + os.pathsep + os.environ.get('PATH', ''))
    stdout = stack.enter_context(log_path.open('xb'))
    proc = subprocess.Popen([runtime / 'bin/node', runtime / 'openclaw/openclaw.mjs', 'gateway', 'run'],
                            start_new_session=True, cwd=runtime / 'openclaw', env=env,
                            stdout=stdout, stderr=subprocess.STDOUT)
    stack.callback(stop_process_group, proc)
    until = min(time.time() + 65, deadline.timestamp() if deadline else math.inf)
    while proc.poll() is None and time.time() < until:
        try:
            with urlopen(f'http://127.0.0.1:{port}/readyz', timeout=2) as response:
                if json.load(response).get('ready') is True:
                    return proc
        except (OSError, ValueError):
            pass
        time.sleep(.5)
    raise RuntimeError(f'Query gateway failed to become ready. See {stdout.name}')


def saved_root(runtime):
    return runtime.parent / 'category-query-review'


def review(args):
    out = args.reopen_from.expanduser().resolve()
    runtime = args.runtime.expanduser().resolve()
    saved = json.loads((out / 'review-state.json').read_text())
    state = Path(saved['state']).resolve()
    if state.parent != saved_root(runtime).resolve() or not state.name.startswith('category-query-'):
        raise ValueError('Review state must be in the private campaign cache.')
    config = json.loads((state / 'openclaw.json').read_text())
    if config['gateway']['bind'] != 'loopback':
        raise ValueError('Review mode requires a local-only gateway')
    runtime_info(runtime)
    port = config['gateway']['port']
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', port))
    # Reopening starts the UI only. No session creation, prompts or model calls.
    with contextlib.ExitStack() as stack:
        log = state / f'review-{uuid4()}.log'
        proc = start_gateway(stack, runtime, state, port, log, provider_key(runtime), None)
        print(f'Original sessions available on http://127.0.0.1:{port}/ ; stop with Ctrl-C.', flush=True)
        proc.wait()


def failure_type(raw, receipts):
    """Only classify documented provider errors or this run's retail fetches."""
    if any(failure.get('status') in (401, 403) for failure in raw.get('providerFailures', [])):
        raise RuntimeError('Provider authentication failed; stopping before any more sends.')
    for path in (receipts / raw['id']).glob('*.json'):
        receipt = json.loads(path.read_text())
        if receipt.get('status') == 429 or re.search(r'\b429\b', str(receipt.get('error', ''))):
            return 'merchant_429'
    if any(failure.get('status') == 429 for failure in raw.get('providerFailures', [])):
        return 'provider_429'
    for msg in raw.get('history', {}).get('messages', []):
        if msg.get('role') == 'assistant' and msg.get('provider') == 'cerebras' and msg.get('stopReason') == 'error':
            if re.search(r'\b429\b|queue_exceeded|too_many_requests_error',
                         ' '.join(str(msg.get(k, '')) for k in ('errorMessage','errorCode','errorType')), re.I):
                return 'provider_429'
    return None


def run(args, deadline):
    runtime = args.runtime.expanduser().resolve()
    out = args.out.expanduser().resolve()
    trials = make_trials(args.count)
    info = runtime_info(runtime)
    with contextlib.ExitStack() as stack:
        campaign_locks(stack, runtime)
        if deadline and time.time() >= deadline.timestamp():
            raise RuntimeError('Requested deadline has elapsed. No session was started.')
        if out.exists():
            raise ValueError('--out must be a new directory to avoid overwriting a prior campaign.')
        with socket.socket() as probe:
            probe.bind(('127.0.0.1', args.port))
        key = provider_key(runtime)
        out.mkdir(mode=0o700, parents=True)
        (out / 'receipts').mkdir(mode=0o700)
        save(out / 'plan.json', dict(count=args.count, pauseSeconds=args.pause_seconds,
                                    deadline=deadline.isoformat() if deadline else None, trials=trials,
                                    runtime=info, providerRoute='direct', providerMaxRetries=0))
        # Retained states include a local operator token; keep them outside exportable results.
        if args.keep_state:
            cache = saved_root(runtime)
            cache.mkdir(mode=0o700, exist_ok=True)
            state = Path(tempfile.mkdtemp(prefix='category-query-', dir=cache))
            save(out / 'review-state.json', {'state': str(state)})
        else:
            state = Path(stack.enter_context(tempfile.TemporaryDirectory(prefix='category-query-')))
        prepare_state(runtime, state, args.port, out)
        gateway = start_gateway(stack, runtime, state, args.port, out / 'gateway.log', key, deadline)
        provider_streak = 0
        for slot in trials:
            if deadline and time.time() >= deadline.timestamp():
                break
            if gateway.poll() is not None:
                raise RuntimeError('Query gateway exited; stopping before the next send.')
            client = subprocess.Popen([runtime / 'bin/node', '--experimental-transform-types',
                                       TOOLS / 'category_query_session.mjs', runtime / 'openclaw',
                                       state, str(args.port), out, slot['label']], start_new_session=True)
            try:
                code = client.wait(timeout=295)
            finally:
                stop_process_group(client)
            if code and deadline and time.time() >= deadline.timestamp():
                break
            if code:
                raise RuntimeError(f"Slot {slot['label']} failed to start or stop cleanly. Inspect retained evidence.")
            if slot is not trials[-1]:
                pause = args.pause_seconds
                raw = json.loads((out / (slot['label'] + '.json')).read_text())
                failure = failure_type(raw, out / 'receipts')
                provider_streak = provider_streak + 1 if failure == 'provider_429' else 0
                if failure == 'merchant_429':
                    pause = max(pause, 90)
                if failure == 'provider_429':
                    pause = max(pause, min(90, 30 * provider_streak))
                if deadline:
                    pause = min(pause, max(0, deadline.timestamp() - time.time()))
                if failure:
                    print(f'{failure}: waiting {pause:.1f}s before the next slot', flush=True)
                time.sleep(pause)
    print(f'Raw sessions and receipts saved to {out}. Run category_query_report.py on this directory.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', type=Path, default=DEFAULT_RUNTIME)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--out', type=Path, help='New output directory for B-only trials')
    mode.add_argument('--reopen-from', type=Path, help='Reopen the original gateway UI for retained sessions; sends no prompts')
    parser.add_argument('--keep-state', action='store_true', help='Keep private local gateway history for a later dashboard recording')
    parser.add_argument('--count', type=int, default=12, help='Maximum number of B-only fresh sessions')
    parser.add_argument('--pause-seconds', type=float, default=45)
    parser.add_argument('--port', type=int, default=19869)
    parser.add_argument('--deadline', help='Absolute ISO-8601 time with UTC offset; stops sending and bounds active trials')
    args = parser.parse_args()
    if (args.count < 1 or not math.isfinite(args.pause_seconds) or args.pause_seconds < 0
            or not 1024 <= args.port <= 65535):
        parser.error('Use a positive count, a nonnegative pause and an unprivileged port.')
    try:
        deadline = datetime.fromisoformat(args.deadline) if args.deadline else None
        if deadline and deadline.tzinfo is None:
            parser.error('--deadline requires an explicit UTC offset')
    except ValueError as exc:
        parser.error(str(exc))
    os.umask(0o077)
    try:
        if args.reopen_from:
            review(args)
        else:
            run(args, deadline)
    except (OSError, RuntimeError, ValueError) as exc:
        parser.exit(1, f'{exc}\n')


if __name__ == '__main__':
    # Ensure the owned gateway is released when the caller requests a graceful stop.
    def interrupt(signum, frame):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, interrupt)
    main()
