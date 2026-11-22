"""Record and seal one A, F or P slot on the private test gateway."""
import argparse
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import time
import uuid
from types import SimpleNamespace

import ledger
import loop
import validate
from first5027 import terminal_429
from method_1700 import assess
from variants import WORKSPACE_AGENTS_BY_VARIANT, prompt

BASE_VARIANT = 'synth-five-categories-cap'
RECORD = 1354.6625976356386


def sha(data):
    return hashlib.sha256(data).hexdigest()


def make_plan(arm, campaign, slot):
    ident = str(uuid.uuid4())
    label = f'D{loop.next_trial_number():04d}-speed1500-{arm.lower()}'
    baseline = (BASE_VARIANT, .2, 'low')
    text = prompt(baseline, ident[:8])
    experiment = f'{campaign} slot={slot} arm={arm}'
    if arm == 'P':
        import prefetch1500
        text = prefetch1500.prompt(ident)
        experiment += '; plugin=' + prefetch1500.plugin_sha()
    mode = 'final-only' if arm == 'F' else 'retry-only'
    return dict(id=ident, label=label, sessionKey=f'agent:main:shop-{label.lower()}-{ident[:8]}',
                prompt=text, experiment=experiment, variant='speed1500-prefetch' if arm == 'P' else BASE_VARIANT,
                thinking='low', temperature=.2, top_p=None, max_completion_tokens=1024,
                workspace_agents_md=WORKSPACE_AGENTS_BY_VARIANT[BASE_VARIANT],
                provider_max_retries=0, request_relay=f'relay-v1:{loop.relay_sha256()}:{mode}',
                video_threshold_tps=1, official_commit=loop.BENCH['patch_source_commit'],
                official_patch_sha256=loop.BENCH['patch_sha256'],
                benchmark_sha256=sha((loop.REPO/'benchmark.json').read_bytes()),
                organizer_reproduction_request=loop.BENCH['organizer_reproduction_request'])


def configure(plan, arm, receipt_dir):
    loop.relay_health()
    if plan['request_relay'].split(':')[1] != loop.relay_sha256():
        raise RuntimeError('Relay changed since the slot plan was sealed')
    loop.configure(.2, None, 1024, workspace_agents=plan['workspace_agents_md'], relay=True)
    nonce = plan['id'][:8]
    binding = dict(protocol='relay-v1', id=plan['id'], nonce=nonce, relay_sha256=loop.relay_sha256(),
                   mode='final-only' if arm == 'F' else 'retry-only')
    if arm == 'F':
        binding['urls'] = [json.loads(line)['url'] for line in plan['prompt'].splitlines()[1:]]
    if arm == 'P':
        import prefetch1500
        prefetch1500.prepare(plan, receipt_dir)
    target = loop.RELAY_ROOT/'bindings'/(nonce+'.json')
    if target.exists() and loop.get(target) != binding:
        raise RuntimeError('Conflicting nonce binding')
    loop.put(target, binding)


def five_numbered_links(result):
    products = result.get('products') or []
    if len(products) != 5 or not all(p.get('verified') and p.get('catalog_name') and p.get('url') for p in products):
        return False
    expected = [f"{i}. [{p['catalog_name']}]({p['url']})" for i, p in enumerate(products, 1)]
    return result.get('final_text', '').strip().splitlines() == expected


def prefetch_wire(plan, row, expected_context):
    digest = row.get('forwarded_sha256', '')
    file = loop.RELAY_ROOT/'logs'/plan['id']/f"{row.get('at_ms')}-{digest[:12]}.json"
    if not re.fullmatch(r'[a-f0-9]{64}', digest) or not file.is_file():
        return False
    body = file.read_bytes()
    if sha(body) != digest or digest != row.get('received_sha256'):
        return False
    user_text = []
    for message in json.loads(body).get('messages', []):
        if message.get('role') != 'user':
            continue
        content = message.get('content')
        if isinstance(content, str):
            user_text.append(content)
        elif isinstance(content, list):
            user_text.extend(part['text'] for part in content if isinstance(part, dict)
                             and isinstance(part.get('text'), str))
    return sum(t.count(expected_context) for t in user_text) == 1 and any(plan['prompt'] in t for t in user_text)


def relay_proof(plan, arm, calls, rows, native_proof=None, receipt_dir=None):
    reasons = []
    http_ok = [r for r in rows if r.get('status') == 200]
    if not rows or len(http_ok) != len(calls):
        reasons.append('measured raw calls and successful relay requests differ')
    for index, (row, call) in enumerate(zip(http_ok, calls), 1):
        timing = row.get('timing') or {}
        seconds = timing.get('completion_time')
        if (timing.get('completion_tokens') != call['outputTokens'] or type(seconds) not in (int, float)
                or not math.isclose(seconds * 1000, call['completionMs'], rel_tol=1e-8, abs_tol=1e-8)):
            reasons.append(f'measured call {index}: provider SSE and raw generation timing differ or are missing')
    wire = []
    if arm == 'P' and rows:
        import prefetch1500
        try:
            live = []
            for category in prefetch1500.SYNTH_CATEGORIES:
                item = json.loads((receipt_dir/(category+'.bin')).read_bytes())[0]
                live.append(dict(name=item['name'], permalink=item['permalink']))
            context = prefetch1500.CONTEXT_PREFIX + json.dumps(live, ensure_ascii=False, separators=(',', ':'))
            if sha(context.encode()) != (native_proof or {}).get('context_sha256'):
                reasons.append('merchant responses and native context digest differ or native proof is missing')
            for row in rows:
                confirmed = prefetch_wire(plan, row, context)
                wire.append(dict(at_ms=row.get('at_ms'), sha256=row.get('forwarded_sha256'), context_present=confirmed))
                if not confirmed:
                    reasons.append('live context or original task missing in recorded provider request')
        except (KeyError, IndexError, TypeError, ValueError, OSError):
            reasons.append('native provider request could not be checked against retained merchant data')
    return dict(valid=not reasons, sse_calls_checked=len(http_ok), native_wire=wire, reasons=reasons)


def collect_relay(plan, arm, calls, native_proof=None, receipt_dir=None):
    path = loop.RELAY_ROOT/'logs/requests.jsonl'
    rows = [row for line in path.read_text().splitlines() if line.strip()
            and (row := json.loads(line)).get('run_id') == plan['id']] if path.exists() else []
    proof = relay_proof(plan, arm, calls, rows, native_proof, receipt_dir)
    ok = proof['valid']
    for row in rows:
        if row.get('relay_sha256') != plan['request_relay'].split(':')[1] or row.get('error'):
            ok = False
        final = arm == 'F' and row.get('phase') == 'final'
        if final:
            changes = set(row.get('changes', []))
            if 'removed_tools' not in changes or changes - {'removed_tools', 'removed_tool_choice', 'removed_parallel_tool_calls'}:
                ok = False
        elif row.get('received_sha256') != row.get('forwarded_sha256') or row.get('changes'):
            ok = False
        if arm != 'F' and row.get('phase') != 'passthrough':
            ok = False
    if arm == 'F':
        phases = [row.get('phase') for row in rows if row.get('status') == 200]
        ok = ok and bool(phases) and phases[0] == 'first' and phases[-1] == 'final'
    proof['valid'] = ok
    if not ok and not proof['reasons']:
        proof['reasons'].append('relay phase, version or allowed changes differ from plan')
    return rows, proof


def perform(plan, directory, attempt, lock_fd):
    media = attempt/'media'
    media.mkdir(parents=True)
    inputs = directory/'run.json'
    loop.put(inputs, dict(plan, readyPath=str(media/'ready.json')))
    raw = loop.RUNS/(plan['label']+'.json')
    agent = recorder = None
    env = dict(os.environ, RECORDER_AUTH_WRAPPER=os.environ.get('BOUNTY_PROFILE_CLI', str(loop.CACHE/'profile.mjs')))
    try:
        with (attempt/'agent.log').open('wb') as alog, (attempt/'recorder.log').open('wb') as vlog:
            agent = subprocess.Popen([str(loop.NODE), str(loop.TOOLS/'run.mjs'), str(inputs)], stdout=alog,
                                     stderr=subprocess.STDOUT, pass_fds=(lock_fd,))
            loop.wait_for(loop.RUNS/(plan['label']+'.session.json'), agent, 100)
            recorder = subprocess.Popen([str(loop.NODE), str(loop.TOOLS/'record.mjs'), '--session-key',
                                         plan['sessionKey'], '--dir', str(media)], env=env, stdout=vlog,
                                        stderr=subprocess.STDOUT)
            loop.put(attempt/'recorder.json', dict(pid=recorder.pid, session=plan['sessionKey']))
            loop.wait_for(media/'ready.json', recorder, 275)
            code = agent.wait(timeout=915)
            if not raw.exists():
                raise RuntimeError(f'Gateway sender exited {code} without a terminal artifact; inspect {attempt}')
            return recorder, media
    except BaseException:
        loop.stop_child(agent)
        loop.stop_child(recorder)
        raise


def finalize(plan, arm, campaign, slot, directory, receipt_dir, media, recorder):
    ident, label = plan['id'], plan['label']
    raw_path = directory/'raw.json'
    source = loop.RUNS/(label+'.json')
    if not raw_path.exists():
        ledger.atomic(raw_path, source.read_bytes())
    if raw_path.read_bytes() != source.read_bytes():
        raise RuntimeError('Gateway archive and retained raw bytes differ')
    raw = loop.get(raw_path)
    if raw['id'] != ident or raw['sessionKey'] != plan['sessionKey'] or raw['prompt'] != plan['prompt']:
        raise RuntimeError('Terminal raw does not match the bound plan')
    raw_sha = loop.preserve_raw(raw_path, ident)
    validation_path = directory/'validation.json'
    if validation_path.exists():
        result = loop.get(validation_path)
    else:
        if arm == 'P':
            import prefetch1500
            result = prefetch1500.validate(loop.REPO, raw_path, plan, receipt_dir)
        else:
            result = validate.validate(raw)
        result.update(input_path=str(raw_path), input_sha256=raw_sha)
        loop.put(validation_path, result)
    if result.get('run_id') != ident or result.get('input_sha256') != raw_sha:
        raise RuntimeError('Validation and raw hashes differ')
    calls = result['calls']
    score = result['score']['mean_exact_tps']
    ui = result['score']['ui_rounded_tps']
    measured_count = result['score']['call_count']
    rows, proof = collect_relay(plan, arm, calls, result.get('native_prefetch'), receipt_dir)
    relay_valid = proof['valid']
    loop.put(directory/'relay.json', rows)
    loop.put(directory/'relay-proof.json', proof)
    native_check = result.get('method_valid', result.get('valid')) if arm == 'P' else assess(plan, raw, result)
    format_valid = five_numbered_links(result)
    method_valid = bool(native_check and relay_valid and format_valid)
    product_valid = bool(result.get('product_valid', result['valid']))
    valid = product_valid and method_valid
    urls = [p['url'] for p in result['products'] if p.get('verified')]
    loop.put(media/'finish.json', dict(run_id=ident, mean=ui, video_threshold_tps=1,
                                       urls=urls, qualifying=product_valid and len(urls)==5 and ui is not None,
                                       discard_unverified=False, preserve_unqualified=True))
    if recorder is not None:
        try:
            recorder.wait(timeout=900)
        except subprocess.TimeoutExpired:
            loop.stop_child(recorder)
    elif not (media/'recording.json').exists() and (media.parent/'recorder.json').exists():
        # After a controller restart the independent recorder can still be rendering this exact run.
        owner = loop.get(media.parent/'recorder.json')
        deadline = time.monotonic() + 900
        while owner.get('session') == plan['sessionKey'] and time.monotonic() < deadline:
            command = subprocess.run(['ps', '-p', str(owner['pid']), '-o', 'command='],
                                     capture_output=True, text=True).stdout
            if (media/'recording.json').exists() or (str(media) not in command or 'record.mjs' not in command):
                break
            time.sleep(1)
    # A newly retained leader can supersede an older ledger clip. Keep its originals privately.
    if product_valid and score is not None and score > 0:
        for item in ledger.retention_records(loop.REPO):
            if item.get('evidence_status') != 'complete' or item['score']['mean_exact_tps'] >= score:
                continue
            for name in ledger.VIDEOS:
                old_clip = loop.REPO/'runs'/item['id']/name
                if old_clip.is_file():
                    backup = directory.parent.parent/'previous-records'/item['id']/name
                    backup.parent.mkdir(parents=True, exist_ok=True)
                    if not backup.exists():
                        shutil.copy2(old_clip, backup)
    entry = ledger.finish(loop.REPO, SimpleNamespace(raw=raw_path, validation=validation_path,
                                                     media_dir=media, historical=False))
    evidence = loop.get(Path(entry['path']))
    loop.put(directory/'evidence.json', evidence)
    confirmed = evidence['evidence_status'] in ('complete','video_superseded') and (media/'demo.mp4').is_file()
    summary = dict(slot=slot, campaign=campaign, arm=arm, id=ident, label=label, score=score, ui=ui,
                   valid=valid, product_valid=product_valid, method_valid=method_valid, relay_valid=relay_valid,
                   format_valid=format_valid,
                   recorded_video=confirmed, evidence_status=evidence['evidence_status'],
                   record=valid and score is not None and score > RECORD,
                   goal=valid and score is not None and score>=1500 and ui>=1500 and confirmed,
                   calls=calls, call_count=measured_count, first_tps=calls[0].get('tokensPerSecond') if calls else None,
                   final_tps=calls[-1].get('tokensPerSecond') if calls and calls[-1]['stopReason']=='stop' else None,
                   terminal_429=terminal_429(raw, loop.ROOT/'gateway.log'), started_wall=raw.get('startedWall'),
                   ended_wall=raw['ended']['time'], raw_sha256=raw_sha, product_urls=urls,
                   provider_attempts=sum(len(r.get('attempts', [])) + int('status' in r) for r in rows),
                   provider_429s=sum(int(r.get('status')==429) + sum(a.get('status')==429 for a in r.get('attempts', []))
                                     for r in rows),
                   paths=dict(plan=str(directory/'plan.json'), raw=str(raw_path), validation=str(validation_path),
                              relay=str(directory/'relay.json'), media=str(media), ledger=entry['path'], receipts=str(receipt_dir)))
    loop.put(directory/'summary.json', summary)
    return summary


def run(args, directory, lock_fd):
    summary = directory/'summary.json'
    slot_plan = directory/'plan.json'
    if slot_plan.exists():
        plan = loop.get(slot_plan)
        if not plan['experiment'].startswith(f'{args.campaign} slot={args.slot} arm={args.arm}'):
            raise ValueError('Slot belongs to a different arm or campaign')
    else:
        plan = make_plan(args.arm, args.campaign, args.slot)
        loop.put(slot_plan, plan)
    if summary.exists():
        return loop.get(summary)
    receipt_dir = args.root/args.campaign/'receipts'/plan['id']
    ledger.plan(loop.REPO, plan)
    raw = loop.RUNS/(plan['label']+'.json')
    attempts = sorted(directory.glob('attempt-*'))
    recorder = None
    if raw.exists():
        if not attempts:
            raise RuntimeError('Terminal run lacks a private capture attempt')
        media = attempts[-1]/'media'
    else:
        if (loop.RUNS/(plan['label']+'.pending.json')).exists() or any((a/'media/ready.json').exists() for a in attempts):
            raise RuntimeError('A send may already exist; recover the original gateway raw before resuming')
        configure(plan, args.arm, receipt_dir)
        attempt = directory/f'attempt-{len(attempts)+1:03d}'
        recorder, media = perform(plan, directory, attempt, lock_fd)
    try:
        return finalize(plan, args.arm, args.campaign, args.slot, directory, receipt_dir, media, recorder)
    finally:
        loop.stop_child(recorder)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--arm', choices=['A','F','P'], required=True)
    p.add_argument('--campaign', required=True)
    p.add_argument('--slot', required=True, type=int)
    p.add_argument('--root', type=Path, default=loop.CACHE)
    args = p.parse_args()
    if not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_-]{0,60}', args.campaign) or not 1 <= args.slot <= 999:
        p.error('Invalid campaign name or slot number')
    if (not loop.TEST_SCHEDULE or loop.ROOT != loop.MAIN_ROOT.with_name('2026-11-22-test')
            or os.environ.get('BOUNTY_GATEWAY_PORT') != '19863' or ledger.git(loop.REPO, 'branch','--show-current') != 'test'):
        p.error('Use BOUNTY_SCHEDULE=test, isolated test root/raw archive/label base and gateway port 19863')
    os.umask(0o077)
    args.root = args.root.resolve()
    directory = args.root/args.campaign/'slots'/f'{args.slot:03d}'
    directory.mkdir(parents=True, exist_ok=True)
    with (directory/'slot.lock').open('ab') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        row = run(args, directory, lock.fileno())
    print(json.dumps(row, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
