'use strict';
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const categories = ['filter', 'mixer', 'oscillator', 'echo', 'cable'];
const protocol = 'speed1500-native-v1';
const sha = bytes => crypto.createHash('sha256').update(bytes).digest('hex');
const pluginSha = () => sha(Buffer.concat(['index.cjs', 'openclaw.plugin.json', 'package.json'].map(n => fs.readFileSync(path.join(__dirname, n)))));
const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
function query(id, category) {
  return 'https://aisynthesis.com/wp-json/wc/store/v1/products?search=' + category
    + '&per_page=1&stock_status=instock&_fields=name,permalink&_run=' + id.slice(0, 8);
}
function exclusive(file, bytes) {
  try { fs.writeFileSync(file, bytes, {flag:'wx', mode:0o600}); }
  catch (e) { if (e.code !== 'EEXIST' || !fs.readFileSync(file).equals(Buffer.from(bytes))) throw e; }
}
function createRuntime({root}, fetcher = fetch) {
  const active = new Map();
  function bound(ctx) {
    if (!uuid.test(ctx.runId || '') || !ctx.sessionKey) return null;
    const dir = path.join(root, ctx.runId);
    const file = path.join(dir, 'manifest.json');
    if (!fs.existsSync(file)) return null;
    const bytes = fs.readFileSync(file);
    const m = JSON.parse(bytes);
    if (m.id !== ctx.runId || m.sessionKey !== ctx.sessionKey) return null;
    if (m.protocol !== protocol || m.plugin_sha256 !== pluginSha() || sha(m.prompt) !== m.prompt_sha256
        || !m.prompt.includes('_run=' + m.id.slice(0,8))
        || JSON.stringify(m.urls) !== JSON.stringify(categories.map(c => query(m.id, c)))) throw Error('Invalid prefetch binding');
    return {m, dir, manifestHash:sha(bytes)};
  }
  function log(b, type, details) {
    fs.appendFileSync(path.join(b.dir, 'events.jsonl'), JSON.stringify({type, id:b.m.id, sessionKey:b.m.sessionKey,
      manifest_sha256:b.manifestHash, at:Date.now(), ...details}) + '\n', {mode:0o600});
  }
  async function acquire(b) {
    const rows = await Promise.all(categories.map(async (category, index) => {
      const url = b.m.urls[index], started = Date.now();
      const response = await fetcher(url, {redirect:'error', cache:'no-store', signal:AbortSignal.timeout(15000),
        headers:{accept:'application/json','cache-control':'no-cache'}});
      if (response.status !== 200 || response.url !== url) throw Error('Category lookup failed: ' + category);
      const bytes = Buffer.from(await response.arrayBuffer());
      const products = JSON.parse(bytes.toString('utf8'));
      if (!Array.isArray(products) || products.length !== 1) throw Error('Expected one live item per category');
      const {name, permalink} = products[0];
      if (typeof name !== 'string' || !name.trim() || /[\r\n]/.test(name)
          || typeof permalink !== 'string' || !/^https:\/\/aisynthesis\.com\/product\/[\w%.-]+\/?$/.test(permalink)) {
        throw Error('Invalid live product');
      }
      exclusive(path.join(b.dir, category + '.bin'), bytes);
      exclusive(path.join(b.dir, category + '.json'), JSON.stringify({id:b.m.id, sessionKey:b.m.sessionKey,
        manifest_sha256:b.manifestHash, category, url, final_url:response.url, status:response.status,
        started, ended:Date.now(), body_sha256:sha(bytes)}));
      return {name, permalink};
    }));
    if (new Set(rows.map(r => r.permalink)).size !== 5) throw Error('Repeated live product');
    return 'Current live merchant results in requested category order: ' + JSON.stringify(rows);
  }
  async function enrich(event, ctx) {
    const b = bound(ctx);
    if (!b) return;
    if (!ctx.toolAuthority?.allows('web_fetch')) throw Error('Live web fetch unavailable');
    ctx.toolAuthority.assertActive();
    let state = active.get(b.m.id);
    if (!state) {
      if (typeof event.prompt !== 'string' || !event.prompt.includes(b.m.prompt)) throw Error('Unbound original shopping prompt');
      state = {hash:b.manifestHash, context:acquire(b)};
      active.set(b.m.id, state);
    }
    if (b.manifestHash !== state.hash) throw Error('Prefetch binding changed');
    const context = await state.context;
    ctx.toolAuthority.assertActive();
    log(b, 'injection', {context_sha256:sha(context), hook_prompt_sha256:sha(event.prompt)});
    return {prependContext:context};
  }
  async function llmInput(event, ctx) {
    const b = bound({...ctx, runId:event.runId});
    if (!b) return;
    const state = active.get(b.m.id);
    const context = state ? await state.context : null;
    log(b, 'model_input', {provider:event.provider, model:event.model, sessionId:event.sessionId,
      context_sha256:context && sha(context), prompt:event.prompt, system_sha256:sha(event.systemPrompt || '')});
  }
  return {enrich, llmInput};
}
module.exports = {id:'speed1500', name:'Live category prefetch', createRuntime, pluginSha,
  register(api) {
    const hooks = createRuntime(api.pluginConfig);
    api.on('before_prompt_build', hooks.enrich, {requiresToolAuthority:true});
    api.on('llm_input', hooks.llmInput);
  }};
