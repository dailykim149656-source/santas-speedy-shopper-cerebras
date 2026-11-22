import argparse, copy, importlib, json, pathlib, subprocess, sys, tempfile
sys.path.insert(0,'/tmp'); import report_first5027 as r
P=r.DEFAULT_PROJECT; repo=P/'speed-bounty-evidence-test'; sys.path.insert(0,str(repo/'tools'))
api={k:importlib.import_module(v) for k,v in dict(first='first5027',film='first5027_film',method='method_1700',scoring='scoring',variants='variants',verify='verify_run',ledger='ledger',subprocess='subprocess').items()}
root=pathlib.Path('/tmp/first5027-report-qa');root.mkdir(exist_ok=True)
results=[]
def check(name,fn):
 try:
  detail=fn();results.append(dict(scenario=name,passed=True,observable=detail));print('PASS',name)
 except Exception as e:
  results.append(dict(scenario=name,passed=False,observable=type(e).__name__+': '+str(e))); print('FAIL',name,type(e).__name__,str(e))
def put(p,x):
 p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x))
ident='cd75e5e0-be7c-471f-a9ab-c9e6f0d1bd77';pp=repo/'runs'/ident/'plan.json'
a=argparse.Namespace(repo=repo,cache=r.DEFAULT_BASE/'2026-11-22-test/mean-2000',archive=r.DEFAULT_ARCHIVE)
plan=r.read(pp);raw=r.read(a.archive/(ident+'.json'));v=r.read(a.cache/'capture'/ident/'validation.json');e=r.read(pp.with_name('evidence.json'))
def baseline():
 t=r.audit_trial(pp,a,api);put(root/'genuine-D5027.audit.json',t)
 assert t['state']=='complete' and t['row']['method_valid'] and t['row']['first_tps']==1035.3901327436165 and t['row']['score']==1354.6625976356386 and len(t['products'])==5
 return 'genuine D5027 SHA, committed identity, 2 calls, 5 products, first TPS and mean exact match'
check('genuine D5027 baseline',baseline)
def failed_partial():
 rr,vv,ee=copy.deepcopy(raw),copy.deepcopy(v),copy.deepcopy(e)
 final=rr['history']['messages'][-1];assert final['role']=='assistant'
 final['stopReason']='error';final.pop('serverGeneration');final['content']=[];rr['ended']['terminal']='error'
 ec=ee['calls'][-1];ec['stopReason']='error';ec['serverGeneration']={};ec['timed_sample']=False
 vv['calls']=vv['calls'][:1];ee['ended']={k:rr['ended'][k] for k in ('elapsedMs','terminal','time')};vv['valid']=False;ee['validation']['valid']=False
 score=vv['calls'][0]['tokensPerSecond']
 for item in(vv,ee):item['score']['mean_exact_tps']=score;item['score']['ui_rounded_tps']=api['scoring'].round_rate(score)
 row,calls=r.extract(plan,rr,vv,ee,api);put(root/'failed-partial.json',row)
 assert row['first_tokens']==447 and row['first_think_chars']==304 and row['final_tps'] is None and not row['valid'] and row['score']==score
 return 'measured first 447 tokens/304 reasoning chars retained; no final TPS; failed run not valid'
check('failed trial first diagnostic retained',failed_partial)
def extra():
 rr,vv,ee=copy.deepcopy(raw),copy.deepcopy(v),copy.deepcopy(e)
 m=copy.deepcopy(rr['history']['messages'][-1]);m['responseId']='fixture-extra';m['serverGeneration']={'outputTokens':100,'completionMs':200};i=len(rr['history']['messages']);rr['history']['messages'].append(m)
 c=copy.deepcopy(ee['calls'][-1]);c.update(responseId='fixture-extra',message_index=i,serverGeneration=m['serverGeneration']);ee['calls'].append(c)
 vc=dict(message_index=i,response_id='fixture-extra',outputTokens=100,completionMs=200,tokensPerSecond=500,stopReason='stop');vv['calls'].append(vc)
 mean=api['scoring'].mean_rate([x['tokensPerSecond'] for x in vv['calls']])
 for item in(vv,ee):item['score']['mean_exact_tps']=mean;item['score']['ui_rounded_tps']=api['scoring'].round_rate(mean)
 row,calls=r.extract(plan,rr,vv,ee,api);put(root/'extra-call.json',dict(row=row,calls=calls));assert len(calls)==3 and row['score']==mean and mean!=e['score']['mean_exact_tps']
 return f'all 3 calls included in arithmetic mean={mean}'
check('all measured calls contribute to official mean',extra)
def mismatch():
 for mode in ('response','metric','mean'):
  rr,vv,ee=copy.deepcopy(raw),copy.deepcopy(v),copy.deepcopy(e)
  if mode=='response':vv['calls'][0]['response_id']='wrong'
  if mode=='metric':ee['calls'][0]['serverGeneration']['completionMs']=1
  if mode=='mean':ee['score']['mean_exact_tps']=9999
  try:r.extract(plan,rr,vv,ee,api)
  except ValueError:continue
  raise AssertionError(mode+' accepted')
 return 'response identity, server metric and wrong mean each rejected'
check('tampered identity metrics means rejected',mismatch)
def sha_bad():
 tmp=root/'sha';aa=argparse.Namespace(repo=repo,cache=a.cache,archive=tmp);tmp.mkdir(exist_ok=True)
 (tmp/(ident+'.json')).write_bytes((a.archive/(ident+'.json')).read_bytes()+b' ')
 result=r.audit_trial(pp,aa,api);put(root/'tampered-sha.json',result);assert result['state']=='audit_failed' and 'SHA256' in result['errors'][0]
 return 'one-byte altered raw rejected before use'
check('SHA256 tamper rejection',sha_bad)
def overlap():
 d=root/'overlap'; import shutil; shutil.rmtree(d,ignore_errors=True); args=argparse.Namespace(cache=d/'test',main_cache=d/'main',exp_cache=d/'exp',project=d/'project',start=5037)
 def rawfile(cache,label,ident,start,end):
  put(cache/'runs'/(label+'.json'),dict(id=ident,label=label,startedWall=start,history={'messages':[]},ended={'time':end,'terminal':'final'}))
 rawfile(args.main_cache,'D10-a','main',100,200);rawfile(args.exp_cache,'D6001-a','exp',250,400);rawfile(args.cache,'D5037-first5027-extract-text','test',300,500)
 locks=[str(c/'loop.lock') for c in(args.cache,args.main_cache,args.exp_cache)]
 rp=args.cache/'first5027-5037-reservation.jsonl';rp.write_text(json.dumps(dict(event='reserved',at_ms=275,pid=1,locks=locks))+'\n'+json.dumps(dict(event='releasing',at_ms=600,pid=1))+'\n')
 result=r.overlap_audit(args);put(root/'overlap-detected.json',result);assert len(result['overlaps'])==1 and result['interval_comparisons']==2 and not result['verified']
 rawfile(args.cache,'D5037-first5027-extract-text','test',450,500)
 result=r.overlap_audit(args);put(root/'overlap-clear.json',result);assert result['verified'] and result['exp_to_test_gap_ms']==50
 put(args.main_cache/'runs/D11-a.send-intent.json',dict(id='pending',label='D11-a',startedWall=460))
 result=r.overlap_audit(args);put(root/'overlap-pending.json',result);assert not result['verified'] and result['issues'] and len(result['overlaps'])==1
 return 'all 2 cross intervals checked; overlap found; corrected clear; unresolved send fails closed'
check('independent overlap and incomplete interval audit',overlap)
def filmtest():
 d=root/'film';args=argparse.Namespace(repo=d/'repo',cache=d/'cache',films=d/'films')
 base=args.films/ident;directory=base/'attempt-01';directory.mkdir(parents=True,exist_ok=True)
 fakeplan=dict(id=ident,label=plan['label'],sessionKey=plan['sessionKey']);put(args.repo/'runs'/ident/'plan.json',fakeplan)
 put(directory/'recording.json',dict(run_id=ident,sessionKey=plan['sessionKey']))
 subprocess.run(['ffmpeg','-y','-v','error','-f','lavfi','-i','color=c=black:s=160x120:d=1','-c:v','libx264','-pix_fmt','yuv420p',str(directory/'original.mp4')],check=True)
 import shutil;shutil.copyfile(directory/'original.mp4',directory/'demo.mp4')
 film=api['film'];old=film.REPO,film.CACHE,film.put
 try:
  film.REPO,film.CACHE,film.put=args.repo,args.cache,lambda p,x:None
  receipt=film.inspect(plan['label'],fakeplan,directory)
 finally:film.REPO,film.CACHE,film.put=old
 put(base/'receipt.json',receipt)
 trial=dict(id=ident,label=plan['label'],row=None,products=[])
 result=r.film_audit(trial,args,api);put(root/'film-playable-no-ui.json',result)
 assert result['verified'] and not result['viewport_verified'] and result['displayed_mean'] is None
 receipt['media']['demo.mp4']['sha256']='0'*64;put(base/'receipt.json',receipt)
 result=r.film_audit(trial,args,api);put(root/'film-stale-rejected.json',result);assert not result['verified']
 assert not (directory/'inspection.json').exists()
 return 'real ffprobe playable fixture, no invented UI; tampered receipt rejected; inspector wrote nothing'
check('film receipt ffprobe reinspection and absent UI',filmtest)
def secret():
 args=r.public_arguments([{'url':'https://example.com/?token=secret123','password':'private','extractMode':'text'}]);assert 'secret123' not in json.dumps(args) and 'private' not in json.dumps(args)
 return 'unexpected URL and argument values redacted'
check('public argument redaction',secret)
def partial():
 out=root/'partial.md';proc=subprocess.run([sys.executable,'-B','/tmp/report_first5027.py','--output',str(out)],capture_output=True,text=True)
 (root/'partial-cli.log').write_text(proc.stdout+proc.stderr);assert proc.returncode==0 and out.stat().st_size>0
 data=r.read(pathlib.Path(str(out)+'.audit.json'));assert data['status']=='partial'
 return f'CLI exit 0; Korean report and audit JSON nonempty; {data["actual_sends"]} actual sends'
check('real current campaign partial CLI',partial)
def selection():
    rows=[]
    for i,side in enumerate(api['first'].ORDER+'ABBA'):
        gains={'A':0,'B':150,'C':50}
        row=dict(id='fixture-'+str(i),label=f'D{5037+i}-'+api['first'].ARMS[side],arm=api['variants'].arm_key((api['first'].ARMS[side],.2,'low')),
                 valid=True,method_valid=True,score=1300+gains[side]/2,first_tps=1000+gains[side],first_ms=400-gains[side]/10,
                 first_tokens=400,first_think_chars=0,final_tps=1600,started_wall=1000000+i*60000,product_urls=['https://example.test/product/'+str(n) for n in range(5)])
        rows.append(row)
    result=api['first'].summary(repo,5037,rows);put(root/'selection-confirmation.json',result)
    assert result['promotion']==api['first'].ARMS['B'] and result['confirmation']['qualified'] and result['selection']['B']['valid_pairs']==4 and not result['selection']['C']['qualified']
    rows[1]['started_wall']+=10000000
    result=api['first'].summary(repo,5037,rows);put(root/'selection-time-exclusion.json',result)
    assert not result['pairs'][0]['valid'] and any('15 minutes' in x for x in result['pairs'][0]['reasons'])
    return '16 planned slots: B selected and both confirmation pairs pass; >15-minute pair excluded'
check('selection confirmation and temporal exclusion',selection)
def copytest():
    import shutil
    project=root/'copy-project';project.mkdir(exist_ok=True);dest=project/'verified-demos';shutil.rmtree(dest,ignore_errors=True)
    directory=root/'film/films'/ident/'attempt-01';digest=r.sha(directory/'demo.mp4')
    trial=dict(id=ident,label='D5037-fixture',film=dict(verified=True,viewport_verified=True,directory=str(directory),media={'demo.mp4':{'sha256':digest}}))
    result=r.copy_demos([trial],dest,project)
    assert result[0]['sha256']==digest and r.sha(dest/'D5037.mp4')==digest and r.read(dest/'checksums-first5027.json')==result
    try:r.copy_demos([trial],root/'outside',project)
    except ValueError:pass
    else:raise AssertionError('outside project copy accepted')
    put(root/'copy-result.json',result)
    return 'verified fixture demo copied with matching checksum manifest; outside-project destination rejected'
check('optional project-local verified demo copy',copytest)
put(root/'results.json',dict(invocation='python3 -B /tmp/test_report_first5027.py',results=results,passed=all(x['passed'] for x in results)))
assert all(x['passed'] for x in results)
