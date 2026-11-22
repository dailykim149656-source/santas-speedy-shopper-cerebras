// Diagnostic replays of saved relay request bodies with prompt/reasoning variants. Prints no secrets.
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {pathToFileURL} from 'node:url';

const home = os.homedir();
const installed = path.resolve(path.dirname(fs.realpathSync(process.execPath)), '../lib/node_modules/openclaw');
const {resolveApiKeyForProvider} = await import(pathToFileURL(path.join(installed, 'dist/plugin-sdk/provider-auth-runtime.js')));
const cfg = JSON.parse(fs.readFileSync(path.join(home, '.openclaw/openclaw.json'), 'utf8'));
const {apiKey} = await resolveApiKeyForProvider({provider: 'cerebras', cfg, agentDir: path.join(home, '.openclaw/agents/main/agent'), modelId: 'moonshotai-kimi-k3.1-pro-trial'});
if (!apiKey) throw Error('no key');

const spec = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const delay = ms => new Promise(r => setTimeout(r, ms));

async function send(body) {
  for (let attempt = 0; attempt < 12; attempt++) {
    const res = await fetch('https://api.cerebras.ai/v1/chat/completions', {method: 'POST', headers: {authorization: 'Bearer ' + apiKey, 'content-type': 'application/json'}, body: JSON.stringify(body)});
    if (res.status === 429) { await res.text(); await delay(1500 + attempt * 700); continue; }
    if (res.status !== 200) return {status: res.status, error: (await res.text()).slice(0, 300), retries: attempt};
    const text = await res.text();
    let reasoning = '', content = '', tools = 0, usage, timing;
    for (const line of text.split('\n')) {
      if (!line.startsWith('data:') || line.includes('[DONE]')) continue;
      const c = JSON.parse(line.slice(5));
      const d = c.choices?.[0]?.delta || {};
      reasoning += d.reasoning || d.reasoning_content || '';
      content += d.content || '';
      for (const t of d.tool_calls || []) if (t.function?.name) tools += 1;
      if (c.usage) usage = c.usage;
      if (c.time_info) timing = c.time_info;
    }
    const out = usage?.completion_tokens, ms = timing?.completion_time * 1000;
    return {status: 200, retries: attempt, out, ms: Math.round(ms), tps: Math.round(out / ms * 1000), reasoning_chars: reasoning.length, reasoning: reasoning.slice(0, 90), links: new Set(content.match(/https:\/\/aisynthesis\.com\/product\/[^"\s)]+/g) || []).size, content_chars: content.length, head: content.slice(0, 60), tools};
  }
  return {status: 429, error: 'gave up'};
}

for (const v of spec.variants) {
  const base = JSON.parse(fs.readFileSync(v.body, 'utf8'));
  const body = structuredClone(base);
  if ('system' in v) {
    const i = body.messages.findIndex(m => m.role === 'system');
    if (v.system === null) body.messages.splice(i, 1); else body.messages[i] = {role: 'system', content: v.system};
  }
  for (const [k, val] of Object.entries(v.set || {})) { if (val === null) delete body[k]; else body[k] = val; }
  for (let rep = 0; rep < (v.reps || 2); rep++) {
    const r = await send(body);
    console.log(JSON.stringify({variant: v.name, rep, ...r}));
    await delay(800);
  }
}
