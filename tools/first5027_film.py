#!/usr/bin/env python3
"""Independent private film watcher for the test first5027 campaign; never sends requests."""
import argparse
from datetime import datetime, timezone
import fcntl
import json
import hashlib
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import time

REPO = Path(__file__).resolve().parents[1]
MAIN_ROOT = Path.home() / 'Library/Caches/cerebras-speed-bounty/2026-11-22'
ROOT = Path(os.environ.get('BOUNTY_ROOT', str(MAIN_ROOT) + '-test'))
CACHE = ROOT / 'mean-2000'
START = 5037
FILMS = CACHE / f'film-first5027-{START}'
SENTINEL = CACHE / f'recording-complete-{START}'
VARIANTS = {'synth-five-categories-cap', 'first5027-extract-text', 'first5027-defer-answer'}
sys.path.insert(0, str(REPO / 'tools'))
from ledger import read_capture_file, viewport_proof

def read(path):
    try: return json.loads(path.read_text())
    except (FileNotFoundError, json.JSONDecodeError): return {}

def put(path, value):
    tmp = path.with_suffix('.writing')
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    tmp.chmod(0o600)
    tmp.replace(path)

def utc():
    return datetime.now(timezone.utc).isoformat()

def unixms(stamp):
    parsed = datetime.fromisoformat(stamp.replace('Z', '+00:00'))
    if parsed.tzinfo is None:
        raise ValueError('capture timestamp needs timezone')
    return round(parsed.timestamp() * 1000)

def eligible(plan, start=None):
    start = START if start is None else start
    label = plan.get('label', '')
    match = re.fullmatch(r'D([0-9]+)-([A-Za-z0-9-]+)', label)
    ident = plan.get('id', '')
    return bool(match and int(match[1]) >= start and match[2] in VARIANTS
                and plan.get('variant') == match[2]
                and re.fullmatch(r'[0-9a-f]{8}-[0-9a-f-]{27}', ident)
                and plan.get('capturePolicy') == 'score-first'
                and plan.get('sessionKey') == 'agent:main:shop-' + label.lower() + '-' + ident[:8])


def committed_plan(ident, start=None):
    private = CACHE / 'capture' / ident / 'plan.json'
    plan = read(private)
    if not eligible(plan, start) or plan['id'] != ident:
        return None
    name = f'runs/{ident}/plan.json'
    result = subprocess.run(['git', '-C', str(REPO), 'show', 'HEAD:' + name], capture_output=True)
    if result.returncode:
        return None
    committed = json.loads(result.stdout)
    fields = ('id', 'label', 'sessionKey', 'capturePolicy', 'prompt', 'variant')
    return plan if all(plan.get(k) == committed.get(k) for k in fields) else None


def sessions(start=None, skip_recorded=False):
    for private in (CACHE / 'capture').glob('*/plan.json'):
        ident = private.parent.name
        if skip_recorded and ((FILMS / ident / 'receipt.json').is_file()
                              or (REPO / 'runs' / ident / 'preflight.json').exists()):
            continue
        plan = committed_plan(ident, start)
        if plan:
            label = plan['label']
            session = read(CACHE / 'runs' / (label + '.session.json'))
            if skip_recorded and not session:
                continue
            if session and any(session.get(k) != plan[k] for k in ('id', 'sessionKey')):
                continue
            yield int(label.split('-')[0][1:]), label, {'id': plan['id'], 'sessionKey': plan['sessionKey']}


def campaign_complete():
    # Root writes this only after the controller has stopped and no sends remain pending.
    return SENTINEL.is_file()


def send_begun(label):
    return any((CACHE/'runs'/(label+suffix)).exists() for suffix in
               ('.send-intent.json', '.pending.json', '.ack.json', '.terminal.json', '.json'))


def watch_queue(start):
    return sorted(row for row in sessions(start, skip_recorded=True)
                  if (not campaign_complete() or send_begun(row[1]))
                  and not (REPO/'runs'/row[2]['id']/'preflight.json').exists()
                  and not (FILMS/row[2]['id']/'receipt.json').exists())

def state(label, session):
    ident = session['id']
    evidence = read(REPO / 'runs' / ident / 'evidence.json')
    validation = read(CACHE / 'capture' / ident / 'validation.json')
    source = validation or evidence
    if not source:
        return None
    if validation and validation.get('run_id') != ident and (validation.get('valid') is True or 'run_id' in validation):
        raise ValueError('validation id mismatch')
    if evidence and evidence.get('id') != ident:
        raise ValueError('evidence id mismatch')
    valid = (validation or evidence.get('validation', {})).get('valid') is True
    urls = [p['url'] for p in source.get('products', [])
            if p.get('verified') is True and isinstance(p.get('url'), str)]
    rounded = source.get('score', {}).get('ui_rounded_tps')
    qualifies = valid and type(rounded) is int and len(set(urls)) == len(urls) == 5
    return dict(run_id=ident, mean=rounded, urls=urls, qualifying=qualifies,
                video_threshold_tps=1700, retain_verified_record=True, discard_unverified=False,
                retention_policy='all campaign sessions; independent of score qualification')

def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def rank(info):
    return (info['full_run_verified'], info['viewportVerified'], info['playable'],
            info.get('timing') == 'first_frame_during_run')


def inspect(label, session, directory):
    work = CACHE / 'runs'
    def runfile(suffix): return read(work / (label + suffix))
    intent, terminal, raw = runfile('.send-intent.json'), runfile('.terminal.json'), runfile('.json')
    saved_session = runfile('.session.json')
    ident = session['id']
    for val in (intent, terminal, raw, saved_session):
        if val and (val.get('id') != ident or val.get('sessionKey') != session['sessionKey']):
            raise ValueError('source timing identity mismatch')
    ready, metadata = read(directory / 'ready.json'), read(directory / 'recording.json')
    sent = intent.get('startedWall', raw.get('startedWall'))
    ended = terminal.get('ended', {}).get('time')
    stamp = ready.get('readyAt')
    if ready and (ready.get('sessionKey') != session['sessionKey'] or ready.get('ready') is not True):
        raise ValueError('recorded session identity mismatch')
    info = dict(id=ident, label=label, sessionKey=session['sessionKey'], inspected_at=utc(),
                readyAfterFirstScreenshot=stamp, sendIntentMs=sent, terminalReceiptMs=ended,
                timing='unknown', full_run_verified=False, directory=str(directory))
    if stamp and finite(ended) and finite(sent):
        first = unixms(stamp)
        info.update(timing='first_frame_before_send' if first <= sent else
                    ('first_frame_during_run' if first < ended else 'first_frame_after_terminal'),
                    firstFrameMinusSendMs=first-sent, firstFrameMinusTerminalMs=first-ended)
    media = {}
    errors = []
    if metadata and (metadata.get('run_id') != ident or metadata.get('sessionKey') != session['sessionKey']):
        errors.append('recording identity mismatch')
    for name in ('original.mp4', 'demo.mp4'):
        try:
            if (directory/name).is_symlink():
                raise ValueError('media must be a regular file')
            media[name] = read_capture_file(directory/name)[1]
        except (ValueError, OSError, subprocess.SubprocessError, KeyError) as error:
            errors.append(f'{name}: {type(error).__name__}')
    info['media'] = media
    info['playable'] = 'demo.mp4' in media and 'original.mp4' in media and bool(metadata) and metadata.get('run_id') == ident and metadata.get('sessionKey') == session['sessionKey']
    reference = state(label, session)
    info['viewportVerified'] = False
    if reference and reference['qualifying'] and info['playable']:
        try:
            if (metadata.get('final_ui_tps') != reference['mean']
                    or metadata.get('qualifying') is not True
                    or metadata.get('urls') != reference['urls']):
                raise ValueError('recording final UI does not match result')
            _, result = viewport_proof(directory, reference['mean'], set(reference['urls']), media)
            info.update(viewportVerified=True, viewportProofSha256=result['sha256'],
                        displayedMean=reference['mean'], verifiedProductURLs=reference['urls'])
        except (KeyError, ValueError, OSError, subprocess.SubprocessError) as error:
            errors.append(f'viewport: {type(error).__name__}')
    timeline = read(directory / 'capture-timeline.json')
    info['real_time_verified'] = False
    if info['playable']:
        original = float(media['original.mp4']['ffprobe']['format']['duration'])
        demo = float(media['demo.mp4']['ffprobe']['format']['duration'])
        duration = timeline.get('durationSeconds')
        frames = timeline.get('frames', [])
        offsets = [frame.get('seconds') for frame in frames]
        info['real_time_verified'] = bool(
            finite(duration) and duration > 0 and offsets and offsets[0] == 0
            and all(finite(value) and 0 <= value <= duration for value in offsets)
            and all(a < b for a, b in zip(offsets, offsets[1:]))
            and abs(original - duration) <= .12
            and abs(demo - min(55, duration)) <= .12
            and metadata.get('durationSeconds') == duration)
        info['full_run_verified'] = bool(
            info['real_time_verified'] and info['timing'] == 'first_frame_before_send'
            and intent and terminal and raw and saved_session
            and raw.get('startedWall') == sent
            and finite(raw.get('ended', {}).get('time'))
            and sent <= ended <= raw['ended']['time']
            and original + .12 >= (ended - unixms(stamp)) / 1000
            and ready.get('initialSummary') == '' and ready.get('rehearsal') is False
            and ready.get('capture') == 'owned-local-viewport'
            and metadata.get('readyAt') == stamp and metadata.get('full_run') is True
            and metadata.get('rehearsal') is False and metadata.get('authless') is True
            and metadata.get('provisional') is not True and metadata.get('discarded') is not True)
    info['target_1700_verified'] = bool(
        info['full_run_verified'] and info['viewportVerified']
        and reference and reference['mean'] >= 1700)
    info['classification'] = ('full_run' if info['full_run_verified'] else
                              'partial_or_post_run' if info['playable'] else 'unavailable')
    info['source_provenance'] = {}
    sources = {suffix: work / (label + suffix) for suffix in
               ('.session.json', '.send-intent.json', '.terminal.json', '.json')}
    sources.update({name: directory / name for name in
                    ('ready.json', 'recording.json', 'capture-timeline.json', 'viewport-evidence.json')})
    sources['validation.json'] = CACHE / 'capture' / ident / 'validation.json'
    sources['evidence.json'] = REPO / 'runs' / ident / 'evidence.json'
    for name, path in sources.items():
        if path.is_file():
            body = path.read_bytes()
            info['source_provenance'][name] = dict(sha256=hashlib.sha256(body).hexdigest(),
                                                   bytes=len(body), modified_ns=path.stat().st_mtime_ns)
    if errors: info['issues'] = errors
    put(directory / 'inspection.json', info)
    return info

def record(label, session, directory):
    directory.mkdir(mode=0o700, parents=True, exist_ok=False)
    env = dict(os.environ, BOUNTY_ROOT=str(ROOT), BOUNTY_GATEWAY_PORT='19863',
               RECORDER_AUTH_WRAPPER=str(CACHE/'profile.mjs'))
    env.pop('RECORDER_AUTH_NODE', None)
    put(directory/'launch.json', dict(startedAt=utc(), label=label, sessionKey=session['sessionKey']))
    with (directory/'recorder.log').open('wb') as log:
        proc = subprocess.Popen([str(ROOT/'bin/node'), str(REPO/'tools/record.mjs'),
                                 '--session-key',session['sessionKey'],'--dir',str(directory)],
                                env=env, cwd=REPO, stdout=log, stderr=subprocess.STDOUT)
        (directory/'recorder.pid').write_text(str(proc.pid))
        print('RECORDING', label, str(directory), flush=True)
        start = time.monotonic()
        finish_at = None
        try:
            while proc.poll() is None:
                ready = read(directory/'ready.json')
                aborted = (REPO / 'runs' / session['id'] / 'preflight.json').exists()
                if aborted or (not send_begun(label) and campaign_complete()):
                    proc.terminate()
                    try: proc.wait(timeout=15)
                    except subprocess.TimeoutExpired: proc.kill()
                    break
                if ready and finish_at is None:
                    result = state(label, session)
                    if result and (result['qualifying'] or time.time()*1000-unixms(ready['readyAt']) >= 5000):
                        put(directory/'finish.json',result)
                        finish_at = time.monotonic()
                elapsed = time.monotonic() - start
                if (not ready and elapsed > 430) or elapsed > 2100 or (finish_at and time.monotonic()-finish_at > 420):
                    proc.terminate()
                    try: proc.wait(timeout=15)
                    except subprocess.TimeoutExpired: proc.kill()
                    break
                time.sleep(0.7)
        finally:
            if proc.poll() is None:
                proc.terminate()
                try: proc.wait(timeout=15)
                except subprocess.TimeoutExpired: proc.kill()
        proc.wait()
    return inspect(label, session, directory)

def attempts(base):
    values = []
    if (base/'recorder.pid').exists() or (base/'ready.json').exists(): values.append(base)
    return values + sorted(base.glob('attempt-[0-9][0-9]'))

def process(label, session, retry=False):
    base = FILMS/session['id']
    base.mkdir(parents=True, exist_ok=True)
    prev = attempts(base)
    results = []
    for directory in prev:
        result = inspect(label, session, directory)
        results.append(result)
    def enough(result):
        comparison = state(label, session)
        target = comparison and comparison['qualifying'] and comparison['mean'] >= 1700
        return result['playable'] and (not target or result['viewportVerified'])
    if not any(enough(r) for r in results) or retry:
        budget = 1 if retry else max(0, 2-len(prev))
        for _ in range(budget):
            # Open the UI only after the sender has finished both local preflight RPCs.
            marker = read(CACHE / 'runs' / (label + '.session.json'))
            if (not marker or any(marker.get(k) != session[k] for k in ('id', 'sessionKey'))
                    or (REPO / 'runs' / session['id'] / 'preflight.json').exists()):
                break
            index = max([int(d.name[-2:]) for d in attempts(base) if d.name.startswith('attempt-')] or [0])+1
            result = record(label, session, base/f'attempt-{index:02d}')
            results.append(result)
            if enough(result) or (not send_begun(label) and campaign_complete()): break
    best = max(results, key=rank, default=None)
    if best:
        put(base/'receipt.json', best)
        print('FILM_RESULT', label, best['playable'], best['timing'], best.get('displayedMean'), flush=True)

def main():
    os.umask(0o077)
    parser=argparse.ArgumentParser(description=__doc__)
    parser.epilog = ('Run before the test controller. Waits through idle periods until ' + str(SENTINEL) +
                     ' exists. Videos remain private; no score-controller dependency. ' +
                     '--retry is a post-run capture when the original run has ended.')
    parser.add_argument('--start',type=int,default=START)
    group=parser.add_mutually_exclusive_group()
    group.add_argument('--inspect',type=int)
    group.add_argument('--retry',type=int)
    args=parser.parse_args()
    if args.start < START:
        parser.error(f'start must be {START} or later')
    branch = subprocess.check_output(['git', '-C', str(REPO), 'branch', '--show-current'], text=True).strip()
    if branch != 'test' or ROOT.resolve() == MAIN_ROOT.resolve():
        parser.error('requires the test branch and an isolated test BOUNTY_ROOT')
    FILMS.mkdir(mode=0o700,parents=True,exist_ok=True)
    number=args.inspect if args.inspect is not None else args.retry
    if number is not None:
        matches = [item for item in sessions() if item[0] == number]
        if len(matches) != 1:
            parser.error('expected one committed campaign plan for this trial number')
        _,label,session=matches[0]
        base=FILMS/session['id']
        if args.retry is not None:
            process(label,session,retry=True)
        else:
            info=[inspect(label,session,d) for d in attempts(base)]
            if not info:
                parser.error('no recording attempt exists for this session')
            best=max(info,key=rank)
            put(base/'receipt.json',best)
            print(json.dumps(best,ensure_ascii=False))
        return
    with (FILMS/'watcher.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        while True:
            queue=watch_queue(args.start)
            if queue:
                for _,label,session in sorted(queue):
                    try:
                        process(label,session)
                    except (ValueError, OSError, subprocess.SubprocessError) as error:
                        base = FILMS / session['id']
                        base.mkdir(mode=0o700, parents=True, exist_ok=True)
                        put(base / 'receipt.json', dict(id=session['id'], label=label,
                            inspected_at=utc(), classification='unavailable',
                            full_run_verified=False, target_1700_verified=False,
                            issue=type(error).__name__))
                        print('FILM_ERROR', label, type(error).__name__, flush=True)
                continue
            if campaign_complete():
                print('FILM_QUEUE_EMPTY', 'campaign completion sentinel', flush=True)
                return
            time.sleep(.2)
if __name__=='__main__':
    main()
