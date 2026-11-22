import hashlib,json,math,pathlib,subprocess,tempfile
root=pathlib.Path.cwd(); ledger=root/'speed-bounty-evidence/tools/ledger.py'; out=root/'.omo/evidence/git-ledger'
repo=pathlib.Path(tempfile.mkdtemp(prefix='ledger-qa-'))
log=[]
def run(*args,ok=True):
 p=subprocess.run([str(a) for a in args],capture_output=True,text=True);log.append({'argv':[str(a) for a in args],'returncode':p.returncode,'stdout':p.stdout,'stderr':p.stderr});assert (p.returncode==0)==ok,log[-1];return p.stdout
run('git','init',repo);run('git','-C',repo,'config','user.name','Ledger QA');run('git','-C',repo,'config','user.email','ledger-qa@example.invalid')
raw=pathlib.Path.home()/'Library/Caches/cerebras-speed-bounty/2026-11-22/mean-2000/runs/D0001-native-links.json';validation=pathlib.Path('/tmp/cerebras-2k-goal/initial-check.json')
x=json.loads(raw.read_bytes()); plan=repo/'input-plan.json'; plan.write_text(json.dumps({k:x[k] for k in ('id','label','sessionKey','prompt')}))
run('python3',ledger,'plan','--repo',repo,'--plan',plan)
(repo/'unrelated.txt').write_text('preserve staged work');run('git','-C',repo,'add','unrelated.txt')
args=['python3',ledger,'finish','--repo',repo,'--raw',raw,'--validation',validation,'--historical']
a=json.loads(run(*args));b=json.loads(run(*args));assert a['commit']==b['commit'];assert a['evidence_status']=='below_threshold_recorded'
assert run('git','-C',repo,'diff','--cached','--name-only').strip()=='unrelated.txt'
e=pathlib.Path(a['path']).read_text();assert json.loads(e)['private_raw_sha256']==hashlib.sha256(raw.read_bytes()).hexdigest()
for forbidden in ('reasoning','participants','sessionInfo','activitySummary','input_path','devicePlacement'):
 assert forbidden not in e
v=json.loads(validation.read_text());v['input_sha256']='0'*64;bad=repo/'bad.json';bad.write_text(json.dumps(v));run('python3',ledger,'finish','--repo',repo,'--raw',raw,'--validation',bad,'--historical',ok=False)
# Synthetic score fixture uses saved real structure. It is not a benchmark claim.
x['id']='synthetic-high';x['label']='synthetic-high';x['ended']['elapsedMs']=500; rates=[]
for m in x['history']['messages']:
 if m.get('__openclaw',{}).get('runId')==v['run_id']:
  m['__openclaw']['runId']=x['id']
  if m.get('role')=='assistant':
   g=m['serverGeneration'];g['completionMs']=g['outputTokens']/1800*1000;rates.append(1800)
high=repo/'high.json';high.write_text(json.dumps(x));v.update(run_id=x['id'],input_sha256=hashlib.sha256(high.read_bytes()).hexdigest());v['score']['mean_exact_tps']=1800;v['score']['ui_rounded_tps']=1800;hv=repo/'high-validation.json';hv.write_text(json.dumps(v));h=json.loads(run('python3',ledger,'finish','--repo',repo,'--raw',high,'--validation',hv,'--historical'));assert h['evidence_status']=='provisional_capture_required'
media=repo/'media';media.mkdir()
run('ffmpeg','-v','error','-f','lavfi','-i','color=c=black:s=16x16:r=1','-t','1','-pix_fmt','yuv420p',media/'original.mp4')
(media/'demo.mp4').write_bytes((media/'original.mp4').read_bytes())
run('ffmpeg','-v','error','-i',media/'original.mp4','-frames:v','1',media/'final.png')
(media/'recording.json').write_text(json.dumps({'run_id':'synthetic-high','full_run':True,'authless':True,'final_ui_tps':1800}))
# A 61-second short must remain provisional; replacing it permits recovery.
run('ffmpeg','-v','error','-y','-f','lavfi','-i','color=c=black:s=16x16:r=1','-t','61','-pix_fmt','yuv420p',media/'demo.mp4')
too_long=json.loads(run('python3',ledger,'finish','--repo',repo,'--raw',high,'--validation',hv,'--historical','--media-dir',media));assert too_long['evidence_status']=='provisional_capture_required'
assert 'exceeds 60 seconds' in pathlib.Path(too_long['path']).read_text()
(media/'demo.mp4').write_bytes((media/'original.mp4').read_bytes())
complete=json.loads(run('python3',ledger,'finish','--repo',repo,'--raw',high,'--validation',hv,'--historical','--media-dir',media));assert complete['evidence_status']=='complete'
assert json.loads(pathlib.Path(complete['path']).read_text())['media']['original.mp4']['sha256']==hashlib.sha256((media/'original.mp4').read_bytes()).hexdigest()
# Rejected run with no timed calls is retained; reasoning must not escape.
x['id']='synthetic-failed';x['label']='synthetic-failed'
for m in x['history']['messages']:
 if m.get('__openclaw',{}).get('runId')=='synthetic-high':
  m['__openclaw']['runId']=x['id'];m.pop('serverGeneration',None)
failed=repo/'failed.json';failed.write_text(json.dumps(x));v.update(run_id=x['id'],input_sha256=hashlib.sha256(failed.read_bytes()).hexdigest(),valid=False,status='rejected');v['score'].update(mean_exact_tps=None,ui_rounded_tps=None);fv=repo/'failed-validation.json';fv.write_text(json.dumps(v))
f=json.loads(run('python3',ledger,'finish','--repo',repo,'--raw',failed,'--validation',fv,'--historical'));assert f['evidence_status']=='unscored_failed_run'
run('git','-C',repo,'fsck','--full');tracked=run('git','-C',repo,'ls-tree','-r','--name-only','HEAD');assert all(p.startswith('runs/') for p in tracked.splitlines())
(out/'qa-log.json').write_text(json.dumps(log,indent=2));(out/'result.json').write_text(json.dumps({'passed':True,'temporary_repo':str(repo),'real_run':a,'synthetic_provisional':h,'scenarios':['real D0001 plan and historical finish','exact raw SHA binding','idempotent finish unchanged commit','unrelated staged file preserved','privacy excluded history/profile/reasoning keys','tampered validation SHA rejected','synthetic 1800 TPS missing media provisional','61-second demo rejected then recovered','synthetic playable media completion and hashes','unscored rejected run traceability','git fsck and only runs paths committed']},indent=2));print(repo)
