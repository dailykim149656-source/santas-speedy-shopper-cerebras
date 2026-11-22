"""Synthetic local report fixtures; no provider, HTTP or campaign UI proof."""
import copy,json,shutil,subprocess,sys,uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3];OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'tools'))
import gift8_report as r
from gift8_evidence import score_raw, validate_events, canonical_card, jsjson
checks=[]
def check(name,value):
 assert value,name
 checks.append(dict(scenario=name,passed=True))
 print('PASS',name)
def save(path,value):
 path.parent.mkdir(parents=True,exist_ok=True)
 path.write_text(value if isinstance(value,str) else json.dumps(value,ensure_ascii=False,indent=2))
base=OUT/'fixtures'
if base.exists():shutil.rmtree(base)
repo=base/'repo';cache=base/'test';archive=base/'raw-test';campaign=cache/'gift8-5051'
repo.mkdir(parents=True);(repo/'tools/gift8-plugin').mkdir(parents=True)
for name in ('index.cjs','openclaw.plugin.json','package.json'):shutil.copyfile(ROOT/'tools/gift8-plugin'/name,repo/'tools/gift8-plugin'/name)
subprocess.run(['git','init','-q',str(repo)],check=True)
subprocess.run(['git','-C',str(repo),'config','user.email','fixture@invalid'],check=True)
subprocess.run(['git','-C',str(repo),'config','user.name','Offline fixture'],check=True)
plugin_sha=r.digest(b''.join((repo/'tools/gift8-plugin'/name).read_bytes() for name in sorted(('index.cjs','openclaw.plugin.json','package.json'))))
rows=[]
for index,arm in enumerate(r.ORDER):
 ident=str(uuid.uuid5(uuid.NAMESPACE_URL,'gift8-report-fixture-'+str(index)));variant='gift8-tool' if arm=='A' else 'gift8-prefetch';side='tool' if arm=='A' else 'prefetch'
 label=f'D{5051+index}-{variant}';session='agent:main:shop-'+label.lower()+'-'+ident[:8];start=1700000000000+index*60000;end=start+10000
 plan=dict(id=ident,label=label,sessionKey=session,variant=variant,prompt='OFFLINE QA fixture '+ident,thinking='low',temperature=.2,top_p=None,max_completion_tokens=1024,capturePolicy='score-first')
 manifest=dict(id=ident,sessionKey=session,arm=side,prompt_sha256=r.digest(plan['prompt'].encode()),created_ms=start-1,ids=r.IDS,protocol='gift8-v1',plugin_sha256=plugin_sha)
 run=repo/'runs'/ident;rec=campaign/'receipts'/ident;cards=[];receipts=[]
 for product_id in r.IDS:
  product=dict(id=product_id,name=f'Fixture {product_id}',permalink=f'https://aisynthesis.com/product/fixture-{product_id}/',prices=dict(price='1000',currency_code='USD',price_range=None),is_in_stock=True,variations=[])
  body=jsjson(product);card=canonical_card(product);cards.append(card);bodyname=f'body-{product_id}.bin';url=f'https://aisynthesis.com/wp-json/wc/store/v1/products/{product_id}?_fields=id,name,permalink,prices,stock_availability,variations,is_in_stock'
  receipt=dict(protocol='gift8-v1',id=ident,sessionKey=session,arm=side,prompt_sha256=manifest['prompt_sha256'],product_id=product_id,tool_call_id=f'call-{product_id}' if arm=='A' else None,started_ms=start+(300 if arm=='A' else 100),completed_ms=start+(350 if arm=='A' else 150),url=url,final_url=url,status=200,body_sha256=r.digest(body),body_file=bodyname,card=card,card_sha256=r.digest(jsjson(card)))
  for directory in (rec,run/'gift-receipts'):
   directory.mkdir(parents=True,exist_ok=True);(directory/bodyname).write_bytes(body);save(directory/f'fetch-{product_id}.json',receipt)
  receipts.append(receipt)
 system='fixture system';events=[]
 def event(kind,offset,**fields):
  value=dict(type=kind,runId=ident,sessionKey=session,timestamp_ms=start+offset,plugin_sha256=plugin_sha,**fields)
  save(rec/'events'/f'{offset}-{kind}.json',value)
 event('prompt_binding',1,prompt_sha256=manifest['prompt_sha256'],arm=side,system_prompt_sha256=r.digest(system.encode()))
 prompt=plan['prompt']
 if arm=='B':
  context='Current merchant cards: '+jsjson(dict(gifts=cards)).decode();prompt=context+'\n'+prompt
  event('prefetch_injection',175,context=context,context_sha256=r.digest(context.encode()),prompt_sha256=manifest['prompt_sha256'])
 event('llm_input',200,event=dict(runId=ident,provider='cerebras',model=r.MODEL,prompt=prompt,systemPrompt=system,historyMessages=[]),prompt_sha256=r.digest(prompt.encode()),bound_prompt_sha256=manifest['prompt_sha256'])
 messages=[]
 def assistant(content,tokens,stop):return dict(role='assistant',provider='cerebras',model=r.MODEL,responseId='response-'+str(len(messages)),stopReason=stop,serverGeneration=dict(completionMs=1000,outputTokens=tokens),content=content,__openclaw=dict(runId=ident))
 if arm=='A':
  messages.append(assistant([dict(type='toolCall',id=f'call-{i}',name='gift_lookup',arguments=dict(id=i)) for i in r.IDS],1000,'toolUse'))
  for card in cards:messages.append(dict(role='toolResult',toolName='gift_lookup',toolCallId=f"call-{card['id']}",isError=False,content=[dict(type='text',text=jsjson(card).decode())],details=dict(card=card,receipt_file=f"fetch-{card['id']}.json"),__openclaw=dict(runId=ident)))
 messages.append(assistant([dict(type='text',text=jsjson(dict(gifts=cards)).decode())],1200 if arm=='A' else 1400,'stop'))
 raw=dict(plan,startedWall=start,ended=dict(time=end,terminal='final'),history=dict(messages=messages));blob=jsjson(raw)
 rawpath=cache/'runs'/(label+'.json');rawpath.parent.mkdir(parents=True,exist_ok=True);rawpath.write_bytes(blob);archive.mkdir(exist_ok=True);(archive/(ident+'.json')).write_bytes(blob);(rec/'private-raw.json').write_bytes(blob)
 save(cache/'runs'/(label+'.send-intent.json'),dict(id=ident,sessionKey=session,startedWall=start))
 calls,score,reasons=score_raw(raw);assert not reasons
 validation=dict(run_id=ident,input_sha256=r.digest(blob),valid=True,calls=calls,score=score,products=[dict(url=c['url'],verified=True) for c in cards])
 save(cache/'capture'/ident/'validation.json',validation)
 evidence=dict(id=ident,private_raw_sha256=r.digest(blob),private_raw_bytes=len(blob),score=score,calls=calls,validation=dict(valid=True),products=validation['products'],plugin_sha256=plugin_sha)
 save(run/'plan.json',plan);save(run/'gift-manifest.json',manifest);save(campaign/'manifests'/(ident+'.json'),manifest)
 for apple in (rec/'events').glob('._*'): apple.unlink()
 evidence['manifest_sha256']=r.digest((campaign/'manifests'/(ident+'.json')).read_bytes());hook=dict(calls=calls);validate_events(rec,raw,manifest,cards,receipts,hook)
 evidence.update({key:hook[key] for key in ('hook_evidence','first_input_sha256')});save(run/'evidence.json',evidence)
 rows.append(dict(id=ident,label=label,arm=arm,variant=variant,valid=True,method_valid=True,score=score['mean_exact_tps'],ui=score['ui_rounded_tps'],first_tps=calls[0]['tokensPerSecond'],final_tps=calls[-1]['tokensPerSecond'],call_count=len(calls),started_wall=start,ended_wall=end,terminal_429=False,product_urls=[c['url'] for c in cards],rejection=[]))
(campaign/'iterations.jsonl').write_text(''.join(json.dumps(row)+'\n' for row in rows))
reservation=[dict(event='reserved',pid=123,at_ms=rows[0]['started_wall']-1,locks=[str(cache/'loop.lock'),str(base/'main/loop.lock'),str(base/'exp/loop.lock')]),dict(event='releasing',pid=123,at_ms=rows[-1]['ended_wall']+1)]
(campaign/'reservation.jsonl').write_text(''.join(json.dumps(event)+'\n' for event in reservation))
subprocess.run(['git','-C',str(repo),'add','.'],check=True);subprocess.run(['git','-C',str(repo),'commit','-qm','Explicit offline fixture'],check=True)
caches=dict(test=cache,main=base/'main',exp=base/'exp')
audit=r.build(repo,cache,archive,caches,base/'demos',base/'inspections');save(OUT/'eight-fixture.audit.json',audit)
check('eight complete fixtures and exact ABBABAAB pass independent audit',audit['passed'])
check('four pairs yield B-A first400 and mean300',len(audit['pairs'])==4 and all(p['valid'] and p['delta_first_tps']==400 and p['delta_official_mean_tps']==300 for p in audit['pairs']))
check('allcall mean1100 differs from first1000 and final1200',audit['rows'][0]['score']==1100 and audit['rows'][0]['first_tps']==1000 and audit['rows'][0]['final_tps']==1200)
check('all local raw spans compared',audit['no_overlap']['comparisons']==28)
check('closed samePID reservation covers each send',audit['reservation']['passed'] and len(audit['reservation']['coverage'])==8)
head=audit['pinned_commit'];changed=copy.deepcopy(rows[0]);changed['first_tps']+=1
bad=r.audit_trial(changed,repo,cache,archive,head,r.Sources());check('forged row metric rejected',not bad['audit_passed']);save(OUT/'wrong-metric.json',bad)
private=archive/(rows[0]['id']+'.json');original=private.read_bytes();private.write_bytes(original+b' ')
bad=r.audit_trial(rows[0],repo,cache,archive,head,r.Sources());check('archive bytes mismatch rejected',not bad['audit_passed']);private.write_bytes(original)
changed=copy.deepcopy(audit['rows']);changed[1]['product_urls'].reverse();check('reordered products exclude pair',not r.pair_results(changed)[0]['valid'])
changed=copy.deepcopy(audit['rows']);changed[1]['started_wall']=changed[0]['started_wall']+900000;check('exact15minute pair accepted',r.pair_results(changed)[0]['valid']);changed[1]['started_wall']+=1;check('over15minute pair excluded',not r.pair_results(changed)[0]['valid'])
changed=copy.deepcopy(audit['rows']);changed[1]['valid']=False;check('invalid run excludes paired delta',r.pair_results(changed)[0]['delta_first_tps'] is None)
check('wrongPID release rejected',not r.reservation_audit([reservation[0],reservation[1]|dict(pid=999)],rows)['passed'])
check('open reservation rejected',not r.reservation_audit(reservation[:1],rows)['passed'])
foreign=caches['main']/'runs/foreign.json';save(foreign,dict(id='foreign',startedWall=rows[0]['started_wall']+1,ended=dict(time=rows[0]['ended_wall']-1,terminal='final')))
result=r.span_audit(caches,{x['id'] for x in rows},r.Sources());check('actual overlapping foreign span blocksaudit',not result['passed'] and len(result['campaign_overlaps'])==1);save(OUT/'overlap.json',result);foreign.unlink()
pending=caches['exp']/'runs/unfinished.send-intent.json';save(pending,dict(id='unfinished',startedWall=1))
result=r.span_audit(caches,{x['id'] for x in rows},r.Sources());check('incomplete foreign send blocksaudit',not result['passed'] and len(result['incomplete_sends'])==1);save(OUT/'incomplete-send.json',result);pending.unlink()
raw=json.loads((cache/'runs'/(rows[0]['label']+'.json')).read_bytes());raw['history']['messages'].insert(0,dict(role='assistant',provider='cerebras',model=r.MODEL,responseId='extra',stopReason='stop',serverGeneration=dict(completionMs=1000,outputTokens=2000),__openclaw=dict(runId=raw['id'])))
calls,score,reasons=r.independent_score(raw);check('additional actual call included in arithmetic',score['assistant_call_count']==3 and score['mean_exact_tps']==1400)
raw['history']['messages'][0]['serverGeneration']={};calls,score,reasons=r.independent_score(raw);check('unmeasured assistant remains counted and invalidates method',len(calls)==3 and score['call_count']==2 and bool(reasons))
text=r.korean_report(audit,OUT/'fixture.audit.json',OUT/'fixture.sha256.json');save(OUT/'fixture-report.md',text)
check('Korean report includes denominator failures and honest scope','실패' in text and '하드웨어' in text and '4/4쌍' in text)
# A >=1700 run has no fixture video: the report must refuse target completion.
first=rows[0];ident=first['id'];raw_path=cache/'runs'/(first['label']+'.json');raw=json.loads(raw_path.read_bytes())
for message in raw['history']['messages']:
 if message.get('role')=='assistant':message['serverGeneration']['outputTokens']+=1000
blob=jsjson(raw);raw_path.write_bytes(blob);(archive/(ident+'.json')).write_bytes(blob);(campaign/'receipts'/ident/'private-raw.json').write_bytes(blob)
calls,score,_=score_raw(raw)
validation_path=cache/'capture'/ident/'validation.json';validation=json.loads(validation_path.read_bytes());validation.update(input_sha256=r.digest(blob),calls=calls,score=score);save(validation_path,validation)
evidence_path=repo/'runs'/ident/'evidence.json';evidence=json.loads(evidence_path.read_bytes());evidence.update(private_raw_sha256=r.digest(blob),private_raw_bytes=len(blob),calls=calls,score=score);save(evidence_path,evidence)
first.update(score=score['mean_exact_tps'],ui=score['ui_rounded_tps'],first_tps=calls[0]['tokensPerSecond'],final_tps=calls[-1]['tokensPerSecond'])
(campaign/'iterations.jsonl').write_text(''.join(json.dumps(row)+'\n' for row in rows))
subprocess.run(['git','-C',str(repo),'add','.'],check=True);subprocess.run(['git','-C',str(repo),'commit','-qm','High-score fixture without movie'],check=True)
target=r.build(repo,cache,archive,caches,base/'demos',base/'inspections');save(OUT/'target-without-video.json',target)
check('1700target without genuine same-run UI fiveURLs movie cannot pass',not target['passed'] and any('1700 target lacks' in x for x in target['errors']))
# A documented validation failure stays in the denominator without becoming an audit mismatch.
validation['valid']=False;save(validation_path,validation);evidence['validation']['valid']=False;save(evidence_path,evidence)
first.update(valid=False,method_valid=False,rejection=['offline fixture shopping rejection'])
(campaign/'iterations.jsonl').write_text(''.join(json.dumps(row)+'\n' for row in rows))
subprocess.run(['git','-C',str(repo),'add','.'],check=True);subprocess.run(['git','-C',str(repo),'commit','-qm','Explicit invalid fixture'],check=True)
failed=r.build(repo,cache,archive,caches,base/'demos',base/'inspections');save(OUT/'failed-run-denominator.json',failed)
check('failed send retained in successrate denominator',failed['conditions']['A']['sent']==4 and failed['conditions']['A']['valid']==3 and failed['conditions']['A']['success_rate']==.75 and failed['passed'])
legacy=cache/'runs/D5003-legacy.send-intent.json';save(legacy,dict(id='legacy',startedWall=1))
scoped=r.span_audit(caches,{x['id'] for x in rows},r.Sources());check('old same-root test excluded with explicit provenance',scoped['passed'] and len(scoped['historical_test_exclusions'])==1);save(OUT/'legacy-scope.json',scoped)
current=cache/'runs/D5059-gift8-tool.send-intent.json';save(current,dict(id='new-unfinished',startedWall=rows[-1]['ended_wall']+1))
scoped=r.span_audit(caches,{x['id'] for x in rows},r.Sources());check('unresolved current gift8 blocks even before iteration row',not scoped['passed'] and len(scoped['incomplete_sends'])==1)
check('reservation with incorrect profile lock set fails',not r.reservation_audit(reservation,rows,['different'])['passed'])
current.unlink()
raw=json.loads(raw_path.read_bytes());raw['ended']['terminal']='error';raw['history']['messages'][-1].update(stopReason='error',errorMessage='429 too many requests')
blob=jsjson(raw);raw_path.write_bytes(blob);(archive/(ident+'.json')).write_bytes(blob);(campaign/'receipts'/ident/'private-raw.json').write_bytes(blob)
calls,score,_=score_raw(raw);validation.update(input_sha256=r.digest(blob),calls=calls,score=score);save(validation_path,validation)
evidence.update(private_raw_sha256=r.digest(blob),private_raw_bytes=len(blob),calls=calls,score=score);save(evidence_path,evidence)
first['terminal_429']=True;(campaign/'iterations.jsonl').write_text(''.join(json.dumps(row)+'\n' for row in rows))
subprocess.run(['git','-C',str(repo),'add','.'],check=True);subprocess.run(['git','-C',str(repo),'commit','-qm','Terminal429 failure fixture'],check=True)
limited=r.build(repo,cache,archive,caches,base/'demos',base/'inspections');save(OUT/'terminal-429.json',limited)
check('terminal429 failure retained in count and denominator',limited['passed'] and limited['conditions']['A']['terminal_429']==1 and limited['conditions']['A']['success_rate']==.75)
# A valid B trial can do an additional generation plus five native follow-up calls.
b=rows[1];bid=b['id'];brec=campaign/'receipts'/bid;brun=repo/'runs'/bid;brawpath=cache/'runs'/(b['label']+'.json');braw=json.loads(brawpath.read_bytes())
bcards=[json.loads((brec/f'fetch-{product_id}.json').read_bytes())['card'] for product_id in r.IDS]
followup=dict(role='assistant',provider='cerebras',model=r.MODEL,responseId='fixture-B-extra',stopReason='toolUse',serverGeneration=dict(completionMs=1000,outputTokens=1000),content=[dict(type='toolCall',id=f'extra-{product_id}',name='gift_lookup',arguments=dict(id=product_id)) for product_id in r.IDS],__openclaw=dict(runId=bid))
bmessages=[followup];links=[]
for card in bcards:
 product_id=card['id'];call_id=f'extra-{product_id}'
 bmessages.append(dict(role='toolResult',toolName='gift_lookup',toolCallId=call_id,isError=False,content=[dict(type='text',text=jsjson(card).decode())],__openclaw=dict(runId=bid)))
 link=dict(id=bid,sessionKey=braw['sessionKey'],arm='prefetch',product_id=product_id,tool_call_id=call_id,receipt_file=f'fetch-{product_id}.json',card_sha256=r.digest(jsjson(card)),timestamp_ms=braw['startedWall']+300)
 name=r.digest(call_id.encode())+'.json';save(brec/'calls'/name,link);save(brun/'gift-receipts/calls'/name,link)
 links.append(dict(file=name,sha256=r.digest((brec/'calls'/name).read_bytes()),**link))
bmessages+=braw['history']['messages'];braw['history']['messages']=bmessages;blob=jsjson(braw);brawpath.write_bytes(blob);(archive/(bid+'.json')).write_bytes(blob);(brec/'private-raw.json').write_bytes(blob)
bcalls,bscore,_=score_raw(braw);structural=dict(actual_generation_count=2,expected_generation_count=1,native_tool_call_count=5,structure_expected=False,followup_call_receipts=links)
bvalidation_path=cache/'capture'/bid/'validation.json';bvalidation=json.loads(bvalidation_path.read_bytes());bvalidation.update(input_sha256=r.digest(blob),calls=bcalls,score=bscore,**structural);save(bvalidation_path,bvalidation)
bevidence_path=brun/'evidence.json';bevidence=json.loads(bevidence_path.read_bytes());bevidence.update(private_raw_sha256=r.digest(blob),private_raw_bytes=len(blob),calls=bcalls,score=bscore,**structural);save(bevidence_path,bevidence)
b.update(score=bscore['mean_exact_tps'],ui=bscore['ui_rounded_tps'],first_tps=1000,final_tps=1400,call_count=2)
(campaign/'iterations.jsonl').write_text(''.join(json.dumps(row)+'\n' for row in rows))
subprocess.run(['git','-C',str(repo),'add','.'],check=True);subprocess.run(['git','-C',str(repo),'commit','-qm','Valid B followup two-generation fixture'],check=True)
multicall=r.build(repo,cache,archive,caches,base/'demos',base/'inspections');save(OUT/'prefetch-extra-generation.json',multicall)
check('validB extra-generation uses actual allcalls1200mean',multicall['passed'] and multicall['rows'][1]['valid'] and multicall['rows'][1]['score']==1200 and multicall['rows'][1]['actual_generation_count']==2)
check('validB extra-generation succeeds but one-generation hypothesis fails',not multicall['rows'][1]['structure_expected'] and multicall['conditions']['B']['valid']==4 and multicall['conditions']['B']['success_rate']==1 and multicall['conditions']['B']['single_generation_successes']==3 and multicall['conditions']['B']['extra_generation_successes']==1)
check('allfive native extra-call receipts independently hashed',len(multicall['rows'][1]['followup_call_receipts'])==5)
linkpath=brec/'calls'/links[0]['file'];original=linkpath.read_bytes();linkpath.unlink()
missing=r.audit_trial(b,repo,cache,archive,multicall['pinned_commit'],r.Sources());check('B extra call without source binding receipt rejected',not missing['valid'] and not missing['audit_passed']);save(OUT/'prefetch-missing-binding.json',missing);linkpath.write_bytes(original)
# Bind the same stale timestamp into private/public/evidence copies: timing must still reject it.
stale=json.loads(original);stale['timestamp_ms']=braw['startedWall']+175;save(linkpath,stale);save(brun/'gift-receipts/calls'/links[0]['file'],stale)
links[0]=dict(file=links[0]['file'],sha256=r.digest(linkpath.read_bytes()),**stale);bvalidation['followup_call_receipts']=links;bevidence['followup_call_receipts']=links;save(bvalidation_path,bvalidation);save(bevidence_path,bevidence)
subprocess.run(['git','-C',str(repo),'add','.'],check=True);subprocess.run(['git','-C',str(repo),'commit','-qm','Stale B followup binding fixture'],check=True)
stale_head=subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD'],text=True).strip();bad=r.audit_trial(b,repo,cache,archive,stale_head,r.Sources());check('B followup before first native model input rejected despite matching hashes',not bad['audit_passed'] and any('preceded first model input' in x for x in bad['audit_errors']));save(OUT/'prefetch-stale-binding.json',bad)
extra_text=r.korean_report(multicall,OUT/'prefetch-extra-generation.json',OUT/'fixture.sha256.json');save(OUT/'prefetch-extra-generation.md',extra_text)
check('Korean report separates three single-generation successes from one extra-generation success','3/4회' in extra_text and '추가 생성이 발생한 성공은 1회' in extra_text)
# Corrupt a native card while updating all raw archive hashes: content binding still rejects.
linkpath.write_bytes(original);(brun/'gift-receipts/calls'/links[0]['file']).write_bytes(original)
links[0]=dict(file=links[0]['file'],sha256=r.digest(original),**json.loads(original));bvalidation['followup_call_receipts']=links;bevidence['followup_call_receipts']=links
wrongcard=dict(bcards[0],price_minor=bcards[0]['price_minor']+1);braw['history']['messages'][1]['content'][0]['text']=jsjson(wrongcard).decode()
blob=jsjson(braw);brawpath.write_bytes(blob);(archive/(bid+'.json')).write_bytes(blob);(brec/'private-raw.json').write_bytes(blob)
bvalidation['input_sha256']=r.digest(blob);bevidence.update(private_raw_sha256=r.digest(blob),private_raw_bytes=len(blob));save(bvalidation_path,bvalidation);save(bevidence_path,bevidence)
subprocess.run(['git','-C',str(repo),'add','.'],check=True);subprocess.run(['git','-C',str(repo),'commit','-qm','Wrong B native card despite consistent raw hashes'],check=True)
wrong_head=subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD'],text=True).strip();bad=r.audit_trial(b,repo,cache,archive,wrong_head,r.Sources());check('B native followup card mutation rejected despite consistent raw hashes',not bad['audit_passed'] and any('prefetch follow-up native result' in x for x in bad['audit_errors']));save(OUT/'prefetch-wrong-native-card.json',bad)
save(OUT/'offline-results.json',dict(fixture_only=True,pass_=True,checks=checks))
