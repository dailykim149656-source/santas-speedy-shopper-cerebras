// Read-only preparation by default. --send consumes this campaign's single five-request diagnostic.
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {fileURLToPath, pathToFileURL} from 'node:url';

const dir = path.dirname(fileURLToPath(import.meta.url));
const source = path.join(dir, '../relay/logs/f039d055-caa3-4ed7-bcc8-e571d4dea5fb/1795357747588-ffdbc2a65b8b.json');
const expectedHash = 'ffdbc2a65b8b41e546faedd700d3e5e6b2520a345d42518aee18ec0e7d592556';
const arms = ['auto', 'required', 'required', 'auto', 'required'];
const deadline = Date.parse('2026-11-23T03:00:00+09:00');
const sha = x => createHash('sha256').update(x).digest('hex');
const now = () => new Date().toISOString();

function createOnce(name, value) {
  const fd = fs.openSync(path.join(dir, name), 'wx', 0o600);
  try {
    fs.writeFileSync(fd, JSON.stringify(value) + '\n');
    fs.fsyncSync(fd);
  } finally { fs.closeSync(fd); }
  const parent = fs.openSync(dir, 'r');
  try { fs.fsyncSync(parent); } finally { fs.closeSync(parent); }
}

function inputs() {
  const original = fs.readFileSync(source, 'utf8');
  assert.equal(sha(original), expectedHash);
  const base = JSON.parse(original);
  assert.deepEqual(base.messages.map(m => m.role), ['system', 'user']);
  assert.equal(base.tool_choice, 'auto');
  assert.equal(base.stream, true);
  const args = base.messages[1].content.split('\n').filter(l => l.startsWith('{"url":')).map(l => JSON.parse(l).url);
  assert.equal(new Set(args).size, 5);
  const required = original.replace(/("tool_choice"\s*:\s*)"auto"/, '$1"required"');
  assert.deepEqual(JSON.parse(required), {...base, tool_choice: 'required'});
  return {bodies: {auto: original, required}, urls: args};
}

function upstreamCode(value) {
  return typeof value === 'string' && /^[a-z][a-z0-9_]{0,48}$/i.test(value) ? value : null;
}

function usageNumber(...fields) {
  return fields.find(v => typeof v === 'number' && Number.isFinite(v) && v >= 0) ?? null;
}

async function consume(response, expectedUrls, report) {
  if (response.status !== 200) {
    const err = await response.json().catch(() => null);
    report.error_code = upstreamCode(err?.error?.code) ?? upstreamCode(err?.code) ?? 'http_error';
    return;
  }
  const tools = new Map(), decoder = new TextDecoder();
  let buffer = '', usage, timing, finished = false, chars = 0;
  function line(input) {
    if (!input.startsWith('data:')) return;
    const payload = input.slice(5).trim();
    if (payload === '[DONE]') { finished = true; return; }
    const chunk = JSON.parse(payload);
    if (chunk.error) throw new Error('stream_error');
    if (chunk.usage) usage = chunk.usage;
    if (chunk.time_info) timing = chunk.time_info;
    const choice = chunk.choices?.[0], delta = choice?.delta;
    if (choice?.finish_reason) report.finish_reason = upstreamCode(choice.finish_reason);
    if (!delta) return;
    const thought = delta.reasoning_content ?? delta.reasoning;
    if (typeof thought === 'string') chars += [...thought].length;
    for (const part of delta.tool_calls ?? []) {
      const call = tools.get(part.index) ?? {name:'', args:''};
      call.name += part.function?.name ?? '';
      call.args += part.function?.arguments ?? '';
      tools.set(part.index, call);
    }
  }
  for await (const bytes of response.body) {
    const lines = (buffer + decoder.decode(bytes, {stream:true})).split('\n');
    buffer = lines.pop();
    for (const content of lines) line(content);
  }
  if (buffer) line(buffer + decoder.decode());
  report.stream_complete = finished;
  if (!finished) { report.error_code = 'incomplete_stream'; return; }
  report.output_tokens = usageNumber(usage?.completion_tokens);
  report.prompt_tokens = usageNumber(usage?.prompt_tokens);
  report.reasoning_tokens = usageNumber(usage?.completion_tokens_details?.reasoning_tokens, usage?.reasoning_tokens);
  report.cache_read = usageNumber(usage?.prompt_tokens_details?.cached_tokens, usage?.cached_tokens);
  const seconds = usageNumber(timing?.completion_time);
  report.server_generation_ms = seconds === null ? null : seconds * 1000;
  report.tps = seconds > 0 && report.output_tokens !== null ? report.output_tokens / seconds : null;
  report.reasoning_chars = chars;
  report.tool_count = tools.size;
  const urls = [];
  for (const call of tools.values()) {
    const obj = (() => { try { return JSON.parse(call.args); } catch { return null; } })();
    if (call.name === 'web_fetch' && obj && Object.keys(obj).length === 1 && typeof obj.url === 'string') urls.push(obj.url);
  }
  report.tool_args_match = tools.size === 5 && expectedUrls.every(url => urls.includes(url));
}

async function main() {
  const {bodies, urls} = inputs();
  if (process.argv.length === 2) { console.log('Verified D5108 source, five URLs, and single-field treatment. No sends.'); return; }
  assert.deepEqual(process.argv.slice(2), ['--send']);
  const start = Date.now(), end = Math.min(deadline, start + 300_000);
  if (end <= start || fs.existsSync(path.join(dir, 'probe-reservation.json'))) throw new Error('expired_or_already_reserved');
  const watchdog = setTimeout(() => process.exit(124), end - start);
  try {
    const home = os.homedir();
    const installed = path.resolve(path.dirname(fs.realpathSync(process.execPath)), '../lib/node_modules/openclaw');
    const {resolveApiKeyForProvider} = await import(pathToFileURL(path.join(installed, 'dist/plugin-sdk/provider-auth-runtime.js')));
    const cfg = JSON.parse(fs.readFileSync(path.join(home, '.openclaw/openclaw.json'), 'utf8'));
    const {apiKey} = await resolveApiKeyForProvider({provider:'cerebras',cfg,agentDir:path.join(home,'.openclaw/agents/main/agent'),modelId:'moonshotai-kimi-k3.1-pro-trial'});
    if (typeof apiKey !== 'string' || !apiKey.trim()) throw new Error('credential_unavailable');
    createOnce('probe-reservation.json', {source:'D5108', original_sha256:expectedHash, arms, start:new Date(start).toISOString(), deadline:new Date(end).toISOString()});
    for (const [index, arm] of arms.entries()) {
      const budget = Math.floor((end-Date.now()-1000)/(arms.length-index));
      if (budget < 1) throw new Error('deadline');
      const ident = 'probe-' + String(index+1).padStart(2,'0');
      const record = {slot:index+1, arm, started:now(), sent_sha256:sha(bodies[arm])};
      createOnce(ident+'.intent.json', record);
      Object.assign(record,{http:null, error_code:null, stream_complete:false, finish_reason:null, output_tokens:null, reasoning_tokens:null, reasoning_chars:null, prompt_tokens:null, cache_read:null, server_generation_ms:null, tps:null, tool_count:null, tool_args_match:null});
      try {
        const res = await fetch('https://api.cerebras.ai/v1/chat/completions', {method:'POST', redirect:'error', headers:{authorization:'Bearer '+apiKey, 'content-type':'application/json'},body:bodies[arm],signal:AbortSignal.timeout(budget)});
        record.http=res.status;
        await consume(res,urls,record);
      } catch (err) { record.error_code = ['TimeoutError','AbortError'].includes(err?.name) ? 'timeout' : 'transport_or_stream_error'; }
      record.ended = now();
      createOnce(ident+'.result.json',record);
      console.log(JSON.stringify(record));
    }
    createOnce('probe-finished.json', {ended:now(),slots:arms.length});
  } finally { clearTimeout(watchdog); }
}
main().catch(() => { console.error('Diagnostic stopped. Inspect reservation and numeric slot receipts.'); process.exitCode=1; });
