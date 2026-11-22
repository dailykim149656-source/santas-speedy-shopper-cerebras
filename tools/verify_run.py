#!/usr/bin/env python3
"""Read a local Git clone and verify a benchmark record without network access.

Example: python3 tools/verify_run.py 694ee975-2931-4496-af62-38fc6650d6a6
Use --raw FILE for the private trace digest or --prompt for a fresh rerun prompt.
Exit 0 means the archive is internally consistent. Its result field reports the outcome.
"""
import argparse
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
import re
import secrets
import subprocess
import sys

sys.dont_write_bytecode = True
from validate import MODEL, answer_links, finite, identity, merchant

VIEWPORT = 'viewport-evidence.json'
MEDIA = ('original.mp4', 'demo.mp4', 'final.png', VIEWPORT)
SHA256 = re.compile('[a-f0-9]{64}')


def require(ok, message):
    if not ok:
        raise ValueError(message)


def git(repo, *args, check=True):
    return subprocess.run(['git','--no-optional-locks','-C',str(repo),*args],check=check,
                          stdout=subprocess.PIPE,stderr=subprocess.PIPE)


def digest(path):
    with path.open('rb') as source:
        result = hashlib.sha256()
        for chunk in iter(lambda: source.read(1024 * 1024), b''):
            result.update(chunk)
        return result.hexdigest()


def committed(repo, path):
    name = path.relative_to(repo).as_posix()
    require(path.is_file() and not path.is_symlink(), 'missing or symlinked archive file: ' + name)
    git(repo, 'cat-file', '-e', 'HEAD:' + name)
    require(git(repo,'diff','--quiet','--no-ext-diff','HEAD','--',name,check=False).returncode == 0,
            'working copy differs from committed version: ' + name)
    return name


def samples(calls, valid):
    rates, fetches = [], {}
    for call in calls:
        generation = call['serverGeneration']
        tokens, ms = generation.get('outputTokens'), generation.get('completionMs')
        timed = finite(ms) and ms > 0 and finite(tokens) and tokens >= 1
        require(call['timed_sample'] is timed, 'incorrect timing inclusion flag')
        if timed:
            rates.append(tokens * 1000 / ms)
        if valid:
            require(timed and call.get('provider') == 'cerebras' and call.get('model') == MODEL
                    and call.get('responseId') and call.get('stopReason') in ('stop','toolUse'),
                    'invalid provider, model or response identity on a validated run')
        for tool in call['tool_inputs']:
            if tool['name'] == 'web_fetch':
                fetches[tool['id']] = tool['arguments'].get('url')
            elif tool['name'] == 'tool_call' and tool['arguments'].get('id') in ('web_fetch','openclaw:core:web_fetch'):
                fetches[tool['id']] = tool['args'].get('url')
    return rates, fetches


def check_products(run, fetches):
    products = run['products']
    urls, misleading = answer_links(run['final_text'])
    require(not misleading and len(products) == len(urls) == 5 and len(set(urls)) == 5
            and set(urls) == {p['url'] for p in products}, 'five distinct final product links do not match')
    sources = {s['tool_call_id']:s for s in run['retail_sources'] if s.get('accepted') is True}
    for product in products:
        url = product['url']
        source_id = product['source_tool_call_id']
        source = sources.get(source_id, {})
        require(merchant(url,product=True) and merchant(source.get('url')) and fetches.get(source_id) == source.get('url')
                and identity(source['url'])[0] == identity(url)[0] and url in source.get('products',[])
                and source.get('status') == 200 and source.get('cached') is False, 'product lacks matching fresh catalog call')
        fetched = datetime.fromisoformat(source['fetched_at'].replace('Z','+00:00')).timestamp() * 1000
        require(run['startedWall'] <= fetched <= run['ended']['time'], 'catalog timestamp falls outside the run')
        require(product['verified'] is True and not product['reasons'] and product['http'] == 200 and product['html_bytes_read'] > 0
                and SHA256.fullmatch(product['html_sha256']) and product['title_matches_catalog'] is True
                and any(product['product_evidence'].values()) and all(merchant(product[k],product=True)
                and identity(product[k]) == identity(url) for k in ('canonical','final_url')), 'product page check differs from catalog')


def check_viewport(directory, media, ui, urls):
    path = directory/VIEWPORT
    require(path.stat().st_size <= 32768, 'viewport proof exceeds size limit')
    proof = json.loads(path.read_bytes())
    require(proof == media[VIEWPORT]['proof'] and proof.get('schema_version') == 1
            and proof.get('verified') is True, 'viewport proof differs from its manifest')
    original = float(media['original.mp4']['ffprobe']['format']['duration'])
    demo = float(media['demo.mp4']['ffprobe']['format']['duration'])
    finish, start = proof['finishSeconds'], proof['demoStartSeconds']
    require(finite(original) and original > 0 and finite(demo) and 0 < demo <= 55
            and all(finite(t) and 0 <= t <= original for t in (finish,start)), 'invalid viewport or clip duration')
    score, links = proof['score'], proof['links']
    require(score['mean'] == ui and len(links) == len(urls) == 5 and {entry['url'] for entry in links} == urls,
            'viewport evidence differs from displayed mean or five verified product links')
    for item, minimum in [(score,4)] + [(entry,1) for entry in links]:
        first, last, clip_first, clip_last = (item[key] for key in (
            'originalFromSeconds','originalToSeconds','clipFromSeconds','clipToSeconds'))
        require(all(finite(t) and t >= 0 for t in (first,last,clip_first,clip_last))
                and first >= finish and last <= original+0.05 and clip_last <= demo
                and clip_last-clip_first >= minimum-1e-6 and abs(first-start-clip_first) <= 1e-6
                and abs(last-start-clip_last) <= 1e-6, 'viewport interval fails clip bounds or visible hold')
        require(all(isinstance(item[k],str) and SHA256.fullmatch(item[k]) for k in ('firstFrameSha256','lastFrameSha256')),
                'invalid captured-frame digest')

def verify(repo, ident, plan, raw):
    directory = repo/'runs'/ident
    evidence = directory/'evidence.json'
    name = evidence.relative_to(repo).as_posix()
    if not evidence.exists() and git(repo,'cat-file','-e','HEAD:'+name,check=False).returncode:
        require(raw is None,'a pending run has no committed raw digest')
        return {'result':'pending_plan','run_id':ident}
    committed(repo,evidence)
    run = json.loads(evidence.read_bytes())
    require(run['id'] == ident, 'evidence run ID mismatch')
    commit = run['plan_commit']
    require(re.fullmatch('[a-f0-9]{40}',commit), 'invalid plan commit')
    git(repo,'merge-base','--is-ancestor',commit,'HEAD')
    plan_name = f'runs/{ident}/plan.json'
    require(git(repo,'show',commit+':'+plan_name).stdout == (repo/plan_name).read_bytes(), 'plan differs from plan commit')
    require(git(repo,'cat-file','-e',commit+':'+name,check=False).returncode != 0,'result already present in plan commit')

    valid = run['validation']['valid']
    require(isinstance(valid,bool), 'invalid validation flag')
    rates, fetches = samples(run['calls'],valid)
    mean = sum(rates) / len(rates) if rates else None
    ui = math.floor(mean + 0.5) if mean is not None else None
    recorded = run['score']
    require((mean is None and recorded['mean_exact_tps'] is None) or (mean is not None and
            math.isclose(mean,recorded['mean_exact_tps'],rel_tol=1e-12)), 'recorded mean differs from provider timings')
    require(recorded['ui_rounded_tps'] == ui, 'rounded UI score mismatch')
    benchmark = repo/'benchmark.json'
    committed(repo,benchmark)
    config = json.loads(benchmark.read_bytes())
    require(recorded['official_patch_sha256'] == config['patch_sha256'], 'patch fingerprint mismatch')
    if valid:
        require(rates and run['ended']['terminal'] == 'final' and not run['validation']['reject_reasons'], 'validated run incomplete')
        check_products(run,fetches)
    target = bool(valid and ui is not None and mean > 2000 and ui > 2000)
    require(run['validation']['target_met'] is target,'target claim differs from measurements')
    # Earlier records used the original threshold without an explicit field.
    video_threshold = run.get('video_threshold_tps',1700)
    require(type(video_threshold) is int and video_threshold > 0,'invalid recorded video threshold')
    require(plan.get('video_threshold_tps',video_threshold) == video_threshold,'video threshold differs from the committed plan')
    threshold = ui is not None and ui >= video_threshold
    require(run['requires_video'] is threshold,'video threshold mismatch')
    state = run['evidence_status']
    superseded = state == 'video_superseded'
    if superseded:
        replacement = run.get('video_superseded_by')
        require(valid and isinstance(replacement,str) and replacement != ident
                and re.fullmatch(r'[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}',replacement),
                'superseded video lacks a valid replacement run ID')
    media = run.get('media',{})
    checked_media = []
    for asset in MEDIA:
        if asset in media:
            if asset in MEDIA[:2] and state in ('video_superseded','provisional_video_retained','validation_rejected'):
                continue
            path = directory/asset
            # Videos are local, with bytes bound to their committed SHA-256 receipt.
            if asset in MEDIA[:2]:
                require(path.is_file() and not path.is_symlink(),'missing or symlinked local video: '+asset)
            else:
                committed(repo,path)
            require(path.stat().st_size == media[asset]['bytes'] and digest(path) == media[asset]['sha256'], 'media digest mismatch: '+asset)
            checked_media.append(asset)
    require(set(media).issubset((*MEDIA,'attestation')),'unrecognized archived media')
    if VIEWPORT in media:
        check_viewport(directory,media,ui,{p['url'] for p in run['products'] if p.get('verified')})
    allowed = ({'complete','video_superseded','provisional_video_retained','provisional_capture_required','validation_rejected'} if threshold else
               {'unscored_failed_run'} if ui is None else {'below_threshold_recorded'} if valid else {'validation_rejected'})
    require(state in allowed,'evidence status inconsistent with result')
    if state == 'validation_rejected':
        require(not valid,'a validated shopping run is marked rejected')
    if state == 'provisional_video_retained':
        attestation = media['attestation']
        require(any(name in media for name in MEDIA[:2]) and attestation['run_id'] == ident
                and attestation['authless'] is True and attestation['rehearsal'] is False
                and attestation['capture_ready']['sessionKey'] == plan['sessionKey'],
                'retained provisional video is missing or belongs to a different run')
    if state == 'complete':
        attestation = media['attestation']
        ready = attestation['capture_ready']
        require(valid and all(asset in media for asset in MEDIA) and attestation['run_id'] == ident and attestation['full_run'] is True
                and attestation['authless'] is True and attestation['rehearsal'] is False and attestation['final_ui_tps'] == ui
                and attestation.get('qualifying') is True and attestation.get('provisional') is not True
                and ready['capture'] == 'owned-local-viewport' and ready['sessionKey'] == plan['sessionKey'] and ready['blank_initial_score'] is True
                and ready['before_send'] is True and ready['readyAt'] == attestation['readyAt']
                and datetime.fromisoformat(ready['readyAt'].replace('Z','+00:00')).timestamp()*1000 <= run['startedWall']
                and sorted(attestation['verified_product_urls_seen']) == sorted(p['url'] for p in run['products']),
                'complete media lacks matching score, links, pre-capture or run identity')
    require(SHA256.fullmatch(run['private_raw_sha256']), 'malformed raw trace digest')
    if raw is not None:
        require(raw.stat().st_size == run['private_raw_bytes'] and digest(raw) == run['private_raw_sha256'],'private raw trace digest mismatch')
    result = ('rejected' if not valid else 'video_superseded' if superseded else 'pending_video' if threshold and state != 'complete'
              else 'target_verified' if target else 'below_target')
    return dict(result=result,run_id=ident,historical=run['historical'],plan_commit=commit,samples=len(rates),mean=mean,
                displayed_tps=ui,verified_products=sum(p.get('verified') is True for p in run['products']),
                evidence_status=state,checked_media=checked_media,raw_digest_checked=raw is not None)


def main():
    parser = argparse.ArgumentParser(description=__doc__,formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('run_id')
    parser.add_argument('--repo',type=Path,default=Path(__file__).resolve().parents[1])
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--raw',type=Path)
    mode.add_argument('--prompt',action='store_true',help='print the committed prompt with a fresh shared _run query value')
    args = parser.parse_args()
    try:
        repo, ident = args.repo.resolve(), args.run_id
        require(re.fullmatch('[A-Za-z0-9][A-Za-z0-9_.-]{0,127}',ident),'unsafe run ID')
        path = repo/'runs'/ident/'plan.json'
        committed(repo,path)
        plan = json.loads(path.read_bytes())
        require(plan['id'] == ident,'plan run ID mismatch')
        if args.prompt:
            name = path.relative_to(repo).as_posix()
            initial = git(repo,'log','-1','--diff-filter=A','--format=%H','--',name).stdout.decode().strip()
            require(initial and git(repo,'show',initial+':'+name).stdout == path.read_bytes(),'prompt differs from initial plan')
            pattern = re.compile(r'([?&]_run=)([a-fA-F0-9]{8})(?=[&#\s]|$)')
            existing = {match[2].lower() for match in pattern.finditer(plan['prompt'])}
            require(existing,'no recorded eight-digit _run query value to refresh')
            nonce = secrets.token_hex(4)
            while nonce in existing:
                nonce = secrets.token_hex(4)
            sys.stdout.write(pattern.sub(lambda m:m[1]+nonce,plan['prompt']))
        else:
            print(json.dumps(verify(repo,ident,plan,args.raw),ensure_ascii=False,indent=2))
    except (ValueError, TypeError, KeyError, AttributeError, OSError, subprocess.CalledProcessError) as exc:
        parser.exit(2,'Verification failed: ' + str(exc) + '\n')


if __name__ == '__main__':
    main()
