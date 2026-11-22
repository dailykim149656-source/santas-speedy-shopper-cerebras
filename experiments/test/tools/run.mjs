import fs from 'node:fs/promises';
import {execFileSync} from 'node:child_process';
import os from 'node:os';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
const root=process.env.BOUNTY_ROOT || path.join(os.homedir(),'Library/Caches/cerebras-speed-bounty/2026-11-22');
const state=path.join(root,'shopper-test');
const gatewayPort=process.env.BOUNTY_GATEWAY_PORT || '19862';
if (!/^[0-9]{4,5}$/.test(gatewayPort)) throw Error('invalid gateway port');
const out=path.join(root,'mean-2000','runs');
process.env.OPENCLAW_STATE_DIR=state;
process.env.OPENCLAW_CONFIG_PATH=path.join(state,'openclaw.json');
const {GatewayClient}=await import(pathToFileURL(path.join(root,'openclaw/dist/plugin-sdk/gateway-runtime.js')));
const input=JSON.parse(await fs.readFile(process.argv[2],'utf8'));
const label=input.label;
if (!/^[A-Za-z0-9-]{1,52}$/.test(label))throw Error('invalid label');
const id=input.id;
if (!/^[0-9a-f-]{36}$/.test(id)) throw Error('Expected a precommitted run ID');
const sessionKey=input.sessionKey;
if (sessionKey!=='agent:main:shop-'+label.toLowerCase()+'-'+id.slice(0,8))throw Error('Session key does not match plan');
const scoreFirst = input.capturePolicy === 'score-first';
if (input.capturePolicy !== undefined && !scoreFirst) throw Error('Unknown capture policy');
if (scoreFirst) {
  if (process.env.BOUNTY_SCHEDULE !== 'test' || !process.env.BOUNTY_ROOT || gatewayPort === '19862') {
    throw Error('Score-first capture requires the isolated test schedule');
  }
  const committed = JSON.parse(execFileSync('git', ['show', `HEAD:runs/${id}/plan.json`], {
    cwd: new URL('../', import.meta.url), encoding: 'utf8',
  }));
  if (['id', 'label', 'sessionKey', 'prompt', 'capturePolicy'].some(key => input[key] !== committed[key]) || input.readyPath !== undefined) {
    throw Error('Score-first inputs differ from the committed test plan');
  }
}
const persistReceipt = (suffix, body) => fs.writeFile(path.join(out, label + suffix),
  JSON.stringify({id, label, sessionKey, ...body}), {mode:0o600, flag:'wx', flush:true});
const persist=(suffix,body)=>fs.writeFile(path.join(out,label+suffix),JSON.stringify(body),{mode:0o600});
const start=Promise.withResolvers(),completed=Promise.withResolvers();
let launched=false;
let finishTime,started,finishedKind,terminalSource='chat event';
let terminalReceipt, terminalReceiptError;
function recordTerminal(time) {
  if (scoreFirst && !terminalReceipt) {
    terminalReceipt = persistReceipt('.terminal.json', {
      ended: {time, elapsedMs:finishTime-started, terminal:finishedKind, from:terminalSource},
    }).catch(error => { terminalReceiptError = error; });
  }
}
const token=(await fs.readFile(path.join(state,'gateway-token'),'utf8')).trim();
const client=new GatewayClient({
  token,url:'ws://127.0.0.1:'+gatewayPort,clientName:'cli',mode:'cli',caps:['ultrafast'],role:'operator',scopes:['operator.read','operator.write','operator.admin'],
  onHelloOk:()=>start.resolve(),onConnectError:e=>start.reject(e),
  onEvent:e=>{
    const d=e.payload;
    if(!launched||e.event!=='chat'||d?.runId!==id||!['final','aborted','error'].includes(d.state))return;
    if(finishTime===undefined){
      finishTime=performance.now();finishedKind=d.state;
      const time=Date.now();
      recordTerminal(time);
      completed.resolve({kind:d.state,time});
    }
  }
});
const req=(method,params)=>client.request(method,params,{timeoutMs:65000});
const delay=ms=>new Promise(resolve=>setTimeout(resolve,ms));
async function readRunHistory() {
 const params={sessionKey,limit:100,toolResultMaxChars:60000,maxBytes:1500000};
 for(let attempt=1;;attempt++){
  try{return await req('chat.history',params);}
  catch(error){
   if(attempt>=3 || !/gateway request timeout for chat\.history/i.test(error.message))throw error;
   await delay(1000*attempt);
  }
 }
}
const timeout=(ms,msg)=>{const a=Promise.withResolvers();const t=setTimeout(()=>a.reject(Error(msg)),ms);t.unref();return a.promise};
let latest={messages:[]};
const prompt=input.prompt;
if (!prompt.includes('_run='+id.slice(0,8))) throw Error('The committed prompt must include its fresh retail request ID');
const meta = {
  id, sessionKey, label, prompt,
  ...(scoreFirst ? {capturePolicy:input.capturePolicy} : {}),
  variant: input.variant,
  thinking: input.thinking || 'low',
  experiment: input.experiment,
  temperature: input.temperature,
  top_p: input.top_p,
  max_completion_tokens: input.max_completion_tokens,
  video_threshold_tps: input.video_threshold_tps,
  prior_verified_mean_tps: input.prior_verified_mean_tps,
  context_injection: input.context_injection,
  workspace_agents_md: input.workspace_agents_md,
  ...(input.variant?.startsWith('gift8-') ? {
    official_commit: input.official_commit,
    official_patch_sha256: input.official_patch_sha256,
    benchmark_sha256: input.benchmark_sha256,
    organizer_reproduction_request: input.organizer_reproduction_request,
  } : {}),
};
try{
 client.start();await Promise.race([start.promise,timeout(60000,'gateway connection timed out')]);
 await req('sessions.create',{key:sessionKey,agentId:'main',label:'Santa '+label});
 await req('chat.history',{sessionKey,limit:1});
 await fs.writeFile(path.join(out,label+'.session.json'),JSON.stringify({id,sessionKey}),{mode:0o600});
 if (!scoreFirst) {
  // The controller supplies this private flag only after the real recorder is ready.
  const recordReady=input.readyPath;
  if(!recordReady)throw Error('Video readiness path missing');
  const readyBy=Date.now()+285000;
  let ready=false;
  while (Date.now()<readyBy) {
    try { const flag=JSON.parse(await fs.readFile(recordReady,'utf8')); if(flag.sessionKey===sessionKey&&flag.ready===true){ready=true;break;} }
    catch(error){ if(error.code!=='ENOENT'&&!(error instanceof SyntaxError))throw error; }
    await delay(300);
  }
  if(!ready)throw Error('Recorder not ready; no chat request sent');
 }
 started=performance.now();launched=true;
 const startedWall=Date.now();
 if (scoreFirst) await persistReceipt('.send-intent.json', {startedWall});
 await persist('.pending.json',{...meta,startedWall});
 const ack=await req('chat.send',{sessionKey,message:prompt,thinking:meta.thinking,idempotencyKey:id});
 if(ack.runId&&ack.runId!==id)throw Error('id mismatch');
 const ackMs=performance.now()-started;
 if (scoreFirst) await persistReceipt('.ack.json', {startedWall, ackMs, acknowledgedAt:Date.now(), runId:ack.runId ?? null});
 const deadline=Date.now()+720000;
 while(Date.now()<deadline){
   if(finishTime===undefined)await Promise.race([completed.promise,delay(4500)]);
   latest=await readRunHistory();
   const hasFinal=latest.messages.some(m=>m.role==='assistant'&&m.stopReason==='stop'&&m.content?.some?.(b=>b.type==='text'&&/https?:\/\//.test(b.text||'')));
   if(hasFinal) {
     if(!finishedKind)await Promise.race([completed.promise,delay(6000)]);
     break;
   }
   if(finishedKind==='error'||finishedKind==='aborted')break;
   if(finishTime!==undefined){
     if(performance.now()-finishTime>12000)break;
     await delay(600);
   }
 }
 // Do not admit another trial while this model run is still active. A terminal wait
 // can recover a missed WS event; if a run truly hangs, stop this exact run before advancing.
 if(!finishedKind) {
   let wait=await req('agent.wait',{runId:id,timeoutMs:15000});
   if(wait.status==='timeout') {
     await req('chat.abort',{sessionKey,runId:id});
     wait=await req('agent.wait',{runId:id,timeoutMs:30000});
   }
   if(!finishedKind&&wait.status==='timeout')throw Error('Previous run has not acknowledged termination; preserved pending evidence');
   if(!finishedKind){finishedKind=wait.status==='ok'?'final':'error';finishTime=performance.now();terminalSource='gateway agent.wait';recordTerminal(Date.now());}
   latest=await readRunHistory();
 }
 const elapsedMs=(finishTime||performance.now())-started;
 const result={...meta,startedWall,ackMs,ended:{elapsedMs,time:Date.now(),terminal:finishedKind||'history',from:terminalSource},history:latest};
 await persist('.json',result);
 await fs.unlink(path.join(out,label+'.pending.json'));
 const measured=latest.messages.filter(m=>m.serverGeneration).map(m=>1000*m.serverGeneration.outputTokens/m.serverGeneration.completionMs);
 console.log(JSON.stringify({label,id,sessionKey,elapsedMs,mean:measured.length?measured.reduce((a,b)=>a+b)/measured.length:null,count:measured.length,ended:result.ended.terminal}));
} finally {
 await terminalReceipt;
 await client.stop();
 if (terminalReceiptError) throw terminalReceiptError;
}
