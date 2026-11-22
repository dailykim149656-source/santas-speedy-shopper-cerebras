// Single-use transport for a dedicated OpenClaw session. The upstream response is never rewritten.
import {createHash} from 'node:crypto';
import fs from 'node:fs';
import http from 'node:http';
import https from 'node:https';
import path from 'node:path';
import {fileURLToPath} from 'node:url';

const MODEL = 'moonshotai-kimi-k3.1-pro-trial';
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const sha = data => createHash('sha256').update(data).digest('hex');
const fileOptions = {mode:0o600, flag:'wx', flush:true};
const write = (file, data) => fs.writeFileSync(file, data, fileOptions);
const read = file => JSON.parse(fs.readFileSync(file, 'utf8'));
const MODULE_SHA = sha(fs.readFileSync(fileURLToPath(import.meta.url)));

function reject(res, status, code) {
  if (res.headersSent || res.destroyed) return res.destroy();
  res.writeHead(status, {'content-type':'application/json'});
  res.end(JSON.stringify({error:{code}}));
}

function prep(root, input) {
  const binding = read(path.join(root,'active.json'));
  if (!UUID.test(binding.id) || typeof binding.prompt !== 'string' || !binding.prompt.trim()) throw Error('binding');
  const deadline = typeof binding.deadline === 'number' ? binding.deadline : Date.parse(binding.deadline);
  if (!Number.isFinite(deadline) || Date.now() >= deadline) throw Error('cutoff');
  const turns = input.messages;
  if (input.model !== MODEL || !Array.isArray(turns) || turns.at(-1)?.role !== 'user'
      || !turns.every(m=>['developer','system','user'].includes(m?.role)) || turns.filter(m=>m.role==='user').length!==1) throw Error('turn');
  const content = turns.at(-1).content;
  const txt = typeof content === 'string' ? content : Array.isArray(content) ? content.map(c=>c?.text ?? '').join('\n') : '';
  if (!txt.includes(binding.prompt.trim())) throw Error('prompt');
  const folder = path.join(root,binding.id);
  const doc = read(path.join(folder,'prefetch.json'));
  if (doc.id!==binding.id || doc.valid!==true || !Number.isFinite(doc.startedMs) || !Number.isFinite(doc.completedMs)
      || doc.startedMs>doc.completedMs || doc.completedMs>Date.now() || typeof doc.rendered!=='string' || !doc.rendered.trim()
      || doc.products?.length!==5 || new Set(doc.products.map(p=>p.url)).size!==5 || doc.lookups?.length!==5
      || !doc.products.every(p=>typeof p.url==='string' && p.url.startsWith('https://') && doc.rendered.includes(p.url))
      || !doc.lookups.every(l=>l.status===200 && typeof l.bodySha256==='string' && /^[a-f0-9]{64}$/.test(l.bodySha256))) throw Error('prefetch');
  const outbound = {model:MODEL, messages:[{role:'system',content:'Zero prose.'},
      {role:'user',content:doc.rendered+'\n\nRepeat the list above in full.'}],
      temperature:0.1, reasoning_effort:'low', max_completion_tokens:2400};
  if (typeof input.max_tokens === 'number') outbound.max_tokens=2400;
  if (typeof input.stream === 'boolean') outbound.stream=input.stream;
  if (input.stream_options && typeof input.stream_options.include_usage === 'boolean') {
    outbound.stream_options={include_usage:input.stream_options.include_usage};
  }
  return {binding,deadline,folder,outbound};
}

function metrics(bytes) {
  let responseId=null, usage=null, timeInfo=null;
  const text=bytes.toString('utf8');
  const payloads=text.trimStart().startsWith('{') ? [text] : text.split(/\r?\n/).filter(s=>s.startsWith('data:')).map(s=>s.slice(5).trim());
  for (const payload of payloads) {
    if (!payload || payload==='[DONE]') continue;
    try {
      const c=JSON.parse(payload);
      if (typeof c.id==='string') responseId=c.id;
      if (c.usage) usage=c.usage;
      if (c.time_info) timeInfo=c.time_info;
    } catch {}
  }
  return {responseId,usage,time_info:timeInfo};
}

export function createTransport({root, upstream='https://api.cerebras.ai'}) {
  const dest=new URL(upstream);
  if (dest.origin!=='https://api.cerebras.ai' && !(dest.protocol==='http:' && dest.hostname==='127.0.0.1')) throw Error('unexpected upstream');
  const client=dest.protocol==='https:' ? https : http;
  return http.createServer(async (req,res)=>{
    if (req.method==='GET' && req.url==='/health') {
      res.writeHead(200,{'content-type':'application/json'});
      return res.end(JSON.stringify({ok:true,transport_sha256:MODULE_SHA,protocol:'simethan-one-call'}));
    }
    if (req.method!=='POST' || req.url!=='/v1/chat/completions') return reject(res,404,'unsupported_route');
    const auth=req.headers.authorization || '';
    if (!/^Bearer [^\s]+$/i.test(auth)) return reject(res,401,'missing_gateway_authorization');
    let body, prepared;
    try {
      const chunks=[]; let size=0;
      for await (const chunk of req) {
        size+=chunk.length;
        if (size>3000000) return reject(res,413,'oversized_request');
        chunks.push(chunk);
      }
      body=Buffer.concat(chunks);
      prepared=prep(root,JSON.parse(body));
    } catch {return reject(res,422,'unmatched_request_or_missing_fresh_prefetch');}
    const {binding,deadline,folder,outbound}=prepared;
    const dir=path.join(folder,'transport');
    const bytes=Buffer.from(JSON.stringify(outbound));
    const secret=Buffer.from(auth.slice(7));
    if (bytes.includes(secret)) return reject(res,422,'unexpected_sensitive_body');
    const trace={id:binding.id,received_ms:Date.now(),received_sha256:sha(body),
      forwarded_sha256:sha(bytes),forwarded_bytes:bytes.length,transport_sha256:MODULE_SHA};
    try {
      fs.mkdirSync(dir,{recursive:true,mode:0o700});
      write(path.join(dir,'claim.json'),JSON.stringify({id:binding.id,claimed_ms:Date.now()}));
      write(path.join(dir,'request.json'),bytes);
    } catch {return reject(res,409,'already_claimed_or_unwritable');}
    let sealed=false;
    function seal(value) {
      if (sealed) return;
      sealed=true;
      try {write(path.join(dir,'trace.json'),JSON.stringify({...trace,...value,finished_ms:Date.now()})+'\n');}
      catch {if (!res.headersSent) reject(res,500,'trace_write_failed');}
    }
    if (Date.now()>=deadline || res.destroyed) {
      seal({sent:false,error:'cutoff_or_disconnect'});return reject(res,409,'expired');
    }
    trace.sent=false;
    const headers={authorization:auth,'content-type':'application/json','content-length':bytes.length,'accept-encoding':'identity'};
    if (req.headers.accept) headers.accept=req.headers.accept;
    const up=client.request(new URL('/v1/chat/completions',dest),{method:'POST',headers},incoming=>{
      const parts=[];trace.status=incoming.statusCode;trace.headers_ms=Date.now();
      const complete=(ok)=>{
        if (sealed) return;
        const all=Buffer.concat(parts);
        const persist=!all.includes(secret);
        try {if (persist) write(path.join(dir,'response.bin'),all);}
        catch {seal({complete:false,error:'response_write_failed'});return;}
        seal({complete:ok,response_bytes:all.length,response_sha256:sha(all),response_persisted:persist,
          rate_limited:trace.status===429,...(persist ? metrics(all) : {})});
      };
      res.writeHead(incoming.statusCode,incoming.rawHeaders);
      incoming.on('data',part=>parts.push(part));
      incoming.once('end',()=>complete(true));
      incoming.once('aborted',()=>{complete(false);res.destroy();});
      incoming.once('error',()=>{complete(false);res.destroy();});
      incoming.pipe(res);
    });
    const expire=()=>{
      if (trace.sent) return;
      seal({sent:false,complete:false,error:'expired_before_transport_write'});
      reject(res,409,'expired');
      up.destroy();
    };
    const cutoffTimer=setTimeout(expire,Math.max(1,deadline-Date.now()));
    cutoffTimer.unref();
    up.once('error',()=>{clearTimeout(cutoffTimer);seal({complete:false,error:'upstream_request_failed'});reject(res,502,'upstream_failed');});
    res.once('close',()=>{if (!res.writableEnded) up.destroy();});
    up.once('socket',socket=>{
      const transmit=()=>{
        if (up.destroyed) return;
        if (Date.now()>=deadline) return expire();
        clearTimeout(cutoffTimer);
        trace.sent=true;trace.sent_ms=Date.now();
        up.end(bytes);
      };
      if (socket.connecting) socket.once(dest.protocol==='https:'?'secureConnect':'connect',transmit);
      else transmit();
    });
  });
}

if (process.argv[1] && fileURLToPath(import.meta.url)===path.resolve(process.argv[1])) {
  const opts=Object.fromEntries(process.argv.slice(2).map(arg=>arg.replace(/^--/,'').split('=')));
  if (!opts.root || !path.isAbsolute(opts.root) || !/^\d+$/.test(opts.port || '')) throw Error('use --root=/absolute/path --port=19872');
  createTransport({root:opts.root}).listen(Number(opts.port),'127.0.0.1');
}
