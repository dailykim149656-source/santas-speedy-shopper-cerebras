"""Verify one-generation shopping evidence locally, without issuing catalog or model requests."""
import argparse
from collections import Counter
from datetime import datetime
from decimal import Decimal
import hashlib
import json
import math
import os
from pathlib import Path
import re
from statistics import mean, median
from tempfile import NamedTemporaryFile
from urllib.parse import parse_qs, urlsplit, urlunsplit
from uuid import UUID
from zoneinfo import ZoneInfo

from scoring import call_rate, mean_rate, round_rate

QUERIES = ['collapsible coffee dripper', 'cast iron skillet', 'enamel camp mug', 'leather pocket journal', 'leather keychain']
TYPES = [r'dripper|pour[ -]?over', r'skillet|frying pan|fry pan', r'\bmugs?\b', r'journal|notebook', r'key[ -]?(chain|ring|fob)']
ENDPOINT = 'https://catalog.shopify.com/api/ucp/mcp'
PROFILE = 'https://shopify.dev/ucp/agent-profiles/examples/2026-08-25/valid-with-capabilities.json'
MODEL = 'moonshotai-kimi-k3.1-pro-trial'
KST = ZoneInfo('Asia/Seoul')
D5027 = mean_rate([call_rate(447, 431.721325), call_rate(161, 96.180553)])
REFERENCE = '121842981f3214db7066de4f12540d51195bcc36'


def read(path):
    return json.loads(path.read_bytes())


def optional(path):
    return read(path) if path.is_file() else {}


def digest(body):
    return hashlib.sha256(body).hexdigest()


def need(check, message):
    if not check:
        raise ValueError(message)


def close(x, y):
    return type(x) in (int, float) and type(y) in (int, float) and math.isclose(x, y, rel_tol=1e-10, abs_tol=1e-8)


def documents(raw):
    text = raw.decode('utf-8')
    if text.lstrip().startswith('{'):
        return [json.loads(text)]
    docs = []
    for block in re.split(r'\r?\n\r?\n', text):
        payload = '\n'.join(line[5:].lstrip() for line in block.splitlines() if line.startswith('data:'))
        if payload and payload != '[DONE]':
            docs.append(json.loads(payload))
    return docs


def text_field(text):
    entities = {'amp': '&', 'nbsp': ' ', 'quot': '"', 'apos': "'", '#39': "'", 'rsquo': '’', 'mdash': '—', 'ndash': '–'}
    text = re.sub(r'<[^>]*>', ' ', text or '')
    text = re.sub(r'&([\w#]+);', lambda m: entities.get(m[1], ' '), text)
    text = re.sub(r'https?://\S+', '', text, flags=re.I)
    text = re.sub(r'[<>*_\x60\[\]#]', '', text)
    return ' '.join(re.sub(r'[\x00-\x1f\x7f]', ' ', text).split())


def clipped_description(text):
    clean = text_field(text)
    units = clean.encode('utf-16-le', errors='surrogatepass')
    if len(units) <= 1400:
        return clean
    head = units[:1400].decode('utf-16-le', errors='surrogatepass')
    sentence = max(head.rfind(dot) for dot in ('. ', '! ', '? '))
    if sentence >= 0:
        return head[:sentence + 1]
    return (head[:head.rfind(' ')] if head.rfind(' ') > 0 else head).rstrip()


def direct_link(url):
    u = urlsplit(url)
    need(u.scheme == 'https' and u.hostname and not (u.username or u.password or u.port)
         and re.search(r'(?:^|/)products/[^/]+/?$', u.path), 'invalid direct merchant link')
    values = parse_qs(u.query).get('variant', [])
    need(not values or values[0].isdigit(), 'invalid Shopify variant')
    return urlunsplit(('https', u.hostname.lower(), u.path.rstrip('/'), 'variant='+values[0] if values else '', ''))


def validate_product(folder, id_, index, pref):
    p, row = pref['products'][index], pref['lookups'][index]
    query = QUERIES[index]
    need(row['id'] == id_ and row['query']==query and row['index']==index and row.get('status')==200
         and row.get('ok') is True and row['endpoint']==ENDPOINT, 'invalid search receipt')
    need(pref['startedMs'] <= row['startedMs'] <= row['completedMs'] <= pref['completedMs'], 'search timestamps out of order')
    prefix = 'lookup-'+str(index+1)
    need(read(folder/(prefix+'.json'))==row and row['rawFile']==prefix+'.response.bin'
         and row['requestFile']==prefix+'.request.json', 'saved per-query receipt mismatch')
    request, raw = (folder/row['requestFile']).read_bytes(), (folder/row['rawFile']).read_bytes()
    need(digest(request)==row['requestSha256'] and digest(raw)==row['bodySha256']==p['bodySha256'], 'catalog SHA-256 mismatch')
    req = json.loads(request)
    args = req['params']['arguments']
    need(req['jsonrpc']=='2.0' and req.get('id')==1 and req['method']=='tools/call' and req['params']['name']=='search_catalog'
         and args['meta']['ucp-agent']['profile']==PROFILE and args['catalog']=={
            'query':query, 'context':{'address_country':'US','currency':'USD'},
            'filters':{'ships_to':{'country':'US'},'available':True}, 'pagination':{'limit':10}}, 'different Shopify query or filters')
    responses = [d for d in documents(raw) if 'result' in d or 'error' in d]
    rpc = responses[-1]
    need(not rpc.get('error') and not rpc['result'].get('isError'), 'catalog RPC error')
    need(p['lookupIndex']==index and p['query']==query and p['variantIndex']==0 and type(p['productIndex']) is int
         and p['productIndex']>=0, 'product source index mismatch')
    product = rpc['result']['structuredContent']['products'][p['productIndex']]
    v = product['variants'][0]
    name = text_field(product['title'])
    need(re.search(TYPES[index],name,re.I) and sum(w in name.lower() for w in query.split())*2>=len(query.split()), 'wrong gift type')
    need(v['availability']['available'] is True and v['price']['currency']=='USD' and p['currency']=='USD'
         and type(v['price']['amount']) is int and 0<v['price']['amount']<=5000
         and Decimal(str(p['price']))*100==v['price']['amount'], 'stock or original price mismatch')
    need(p['url']==direct_link(v['url']) and name==p['name'] and text_field(v['seller']['name'])==p['seller']
         and p['seller'] and p['name'], 'product identity, link, or seller mismatch')
    origin = product['description']
    need(p['description'] and p['description']==clipped_description(origin.get('plain') or origin.get('html')),
         'seller description differs from catalog')
    return dict(query=query, name=name, seller=p['seller'],price=p['price'],currency='USD',url=p['url'],
                description=p['description'], receipt=str(folder/(prefix+'.json')), catalog_raw=str(folder/row['rawFile']),
                sha256=row['bodySha256'], started_ms=row['startedMs'],completed_ms=row['completedMs'])


def catalog(folder, slot, session, pref):
    id_ = slot['id']
    intent = read(folder/'prefetch.intent.json')
    need(intent['id']==id_ and intent['queries']==QUERIES and intent['endpoint']==ENDPOINT
         and intent['startedMs']==pref['startedMs'], 'prefetch intent mismatch')
    need(session['id']==id_ and session['sessionKey']==slot['sessionKey'] and session['freshEmptySession'] is True
         and session['createdAt']<=pref['startedMs'], 'fresh session does not precede product searches')
    need(pref['id']==id_ and pref['queries']==QUERIES and pref['valid'] is True and
         len(pref['products'])==len(pref['lookups'])==5,'five live catalog receipts required')
    products=[validate_product(folder,id_,i,pref) for i in range(5)]
    need(max(p['started_ms'] for p in products)<=min(p['completed_ms'] for p in products),'five catalog searches did not overlap')
    need(len({p['url'].split('?')[0] for p in products})==5,'duplicate source product')
    rendered='\n'.join(f"{i}. **{p['name']}** — {p['seller']} — ${p['price']:.2f}\n   {p['url']}\n   {p['description']}"
                       for i,p in enumerate(products,1))
    need(rendered==pref['rendered']==pref['list'],'catalog-rendered list mismatch')
    return products,rendered


def response_values(data):
    docs = documents(data)
    ids={b['id'] for b in docs if b.get('id')}
    usage=timing=None
    fragments=[]
    for event in docs:
        if event.get('usage'):
            usage=event['usage']
        if event.get('time_info'):
            timing=event['time_info']
        for choice in event.get('choices',[]):
            need(choice.get('index',0)==0,'multiple upstream choices')
            body = choice.get('delta') or choice.get('message') or {}
            need(not body.get('tool_calls') and not body.get('function_call'),'unexpected upstream tool call')
            if body.get('content'):
                fragments.append(body['content'])
    need(len(ids)==1 and usage and timing, 'missing unique upstream response ID, usage, or time_info')
    return ids.pop(),usage,timing,''.join(fragments)


def validate_answer(answer,products):
    links = [u.rstrip(').,;!?') for u in re.findall(r'https?://[^\s<>\[\]\x60]+',answer)]
    need(links==[p['url'] for p in products], 'final URL count, identity, or order mismatch')
    sections=re.split(r'(?m)^\s*(?:\*\*)?[1-5][.)](?:\*\*)?\s+',answer)
    need(len(sections)==6,'final answer lacks five ordered numbered entries')
    for p,entry in zip(products,sections[1:]):
        header=entry.split(p['url'],1)[0]
        def label(s):
            return ' '.join(s.casefold().replace('**','').split())
        amounts = re.findall(r'(?:USD\s*\$?\s*|\$\s*)(\d+(?:,\d{3})*(?:\.\d+)?)(?![\d.])',header)
        need(label(p['name']) in label(header) and label(p['seller']) in label(header)
             and Decimal(str(p['price'])) in [Decimal(a.replace(',','')) for a in amounts],
             'final name, seller, or price mismatch for '+p['query'])


def verify_generation(folder,slot,deadline,pref,rendered,raw,tr,products):
    d = folder/'transport'
    claim = read(d/'claim.json')
    need(tr['id']==claim['id']==slot['id'] and tr.get('sent') is True
         and tr.get('response_persisted') is True and tr.get('status')==200,'unsuccessful upstream transport')
    need(pref['completedMs']<=raw['sentAt']<=tr['received_ms']<=claim['claimed_ms']<=tr['sent_ms']<deadline
         and tr['sent_ms']<=tr['headers_ms']<=tr['finished_ms'], 'model sent outside verified lookup/deadline interval')
    request, response = (d/'request.json').read_bytes(),(d/'response.bin').read_bytes()
    need(digest(request)==tr['forwarded_sha256'] and len(request)==tr['forwarded_bytes'] and
         digest(response)==tr['response_sha256'] and len(response)==tr['response_bytes'],'model request/response SHA-256 or length mismatch')
    request=json.loads(request)
    expect={'model':MODEL,'messages':[{'role':'system','content':'Zero prose.'},
        {'role':'user','content':rendered+'\n\nRepeat the list above in full.'}],
        'temperature':0.1,'reasoning_effort':'low','max_completion_tokens':2400}
    if 'max_tokens' in request:
        expect['max_tokens']=2400
    if 'stream' in request:
        need(type(request['stream']) is bool,'invalid streaming setting')
        expect['stream']=request['stream']
    if 'stream_options' in request:
        opts=request['stream_options']
        need(isinstance(opts,dict) and set(opts)=={'include_usage'} and type(opts['include_usage']) is bool,'unexpected streaming options')
        expect['stream_options']=opts
    need(request==expect,'model request differed from the exact list and single-call settings')
    response_id,usage,timing,text=response_values(response)
    # Some SDKs close the HTTP stream immediately on [DONE], before Node emits its socket 'end'.
    # Only accept that race with both the provider's stop choice and the final protocol sentinel.
    sse_complete = (response.rstrip().endswith(b'data: [DONE]') and
                    any(c.get('finish_reason')=='stop' for part in documents(response) for c in part.get('choices',[])))
    need(tr.get('complete') is True or sse_complete, 'incomplete provider response with no SSE stop and [DONE]')
    need(response_id==tr['responseId'] and usage==tr['usage'] and timing==tr['time_info'], 'upstream raw/trace metrics mismatch')
    need(raw['id']==slot['id'] and raw['sessionKey']==slot['sessionKey'] and raw['prompt']==slot['prompt']
         and not raw.get('error') and not raw.get('unconfirmedTermination') and raw['ended']['terminal']=='final','unfinished or mismatched session')
    messages=raw['history']['messages']
    users=[m for m in messages if m.get('role')=='user']
    assistants=[m for m in messages if m.get('role')=='assistant']
    def content(m):
        c=m.get('content') or []
        return c if isinstance(c,str) else ''.join(str(p.get('text','')) for p in c if p.get('type')=='text')
    need(len(users)==1 and slot['prompt'] in content(users[0]) and len(assistants)==1 and len(messages)==2,'expected one user and one model response')
    a=assistants[0]
    need(a.get('provider')=='cerebras' and a.get('model')==MODEL and a.get('responseId')==response_id
         and a.get('stopReason')=='stop' and a.get('__openclaw',{}).get('runId')==slot['id'], 'transcript provider or response identity mismatch')
    gen=a['serverGeneration']
    tokens=usage['completion_tokens']
    need(type(tokens) is int and tokens>0 and gen.get('outputTokens')==tokens and a['usage']['output']==tokens
         and timing['completion_time']>0 and close(gen['completionMs'],timing['completion_time']*1000), 'server token count or generation time mismatch')
    tps=call_rate(tokens,gen['completionMs'])
    official=raw['official']
    need(official['calls']==1 and official['outputTokens']==tokens and close(official['generationMs'],gen['completionMs'])
         and close(official['meanTokensPerSecond'],tps) and close(official['p90TokensPerSecond'],tps), 'official score disagrees with upstream single call')
    answer=content(a)
    need(answer.strip()==text.strip(), 'final text differs from upstream response')
    validate_answer(answer,products)
    return dict(calls=1,response_id=response_id,output_tokens=tokens,generation_ms=gen['completionMs'],
                mean_tps=official['meanTokensPerSecond'],p90_tps=official['p90TokensPerSecond'],exact_copy=answer.strip()==rendered,
                started_ms=raw['sentAt'],ended_ms=raw['ended']['time'],model_request=str(d/'request.json'),
                model_response=str(d/'response.bin'),trace=str(d/'trace.json'),response_sha256=tr['response_sha256'],
                response_completion='http_end' if tr.get('complete') is True else 'sse_stop_and_done')


def video(folder,raw,slot,pref):
    official=raw.get('official') or {}
    mean_tps=official.get('meanTokensPerSecond')
    expected_urls=[p['url'] for p in pref.get('products',[])]
    best=None
    for media in [folder/'media',*sorted(folder.glob('media-post-run*'))]:
        film=optional(media/'film.json')
        ready=optional(media/'ready.json')
        if not film or film.get('run_id')!=slot['id'] or film.get('sessionKey')!=slot['sessionKey']:
            continue
        path=media/'demo.mp4'
        original=media/'original.mp4'
        if not path.is_file() or not original.is_file() or not path.stat().st_size or not original.stat().st_size:
            continue
        evidence=optional(media/'viewport-evidence.json')
        screen=(len(expected_urls)==5 and evidence.get('verified') is True and film.get('viewport_verified') is True
                and mean_tps is not None and evidence.get('score',{}).get('mean')==round_rate(mean_tps)
                and {entry.get('url') for entry in evidence.get('links',[])}==set(expected_urls))
        try:
            ready_ms=datetime.fromisoformat((film.get('readyAt') or ready['readyAt']).replace('Z','+00:00')).timestamp()*1000
        except (ValueError,TypeError,KeyError,AttributeError):
            ready_ms=None
        post=media.name.startswith('media-post-run') or film.get('post_run_requested') is True
        before=not post and film.get('full_run') is True and ready_ms is not None and ready_ms<=(raw.get('sentAt') or 0)
        early=before and ready_ms<=pref.get('startedMs',0)
        status='사후 녹화' if post else '조회 전부터 녹화' if early else '모델 전송 전부터 녹화' if before else '녹화 시작 시각 미확인'
        if not screen:
            status+=' · 화면 미검증'
        duration=(optional(media/'ffprobe.json').get('format') or {}).get('duration')
        option=dict(status=status,path=str(path),original=str(original),viewport_verified=screen,full_run=before,before_shopify=early,
                    post_run=post,seconds=float(duration) if duration is not None else None,
                    viewport=str(media/'viewport-evidence.json') if screen else None)
        rank=(screen, before, early)
        if best is None or rank>best[0]:
            best=rank,option
    if best:
        return best[1]
    if (folder/'media/film.json').is_file():
        return dict(status='전체 영상 미확인',path=None)
    return dict(status='녹화 증빙 대기' if (folder/'media/ready.json').is_file() else '녹화 증빙 없음',path=None)


def inspect_bytes(folder,pref,tr):
    lookups=[]
    for i,r in enumerate(pref.get('lookups',[])):
        prefix='lookup-'+str(i+1)
        actual=False
        if r.get('rawFile') is not None:
            need(r.get('requestFile')==prefix+'.request.json' and r['rawFile']==prefix+'.response.bin'
                 and digest((folder/r['requestFile']).read_bytes())==r['requestSha256']
                 and digest((folder/r['rawFile']).read_bytes())==r['bodySha256'],'lookup request or response file mismatch')
            actual=True
        lookups.append(dict(query=r.get('query'),http=r.get('status'),response_sha_verified=actual,
                            error=r.get('error'),started_ms=r.get('startedMs'),ended_ms=r.get('completedMs')))
    checked=False
    if tr.get('response_persisted') is True:
        transport=folder/'transport'
        for name,column in [('request.json','forwarded'),('response.bin','response')]:
            b=(transport/name).read_bytes()
            need(digest(b)==tr[column+'_sha256'] and len(b)==tr[column+'_bytes'],'upstream transport file mismatch')
        checked=True
    return lookups,checked


def assess(out,slot,deadline):
    folder=out/slot['id']
    rawpath=out/(slot['label']+'.json')
    row={'slot':slot['slot'],'id':slot['id'],'label':slot['label'],'attempted':False,'model_sent':False,'model_429':False,
         'shopify_429':False,'catalog_5of5':False,'valid':False,'products':[],'stage':'미배정','mean_tps':None,'raw_session':str(rawpath)}
    try:
        need(str(UUID(slot['id']))==slot['id'] and re.fullmatch(r'slot-\d+-shopify',slot['label']), 'invalid slot identity')
        session=optional(out/'sessions'/(slot['id']+'.json'))
        raw=optional(rawpath)
        # Sessions and provider requests have distinct start markers.
        row['attempted']=bool(folder.is_dir() or rawpath.is_file() or session)
        if not row['attempted']:
            return row
        row['stage']='상품 조회'
        pref=optional(folder/'prefetch.json')
        tr=optional(folder/'transport/trace.json')
        row['model_sent']=tr.get('sent') is True
        row['native_calls']=(raw.get('official') or {}).get('calls',0)
        row['native_reported_tps']=(raw.get('official') or {}).get('meanTokensPerSecond')
        row['model_status']=tr.get('status')
        row['observed_response_id']=tr.get('responseId')
        row['upstream_outcome']=tr.get('complete')
        row['model_429']=tr.get('status')==429 or any(x.get('status')==429 for x in raw.get('providerFailures',[]))
        row['shopify_429']=any(x.get('status')==429 for x in pref.get('lookups',[]))
        row['started_ms']=session.get('createdAt',pref.get('startedMs',raw.get('startedWall')))
        row['ended_ms']=raw.get('endedAt') or tr.get('finished_ms') or pref.get('completedMs')
        try:
            row['video']=video(folder,raw,slot,pref)
        except (ValueError, TypeError, OSError, KeyError) as video_error:
            row['video']={'status':'녹화 시각·파일 미확인','path':None,'error_type':type(video_error).__name__}
        row['lookups'],row['transport_bytes_verified']=inspect_bytes(folder,pref,tr)
        if not pref:
            if not (raw.get('ended') or {}).get('terminal'):
                row.update(stage='조회 영수증 대기')
                return row
            raise ValueError(raw.get('error') or 'missing prefetch evidence')
        if not pref.get('valid'):
            errors=[f"{x.get('query')} HTTP {x.get('status')} · {x.get('error','duplicate or missing selection')}" for x in pref.get('lookups',[]) if not x.get('ok')]
            raise ValueError(', '.join(errors) or 'five distinct eligible catalog products unavailable')
        row['products'],rendered=catalog(folder,slot,session,pref)
        row['catalog_5of5']=True
        if not tr and not raw.get('ended'):
            row.update(stage='모델 전송·종료 영수증 대기')
            return row
        row['stage']='Cerebras 429' if row['model_429'] else '모델 단일 호출·최종 답변 검증'
        row.update(verify_generation(folder,slot,deadline,pref,rendered,raw,tr,row['products']))
        row.update(valid=True,stage='유효',terminal_by_cutoff=row['ended_ms']<=deadline)
    except (OSError,ValueError,KeyError,TypeError,IndexError,AttributeError,ArithmeticError) as error:
        reason=str(error)
        row['reason']=reason if reason else type(error).__name__
        if row['shopify_429'] and not row['catalog_5of5']:
            row['stage']='Shopify 429'
    return row


def summarize(rows):
    seen=Counter(r.get('observed_response_id') for r in rows if r.get('observed_response_id'))
    for r in rows:
        if r['valid'] and seen[r['response_id']]!=1:
            r.update(valid=False,stage='중복 모델 응답',reason='provider response ID reused')
    valid=[r for r in rows if r['valid']]
    rates=[r['mean_tps'] for r in valid]
    attempts=[r for r in rows if r['attempted']]
    best=max(valid,key=lambda r:r['mean_tps']) if valid else None
    filmed=[r for r in valid if r.get('video',{}).get('full_run') and r['video'].get('viewport_verified')]
    film_best=max(filmed,key=lambda r:r['mean_tps']) if filmed else None
    return dict(best_live_model_video_slot=film_best['slot'] if film_best else None,
                best_live_model_video_id=film_best['id'] if film_best else None,best_id=best['id'] if best else None,
                best_display_slot=slot_name(best) if best else None,
                best_live_model_video_display_slot=slot_name(film_best) if film_best else None,
                best_live_model_video_tps=film_best['mean_tps'] if film_best else None,
                valid_with_live_model_video=len(filmed), planned=len(rows),attempts=len(attempts),model_sent=sum(r['model_sent'] for r in rows),
                provider_429_sessions=sum(r['model_429'] for r in rows),shopify_429_sessions=sum(r['shopify_429'] for r in rows),
                catalog_5of5=sum(r['catalog_5of5'] for r in rows),valid=len(valid),
                average_tps=mean(rates) if rates else None,median_tps=median(rates) if rates else None,
                best_tps=max(rates) if rates else None,best_slot=best['slot'] if best else None,d5027_tps=D5027,
                above_d5027=sum(s>D5027 for s in rates),above_1500=sum(s>1500 for s in rates),above_1673=sum(s>1673 for s in rates),
                stages=dict(Counter(r['stage'] for r in attempts))),best


def local_time(ms):
    return datetime.fromtimestamp(ms/1000,KST).strftime('%H:%M:%S') if isinstance(ms,(int,float)) else '—'


def fmt(value):
    return '—' if value is None else f'{value:,.2f}'


def link(name,path):
    return f'[{name}](<{path}>)'


def slot_name(row):
    return row.get('display_slot',str(row['slot']))


def markdown(result):
    summary, best = result['summary'],result['best']
    rows=[r for r in result['trials'] if r['attempted']]
    lines=['# Shopify 선조회 단일 생성 실험','',
           f"{result['as_of']} KST 집계. 이번 회차의 다섯 Shopify 응답으로 목록을 구성하고 Kimi 서버 생성 한 번의 공식 TPS를 측정했다. 상품 검증은 각 회차에서 받은 Shopify 재고·판매자·가격·상품 URL 원문을 기준으로 했다. 검색 및 녹화 시간은 TPS에 들어가지 않는다.",'',
           f"시도 {summary['attempts']}회, 모델 전송 확인 {summary['model_sent']}회, Shopify 원문 5/5 검증 {summary['catalog_5of5']}회, 유효 {summary['valid']}회. Cerebras 429를 받은 세션 {summary['provider_429_sessions']}회, Shopify 429를 받은 세션 {summary['shopify_429_sessions']}회.",'',
           f"유효 세션 평균 {fmt(summary['average_tps'])} TPS, 중앙값 {fmt(summary['median_tps'])} TPS, 최고 {fmt(summary['best_tps'])} TPS. 과거 D5027 원점수 {D5027:,.8f} 초과 {summary['above_d5027']}회, 1,500 초과 {summary['above_1500']}회, 1,673 초과 {summary['above_1673']}회.",'',
           '## 실행별 기록','',
           '| 슬롯 | 시작~종료 KST | 소요 초 | 카탈로그 5/5 | 모델 전송 | 판정 | 모델 호출 | 출력 토큰 | 서버 생성 ms | 유효 TPS | 녹화 |',
           '|---|---|---:|---|---|---|---:|---:|---:|---:|---|']
    for r in rows:
        ms=r.get('ended_ms')
        start=r.get('dispatch_ms',r.get('started_ms'))
        sec=fmt((ms-start)/1000) if isinstance(ms,(int,float)) and isinstance(start,(int,float)) else '—'
        vid=r.get('video',{})
        status=link(vid['status'],vid['path']) if vid.get('path') else vid.get('status','—')
        reference=r['raw_session'] if Path(r['raw_session']).is_file() else result['plan']
        lines.append('| '+' | '.join(map(str,[link(slot_name(r),reference),local_time(start)+'~'+local_time(ms),sec,
                     '예' if r['catalog_5of5'] else '미확인','예' if r['model_sent'] else '미확인',r['stage'],
                     r.get('native_calls','—'),r.get('output_tokens','—'),fmt(r.get('generation_ms')),fmt(r['mean_tps']) if r['valid'] else '—',status]))+' |')
    sse_completed=[slot_name(r) for r in rows if r.get('response_completion')=='sse_stop_and_done']
    if sse_completed:
        lines += ['', '슬롯 '+', '.join(sse_completed)+'은 전송 소켓의 종료 표식보다 먼저 스트림이 닫혔다. 저장한 SSE 원문에 최종 stop과 [DONE]이 있고, 응답 ID·토큰·서버 생성 시간·최종 텍스트가 OpenClaw 원본과 일치해 유효로 집계했다.']
    filmed=next((r for r in rows if r['id']==summary['best_live_model_video_id']),None)
    if filmed:
        lines += ['', f"모델 전송 전부터 화면에 점수와 다섯 링크가 기록된 유효 세션은 {summary['valid_with_live_model_video']}건이다. 이 중 최고는 슬롯 {slot_name(filmed)}의 {fmt(filmed['mean_tps'])} TPS다. "
                  +link(filmed['video']['status'],filmed['video']['path'])]
    if best:
        lines += ['','## 최고 세션 증빙','',
                  f"슬롯 {slot_name(best)}은 서버 응답 {best['response_id']}에서 출력 {best['output_tokens']}토큰, 생성 {best['generation_ms']:.5f}ms를 기록했다. 공식 평균과 p90는 모두 {best['mean_tps']:,.5f} TPS다. "
                  +link('OpenClaw 원본',best['raw_session'])+' · '+link('실제 전송 본문',best['model_request'])+' · '
                  +link('Cerebras 응답 원본',best['model_response'])+' · '+link('전송 영수증',best['trace']),'',
                  '| 검색어 | 상품 | 판매처 | USD | 조회 원문 |','|---|---|---|---:|---|']
        for p in best['products']:
            name=p['name'].replace('|','\\|').replace('[','\\[').replace(']','\\]')
            seller=p['seller'].replace('|','\\|')
            lines.append(f"| {p['query']} | {link(name,p['url'])} | {seller} | {p['price']:.2f} | {link('HTTP 200 · SHA 일치',p['catalog_raw'])} |")
        vid=best['video']
        caption=vid['status']+(f" {vid['seconds']:.2f}초" if vid.get('seconds') is not None else '')
        lines += ['', '영상 · '+(link(caption,vid['path']) if vid.get('path') else caption)+
                  (' · '+link('화면 점수와 다섯 링크',vid['viewport']) if vid.get('viewport') else '')+'.']
    elif rows:
        last=rows[-1]
        lines += ['',f"마지막 확인 단계는 슬롯 {slot_name(last)}의 {last['stage']}다. {last.get('reason','')}"]
    failed=[r for r in rows if not r['valid'] and r.get('reason')]
    if failed:
        lines += ['','## 미확정·실패 사유','']
        lines += [f"- 슬롯 {slot_name(r)} · {r['stage']} · {r['reason']}" for r in failed]
    segments=result.get('segments',[])
    if segments:
        lines += ['','## 구간별 결과','',
                  '| 구간 | 시도 | 모델 전송 | 상품 5/5 | 유효 | 모델 / 판매처 429 | 평균 TPS | 중앙값 | 최고 TPS |',
                  '|---|---:|---:|---:|---:|---:|---:|---:|---:|']
        for segment in segments:
            t=segment['summary']
            lines += [f"| {link(segment['name'],segment['plan'])} | {t['attempts']} | {t['model_sent']} | {t['catalog_5of5']} | {t['valid']} | {t['provider_429_sessions']} / {t['shopify_429_sessions']} | {fmt(t['average_tps'])} | {fmt(t['median_tps'])} | {fmt(t['best_tps'])} |"]
    else:
        lines += ['',link('실행 계획',result['plan'])]
    lines += ['',link('전체 감사 결과',result['output_json'])]
    return '\n'.join(lines)+'\n'


def write_report(path,body):
    with NamedTemporaryFile('w',encoding='utf-8',dir=path.parent,delete=False,prefix='.report-') as f:
        f.write(body)
        name=f.name
    os.replace(name,path)


def build(out):
    plan=read(out/'plan.json')
    need(plan['source']==REFERENCE and plan['protocol']=='simethan-shopify-v1','unexpected shopping protocol or source')
    runtime=plan['runtime']
    need(runtime['model']=='cerebras/'+MODEL and runtime['tree']=='aec08de95dc279d3c2a5ef46c641ae31b7a0e219'
         and runtime['patchSha256']=='c964a28808c8d9e33aaaa2897dea951e595dd35c2d4047484eb6e5e97059c9c0'
         and runtime['officialPatch']=='e40e9f7b7ec41ad3fa68181ad297db119e755171','unverified official OpenClaw runtime identity')
    ids=[s['id'] for s in plan['trials']]
    need(len(set(ids))==len(ids) and len({s['label'] for s in plan['trials']})==len(ids),'trial plans collide')
    events={}
    event_file=out/'events.jsonl'
    if event_file.is_file():
        for line in event_file.read_bytes().splitlines(keepends=True):
            if line.endswith(b'\n'):
                e=json.loads(line)
                need(e['id'] not in events and e['id'] in ids, 'unexpected or duplicated slot dispatch')
                events[e['id']]=e
    deadline=datetime.fromisoformat(plan['deadline']).timestamp()*1000
    rows=[]
    for slot in plan['trials']:
        need(slot['model']=='cerebras/'+MODEL and slot['thinking']=='low' and slot['temperature']==0.1 and slot['max_completion_tokens']==2400
             and slot['prompt'].splitlines()[1:]==['- '+q for q in QUERIES], 'different committed source shopping task or generation settings')
        row=assess(out,slot,deadline)
        event=events.get(slot['id'])
        if event:
            need(slot['label']==event['slot'], 'dispatch label mismatch')
            row['dispatch_ms']=event['dispatch']*1000
            if not row['attempted']:
                row.update(attempted=True,stage='세션 생성·종료 영수증 대기')
        rows.append(row)
    summary,best=summarize(rows)
    return dict(as_of=datetime.now(KST).strftime('%Y-%m-%d %H:%M:%S'),plan=str(out/'plan.json'),deadline=plan['deadline'],
                output_json=str(out/'report.json'),summary=summary,trials=rows,best=best)


def combined_result(directories):
    need(len(set(directories))==len(directories),'campaign directory included twice')
    rows,segments=[],[]
    last_deadline=0
    active_ids=set()
    for out in directories:
        part=build(out)
        deadline=datetime.fromisoformat(part['deadline'])
        need(deadline.timestamp()>last_deadline,'supply campaigns in strictly increasing deadline order')
        last_deadline=deadline.timestamp()
        name=deadline.astimezone(KST).strftime('%H:%M')+' 마감'
        for row in part['trials']:
            need(row['id'] not in active_ids, 'run UUID reused across campaign windows')
            active_ids.add(row['id'])
            row.update(segment=name,segment_dir=str(out),display_slot=f"{name} #{row['slot']}")
        segments.append(dict(name=name,directory=str(out),plan=part['plan'],deadline=part['deadline'],summary=part['summary']))
        rows.extend(part['trials'])
    totals,best=summarize(rows)
    # Apply global response deduplication to stage summaries as well.
    for seg in segments:
        seg['summary'],_=summarize([r for r in rows if r['segment_dir']==seg['directory']])
    return dict(as_of=datetime.now(KST).strftime('%Y-%m-%d %H:%M:%S'),segments=segments,deadline=segments[-1]['deadline'],
                output_json=str(directories[-1]/'combined-report.json'),summary=totals,trials=rows,best=best)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory',type=Path)
    parser.add_argument('--include',action='append',type=Path,default=[],metavar='LATER_OUT',
                        help='audit another campaign together; write combined files in the last directory')
    args=parser.parse_args()
    directories=[d.resolve() for d in [args.directory,*args.include]]
    out=directories[-1]
    result=combined_result(directories) if args.include else build(out)
    stem='combined-report' if args.include else 'report'
    write_report(out/(stem+'.json'),json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
    write_report(out/(stem+'.md'),markdown(result))
    print(json.dumps(result['summary'],ensure_ascii=False))


if __name__=='__main__':
    main()
