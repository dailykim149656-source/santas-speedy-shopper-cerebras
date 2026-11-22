'use strict';
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const IDS = [21951, 23345, 11125, 11141, 20209];
const ORIGIN = 'https://aisynthesis.com';
const SYSTEM_PROMPT = 'Use current merchant cards only. When cards are absent, call gift_lookup once for each requested id in parallel. Return only JSON {"gifts":[cards]} in requested id order, copying all card fields exactly. Prices are minor currency units; options are actual variation values, not all finished products.';
const sha = value => crypto.createHash('sha256').update(value).digest('hex');
function pluginSha256() {
  return sha(Buffer.concat(['index.cjs','openclaw.plugin.json','package.json'].sort().map(name=>fs.readFileSync(path.join(__dirname,name)))));
}
function canonicalCard(p) {
  const number = v => { if (!/^\d+$/.test(String(v)) || !Number.isSafeInteger(Number(v))) throw Error('Invalid price'); return Number(v); };
  if (!Number.isInteger(p.id) || typeof p.name !== 'string' || !p.name || typeof p.permalink !== 'string' || typeof p.is_in_stock !== 'boolean' || !/^[A-Z]{3}$/.test(p.prices?.currency_code)) throw Error('Invalid product');
  const options = [...new Set((p.variations || []).flatMap(v => v.attributes.map(a => { if (typeof a.value !== 'string') throw Error('Invalid option'); return a.value; })))].sort();
  return {id:p.id,name:p.name,url:p.permalink,price_minor:number(p.prices.price),price_range_minor:p.prices.price_range ? [number(p.prices.price_range.min_amount),number(p.prices.price_range.max_amount)] : null,currency:p.prices.currency_code,stock:p.is_in_stock,options};
}
function atomic(file, bytes) {
  fs.mkdirSync(path.dirname(file), {recursive:true,mode:0o700});
  const temp = file + '.' + crypto.randomUUID() + '.tmp';
  fs.writeFileSync(temp, bytes, {flag:'wx',mode:0o600});
  const claim = file + '.claim';
  try {
    const fd = fs.openSync(claim,'wx',0o600); fs.closeSync(fd);
    if (fs.existsSync(file)) throw Error('Evidence already exists');
    fs.renameSync(temp,file);
  } finally { if (fs.existsSync(temp)) fs.unlinkSync(temp); }
}
const json = value => JSON.stringify(value);
function createRuntime(config, deps = {}) {
  const root = path.resolve(config.campaignRoot);
  const base = deps.origin || ORIGIN;
  const fetcher = deps.fetch || fetch;
  const sessions = new Map(), pending = new Map();
  const runDir = m => path.join(root,'receipts',m.id);
  function manifest(ctx,prompt) {
    if (!/^[\w-]+$/.test(ctx.runId || '') || !ctx.sessionKey) return null;
    const file = path.join(root,'manifests',ctx.runId+'.json');
    if (!fs.existsSync(file)) return null;
    const m = JSON.parse(fs.readFileSync(file,'utf8'));
    if (m.id !== ctx.runId || m.sessionKey !== ctx.sessionKey || m.plugin_sha256 !== pluginSha256() || m.protocol !== 'gift8-v1' || !['tool','prefetch'].includes(m.arm) || json(m.ids) !== json(IDS) || !Number.isSafeInteger(m.created_ms) || m.created_ms > Date.now() || (prompt !== undefined && m.prompt_sha256 !== sha(prompt))) throw Error('Manifest binding mismatch');
    return m;
  }
  function record(m,type,fields={}) {
    const event = {type,runId:m.id,sessionKey:m.sessionKey,timestamp_ms:Date.now(),plugin_sha256:pluginSha256(),...fields};
    atomic(path.join(runDir(m),'events',Date.now()+'-'+crypto.randomUUID()+'.json'),json(event));
  }
  function checkReceipt(m,id) {
    const file = path.join(runDir(m),`fetch-${id}.json`);
    const r = JSON.parse(fs.readFileSync(file,'utf8'));
    const bytes = fs.readFileSync(path.join(runDir(m),`body-${id}.bin`));
    const card = canonicalCard(JSON.parse(bytes.toString('utf8')));
    if (r.id !== m.id || r.sessionKey !== m.sessionKey || r.arm !== m.arm || r.product_id !== id || r.prompt_sha256 !== m.prompt_sha256 || r.body_file !== `body-${id}.bin` || r.body_sha256 !== sha(bytes) || r.card_sha256 !== sha(json(card)) || json(r.card) !== json(card) || r.started_ms < m.created_ms || r.completed_ms < r.started_ms || r.card?.id !== id || new URL(r.card.url).origin !== base || r.status !== 200 || new URL(r.final_url).origin !== base || r.url !== productUrl(id)) throw Error('Receipt integrity mismatch');
    return r;
  }
  function productUrl(id) { return `${base}/wp-json/wc/store/v1/products/${id}?_fields=id,name,permalink,prices,stock_availability,variations,is_in_stock`; }
  async function lookup(m,id,callId) {
    if (!IDS.includes(id)) throw Error('Unapproved product id');
    const key = m.id+':'+id;
    if (!pending.has(key)) pending.set(key,(async () => {
      const file = path.join(runDir(m),`fetch-${id}.json`);
      if (fs.existsSync(file)) return checkReceipt(m,id);
      const lock = path.join(runDir(m),`fetch-${id}.lock`);
      fs.mkdirSync(runDir(m),{recursive:true,mode:0o700});
      const fd = fs.openSync(lock,'wx',0o600); fs.closeSync(fd);
      const url = productUrl(id), started_ms = Date.now();
      let response, bytes;
      try {
        response = await fetcher(url,{signal:AbortSignal.timeout(config.timeoutMs || 15000),redirect:'follow',headers:{accept:'application/json','cache-control':'no-cache'}});
        bytes = Buffer.from(await response.arrayBuffer());
      } catch (error) {
        bytes = Buffer.alloc(0);
        atomic(path.join(runDir(m),`body-${id}.bin`),bytes);
        atomic(file,json({protocol:'gift8-v1',id:m.id,sessionKey:m.sessionKey,arm:m.arm,prompt_sha256:m.prompt_sha256,product_id:id,tool_call_id:callId,started_ms,completed_ms:Date.now(),url,final_url:response?.url || null,status:response?.status || null,body_sha256:sha(bytes),body_file:`body-${id}.bin`,card:null,card_sha256:null,error:String(error)}));
        throw error;
      }
      const completed_ms = Date.now();
      atomic(path.join(runDir(m),`body-${id}.bin`),bytes);
      let card = null;
      try { card = canonicalCard(JSON.parse(bytes.toString('utf8'))); } catch (_) {}
      const r = {protocol:'gift8-v1',id:m.id,sessionKey:m.sessionKey,arm:m.arm,prompt_sha256:m.prompt_sha256,product_id:id,tool_call_id:callId,started_ms,completed_ms,url,final_url:response.url,status:response.status,body_sha256:sha(bytes),body_file:`body-${id}.bin`,card,card_sha256:card ? sha(json(card)) : null};
      atomic(file,json(r));
      if (new URL(response.url).origin !== base) throw Error('Foreign redirect');
      if (response.status !== 200 || !card || card.id !== id || new URL(card.url).origin !== base) throw Error('Invalid merchant response');
      return r;
    })());
    await pending.get(key);
    const r = checkReceipt(m,id);
    if (callId !== null) {
      const call = {id:m.id,sessionKey:m.sessionKey,arm:m.arm,product_id:id,tool_call_id:callId,receipt_file:`fetch-${id}.json`,card_sha256:r.card_sha256,timestamp_ms:Date.now()};
      const file = path.join(runDir(m),'calls',sha(callId)+'.json');
      if (!fs.existsSync(file)) atomic(file,json(call));
      else if (JSON.parse(fs.readFileSync(file,'utf8')).product_id !== id) throw Error('Call identity collision');
    }
    return r;
  }
  function bind(event,ctx) {
    const m = manifest(ctx,event.prompt); if (!m) return;
    const old = sessions.get(m.sessionKey);
    if (old && json(old) !== json(m)) throw Error('Session reuse');
    sessions.set(m.sessionKey,m);
    record(m,'prompt_binding',{prompt_sha256:sha(event.prompt),arm:m.arm,system_prompt_sha256:sha(SYSTEM_PROMPT)});
    return {systemPrompt:SYSTEM_PROMPT,toolsAllow:['gift_lookup']};
  }
  async function enrich(event,ctx) {
    const m = manifest(ctx,event.prompt); if (!m || m.arm !== 'prefetch') return;
    if (!ctx.toolAuthority?.allows('gift_lookup')) throw Error('gift_lookup denied');
    ctx.toolAuthority.assertActive();
    const cards = await Promise.all(m.ids.map(id=>lookup(m,id,null)));
    ctx.toolAuthority.assertActive();
    const context = 'Current merchant cards: '+json({gifts:cards.map(r=>r.card)});
    record(m,'prefetch_injection',{context,context_sha256:sha(context),prompt_sha256:m.prompt_sha256});
    return {prependContext:context};
  }
  function factory(ctx) {
    return {name:'gift_lookup',label:'Gift lookup',description:'Fetch one current AI Synthesis product by numeric id.',parameters:{type:'object',properties:{id:{type:'integer',enum:IDS}},required:['id'],additionalProperties:false},async execute(callId,args) {
      const bound = sessions.get(ctx.sessionKey);
      if (!bound || typeof callId !== 'string' || !callId || Object.keys(args).some(k=>k!=='id')) throw Error('Unbound tool call');
      const m = manifest({runId:bound.id,sessionKey:ctx.sessionKey});
      if (json(m) !== json(bound)) throw Error('Manifest changed');
      const r = await lookup(m,args.id,callId);
      return {content:[{type:'text',text:json(r.card)}],details:{card:r.card,receipt_file:`fetch-${args.id}.json`}};
    }};
  }
  function sanitize(value) {
    if (Array.isArray(value)) return value.filter(v=>!['thinking','reasoning','redacted_thinking'].includes(v?.type)).map(sanitize);
    if (value && typeof value === 'object') return Object.fromEntries(Object.entries(value).filter(([k])=>!['thinking','reasoning','reasoning_content','signature'].includes(k)).map(([k,v])=>[k,sanitize(v)]));
    return value;
  }
  function llmInput(event,ctx) {
    const m = manifest({...ctx,runId:event.runId}); if (!m) return;
    record(m,'llm_input',{event:sanitize(event),prompt_sha256:sha(event.prompt),bound_prompt_sha256:m.prompt_sha256});
  }
  return {bind,enrich,factory,llmInput,lookup,checkReceipt};
}
module.exports = {id:'gift8',name:'Gift8 merchant lookup',register(api) {
  const config = api.pluginConfig || {};
  const runtime = createRuntime(config);
  api.registerTool(runtime.factory,{name:'gift_lookup'});
  api.on('before_prompt_build',runtime.bind);
  api.on('before_prompt_build',runtime.enrich,{requiresToolAuthority:true});
  api.on('llm_input',runtime.llmInput);
},createRuntime,canonicalCard,sha,pluginSha256,IDS,SYSTEM_PROMPT};
