#!/usr/bin/env python3
"""Repeat a committed shopping prompt once through your own officially patched OpenClaw gateway.

Example: python3 tools/replay_run.py 694ee975-2931-4496-af62-38fc6650d6a6 --dry-run
Omit --dry-run to send one real request with the selected gateway profile.
"""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
from urllib.parse import quote
import uuid

sys.dont_write_bytecode = True
from scoring import call_rate, mean_rate, round_rate
from validate import MODEL, answer_links, finite, merchant

TOOLS = Path(__file__).resolve().parent


def cli_command(binary, profile):
    path = shutil.which(binary) or binary
    # Pass JSON directly to Node on Windows, avoiding batch-shell interpolation of the prompt.
    if os.name == 'nt' and Path(path).suffix.lower() in ('.cmd','.bat'):
        target = Path(path).parent/'node_modules'/'openclaw'/'openclaw.mjs'
        if not target.is_file():
            raise ValueError('Pass --cli with the path to the installed openclaw.mjs entry point.')
        path = str(target)
    command = ['node',path] if path.lower().endswith('.mjs') else [path]
    return command + (['--profile',profile] if profile else [])


def rpc(command, method, params, timeout_ms=30000):
    args = command + ['gateway','call',method,'--json','--timeout',str(timeout_ms),
                      '--params',json.dumps(params,ensure_ascii=True)]
    try:
        result = subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=timeout_ms/1000+12)
    except subprocess.TimeoutExpired:
        raise ValueError(method + ' exceeded its CLI timeout') from None
    if result.returncode:
        error = (result.stderr + result.stdout).lower()
        hint = next((message for pattern,message in ((b'429','upstream rate limit'),(b'unauthorized','authentication required'),
                     (b'pairing','gateway pairing required'),(b'timeout','gateway timeout'),(b'econnrefused','gateway unavailable'))
                     if pattern in error), 'gateway or CLI returned an error')
        raise ValueError(f'{method} failed ({hint}, exit {result.returncode})')
    try:
        payload = json.loads(result.stdout)
    except (ValueError,UnicodeError):
        raise ValueError(method + ' did not return JSON; check the selected CLI and profile') from None
    if not isinstance(payload,dict):
        raise ValueError(method + ' returned an unexpected payload')
    return payload


def outcome(history, run_id):
    messages = [m for m in history.get('messages',[]) if m.get('role') == 'assistant'
                and m.get('__openclaw',{}).get('runId') == run_id]
    final = next((m for m in reversed(messages) if m.get('stopReason') == 'stop'),None)
    if not final:
        return None
    if any(m.get('provider') != 'cerebras' or m.get('model') != MODEL for m in messages):
        raise ValueError('A different provider or model served a call; this run is ineligible.')
    rates = []
    for message in messages:
        timing = message.get('serverGeneration') or {}
        tokens, ms = timing.get('outputTokens'), timing.get('completionMs')
        if finite(tokens) and tokens >= 1 and finite(ms) and ms > 0:
            rates.append(call_rate(tokens, ms))
    if not rates:
        raise ValueError('No serverGeneration samples; verify the official patch and model configuration.')
    content = final.get('content')
    answer = content if isinstance(content,str) else '\n'.join(
        part['text'] for part in content or [] if part.get('type') == 'text' and isinstance(part.get('text'),str))
    if any(ord(char) < 32 and char not in '\n\t\r' for char in answer):
        raise ValueError('The final text contains terminal control characters.')
    if not answer.strip() or re.search(r'</?(?:think|thinking|reasoning)>|Bearer\s+[A-Za-z0-9_-]{8,}|(?:csk-|sk-)[A-Za-z0-9_-]{12,}',answer,re.I):
        raise ValueError('No displayable final shopping answer.')
    links, misleading = answer_links(answer)
    five = len(links) == len(set(links)) == 5 and not misleading and all(merchant(url,product=True) for url in links)
    mean = mean_rate(rates)
    return mean, len(rates), answer, five, len(messages) == len(rates)


def main():
    parser = argparse.ArgumentParser(description=__doc__,formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('run_id',help='archived run to repeat')
    parser.add_argument('--cli',default='openclaw',help='OpenClaw executable or openclaw.mjs entry point')
    parser.add_argument('--profile',help='existing configured OpenClaw profile')
    parser.add_argument('--timeout',type=int,default=600,help='maximum seconds to wait for this run (default 600)')
    parser.add_argument('--dry-run',action='store_true',help='show settings and fresh prompt without contacting OpenClaw')
    args = parser.parse_args()
    if not 1 <= args.timeout <= 3600:
        parser.error('--timeout must be between 1 and 3600 seconds')
    try:
        result = subprocess.run([sys.executable,str(TOOLS/'verify_run.py'),args.run_id,'--prompt'],
                                capture_output=True,env=dict(os.environ,PYTHONIOENCODING='utf-8'))
        if result.returncode:
            raise ValueError('Archive prompt verification failed. Check the run ID with verify_run.py.')
        prompt = result.stdout.decode('utf-8')
        plan = json.loads((TOOLS.parent/'runs'/args.run_id/'plan.json').read_bytes())
        model = 'cerebras/'+MODEL
        thinking = plan.get('thinking') or 'low'
        print('Model:',model,'| Thinking:',thinking)
        if plan.get('temperature') is not None:
            print('Recorded temperature:',plan['temperature'],'(set in your gateway profile before running)')
        if plan.get('top_p') is not None:
            print('Recorded top_p:',plan['top_p'],'(set agents.defaults.params.topP in your gateway profile)')
        if plan.get('max_completion_tokens') is not None:
            print('Recorded completion limit:',plan['max_completion_tokens'],'(set agents.defaults.params.maxTokens)')
        if args.dry_run:
            print(prompt)
            return 0
        command = cli_command(args.cli,args.profile)
        ident = str(uuid.uuid4())
        key = 'agent:main:shop-review-'+ident
        print('Session:',key,'\nRun:',ident,flush=True)
        print('In your OpenClaw dashboard, open chat?session='+quote(key,safe=''),flush=True)
        session = rpc(command,'sessions.create',{'key':key,'agentId':'main','model':model,'thinkingLevel':thinking})
        if session.get('key') != key or session.get('runStarted'):
            raise ValueError('The gateway did not create the requested idle session.')
        ack = rpc(command,'chat.send',{'sessionKey':key,'message':prompt,'thinking':thinking,'deliver':False,'idempotencyKey':ident})
        if ack.get('runId') != ident:
            raise ValueError('Unexpected chat.send acknowledgement. Inspect this session before starting another run.')
        deadline = time.monotonic()+args.timeout
        while True:
            left = int((deadline-time.monotonic())*1000)
            if left <= 0:
                raise ValueError('No terminal result by deadline. The gateway may still be running; inspect the session above.')
            wait_ms = min(left,60000)
            wait = rpc(command,'agent.wait',{'runId':ident,'timeoutMs':wait_ms},wait_ms+5000)
            status = wait.get('status')
            if status not in ('ok','timeout'):
                raise ValueError('Gateway reported an unsuccessful run; inspect its status in the dashboard.')
            history = rpc(command,'chat.history',{'sessionKey':key,'limit':100,'toolResultMaxChars':256,'maxBytes':1500000})
            saved = outcome(history,ident)
            if saved:
                mean, count, answer, five, complete = saved
                shown = f'{mean:.1f}' if mean < 100 else f'{round_rate(mean):,}'
                print(f'Official server mean: {shown} tok/s ({mean:.6f} exact, {count} timed calls)')
                print(answer)
                if not five or not complete:
                    raise ValueError('The replay lacks five distinct merchant links or complete timing coverage.')
                return 0
            if status == 'ok':
                # A terminal turn can precede chat.history persistence.
                time.sleep(min(1,max(0,deadline-time.monotonic())))
    except (ValueError,KeyError,OSError,TypeError,AttributeError) as exc:
        parser.exit(1,'Replay incomplete: '+str(exc)+'\n')
    except KeyboardInterrupt:
        parser.exit(130,'Interrupted. An already submitted turn may continue in the displayed session.\n')


if __name__ == '__main__':
    sys.exit(main())
