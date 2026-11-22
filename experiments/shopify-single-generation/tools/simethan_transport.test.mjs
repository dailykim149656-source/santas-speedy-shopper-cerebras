import assert from 'node:assert/strict';
import fs from 'node:fs';
import http from 'node:http';
import os from 'node:os';
import path from 'node:path';
import {randomUUID, createHash} from 'node:crypto';
import test from 'node:test';
import {createTransport} from './simethan_transport.mjs';

const sha=bytes=>createHash('sha256').update(bytes).digest('hex');
const tagged='test-local-simethan-secret';
const listen=s=>new Promise(resolve=>s.listen(0,'127.0.0.1',()=>resolve('http://127.0.0.1:'+s.address().port)));
const close=s=>new Promise(resolve=>{s.close(resolve);s.closeAllConnections();});

test('one exclusively bound gateway call preserves streamed responses, 429 and authentic timing',async t=>{
  const root=fs.mkdtempSync(path.join(os.tmpdir(),'simethan-transport-'));
  t.after(()=>fs.rmSync(root,{recursive:true,force:true}));
  const sends=[];
  const sse=Buffer.from('data: {"id":"test-1","choices":[{"delta":{"content":"snow"}}]}\r\n\r\n'
    +'data: {"id":"test-1","usage":{"completion_tokens":703},"time_info":{"completion_time":0.467}}\n\ndata: [DONE]\n\n');
  let status=200;
  const mock=http.createServer(async(req,res)=>{
    assert.equal(req.headers.authorization,'Bearer '+tagged);
    const parts=[];for await (const p of req) parts.push(p);
    sends.push(Buffer.concat(parts));
    res.writeHead(status,{'content-type':status===200?'text/event-stream':'application/json','x-origin-test':'preserved'});
    if (status===200) {res.write(sse.subarray(0,23));setTimeout(()=>res.end(sse.subarray(23)),5);}
    else res.end('{"error":"queue_exceeded"}');
  });
  const upstream=await listen(mock);t.after(()=>close(mock));
  const server=createTransport({root,upstream});const addr=await listen(server);t.after(()=>close(server));
  const prompt='Find five Christmas gifts under $50.';
  const headers={'content-type':'application/json','authorization':'Bearer '+tagged};
  const base={model:'moonshotai-kimi-k3.1-pro-trial',messages:[{role:'system',content:'original system discarded'},
    {role:'user',content:[{type:'text',text:'[time] '+prompt}]}],tools:[{type:'function'}],
    parallel_tool_calls:true,tool_choice:'auto',temperature:.2,max_completion_tokens:1024,stream:true};
  const send=(body=base)=>fetch(addr+'/v1/chat/completions',{method:'POST',headers,body:JSON.stringify(body)});
  function bind(deadline=Date.now()+30000){
    const id=randomUUID();const p=path.join(root,id);fs.mkdirSync(p);
    const products=Array.from({length:5},(_,i)=>({url:'https://example.com/products/'+i}));
    const rendered=products.map(q=>q.url).join('\n');
    fs.writeFileSync(path.join(root,'active.json'),JSON.stringify({id,deadline,prompt}));
    fs.writeFileSync(path.join(p,'prefetch.json'),JSON.stringify({id,startedMs:Date.now()-100,
      completedMs:Date.now()-10,valid:true,products,lookups:products.map(()=>({status:200,bodySha256:'0'.repeat(64)})),rendered}));
    return {dir:path.join(p,'transport'),rendered};
  }
  const first=bind();
  assert.equal((await send({...base,messages:[{role:'user',content:'other'}]})).status,422);
  const [a,b]=await Promise.all([send(),send()]);
  assert.deepEqual([a.status,b.status].sort(),[200,409]);assert.equal(sends.length,1);
  const good=a.status===200?a:b;
  assert.equal(good.headers.get('x-origin-test'),'preserved');
  assert.deepEqual(Buffer.from(await good.arrayBuffer()),sse);
  assert.deepEqual(fs.readFileSync(path.join(first.dir,'request.json')),sends[0]);
  assert.deepEqual(fs.readFileSync(path.join(first.dir,'response.bin')),sse);
  const actual=JSON.parse(sends[0]);
  assert.deepEqual(actual,{model:base.model,messages:[{role:'system',content:'Zero prose.'},
    {role:'user',content:first.rendered+'\n\nRepeat the list above in full.'}],temperature:.1,
    reasoning_effort:'low',max_completion_tokens:2400,stream:true});
  const trace=JSON.parse(fs.readFileSync(path.join(first.dir,'trace.json')));
  assert.equal(trace.response_sha256,sha(sse));assert.equal(trace.forwarded_sha256,sha(sends[0]));
  assert.equal(trace.usage.completion_tokens,703);assert.equal(trace.time_info.completion_time,.467);
  assert.equal(trace.responseId,'test-1');assert.equal(trace.complete,true);
  for (const f of fs.readdirSync(first.dir)) assert.equal(fs.readFileSync(path.join(first.dir,f)).includes(tagged),false);
  status=429;const second=bind();const limited=await send();assert.equal(limited.status,429);
  assert.equal(await limited.text(),'{"error":"queue_exceeded"}');
  assert.equal(JSON.parse(fs.readFileSync(path.join(second.dir,'trace.json'))).rate_limited,true);
  assert.equal((await send()).status,409);assert.equal(sends.length,2);
  bind(Date.now()-1);assert.equal((await send()).status,422);assert.equal(sends.length,2);
});
