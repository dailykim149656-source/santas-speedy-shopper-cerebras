import copy, hashlib, json, pathlib, subprocess, sys, tempfile
sys.path.insert(0,str(pathlib.Path('tools').resolve()))
import gift8_evidence as g
import ledger
ROOT=pathlib.Path.cwd()
checks=[]
def save(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_bytes(g.jsjson(value))
def check(name, fn):
    fn(); checks.append({'scenario':name,'passed':True}); print('PASS',name)
def fixture(arm):
    root=pathlib.Path(tempfile.mkdtemp(prefix='gift8-check-')).resolve()
    subprocess.run(['git','init','-q',str(root)],check=True)
    for key,value in [('user.email','fixture@example.invalid'),('user.name','Offline fixture')]:
        subprocess.run(['git','-C',str(root),'config',key,value],check=True)
    plugin=ROOT/'tools/gift8-plugin'
    digest=ledger.sha(b''.join((plugin/n).read_bytes() for n in sorted(('index.cjs','openclaw.plugin.json','package.json'))))
    plan={'id':'fixture','sessionKey':'fixture-session','label':'fixture','prompt':'Give five cards','variant':'gift8-'+arm}
    ledger.plan(root,plan)
    manifest=dict(id='fixture',sessionKey='fixture-session',arm=arm,prompt_sha256=ledger.sha(plan['prompt'].encode()),created_ms=1,ids=g.IDS,protocol=g.PROTOCOL,plugin_sha256=digest)
    save(root/'runs/fixture/gift-manifest.json',manifest)
    ledger.commit(root,[root/'runs/fixture/gift-manifest.json'],'Fixture manifest')
    receipts=root/'private'; receipts.mkdir()
    cards=[]
    for k,id in enumerate(g.IDS):
        product=dict(id=id,name='Product '+str(id),permalink=f'https://aisynthesis.com/product/p-{id}/',prices={'price':'1250','currency_code':'USD','price_range':None},is_in_stock=True,variations=[{'attributes':[{'value':'Kit'}]}])
        body=g.jsjson(product); card=g.canonical_card(product); cards.append(card)
        (receipts/f'body-{id}.bin').write_bytes(body)
        url=f'https://aisynthesis.com/wp-json/wc/store/v1/products/{id}?_fields=id,name,permalink,prices,stock_availability,variations,is_in_stock'
        r=dict(protocol=g.PROTOCOL,id='fixture',sessionKey='fixture-session',arm=arm,prompt_sha256=manifest['prompt_sha256'],product_id=id,tool_call_id='call-'+str(id) if arm=='tool' else None,started_ms=20 if arm=='prefetch' else 40,completed_ms=25 if arm=='prefetch' else 45,url=url,final_url=url,status=200,body_sha256=ledger.sha(body),body_file=f'body-{id}.bin',card=card,card_sha256=ledger.sha(g.jsjson(card)))
        save(receipts/f'fetch-{id}.json',r)
    def event(type,time,**fields):
        e=dict(type=type,runId='fixture',sessionKey='fixture-session',timestamp_ms=time,plugin_sha256=digest,**fields)
        save(receipts/f'events/{time}-{type}.json',e)
    system='fixture-system'
    event('prompt_binding',11,prompt_sha256=manifest['prompt_sha256'],arm=arm,system_prompt_sha256=ledger.sha(system.encode()))
    prompt=plan['prompt']
    if arm=='prefetch':
        context='Current merchant cards: '+g.jsjson({'gifts':cards}).decode()
        prompt=context+'\n\n'+prompt
        event('prefetch_injection',26,context=context,context_sha256=ledger.sha(context.encode()),prompt_sha256=manifest['prompt_sha256'])
    event('llm_input',30,event=dict(runId='fixture',provider='cerebras',model=g.retail.MODEL,prompt=prompt,systemPrompt=system,historyMessages=[]),prompt_sha256=ledger.sha(prompt.encode()),bound_prompt_sha256=manifest['prompt_sha256'])
    def assistant(content,stop='stop',ms=100,tokens=200):
        return dict(role='assistant',provider='cerebras',model=g.retail.MODEL,responseId='resp-'+str(len(messages)),stopReason=stop,serverGeneration=dict(completionMs=ms,outputTokens=tokens),content=content,__openclaw={'runId':'fixture'})
    messages=[]
    if arm=='tool':
        messages.append(assistant([dict(type='toolCall',id='call-'+str(id),name='gift_lookup',arguments={'id':id}) for id in g.IDS],'toolUse'))
        for card in cards:
            messages.append(dict(role='toolResult',toolName='gift_lookup',toolCallId='call-'+str(card['id']),isError=False,content=[dict(type='text',text=g.jsjson(card).decode())],details={'card':card,'receipt_file':f"fetch-{card['id']}.json"},__openclaw={'runId':'fixture'}))
    messages.append(assistant([dict(type='text',text=g.jsjson({'gifts':cards}).decode())]))
    raw=dict(plan,startedWall=10,ended={'time':100,'terminal':'final'},history={'messages':messages})
    save(root/'raw.json',raw)
    return root,receipts,raw

g.retail.verify_product=lambda item:dict(item,verified=True,reasons=[],http=200)
def run(root,receipts):
    return g.validate(root,root/'raw.json',receipts,plugin_dir=ROOT/'tools/gift8-plugin')
def require(valid,message='assertion failed'):
    assert valid,message
for arm in ['tool','prefetch']:
    root,receipts,raw=fixture(arm)
    result=run(root,receipts)
    check(arm+' happy path with explicitly mocked independent HTTP',lambda:require(result['valid'],result))
    check(arm+' exact arithmetic and threshold',lambda:require(result['score']['mean_exact_tps']==2000 and result['target_met']))
    event_path=next((receipts/'events').glob('*llm_input*')); old=event_path.read_bytes(); event_path.unlink()
    check(arm+' absent first-input rejected',lambda:require(not run(root,receipts)['valid']))
    event_path.write_bytes(old)
    native=json.loads(old); native['event']['prompt']='[native sender context]\n'+native['event']['prompt']; native['prompt_sha256']=ledger.sha(native['event']['prompt'].encode()); native['event']['historyMessages']=[{'role':'user','content':'native runtime context'}]; native['event']['systemPrompt']+='\n<!-- OPENCLAW_CACHE_BOUNDARY -->\n\nCurrent model identity: cerebras/'+g.retail.MODEL+'. If asked what model you are, answer with this value for the current run.'; save(event_path,native)
    check(arm+' native normalized prefix and runtime context accepted',lambda:require(run(root,receipts)['valid'],run(root,receipts)))
    native['event']['historyMessages'].append({'role':'assistant','content':'old answer'}); save(event_path,native)
    check(arm+' prior assistant in first input rejected',lambda:require(not run(root,receipts)['valid']))
    event_path.write_bytes(old)
    repeated=json.loads(old);repeated['timestamp_ms']=60
    retry_path=receipts/'events/60-retry.json';save(retry_path,repeated)
    retry_path2=receipts/'events/61-retry.json';repeated['timestamp_ms']=61;save(retry_path2,repeated)
    check(arm+' repeated dispatch hooks do not create generations',lambda:require(run(root,receipts)['valid'] and run(root,receipts)['llm_input_event_count']==3 and run(root,receipts)['score']['call_count']==len([m for m in raw['history']['messages'] if m['role']=='assistant'])))
    for field,value in [('runId','foreign'),('provider','foreign'),('sessionId','foreign')]:
        altered=copy.deepcopy(repeated);altered['event'][field]=value;save(retry_path2,altered)
        check(arm+' foreign later input '+field+' rejected',lambda:require(not run(root,receipts)['valid']))
    retry_path.unlink();retry_path2.unlink()
    tampered=json.loads(old);tampered['event']['systemPrompt']+='\nInjected system suffix';save(event_path,tampered)
    check(arm+' foreign first system suffix rejected',lambda:require(not run(root,receipts)['valid']))
    event_path.write_bytes(old)
    for name,change in [('foreign',lambda r:r.update(sessionKey='foreign')),('stale',lambda r:r.update(started_ms=0)),('spoofed hash',lambda r:r.update(body_sha256='0'*64))]:
        p=receipts/f'fetch-{g.IDS[0]}.json'; old=p.read_bytes(); r=json.loads(old); change(r); save(p,r)
        check(arm+' '+name+' rejected with score retained',lambda:require(not run(root,receipts)['valid'] and run(root,receipts)['score']['mean_exact_tps']==2000))
        p.write_bytes(old)
    altered=copy.deepcopy(raw); final=altered['history']['messages'][-1]; cards=json.loads(final['content'][0]['text']); cards['gifts'].reverse(); final['content'][0]['text']=json.dumps(cards); save(root/'raw.json',altered)
    check(arm+' reordered final rejected',lambda:require(not run(root,receipts)['valid']))
    save(root/'raw.json',raw)
    if arm=='tool':
        projected=copy.deepcopy(raw)
        for message in projected['history']['messages']:
            if message.get('role')=='toolResult': message.pop('details')
        save(root/'raw.json',projected)
        check('native display projection without private details accepted',lambda:require(run(root,receipts)['valid']))
        for field,value in [('toolName','foreign_lookup'),('details',{'card':{},'receipt_file':'foreign.json'}),('content',[{'type':'text','text':json.dumps({'tool':{'id':'gift_lookup','source':'plugin'},'result':{'card':cards}})}])]:
            altered=copy.deepcopy(projected); altered['history']['messages'][1][field]=value; save(root/'raw.json',altered)
            check('spoofed native result '+field+' rejected',lambda:require(not run(root,receipts)['valid']))
        save(root/'raw.json',raw)
        altered=copy.deepcopy(raw); msgs=altered['history']['messages']; msgs[0],msgs[1]=msgs[1],msgs[0]; save(root/'raw.json',altered)
        check('reordered native result rejected',lambda:require(not run(root,receipts)['valid']))
        altered=copy.deepcopy(raw); extra=copy.deepcopy(altered['history']['messages'][0]); extra['content']=[]; extra['responseId']='extra'; extra['serverGeneration']={'completionMs':100,'outputTokens':50}; altered['history']['messages'].insert(0,extra); save(root/'raw.json',altered)
        scored=run(root,receipts)
        check('all three actual calls included',lambda:require(scored['score']['call_count']==3 and scored['score']['mean_exact_tps']==1500 and not scored['target_met']))
        extra['serverGeneration']={}; save(root/'raw.json',altered)
        scored=run(root,receipts)
        check('invalid generation rejects but retains available authentic score',lambda:require(not scored['valid'] and scored['score']['call_count']==2 and scored['score']['mean_exact_tps']==2000))
        save(root/'raw.json',raw)
    if arm=='prefetch':
        extra=copy.deepcopy(raw); msgs=extra['history']['messages']; final=msgs.pop(); cards=json.loads(final['content'][0]['text'])['gifts']
        first=copy.deepcopy(final); first['stopReason']='toolUse'; first['responseId']='extra-prefetch'; first['serverGeneration']={'completionMs':100,'outputTokens':100}; first['content']=[dict(type='toolCall',id='extra-'+str(id),name='gift_lookup',arguments={'id':id}) for id in g.IDS];msgs.append(first)
        for card in cards:
            callid='extra-'+str(card['id']);msgs.append(dict(role='toolResult',toolName='gift_lookup',toolCallId=callid,isError=False,content=[dict(type='text',text=g.jsjson(card).decode())],__openclaw={'runId':'fixture'}))
            save(receipts/'calls'/(ledger.sha(callid.encode())+'.json'),dict(id='fixture',sessionKey='fixture-session',arm='prefetch',product_id=card['id'],tool_call_id=callid,receipt_file=f"fetch-{card['id']}.json",card_sha256=ledger.sha(g.jsjson(card)),timestamp_ms=50))
        msgs.append(final);save(root/'raw.json',extra); scored=run(root,receipts)
        check('prefetch genuine extra five calls valid with both generations scored',lambda:require(scored['valid'] and scored['score']['mean_exact_tps']==1500 and scored['actual_generation_count']==2 and not scored['structure_expected'],scored))
        link_path=next((receipts/'calls').glob('*.json'));original_link=link_path.read_bytes()
        for field,value in [('sessionKey','foreign'),('card_sha256','0'*64),('tool_call_id','foreign-call')]:
            link=json.loads(original_link);link[field]=value;save(link_path,link)
            check('prefetch extra call spoofed '+field+' rejected',lambda:require(not run(root,receipts)['valid']))
        link_path.write_bytes(original_link)
        g.finish(root,root/'raw.json',scored,receipts,plugin_dir=ROOT/'tools/gift8-plugin')
        check('prefetch extra call receipts committed exact',lambda:require((root/'runs/fixture/gift-receipts/calls'/link_path.name).read_bytes()==original_link))
        (receipts/'private-raw.json').unlink(); (root/'runs/fixture/evidence.json').unlink()
        save(root/'raw.json',raw)
        p=next((receipts/'events').glob('*prefetch_injection*')); old=p.read_bytes(); p.unlink()
        check('prefetch without injection rejected',lambda:require(not run(root,receipts)['valid']))
        p.write_bytes(old)
    result=run(root,receipts)
    finished=g.finish(root,root/'raw.json',result,receipts,plugin_dir=ROOT/'tools/gift8-plugin')
    check(arm+' finish stores exact private original and committed evidence',lambda:require(finished['valid'] and (receipts/'private-raw.json').read_bytes()==(root/'raw.json').read_bytes() and subprocess.check_output(['git','-C',str(root),'show','HEAD:runs/fixture/evidence.json'])))
(ROOT/'.omo/evidence/gift8-validator/results.json').write_text(json.dumps({'mode':'offline fixtures; independent HTTP explicitly mocked, no real run claimed','checks':checks},indent=2)+'\n')
