#!/usr/bin/env python3
"""Offline Git evidence ledger. Raw histories remain private; only SHA256 is saved.

plan --repo DIR --plan JSON
finish --repo DIR --raw JSON --validation JSON [--media-dir DIR] [--historical]
Media: original.mp4, demo.mp4, final.png, recording.json. Recording metadata must
identify the same live session and its credential-free viewport. Partial video
is retained provisionally for recovery. Only the best verified MP4 pair is retained
locally. maintain --repo DIR [--capture-root DIR] retries committed cleanup.
"""
import argparse
from contextlib import contextmanager
from datetime import datetime
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

from scoring import call_rate, mean_rate, round_rate, recording_required

PLAN = ('id','label','sessionKey','variant','thinking','temperature','top_p','max_completion_tokens','video_threshold_tps','prior_verified_mean_tps','context_injection','workspace_agents_md','prompt','experiment','official_commit','official_patch_sha256','benchmark_sha256','organizer_reproduction_request')
SOURCE = ('tool_call_id','url','accepted','reasons','status','fetched_at','cached','products')
PRODUCT = ('url','catalog_name','catalog_price','source_tool_call_id','verified','reasons','http','final_url','html_bytes_read','html_sha256','checked_at','canonical','merchant','title','title_matches_catalog','password_protected')
SECRET = re.compile(r'(?i)(?:bearer\s+[a-z0-9._-]{12,}|sk-[a-z0-9_-]{12,}|(?:api[_-]?key|authorization|password|cookie)\s*[=:]\s*[^\s,;]{4,})')


def pick(obj, keys):
    return {k: obj[k] for k in keys if k in obj}


def encode(obj):
    data = (json.dumps(obj, ensure_ascii=False, indent=2, allow_nan=False) + '\n').encode()
    if SECRET.search(data.decode()):
        raise ValueError('possible secret in allowlisted evidence; refusing write')
    return data


def read(path):
    return json.loads(Path(path).read_bytes())


def sha(data):
    return hashlib.sha256(data).hexdigest()


def git(repo, *args):
    return subprocess.check_output(['git','-C',str(repo),*args], stderr=subprocess.PIPE, text=True).strip()


def atomic(path, data):
    if path.is_symlink():
        raise ValueError('symlink destination refused')
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix='.ledger-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def commit(repo, files, subject):
    paths = [str(p.relative_to(repo)) for p in files]
    git(repo, 'add','--',*paths)
    # --only never includes unrelated staged work; supports interrupted retries.
    changes = git(repo,'status','--porcelain','--',*paths)
    if changes:
        git(repo,'commit','--only','-m',subject,'--',*paths)
    return git(repo,'rev-parse','HEAD')


def run_dir(repo, ident):
    if not isinstance(ident,str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,127}',ident):
        raise ValueError('unsafe run id')
    path = repo / 'runs' / ident
    if path.resolve() != path:
        raise ValueError('symlink run directory refused')
    return path


def finite_mean(value):
    return type(value) in (int,float) and math.isfinite(value) and value >= 0


def prior_verified_mean(repo):
    """Maximum exact valid score in committed HEAD; uncommitted evidence is invisible."""
    head = subprocess.run(['git','-C',str(repo),'rev-parse','--verify','-q','HEAD'],capture_output=True,text=True)
    if head.returncode == 1:
        return None
    head.check_returncode()
    tree = git(repo,'ls-tree','-r',head.stdout.strip(),'--','runs')
    best = None
    # Open each blob by immutable object ID, using one Git process even for large ledgers.
    with subprocess.Popen(['git','-C',str(repo),'cat-file','--batch'],stdin=subprocess.PIPE,stdout=subprocess.PIPE) as batch:
        for line in tree.splitlines():
            entry, path = line.split('\t',1)
            parts = path.split('/')
            if len(parts) != 3 or parts[0] != 'runs' or parts[2] != 'evidence.json':
                continue
            oid = entry.split()[-1]
            batch.stdin.write((oid+'\n').encode())
            batch.stdin.flush()
            header = batch.stdout.readline().split()
            if len(header) != 3 or header[1] != b'blob':
                raise ValueError('unreadable committed evidence blob')
            record = json.loads(batch.stdout.read(int(header[2])))
            if batch.stdout.read(1) != b'\n':
                raise ValueError('incomplete committed evidence blob')
            mean = record.get('score',{}).get('mean_exact_tps')
            if record.get('id') == parts[1] and record.get('validation',{}).get('valid') is True and finite_mean(mean):
                best = max(best,mean) if best is not None else mean
        batch.stdin.close()
    if batch.returncode:
        raise ValueError('unable to read committed evidence')
    return best


def plan(repo, source):
    value = pick(source, PLAN)
    for key in ('id','label','sessionKey','prompt'):
        if not isinstance(value.get(key),str) or not value[key]:
            raise ValueError('plan requires nonempty ' + key)
    for key, item in value.items():
        if item is not None and type(item) not in (str, int, float, bool):
            raise ValueError('plan fields must be scalar: ' + key)
    # Experiment is a human-readable description, never arbitrary nested metadata.
    if 'experiment' in value and not isinstance(value['experiment'],str):
        raise ValueError('experiment must be a string')
    if 'context_injection' in value and value['context_injection'] != 'never':
        raise ValueError('invalid workspace context injection mode')
    if 'workspace_agents_md' in value and (not isinstance(value['workspace_agents_md'],str)
            or not value['workspace_agents_md'].strip() or len(value['workspace_agents_md']) > 4000):
        raise ValueError('invalid workspace AGENTS.md text')
    path = run_dir(repo,value['id']) / 'plan.json'
    data = encode(value)
    if 'prior_verified_mean_tps' in value:
        prior = value['prior_verified_mean_tps']
        if prior is not None and not finite_mean(prior):
            raise ValueError('invalid prior verified score')
        if not path.exists() and prior != prior_verified_mean(repo):
            raise ValueError('prior verified score differs from the committed leaderboard')
    if path.exists() and path.read_bytes() != data:
        raise ValueError('existing plan is immutable')
    atomic(path,data)
    return commit(repo,[path],'Plan benchmark ' + value['id'])


VIDEOS = ('original.mp4','demo.mp4')
UUID = re.compile(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}')
MEDIA_NAMES = VIDEOS + ('final.png',)
ARCHIVE_NAMES = MEDIA_NAMES + ('viewport-evidence.json',)
MEDIA_ERRORS = (ValueError, KeyError, TypeError, OSError, subprocess.CalledProcessError)


def captured_file(directory, name):
    path = directory / name
    if not path.is_file() or path.is_symlink():
        raise ValueError(name + ' missing or not a regular recording file')
    return path


def read_capture_file(path):
    details = {}
    if path.suffix == '.mp4':
        output = subprocess.check_output(['ffprobe','-v','error','-show_entries',
            'format=duration:stream=codec_type,codec_name,width,height','-of','json',str(path)],stderr=subprocess.PIPE)
        probe = json.loads(output)
        duration = float(probe['format']['duration'])
        if not math.isfinite(duration) or duration <= 0 or not any(stream.get('codec_type') == 'video' and stream.get('width',0)>0 and stream.get('height',0)>0 for stream in probe.get('streams',[])):
            raise ValueError('unplayable video')
        if path.name == 'demo.mp4' and duration > 60.0:
            raise ValueError('demo exceeds 60 seconds')
        details['ffprobe'] = probe
    blob = path.read_bytes()
    if path.suffix == '.png' and (len(blob) < 33 or not blob.startswith(b'\x89PNG\r\n\x1a\n')):
        raise ValueError('invalid PNG screenshot')
    return blob, dict(details, sha256=sha(blob), bytes=len(blob))


def viewport_proof(directory, rounded, verified_urls, summary):
    source = captured_file(directory, 'viewport-evidence.json')
    if source.stat().st_size > 32768:
        raise ValueError('viewport proof exceeds bounded size')
    proof = read(source)
    if not isinstance(proof,dict) or proof.get('schema_version') != 1 or proof.get('verified') is not True:
        raise ValueError('viewport proof not verified')
    original_duration = float(summary['original.mp4']['ffprobe']['format']['duration'])
    demo_duration = float(summary['demo.mp4']['ffprobe']['format']['duration'])
    if demo_duration > 55:
        raise ValueError('viewport proof demo exceeds 55 seconds')
    def number(value):
        if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
            raise ValueError('invalid viewport offset')
        return value
    finished = number(proof.get('finishSeconds'))
    start = number(proof.get('demoStartSeconds'))
    if finished > original_duration or start > original_duration:
        raise ValueError('viewport proof exceeds original')
    fields = ('originalFromSeconds','originalToSeconds','clipFromSeconds','clipToSeconds')
    def interval(item, minimum):
        if not isinstance(item, dict):
            raise ValueError('invalid viewport interval')
        clean = {key:number(item.get(key)) for key in fields}
        for key in ('firstFrameSha256','lastFrameSha256'):
            value = item.get(key)
            if not isinstance(value,str) or not re.fullmatch(r'[0-9a-f]{64}',value):
                raise ValueError('missing captured-frame SHA256')
            clean[key] = value
        if (clean['originalFromSeconds'] < finished or clean['originalToSeconds'] > original_duration + 0.05
                or clean['clipToSeconds'] > demo_duration or clean['clipToSeconds'] - clean['clipFromSeconds'] < minimum - 1e-6
                or abs(clean['originalFromSeconds'] - start - clean['clipFromSeconds']) > 1e-6
                or abs(clean['originalToSeconds'] - start - clean['clipToSeconds']) > 1e-6):
            raise ValueError('viewport interval outside final clip or post-finish hold')
        return clean
    score = proof.get('score',{})
    if not isinstance(score,dict) or score.get('mean') != rounded:
        raise ValueError('viewport proof score mismatch')
    score = dict(interval(score,4),mean=rounded)
    links = proof.get('links')
    if not isinstance(links,list) or len(links) != 5 or len(verified_urls) != 5:
        raise ValueError('viewport proof requires five verified links')
    clean_links = []
    for item in links:
        url = item.get('url') if isinstance(item,dict) else None
        if not isinstance(url,str) or len(url) > 2048 or not url.startswith(('https://','http://')) or url not in verified_urls:
            raise ValueError('viewport proof product mismatch')
        clean_links.append(dict(interval(item,1),url=url))
    if {item['url'] for item in clean_links} != verified_urls:
        raise ValueError('viewport proof contains duplicate links')
    clean = dict(schema_version=1,verified=True,finishSeconds=finished,demoStartSeconds=start,score=score,links=clean_links)
    blob = encode(clean)
    return blob, dict(sha256=sha(blob),bytes=len(blob),proof=clean)


def media(directory, raw, rounded, products):
    metadata = read(captured_file(directory, 'recording.json'))
    ready = read(captured_file(directory, 'ready.json'))
    if (metadata.get('run_id') != raw['id'] or metadata.get('sessionKey') != raw['sessionKey']
            or ready.get('sessionKey') != raw['sessionKey'] or metadata.get('rehearsal') is not False
            or ready.get('rehearsal') is not False or metadata.get('authless') is not True
            or ready.get('ready') is not True or ready.get('capture') != 'owned-local-viewport'):
        raise ValueError('live run identity, viewport or credential-free capture not attested')
    if metadata.get('discarded') is True:
        raise ValueError('recorder marked capture as discarded')

    summary, blobs, issues = {}, {}, []
    for name in MEDIA_NAMES:
        try:
            blobs[name], summary[name] = read_capture_file(captured_file(directory, name))
        except MEDIA_ERRORS:
            issues.append(name + ' missing or failed file validation')
    if not any(name in blobs for name in ('original.mp4','demo.mp4')):
        raise ValueError('no playable video available')

    # Safe to archive the available video even when the final screen or shopping result is incomplete.
    summary['attestation'] = pick(metadata,('run_id','full_run','authless','rehearsal','qualifying','provisional','final_ui_tps','reportedMean','readyAt'))
    if metadata.get('qualifying') is not True or metadata.get('full_run') is not True or metadata.get('provisional') is True:
        issues.append('recorder marked capture as partial or unverified')
    if metadata.get('final_ui_tps') != rounded:
        issues.append('final UI score unconfirmed')
    before_send = False
    try:
        ready_time = datetime.fromisoformat(ready['readyAt'].replace('Z','+00:00'))
        before_send = bool(ready_time.tzinfo and ready['readyAt'] == metadata.get('readyAt')
                           and ready_time.timestamp()*1000 <= raw['startedWall'])
    except (AttributeError, KeyError, TypeError, ValueError, OverflowError):
        pass
    ready_proof = pick(ready,('readyAt','sessionKey','capture'))
    ready_proof.update(before_send=before_send, blank_initial_score=ready.get('initialSummary') == '')
    summary['attestation']['capture_ready'] = ready_proof
    if not before_send or not ready_proof['blank_initial_score']:
        issues.append('capture before request on a blank session unconfirmed')
    if 'original.mp4' in summary and float(summary['original.mp4']['ffprobe']['format']['duration']) + 1 < raw['ended']['elapsedMs']/1000:
        issues.append('original video shorter than run')
    verified_urls = {product['url'] for product in products if product.get('verified')}
    shown_urls = metadata.get('urls')
    if (metadata.get('qualifying') is True and len(verified_urls) == 5 and isinstance(shown_urls,list)
            and len(shown_urls) == 5 and all(isinstance(url,str) for url in shown_urls) and set(shown_urls) == verified_urls):
        summary['attestation']['verified_product_urls_seen'] = shown_urls
    else:
        issues.append('five verified product links not confirmed on screen')
    if metadata.get('qualifying') is True or (directory / 'viewport-evidence.json').exists():
        try:
            blobs['viewport-evidence.json'], summary['viewport-evidence.json'] = viewport_proof(directory, rounded, verified_urls, summary)
        except MEDIA_ERRORS:
            issues.append('bounded post-finish viewport proof missing or invalid')
    return summary, blobs, issues


@contextmanager
def retention_lock(repo):
    lock = Path(git(repo,'rev-parse','--absolute-git-dir')) / 'benchmark-retention.lock'
    with lock.open('a+b') as handle:
        if os.name == 'nt':
            import msvcrt
            if not handle.tell():
                handle.write(b'0')
                handle.flush()
            handle.seek(0)
            msvcrt.locking(handle.fileno(),msvcrt.LK_LOCK,1)
        else:
            import fcntl
            fcntl.flock(handle,fcntl.LOCK_EX)
        yield


def retention_records(repo):
    # Read committed decisions; a failed commit can leave a half-updated working tree.
    rows = subprocess.run(['git','-C',str(repo),'grep','-l','-E',
        '"evidence_status"[[:space:]]*:[[:space:]]*"(complete|video_superseded|validation_rejected|provisional_video_retained|provisional_capture_required)"',
        'HEAD','--','runs/*/evidence.json'],capture_output=True,text=True)
    if rows.returncode == 1 or (rows.returncode and subprocess.run(
            ['git','-C',str(repo),'rev-parse','--verify','-q','HEAD'],capture_output=True).returncode):
        return []
    rows.check_returncode()
    records = []
    for ref in rows.stdout.splitlines():
        record = json.loads(git(repo,'show',ref))
        status, valid = record.get('evidence_status'), record.get('validation',{}).get('valid')
        if record.get('requires_video') and ((valid is True and status in ('complete','video_superseded'))
                or (valid is False and status in ('validation_rejected','provisional_video_retained','provisional_capture_required'))):
            if ref != 'HEAD:runs/'+record['id']+'/evidence.json' or not UUID.fullmatch(record['id']):
                raise ValueError('inconsistent retained recording identity')
            records.append(record)
    return records


def best_record(repo, records):
    complete = [r for r in records if r['evidence_status']=='complete']
    if not complete:
        return None
    top = max(r['score']['mean_exact_tps'] for r in complete)
    tied = [r for r in complete if r['score']['mean_exact_tps'] == top]
    if len(tied) == 1:
        return tied[0]
    # A formerly provisional record may have an earlier plan but a later first complete commit.
    paths = {f"runs/{r['id']}/evidence.json":r for r in tied}
    for rev in git(repo,'log','--reverse','--format=%H','HEAD','--',*paths).splitlines():
        changed = git(repo,'diff-tree','--root','--no-commit-id','--name-only','-r',rev,'--',*paths).splitlines()
        for name in changed:
            if json.loads(git(repo,'show',rev+':'+name)).get('evidence_status') == 'complete':
                return paths[name]
    raise ValueError('unable to determine first complete recording')


def capture_root(path, ident=None):
    if path is None:
        return None
    path = Path(path)
    if ident is not None:
        if path.name != ident or path.is_symlink():
            return None
        path = path.parent
    if path.name != 'capture' or path.is_symlink() or not path.is_dir():
        return None
    return path.resolve()


def matches_video(path, manifest):
    if path.is_symlink() or not path.is_file() or path.stat().st_size != manifest['bytes']:
        return False
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for block in iter(lambda:handle.read(1024*1024),b''):
            digest.update(block)
    return digest.hexdigest() == manifest['sha256']


def recorded_spool(root, record):
    if root:
        scratch = root/record['id']
        marker = scratch/'recording.json'
        if (scratch.is_dir() and not scratch.is_symlink() and marker.is_file() and not marker.is_symlink()
                and read(marker).get('run_id') == record['id']):
            return scratch
    return None


def verified_replay(repo, folder):
    ident = folder.name
    if not UUID.fullmatch(ident) or folder.is_symlink() or folder.parent.is_symlink() or not folder.is_dir():
        return None
    path, marker = folder/'postrun.mp4', folder/'postrun.json'
    if path.is_symlink() or not path.is_file() or marker.is_symlink() or not marker.is_file():
        return None
    if folder.parent == repo/'runs':
        relative = path.relative_to(repo).as_posix()
        if (git(repo,'ls-files','--',relative) or
                subprocess.run(['git','-C',str(repo),'cat-file','-e','HEAD:'+relative],capture_output=True).returncode == 0):
            return None
    try:
        if marker.stat().st_size > 65536:
            return None
        receipt = read(marker)
    except (OSError,ValueError):
        return None
    if (not isinstance(receipt,dict) or receipt.get('id',receipt.get('run_id')) != ident
            or receipt.get('run_id',ident) != ident or receipt.get('during_original_generation') is not False
            or type(receipt.get('displayed_mean_tps')) is not int or type(receipt.get('bytes')) is not int
            or receipt['bytes'] < 1 or not isinstance(receipt.get('sha256'),str)
            or not re.fullmatch('[0-9a-f]{64}',receipt['sha256'])):
        return None
    check = subprocess.run(['git','-C',str(repo),'show','HEAD:runs/'+ident+'/evidence.json'],capture_output=True)
    if check.returncode:
        return None
    run = json.loads(check.stdout)
    score = run.get('score',{})
    mean = score.get('mean_exact_tps')
    if (run.get('id') != ident or run.get('validation',{}).get('valid') is not True or not finite_mean(mean)
            or score.get('ui_rounded_tps') != receipt['displayed_mean_tps'] or round_rate(mean) != receipt['displayed_mean_tps']):
        return None
    return mean if matches_video(path,receipt) else None


def superseded_replays(repo, root, best):
    if not best:
        return []
    locations = [repo/'runs']
    if root:
        locations.append(root.parent/'record-hold')
    removals = []
    for location in locations:
        if not location.is_dir() or location.is_symlink():
            continue
        for path in location.glob('*/postrun.mp4'):
            mean = verified_replay(repo,path.parent)
            if mean is not None and (path.parent.name == best['id'] or mean < best['score']['mean_exact_tps']):
                removals.append(path)
    return removals


def cleanup_videos(repo, root, records, best):
    removals = []
    protect_winner = False
    for record in records:
        folder = run_dir(repo,record['id'])
        scratch = recorded_spool(root,record)
        # Remove only this run's spool duplicates for the winner. Failed and superseded
        # runs may also have copies left in the local archive after an interrupted finish.
        locations = [] if record['evidence_status'] == 'complete' else [folder]
        if scratch:
            locations.append(scratch)
        for location in locations:
            for name in VIDEOS:
                manifest = record.get('media',{}).get(name)
                path = location/name
                if not manifest or (not path.exists() and not path.is_symlink()):
                    continue
                if not matches_video(path,manifest):
                    print('Preserved a local file differing from its recorded fingerprint: '+record['id']+'/'+name,file=sys.stderr)
                    continue
                if record['evidence_status'] == 'complete' and not (folder/name).exists():
                    atomic(folder/name,path.read_bytes())
                protect_winner |= record['evidence_status'] in ('complete','video_superseded')
                removals.append(path)
    replays = superseded_replays(repo,root,best)
    if protect_winner or replays:
        if not best or not all(matches_video(run_dir(repo,best['id'])/n,best['media'][n]) for n in VIDEOS):
            raise ValueError('retained winner video missing or damaged; preserved predecessors')
    for path in removals + replays:
        path.unlink(missing_ok=True)


def reconcile(repo, root=None):
    records = retention_records(repo)
    best = best_record(repo,records)
    changed = []
    for record in records:
        if not record['validation']['valid']:
            if record['evidence_status'] == 'validation_rejected':
                continue
            record['evidence_status'] = 'validation_rejected'
        elif (not best or record['id'] == best['id'] or
              (record.get('video_superseded_by') == best['id'] and record['evidence_status'] == 'video_superseded')):
            continue
        else:
            record.update(evidence_status='video_superseded',video_superseded_by=best['id'])
        path = run_dir(repo,record['id'])/'evidence.json'
        atomic(path,encode(record))
        changed.append(path)
    if changed:
        commit(repo,[*changed,write_index(repo)],'Reconcile verified video retention')
    cleanup_videos(repo,root,records,best)
    # A detached local replay may arrive or be pruned between ordinary run commits.
    if any((repo/'runs').glob('*/postrun.json')):
        commit(repo,[write_index(repo)],'Update local post-run recording links')
    return best


def finish(repo, args):
    with retention_lock(repo):
        return finish_locked(repo,args)


def finish_locked(repo, args):

    raw_bytes = Path(args.raw).read_bytes()
    raw, validation = json.loads(raw_bytes), read(args.validation)
    ident = raw['id']
    dest = run_dir(repo,ident)
    if validation.get('run_id') != ident or validation.get('input_sha256') != sha(raw_bytes):
        raise ValueError('validation run identity or exact private raw SHA mismatch')
    existing = dest / 'evidence.json'
    root = capture_root(args.media_dir,ident)
    incumbent = reconcile(repo,root)
    if existing.exists():
        previous = read(existing)
        if previous.get('private_raw_sha256') != sha(raw_bytes):
            raise ValueError('run already bound to different raw bytes')
        if (previous.get('evidence_status') in ('video_superseded','validation_rejected')
                and previous.get('requires_video')) or (previous.get('evidence_status') == 'complete'
                and all(matches_video(dest/n,previous['media'][n]) for n in VIDEOS)):
            # A successful finish deliberately removes the original spool, including after recovery.
            extra = [dest/name for name in ('final.png','viewport-evidence.json') if name in previous.get('media',{})]
            commit(repo,[existing,write_index(repo),*extra],'Record benchmark '+ident)
            reconcile(repo,root)
            return {'commit':git(repo,'rev-parse','HEAD'),'run_id':ident,'evidence_status':read(existing)['evidence_status'],'path':str(existing)}
    plan_path = dest / 'plan.json'
    if not plan_path.exists():
        if not args.historical:
            raise ValueError('commit plan before the network run (or explicitly mark historical)')
        plan(repo,raw)
    planned = read(plan_path)
    if planned['sessionKey'] != raw.get('sessionKey') or planned['prompt'] != raw.get('prompt'):
        raise ValueError('raw inputs do not match committed plan')
    for setting in ('top_p','max_completion_tokens','video_threshold_tps'):
        if setting in planned and planned[setting] != raw.get(setting):
            raise ValueError(f'raw {setting} does not match committed plan')
    prior = raw.get('prior_verified_mean_tps')
    if (('prior_verified_mean_tps' in planned) != ('prior_verified_mean_tps' in raw)
            or (prior is not None and not finite_mean(prior)) or planned.get('prior_verified_mean_tps') != prior):
        raise ValueError('raw prior_verified_mean_tps does not match committed plan')
    if planned.get('context_injection') != raw.get('context_injection'):
        raise ValueError('raw context_injection does not match committed plan')
    if planned.get('workspace_agents_md') != raw.get('workspace_agents_md'):
        raise ValueError('raw workspace_agents_md does not match committed plan')
    plan_commit = git(repo,'log','-1','--format=%H','--',str(plan_path.relative_to(repo)))
    if not plan_commit or git(repo,'status','--porcelain','--',str(plan_path.relative_to(repo))):
        raise ValueError('plan is not committed cleanly')
    calls = []
    for index,m in enumerate(raw['history']['messages']):
        if m.get('role') != 'assistant' or m.get('__openclaw',{}).get('runId') != ident:
            continue
        call = pick(m,('provider','model','responseId','timestamp','stopReason','status','retryCount'))
        call['message_index'] = index
        call['serverGeneration'] = pick(m.get('serverGeneration',{}),('completionMs','outputTokens'))
        if isinstance(m.get('usage'),dict):
            call['usage'] = pick(m['usage'],('input','output','cacheRead','cacheWrite','totalTokens'))
        call['tool_inputs'] = []
        for part in m.get('content',[]) if isinstance(m.get('content'),list) else []:
            if part.get('type') == 'toolCall':
                arg = part.get('arguments',{})
                call['tool_inputs'].append({'id':part.get('id'),'name':part.get('name'),'arguments':pick(arg,('id','url','extractMode','maxChars')), 'args':pick(arg.get('args',{}),('url','extractMode','maxChars'))})
        calls.append(call)
    rates = []
    for call in calls:
        g = call['serverGeneration']
        ms, tokens = g.get('completionMs'),g.get('outputTokens')
        if type(ms) not in (int,float) or type(tokens) not in (int,float) or not math.isfinite(ms) or not math.isfinite(tokens) or ms <= 0 or tokens < 1:
            call['timed_sample'] = False
            continue
        call['timed_sample'] = True
        rates.append(call_rate(tokens, ms))
    if not rates and validation.get('valid') is not False:
        raise ValueError('unscored run requires rejected validation')
    mean = mean_rate(rates) if rates else None
    rounded = round_rate(mean) if mean is not None else None
    reported = validation.get('score',{})
    if (mean is not None and not math.isclose(mean,reported.get('mean_exact_tps',-1),rel_tol=1e-10)) or (mean is None and reported.get('mean_exact_tps') is not None) or reported.get('ui_rounded_tps') != rounded:
        raise ValueError('validator score differs from raw provider metric')
    video_threshold = planned.get('video_threshold_tps')
    if video_threshold is None:
        # Legacy plans inherit the benchmark in force when they were committed.
        video_threshold = json.loads(git(repo,'show',plan_commit+':benchmark.json'))['video_threshold_displayed_mean_inclusive']
    if type(video_threshold) is not int or video_threshold < 1:
        raise ValueError('Invalid displayed mean video threshold')
    qualifying = recording_required(mean,rounded,validation.get('valid') is True,video_threshold,planned)
    record = {'schema_version':1,'id':ident,'historical':args.historical,'plan_commit':plan_commit,'private_raw_sha256':sha(raw_bytes),'private_raw_bytes':len(raw_bytes),'startedWall':raw.get('startedWall'),'ended':pick(raw.get('ended',{}),('elapsedMs','terminal','time')),'calls':calls,'score':{'mean_exact_tps':mean,'ui_rounded_tps':rounded,'official_patch_sha256':reported.get('official_patch_sha256')},'validation':pick(validation,('valid','status','target_met','reject_reasons','target_reasons')),'retail_sources':[pick(s,SOURCE) for s in validation.get('retail_sources',[])],'products':[dict(pick(p,PRODUCT),product_evidence=pick(p.get('product_evidence',{}),('matching_schema_product','woocommerce_product_heading','woocommerce_sticky_product_price_and_cart'))) for p in validation.get('products',[])],'requires_video':qualifying}
    record['video_threshold_tps'] = video_threshold
    if 'prior_verified_mean_tps' in planned:
        record['prior_verified_mean_tps'] = planned['prior_verified_mean_tps']
    final_text = validation.get('final_text')
    if isinstance(final_text,str) and len(final_text) <= 32000:
        record['final_text'] = final_text
    files, blobs = [], {}
    if qualifying:
        try:
            if not args.media_dir:
                raise ValueError('media directory not supplied')
            record['media'], blobs, issues = media(Path(args.media_dir),raw,rounded,record['products'])
            if issues:
                record['evidence_status'] = 'provisional_video_retained'
                record['media_issues'] = issues
            else:
                record['evidence_status'] = 'complete' if validation.get('valid') is True else 'validation_rejected'
        except MEDIA_ERRORS as exc:
            record['evidence_status'] = 'provisional_capture_required'
            record['media_error'] = str(exc) if isinstance(exc,ValueError) and not isinstance(exc,json.JSONDecodeError) else 'media verification failed'
        if validation.get('valid') is False:
            record['evidence_status'] = 'validation_rejected'
            if not record.get('media'):
                record.pop('media_error',None)
    else:
        record['evidence_status'] = 'unscored_failed_run' if mean is None else ('below_threshold_recorded' if validation.get('valid') is True else 'validation_rejected')
    target = dest / 'evidence.json'
    if target.exists():
        previous = read(target)
        if previous.get('private_raw_sha256') != record['private_raw_sha256']:
            raise ValueError('run already bound to different raw bytes')
        if previous.get('evidence_status') == 'complete' and record['evidence_status'] != 'complete':
            raise ValueError('refusing to downgrade complete evidence')
        recovering = previous.get('evidence_status') == 'provisional_video_retained' and record['evidence_status'] == 'complete'
        for name in ARCHIVE_NAMES:
            if (not recovering and name in previous.get('media',{})
                    and previous['media'][name]['sha256'] != record.get('media',{}).get(name,{}).get('sha256')):
                raise ValueError('refusing to replace or drop archived ' + name)
    if (record['evidence_status'] == 'complete' and incumbent and incumbent['id'] != ident
            and incumbent['score']['mean_exact_tps'] >= mean):
        record.update(evidence_status='video_superseded',video_superseded_by=incumbent['id'])
    encoded = encode(record)
    for name, blob in blobs.items():
        if name in VIDEOS and record['evidence_status'] != 'complete':
            continue
        atomic(dest / name, blob)
        if name not in VIDEOS:
            files.append(dest / name)
    atomic(target,encoded)
    commit(repo,[target,write_index(repo),*files],'Record benchmark ' + ident)
    reconcile(repo,root)
    return {'commit':git(repo,'rev-parse','HEAD'),'run_id':ident,'evidence_status':read(target)['evidence_status'],'path':str(target)}


def write_index(repo):
    benchmark = read(repo/'benchmark.json')
    video_threshold = benchmark['video_threshold_displayed_mean_inclusive']
    recording_rule = f'현재 표시 평균 {video_threshold:,} tok/s 이상이면 녹화를 검증한다. '
    if benchmark.get('retain_new_verified_record') is True:
        recording_rule += '검증된 공식 평균이 종전 최고 기록을 갱신하면 기준 미만이어도 보관한다. '
    entries = []
    for evidence in (repo / 'runs').glob('*/evidence.json'):
        entry = read(evidence)
        ident = entry['id']
        plan_data = read(evidence.parent / 'plan.json')
        entries.append((entry.get('startedWall') or 0, ident, plan_data, entry))
    entries.sort(reverse=True)
    lines = [
        '# 쇼핑 바운티 실행 기록', '',
        '각 실행 ID를 열면 Git 계획 커밋, Cerebras가 반환한 출력 토큰 수와 생성 시간, 판매처 조회 결과를 확인할 수 있다. '
        + recording_rule + '최고 기록의 원본과 60초 이하 영상 한 쌍을 로컬에 보관한다. 실행별 측정값과 보관했던 영상 해시는 Git에서 확인할 수 있다.', '',
        '| 실행 | 요청 | 공식 평균 (tok/s) | 상품 검증 | 영상 |', '|---|---|---:|---|---|']
    for _, ident, plan_data, item in entries:
        score = item.get('score', {}).get('ui_rounded_tps')
        page_count = sum(1 for product in item['products'] if product.get('verified'))
        available = item.get('media',{})
        links = [f'[{label}](runs/{ident}/{name})' for name,label in (('original.mp4','원본'),('demo.mp4','60초 이내')) if name in available]
        if item.get('evidence_status') == 'video_superseded':
            winner = item['video_superseded_by']
            movie = f'해시 보존 · [보관 중인 최고 기록](runs/{winner}/evidence.json)'
        elif item.get('evidence_status') == 'complete' and links:
            movie = ' · '.join(links) + ' · 로컬 보관'
        elif item.get('evidence_status') == 'provisional_video_retained':
            movie = '검증 대기 · 촬영 원본은 복구용 폴더에 보관'
        elif item.get('requires_video') and item.get('evidence_status') == 'validation_rejected':
            movie = '상품 검증 미통과 · 영상 미보관'
        else:
            movie = '확인 필요' if item.get('requires_video') else '기준 미만' if score is not None else '미측정'
        if verified_replay(repo,repo/'runs'/ident) is not None:
            movie += f' · [사후 녹화](runs/{ident}/postrun.mp4)'
        if item.get('historical') and (repo / 'runs' / ident / 'historical-ui.jpg').is_file():
            movie += f' · [당시 화면](runs/{ident}/historical-ui.jpg)'
        label = str(plan_data.get('label', ident[:8])).replace('|',' ').replace('\n',' ')
        provenance = ' · 소급' if item.get('historical') else ''
        verified = f'{page_count}/5' if item['validation'].get('valid') else f'{page_count}/5 · 검증 미통과'
        lines.append(f"| [{label}](runs/{ident}/evidence.json){provenance} | [요청문](runs/{ident}/plan.json) | {score if score is not None else '미측정'} | {verified} | {movie} |")
    target = repo / 'RESULTS.md'
    atomic(target, ('\n'.join(lines)+'\n').encode())
    return target


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command',required=True)
    p = sub.add_parser('plan'); p.add_argument('--repo',required=True); p.add_argument('--plan',required=True)
    p = sub.add_parser('finish'); p.add_argument('--repo',required=True); p.add_argument('--raw',required=True); p.add_argument('--validation',required=True); p.add_argument('--media-dir'); p.add_argument('--historical',action='store_true')
    p = sub.add_parser('maintain'); p.add_argument('--repo',required=True); p.add_argument('--capture-root')
    args = parser.parse_args()
    try:
        repo = Path(args.repo).resolve()
        if Path(git(repo,'rev-parse','--show-toplevel')).resolve() != repo:
            raise ValueError('--repo must be Git root')
        if args.command == 'maintain':
            root = capture_root(args.capture_root)
            if args.capture_root and root is None:
                raise ValueError('--capture-root must name the dedicated capture directory')
            with retention_lock(repo):
                best = reconcile(repo,root)
            result = {'best_run_id':best['id'] if best else None,'commit':git(repo,'rev-parse','HEAD')}
        else:
            result = {'commit':plan(repo,read(args.plan)),'status':'plan_committed'} if args.command == 'plan' else finish(repo,args)
        print(json.dumps(result,ensure_ascii=False))
        return 0
    except (ValueError,KeyError,TypeError,OSError,subprocess.CalledProcessError) as exc:
        print(json.dumps({'error':type(exc).__name__,'message':str(exc) if not isinstance(exc,subprocess.CalledProcessError) else 'Git or media command failed'}),file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
