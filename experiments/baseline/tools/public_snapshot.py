#!/usr/bin/env python3
"""Export a frozen local commit into a separate, reviewable public Git history.

No network operations. Source Git is read-only. Only destination commits are made;
public plan/result dates represent export time; source mappings preserve chronology.
"""
import argparse
from datetime import datetime, timezone
import getpass
import hashlib
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
from urllib.parse import urlsplit

FILES = {'tools/verify_run.py':'tools/verify_run.py', 'tools/validate.py':'tools/validate.py',
         'tools/scoring.py':'tools/scoring.py', 'tools/variants.py':'tools/variants.py',
         'benchmark.json':'benchmark.json', 'REVIEW.md':'README.md'}
DASHBOARDS = ('review-assets/c1-dashboard', 'review-assets/d0013-dashboard', 'review-assets/d0024-dashboard')
OPTIONAL = ('tools/replay_run.py', 'tools/research_report.py',
            *(base + suffix for base in DASHBOARDS for suffix in ('.png', '.json')))
PLAN = ('id','label','sessionKey','variant','thinking','temperature','top_p','max_completion_tokens',
        'video_threshold_tps','prior_verified_mean_tps','context_injection','workspace_agents_md','prompt','experiment',
        'official_commit','official_patch_sha256','benchmark_sha256','organizer_reproduction_request')
PRODUCT = ('url','catalog_name','catalog_price','source_tool_call_id','verified','reasons','http','final_url','html_bytes_read','html_sha256','checked_at','canonical','merchant','title','title_matches_catalog','password_protected')
SOURCE = ('tool_call_id','url','accepted','reasons','status','fetched_at','cached','products')
CALL = ('provider','model','responseId','timestamp','stopReason','message_index','timed_sample')
MEDIA = ('original.mp4','demo.mp4','final.png','viewport-evidence.json')
PUBLIC_HOSTS = {'mercantile.wordpress.org','raspberrypi.dk','aisynthesis.com','github.com','discord.com','inference-docs.cerebras.ai'}
SHA = re.compile(r'[0-9a-f]{40}')
UUID = r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}'
PRIVATE = re.compile(r'(?i)(?:file://\S+|(?<![\w:])/(?:Users|Volumes|private|tmp|home|var|etc|opt|Applications|Library)/[^\s\"<>]*|[A-Z]:\\[^\s\"]*|\b(?:localhost|127\.0\.0\.1|0\.0\.0\.0|[\w.-]+\.(?:local|internal|lan|localdomain)|10(?:\.\d{1,3}){3}|192\.168(?:\.\d{1,3}){2}|172\.(?:1[6-9]|2\d|3[01])(?:\.\d{1,3}){2})\b|bearer\s+[\w.-]{12,}|sk-[\w-]{12,}|(?:api[_-]?key|authorization|cookie)\s*[=:]\s*[^\s,;]{4,})')
URL = re.compile(r'https?://[^\s<>\]\)\"\']+')
IDENTITIES = {x for x in (getpass.getuser(), Path.home().name, socket.gethostname(), socket.gethostname().split('.')[0]) if len(x) >= 4}


def git(repo, *args, check=True):
    env = {k:v for k,v in os.environ.items() if not k.startswith('GIT_')}
    env.update(GIT_CONFIG_NOSYSTEM='1',GIT_CONFIG_GLOBAL=os.devnull,
               GIT_AUTHOR_NAME='Benchmark Public Export',GIT_AUTHOR_EMAIL='benchmark-export@users.noreply.github.com',
               GIT_COMMITTER_NAME='Benchmark Public Export',GIT_COMMITTER_EMAIL='benchmark-export@users.noreply.github.com')
    return subprocess.run(['git','--no-optional-locks','-c','core.hooksPath='+os.devnull,
                           '-c','commit.gpgsign=false','-C',str(repo),*args],env=env,check=check,
                          stdout=subprocess.PIPE,stderr=subprocess.PIPE)


def read_blob(repo, ref, name):
    return git(repo,'show',f'{ref}:{name}').stdout


def pick(obj, keys):
    return {k:obj[k] for k in keys if k in obj}


def encode(value):
    return (json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n').encode()


def scrub(value):
    if isinstance(value,dict):
        return {k:scrub(v) for k,v in value.items()}
    if isinstance(value,list):
        return [scrub(v) for v in value]
    if isinstance(value,str):
        value = PRIVATE.sub('[redacted private data]',value)
        for identity in sorted(IDENTITIES,key=len,reverse=True):
            value = re.sub(re.escape(identity),'[redacted identity]',value,flags=re.I)
        for match in list(URL.finditer(value))[::-1]:
            parsed = urlsplit(match.group())
            if parsed.hostname not in PUBLIC_HOSTS or parsed.username or parsed.password or parsed.port:
                value = value[:match.start()]+'[redacted non-public URL]'+value[match.end():]
        return value
    if value is None or type(value) in (bool,int,float):
        return value
    raise ValueError('unsupported public JSON value')


def checked_text(data, label):
    text = data.decode('utf8')
    if scrub(text) != text:
        raise ValueError('reviewed public file contains private or non-allowlisted content: '+label)
    return data


def sanitized_plan(value):
    result = scrub(pick(value,PLAN))
    if not re.fullmatch(UUID,result.get('id','')):
        raise ValueError('plan ID must be a UUID')
    for key in ('label','sessionKey','prompt'):
        if not isinstance(result.get(key),str):
            raise ValueError('plan requires '+key)
    return result


def sanitized_result(value):
    result = pick(value,('schema_version','id','historical','private_raw_sha256','private_raw_bytes','startedWall',
                         'video_threshold_tps','prior_verified_mean_tps','requires_video','final_text',
                         'evidence_status','video_superseded_by'))
    result['ended'] = pick(value.get('ended',{}),('elapsedMs','terminal','time'))
    result['score'] = pick(value.get('score',{}),('mean_exact_tps','ui_rounded_tps','official_patch_sha256'))
    result['validation'] = pick(value.get('validation',{}),('valid','status','target_met','reject_reasons','target_reasons'))
    result['calls'] = []
    for call in value.get('calls',[]):
        item = pick(call,CALL)
        usage = pick(call.get('usage',{}),('input','output','cacheRead','cacheWrite','totalTokens'))
        if usage:
            if any(type(v) not in (int,float) for v in usage.values()):
                raise ValueError('call usage must be numeric')
            item['usage'] = usage
        item['serverGeneration'] = pick(call.get('serverGeneration',{}),('completionMs','outputTokens'))
        item['tool_inputs'] = [dict(pick(tool,('id','name')),arguments=pick(tool.get('arguments',{}),('id','url')),args=pick(tool.get('args',{}),('url',))) for tool in call.get('tool_inputs',[])]
        result['calls'].append(item)
    result['retail_sources'] = [pick(item,SOURCE) for item in value.get('retail_sources',[])]
    result['products'] = [dict(pick(item,PRODUCT),product_evidence=pick(item.get('product_evidence',{}),('matching_schema_product','woocommerce_product_heading','woocommerce_sticky_product_price_and_cart'))) for item in value.get('products',[])]
    result = scrub(result)
    # Unreviewed viewport media is never copied, even if the private run is complete.
    withheld = []
    for name in MEDIA:
        meta = value.get('media',{}).get(name,{})
        if isinstance(meta,dict) and re.fullmatch(r'[a-f0-9]{64}',str(meta.get('sha256',''))):
            withheld.append(dict(name=name,sha256=meta['sha256'],bytes=meta.get('bytes')))
    if result.get('requires_video'):
        if result.get('evidence_status') in ('video_superseded','validation_rejected'):
            result.update(media={},media_withheld=withheld)
        else:
            result.update(evidence_status='provisional_capture_required',media={},media_error='media withheld pending review',media_withheld=withheld)
    elif withheld:
        result['media_withheld'] = withheld
    return result


def sanitized_preflight(value):
    result = scrub(pick(value,('schema_version','status','id','label','sessionKey','plan_commit',
                               'runner_sha256','private_sources_sha256','cause_class','sealed_at')))
    sources = result.get('private_sources_sha256')
    if (result.get('schema_version') != 1 or result.get('status') != 'aborted_before_send'
            or not re.fullmatch(UUID,result.get('id',''))
            or not SHA.fullmatch(result.get('plan_commit',''))
            or not re.fullmatch(r'[0-9a-f]{64}',result.get('runner_sha256',''))
            or not isinstance(sources,dict) or 'run.json' not in sources
            or any(name not in {'run.json','run.log','video.log','error.json','status.json'}
                   or not isinstance(digest,str) or not re.fullmatch(r'[0-9a-f]{64}',digest)
                   for name,digest in sources.items())):
        raise ValueError('invalid pre-send abort receipt')
    return result


def permitted(name):
    return name in set(FILES.values())|set(OPTIONAL)|{'RESULTS.md','RESEARCH.md'} or bool(re.fullmatch(r'runs/'+UUID+r'/(?:plan|evidence|preflight)\.json',name))


def commit_files(dest, files, message):
    git(dest,'add','--',*files)
    if git(dest,'diff','--cached','--quiet',check=False).returncode:
        git(dest,'commit','-m',message)
    return git(dest,'rev-parse','HEAD').stdout.decode().strip()


def write(dest,name,data):
    if not permitted(name):
        raise ValueError('public output path is not allowlisted')
    target = dest/name
    if target.is_symlink() or any(p.is_symlink() for p in target.parents if p != dest.parent):
        raise ValueError('symlink public destination refused')
    target.parent.mkdir(parents=True,exist_ok=True)
    target.write_bytes(data)


def snapshot(source,dest,ref):
    source,dest = source.resolve(),dest.resolve()
    if dest == source or source in dest.parents or dest in source.parents:
        raise ValueError('public destination must be separate from source')
    head = git(source,'rev-parse','--verify',ref+'^{commit}').stdout.decode().strip()
    names = git(source,'ls-tree','-r','--name-only',head).stdout.decode().splitlines()
    missing = set(FILES)-set(names)
    if missing:
        raise ValueError('frozen source is missing reviewed files: '+', '.join(sorted(missing)))
    prepared = {target:checked_text(read_blob(source,head,name),name) for name,target in FILES.items()}
    for name in OPTIONAL:
        if name in names:
            data = read_blob(source,head,name)
            if name.endswith('.png'):
                if not data.startswith(b'\x89PNG\r\n\x1a\n'):
                    raise ValueError('reviewed PNG is invalid')
            elif name.endswith('.json'):
                value = json.loads(data)
                if scrub(value) != value:
                    raise ValueError('reviewed asset metadata contains private content')
                checked_text(data,name)
            else:
                checked_text(data,name)
            prepared[name] = data
    reviewed_stills = {}
    for base in DASHBOARDS:
        if base+'.png' not in prepared and base+'.json' not in prepared:
            continue
        receipt = json.loads(prepared[base+'.json'])
        if hashlib.sha256(prepared[base+'.png']).hexdigest() != receipt['sha256']:
            raise ValueError('reviewed dashboard image digest mismatch')
        reviewed_stills[receipt['id']] = base+'.png'
    benchmark = json.loads(prepared['benchmark.json'])
    if scrub(benchmark) != benchmark:
        raise ValueError('benchmark contains private content')
    plans = []
    for name in sorted(names):
        match = re.fullmatch(r'runs/('+UUID+r')/plan\.json',name)
        if not match:
            continue
        ident = match[1]
        value = json.loads(read_blob(source,head,name))
        plan = sanitized_plan(value)
        if plan['id'] != ident:
            raise ValueError('plan path/ID mismatch')
        result_name = f'runs/{ident}/evidence.json'
        preflight_name = f'runs/{ident}/preflight.json'
        if result_name in names and preflight_name in names:
            raise ValueError('run has both scored evidence and a pre-send abort receipt')
        original = json.loads(read_blob(source,head,result_name)) if result_name in names else None
        original_preflight = json.loads(read_blob(source,head,preflight_name)) if preflight_name in names else None
        source_plan = (original or original_preflight or {}).get('plan_commit') or git(source,'log','-1','--diff-filter=A','--format=%H',head,'--',name).stdout.decode().strip()
        if not isinstance(source_plan,str) or not SHA.fullmatch(source_plan):
            raise ValueError('invalid source plan mapping')
        git(source,'merge-base','--is-ancestor',source_plan,head)
        if read_blob(source,source_plan,name) != read_blob(source,head,name):
            raise ValueError('source plan does not match its recorded plan commit')
        source_result = git(source,'log','-1','--format=%H',head,'--',result_name).stdout.decode().strip() if original else None
        source_preflight = git(source,'log','-1','--format=%H',head,'--',preflight_name).stdout.decode().strip() if original_preflight else None
        if original_preflight:
            if not SHA.fullmatch(source_preflight or ''):
                raise ValueError('invalid source pre-send abort mapping')
            git(source,'merge-base','--is-ancestor',source_preflight,head)
            if read_blob(source,source_preflight,preflight_name) != read_blob(source,head,preflight_name):
                raise ValueError('source pre-send abort receipt changed after its commit')
        result = sanitized_result(original) if original else None
        preflight = sanitized_preflight(original_preflight) if original_preflight else None
        if preflight and (preflight['id'] != ident or preflight.get('label') != plan.get('label')):
            raise ValueError('pre-send abort receipt path/plan identity mismatch')
        plan['source_plan_commit'] = source_plan
        plan['publication_timing'] = 'Public plan commit created at export time; use the source plan mapping for original chronology.'
        plans.append((ident,plan,result,preflight,source_plan,source_result,source_preflight))
    # Validate and sanitize every source payload before creating destination history.
    for _,plan,result,preflight,_,_,_ in plans:
        encode(plan)
        if result is not None:
            encode(result)
        if preflight is not None:
            encode(preflight)
    marker = dest/'.git/public-snapshot-state.json'
    if not (dest/'.git').exists():
        if dest.exists() and any(dest.iterdir()):
            raise ValueError('new public destination must be empty')
        dest.mkdir(parents=True,exist_ok=True)
        git(dest,'init','--initial-branch=main')
        marker.write_bytes(encode({'version':1,'first_export_at':datetime.now(timezone.utc).isoformat()}))
    if not marker.is_file() or marker.is_symlink():
        raise ValueError('destination is not managed by public_snapshot.py')
    state = json.loads(marker.read_bytes())
    if state.get('version') != 1:
        raise ValueError('unsupported public export state')
    if git(dest,'status','--porcelain').stdout:
        raise ValueError('destination has uncommitted changes; refusing to overwrite')
    current = git(dest,'ls-files').stdout.decode().splitlines()
    if any(not permitted(name) for name in current):
        raise ValueError('destination tracks a non-allowlisted file')
    lock = dest/'.git/public-snapshot.lock'
    fd = os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
    try:
        note = ('\n\n---\nPublic export provenance: this repository contains a sanitized export, not the original private Git history. '
                'Public plan/result commit dates are export dates; use source plan mappings for original chronology. '
                'Original source commit mappings and private trace digests are retained in JSON. '
                'Unreviewed media is withheld pending review.\n')
        prepared['README.md'] += note.encode()
        for name,data in prepared.items():
            write(dest,name,data)
        commit_files(dest,list(prepared),'Publish reviewed benchmark verifier and documentation')
        index = []
        for ident,plan,result,preflight,source_plan,source_result,source_preflight in plans:
            plan_name = f'runs/{ident}/plan.json'
            data = encode(plan)
            existing = git(dest,'cat-file','-e','HEAD:'+plan_name,check=False).returncode == 0
            if existing:
                if read_blob(dest,'HEAD',plan_name) != data:
                    raise ValueError('public plan is immutable: '+ident)
                public_plan = git(dest,'log','-1','--diff-filter=A','--format=%H','HEAD','--',plan_name).stdout.decode().strip()
            else:
                write(dest,plan_name,data)
                public_plan = commit_files(dest,[plan_name],'Export plan '+ident+' (export time)')
            if result is not None:
                result.update(plan_commit=public_plan,source_plan_commit=source_plan,source_result_commit=source_result,
                              publication_timing='Public result commit created at export time; use source mappings for original chronology.')
                result_name = f'runs/{ident}/evidence.json'
                write(dest,result_name,encode(result))
                commit_files(dest,[result_name],'Export result '+ident+' (media withheld when unreviewed)')
                check = subprocess.run([sys.executable,str(dest/'tools/verify_run.py'),ident,'--repo',str(dest)],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
                if check.returncode:
                    raise ValueError('exported verifier rejected '+ident+'; destination is local and must not be published')
                status = json.loads(check.stdout)['result']
                score = result.get('score',{}).get('ui_rounded_tps')
            elif preflight is not None:
                preflight.update(plan_commit=public_plan,source_plan_commit=source_plan,
                                 source_preflight_commit=source_preflight,
                                 publication_timing='Public pre-send abort commit created at export time; use source mappings for original chronology.')
                receipt_name = f'runs/{ident}/preflight.json'
                receipt_bytes = encode(preflight)
                if git(dest,'cat-file','-e','HEAD:'+receipt_name,check=False).returncode == 0:
                    if read_blob(dest,'HEAD',receipt_name) != receipt_bytes:
                        raise ValueError('public pre-send abort receipt is immutable: '+ident)
                else:
                    write(dest,receipt_name,receipt_bytes)
                    commit_files(dest,[receipt_name],'Export unsent preflight '+ident+' (export time)')
                status,score = 'aborted_before_send',None
            else:
                status,score = 'pending_plan',None
            index.append((ident,plan.get('label',ident),status,score,bool(result and result.get('requires_video'))))
        lines = ['# Results','', 'Public commits are created at export time; use source plan mappings for original chronology. Source history remains separate.', '', '| Run | Displayed TPS | Verification | Media |', '| --- | ---: | --- | --- |']
        for ident,label,status,score,withheld in sorted(index, key=lambda entry: entry[1], reverse=True):
            label = label.replace('|','\\|').replace('\n',' ')
            target = 'preflight.json' if status == 'aborted_before_send' else 'plan.json' if status == 'pending_plan' else 'evidence.json'
            media = 'hash retained after video deletion' if status == 'video_superseded' else 'media withheld pending review' if status == 'pending_video' and withheld else '—'
            if ident in reviewed_stills:
                media = f'[Post-run dashboard]({reviewed_stills[ident]})'
            lines.append(f'| [{label}](runs/{ident}/{target}) | {score if score is not None else "—"} | {status} | {media} |')
        lines += ['', 'Run `python3 tools/verify_run.py RUN_UUID` in this clone. A threshold result without reviewed media is pending, not a public verified winner.', '']
        write(dest,'RESULTS.md','\n'.join(lines).encode())
        summaries = ['RESULTS.md']
        if 'tools/research_report.py' in prepared:
            report = subprocess.check_output([sys.executable,'-B',str(dest/'tools/research_report.py')])
            write(dest,'RESEARCH.md',checked_text(report,'RESEARCH.md'))
            summaries.append('RESEARCH.md')
        public_head = commit_files(dest,summaries,'Update public results and research summaries')
        state.update(last_source_head=head,last_public_head=public_head,run_count=len(index))
        marker.write_bytes(encode(state))
        return dict(source_head=head,public_head=public_head,runs=len(index),destination=str(dest),remote_writes=False)
    finally:
        os.close(fd)
        lock.unlink()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--dest',type=Path,required=True)
    parser.add_argument('--ref',default='HEAD')
    args = parser.parse_args()
    try:
        print(json.dumps(snapshot(args.source,args.dest,args.ref),indent=2))
    except (ValueError,OSError,KeyError,TypeError,subprocess.CalledProcessError) as error:
        parser.exit(1,'Public export stopped: '+str(error)+'\n')


if __name__ == '__main__':
    main()
