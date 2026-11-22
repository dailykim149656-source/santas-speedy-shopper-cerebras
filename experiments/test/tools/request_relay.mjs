// Local request relay between the test gateway and Cerebras (relay-v1).
//
// Responses pass through byte for byte, so the official patch reads the same `time_info` and usage. Only
// requests bound to a committed run (a binding file named by the `_run=` nonce in its first user message)
// are rewritten, and the rewrite is applied to every request of that run, retries included:
//   - the system message is replaced by the binding's short system prompt;
//   - first generation (no tool results yet): tools narrowed to web_fetch, tool_choice "required",
//     parallel_tool_calls true;
//   - final generation: only when the latest assistant turn made exactly the five committed web_fetch
//     calls, in order, and all five results are HTTP 200 merchant data with a product permalink, the
//     tools and tool options are removed so the model can only write the answer;
//   - anything else keeps web_fetch available with automatic tool choice.
// The final-only comparison keeps first and repair requests byte-identical and removes only the
// three tool fields after five verified results. First-required changes only tool_choice on the first
// D5027 request. Retry-only forwards every request unchanged.
// A bound 429 resends the exact forwarded bytes. A request that already carries tool results comes after a
// measured call, so it waits longer (LATE_RETRY_DELAYS_MS) rather than lose the run. Logs retain request and
// response hashes.
import http from 'node:http';
import https from 'node:https';
import crypto from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';

export const PROTOCOL = 'relay-v1';
export const SOURCE_SHA256 = crypto.createHash('sha256').update(fs.readFileSync(fileURLToPath(import.meta.url))).digest('hex');
const sha = value => crypto.createHash('sha256').update(value).digest('hex');
const PERMALINK = /"permalink":\s*"https:\/\/aisynthesis\.com\/product\/[^"\s]+"/;
// Delays before resending a bound request after a 429: about 40 s in all, well inside OpenClaw's 300 s idle limit.
export const RETRY_DELAYS_MS = [1500, 2000, 2500, 3000, 4000, 5000, 6000, 7000, 8000];
// Once a request carries tool results, the run's first call has been measured; a 429 there used to void the run
// after ~33 s (D5077, D5080). Keep trying for about 170 s, which with the first call and the fetches stays under
// the 300 s agent and HTTP idle limits. RELAY_RETRY_SCALE shortens both schedules in tests only.
export const LATE_RETRY_DELAYS_MS = [2000, 3000, 4000, 5000, 6000, 8000, 10000, 12000,
                                     15000, 15000, 15000, 15000, 15000, 15000, 15000, 15000];
const RETRY_SCALE = Number(process.env.RELAY_RETRY_SCALE || 1);
export const isLateRequest = body => (body?.messages || []).some(m => m?.role === 'tool');

function textOf(content) {
  if (typeof content === 'string') return content;
  if (Array.isArray(content)) return content.map(part => typeof part === 'string' ? part : part?.text ?? '').join('');
  return '';
}

export function nonceOf(body) {
  const user = (body.messages || []).find(m => m?.role === 'user');
  const match = /_run=([0-9a-f]{8})\b/.exec(textOf(user?.content));
  return match ? match[1] : null;
}

function resultOk(message, url) {
  let parsed;
  try { parsed = JSON.parse(textOf(message.content)); } catch { return false; }
  return parsed?.status === 200 && parsed?.url === url && typeof parsed.text === 'string' && PERMALINK.test(parsed.text);
}

// Decide the phase from the conversation in the request body alone, so a retried request gets the same answer.
export function phaseOf(body, binding) {
  const messages = body.messages || [];
  let last = -1;
  for (let i = messages.length - 1; i >= 0; i--) {
    if (messages[i]?.role === 'assistant' && Array.isArray(messages[i].tool_calls) && messages[i].tool_calls.length) { last = i; break; }
  }
  if (last < 0) return {phase: 'first'};
  const calls = messages[last].tool_calls;
  const urls = binding.urls;
  const reasons = [];
  if (calls.length !== urls.length) reasons.push(`expected ${urls.length} tool calls, got ${calls.length}`);
  const results = new Map(messages.slice(last + 1).filter(m => m?.role === 'tool').map(m => [m.tool_call_id, m]));
  calls.forEach((call, i) => {
    let args;
    try { args = JSON.parse(call.function?.arguments ?? 'null'); } catch { args = null; }
    if (call.function?.name !== 'web_fetch') reasons.push(`call ${i + 1} is not web_fetch`);
    if (args?.url !== urls[i]) reasons.push(`call ${i + 1} url differs from the committed argument`);
    const result = results.get(call.id);
    if (!result) reasons.push(`call ${i + 1} has no result`);
    else if (!resultOk(result, urls[i])) reasons.push(`call ${i + 1} result is not HTTP 200 product data`);
  });
  return reasons.length ? {phase: 'repair', reasons} : {phase: 'final'};
}

function productLink(message, url) {
  try {
    const result = JSON.parse(textOf(message.content));
    if (result.status !== 200 || result.url !== url || (result.finalUrl && result.finalUrl !== url) || result.truncated) return null;
    let text = result.text.trim();
    if (text.includes('\n---\n') && (text.includes('<<<EXTERNAL_UNTRUSTED_CONTENT') || text.includes('[[MARKER_SANITIZED]]'))) {
      text = text.slice(text.indexOf('\n---\n') + 5).split(/\n(?:<<<END_EXTERNAL_UNTRUSTED_CONTENT|\[\[END_MARKER_SANITIZED\]\])/u, 1)[0];
    }
    const items = JSON.parse(text);
    if (!Array.isArray(items) || items.length !== 1 || !items[0].name?.trim()) return null;
    const link = new URL(items[0].permalink);
    if (link.origin !== 'https://aisynthesis.com' || link.username || link.password || link.search || link.hash
        || !/^\/product\/[^/]+\/?$/u.test(link.pathname)) return null;
    return link.pathname.replace(/\/$/u, '');
  } catch {
    return null;
  }
}

// A later user/recovery turn must never reuse the previous turn's five results.
function finalOnlyPhase(body, binding) {
  const messages = body.messages || [];
  const assistant = messages.findLastIndex(m => m.role === 'assistant' && m.tool_calls?.length);
  if (assistant < 0) return {phase: 'first', reasons: []};
  const calls = messages[assistant].tool_calls;
  const results = messages.slice(assistant + 1);
  if (calls.length !== 5 || results.length !== 5 || !results.every(m => m.role === 'tool')) {
    return {phase: 'repair', reasons: ['waiting for the five live tool results']};
  }
  const byId = new Map(results.map(result => [result.tool_call_id, result]));
  const products = new Set();
  for (const [i, call] of calls.entries()) {
    let args;
    try { args = JSON.parse(call.function?.arguments); } catch {}
    const url = binding.urls[i];
    const product = call.id && call.function?.name === 'web_fetch' && args?.url === url
      && productLink(byId.get(call.id), url);
    if (!product || products.has(product)) return {phase: 'repair', reasons: [`missing or invalid product for fetch ${i + 1}`]};
    products.add(product);
  }
  return {phase: 'final', reasons: []};
}

function removeToolFields(out, changes) {
  for (const key of ['tools', 'tool_choice', 'parallel_tool_calls']) {
    if (key in out) { delete out[key]; changes.push('removed_' + key); }
  }
}

export function rewrite(body, binding) {
  const changes = [];
  if (binding.mode === 'first-required') {
    const {phase, reasons} = finalOnlyPhase(body, binding);
    if (phase !== 'first') return {body, phase, reasons, changes};
    const messages = body.messages;
    const users = messages.filter(m => m.role === 'user');
    if (users.length !== 1 || messages.at(-1)?.role !== 'user'
        || messages.some(m => !['system', 'developer', 'user'].includes(m.role))) {
      return {body, phase: 'repair', reasons: ['not the initial user turn'], changes};
    }
    const user = textOf(users[0].content);
    if (body.tool_choice !== 'auto' || body.tools?.length !== 1 || body.tools[0]?.type !== 'function'
        || body.tools[0].function?.name !== 'web_fetch' || !binding.urls.every(url => user.includes(url))) {
      throw Error('First-required expects the five bound URLs and one automatic web_fetch tool');
    }
    return {body: {...body, tool_choice: 'required'}, phase, reasons, changes: ['tool_choice_required']};
  }
  if (binding.mode === 'final-only') {
    const {phase, reasons} = finalOnlyPhase(body, binding);
    if (phase !== 'final') return {body, phase, reasons, changes};
    const out = {...body};
    removeToolFields(out, changes);
    return {body: out, phase, reasons, changes};
  }
  const out = structuredClone(body);
  const system = out.messages.findIndex(m => m?.role === 'system' || m?.role === 'developer');
  if (system >= 0) {
    if (out.messages[system].content !== binding.system_prompt) changes.push('system_prompt');
    out.messages[system] = {role: out.messages[system].role, content: binding.system_prompt};
  } else {
    out.messages.unshift({role: 'system', content: binding.system_prompt});
    changes.push('system_prompt_added');
  }
  const {phase, reasons} = phaseOf(out, binding);
  const webFetch = (out.tools || []).filter(t => t?.function?.name === 'web_fetch');
  if (phase === 'final') {
    removeToolFields(out, changes);
  } else {
    if (!webFetch.length) throw Error('Request has no web_fetch tool to keep');
    if ((out.tools || []).length !== webFetch.length) changes.push('tools_narrowed');
    out.tools = webFetch;
    if (phase === 'first') {
      out.tool_choice = 'required';
      out.parallel_tool_calls = true;
      changes.push('tool_choice_required', 'parallel_tool_calls');
    } else {
      for (const key of ['tool_choice', 'parallel_tool_calls']) {
        if (key in out) { delete out[key]; changes.push('removed_' + key); }
      }
    }
  }
  return {body: out, phase, reasons: reasons || [], changes};
}

function readBinding(dir, nonce) {
  if (!nonce) return null;
  const file = path.join(dir, nonce + '.json');
  if (!fs.existsSync(file)) return null;
  const binding = JSON.parse(fs.readFileSync(file, 'utf8'));
  // A retry-only binding forwards the request unchanged and only resends it after a 429.
  const retryOnly = binding.mode === 'retry-only';
  if (binding.protocol !== PROTOCOL || binding.nonce !== nonce || binding.relay_sha256 !== SOURCE_SHA256
      || !['rewrite', 'retry-only', 'final-only', 'first-required'].includes(binding.mode)
      || (!retryOnly && (!Array.isArray(binding.urls) || binding.urls.length !== 5))
      || (binding.mode === 'rewrite' && (typeof binding.system_prompt !== 'string' || !binding.system_prompt))
      || (['final-only', 'first-required'].includes(binding.mode) && (new Set(binding.urls).size !== 5
          || !binding.urls.every(url => new URL(url).searchParams.get('_run') === nonce)))) {
    throw Error('Binding does not match this relay or its run');
  }
  return binding;
}

// Pull usage and time_info out of the SSE bytes for the log only; the client still gets the original bytes.
function timingOf(bytes) {
  let found = null;
  for (const line of bytes.toString('utf8').split('\n')) {
    if (!line.startsWith('data:') || !line.includes('time_info')) continue;
    try {
      const chunk = JSON.parse(line.slice(5));
      if (chunk.time_info && chunk.usage) found = {completion_time: chunk.time_info.completion_time, completion_tokens: chunk.usage.completion_tokens, prompt_tokens: chunk.usage.prompt_tokens};
    } catch {}
  }
  return found;
}

export function createRelay({upstream, bindings, logs}) {
  const target = new URL(upstream);
  const client = target.protocol === 'https:' ? https : http;
  fs.mkdirSync(logs, {recursive: true, mode: 0o700});
  const log = entry => fs.appendFileSync(path.join(logs, 'requests.jsonl'), JSON.stringify(entry) + '\n', {mode: 0o600});
  return http.createServer((req, res) => {
    if (req.method === 'GET' && req.url === '/health') {
      res.writeHead(200, {'content-type': 'application/json'});
      return res.end(JSON.stringify({ok: true, protocol: PROTOCOL, relay_sha256: SOURCE_SHA256, upstream: target.origin}));
    }
    const chunks = [];
    req.on('data', c => chunks.push(c));
    req.on('end', () => {
      const received = Buffer.concat(chunks);
      const entry = {at_ms: Date.now(), method: req.method, path: req.url, relay_sha256: SOURCE_SHA256, received_sha256: sha(received)};
      let forwarded = received;
      try {
        if (req.method === 'POST' && req.url.endsWith('/chat/completions')) {
          const body = JSON.parse(received.toString('utf8'));
          const nonce = nonceOf(body);
          const binding = readBinding(bindings, nonce);
          entry.nonce = nonce;
          if (binding) {
            entry.run_id = binding.id;
            if (binding.mode === 'retry-only') {
              Object.assign(entry, {phase: 'passthrough', changes: []});
            } else {
              const result = rewrite(body, binding);
              if (binding.mode === 'rewrite' || result.changes.length) forwarded = Buffer.from(JSON.stringify(result.body));
              Object.assign(entry, {phase: result.phase, reasons: result.reasons, changes: result.changes});
            }
            const dir = path.join(logs, binding.id);
            fs.mkdirSync(dir, {recursive: true, mode: 0o700});
            if (binding.mode === 'first-required' && entry.changes.length) {
              const source = `${entry.at_ms}-${entry.received_sha256.slice(0, 12)}.received.json`;
              fs.writeFileSync(path.join(dir, source), received, {mode: 0o600, flag: 'wx'});
            }
            fs.writeFileSync(path.join(dir, `${entry.at_ms}-${sha(forwarded).slice(0, 12)}.json`), forwarded, {mode: 0o600, flag: 'wx'});
          } else {
            entry.phase = 'unbound';
          }
        }
      } catch (error) {
        // Fail closed: a bound run whose rewrite cannot be applied must not reach the model unchanged.
        entry.error = String(error?.message || error);
        log(entry);
        res.writeHead(409, {'content-type': 'application/json'});
        return res.end(JSON.stringify({error: {message: 'relay refused request: ' + entry.error, type: 'relay_error'}}));
      }
      entry.forwarded_sha256 = sha(forwarded);
      const headers = {...req.headers, host: target.host, 'content-length': String(forwarded.length), 'accept-encoding': 'identity'};
      delete headers.connection;
      const started = performance.now();
      // Bound requests that get a 429 are resent here with the identical bytes. OpenClaw's own retry added
      // recovery context to the conversation; this one leaves the request unchanged and the gateway sees one
      // response. Each attempt is logged.
      const bound = Boolean(entry.run_id);
      let late = false;
      try { late = isLateRequest(JSON.parse(forwarded.toString('utf8'))); } catch {}
      const delays = late ? LATE_RETRY_DELAYS_MS : RETRY_DELAYS_MS;
      if (bound) entry.retry_schedule = late ? 'late' : 'first';
      let clientGone = false;
      res.on('close', () => { clientGone = true; });
      entry.attempts = [];
      const send = attempt => {
        // The gateway's base URL already ends in /v1, so the incoming path is forwarded as-is to the upstream origin.
        const upstreamReq = client.request({protocol: target.protocol, hostname: target.hostname, port: target.port || undefined,
          path: req.url, method: req.method, headers}, upstreamRes => {
          const status = upstreamRes.statusCode;
          if (bound && status === 429 && attempt < delays.length && !clientGone) {
            const body = [];
            upstreamRes.on('data', c => body.push(c));
            upstreamRes.on('end', () => {
              entry.attempts.push({status, at_ms: Date.now(), body: Buffer.concat(body).toString('utf8').slice(0, 200)});
              setTimeout(() => { if (!clientGone) send(attempt + 1); }, delays[attempt] * RETRY_SCALE);
            });
            return;
          }
          entry.status = status;
          res.writeHead(status, upstreamRes.headers);
          const seen = [];
          upstreamRes.on('data', c => { seen.push(c); res.write(c); });
          upstreamRes.on('end', () => {
            res.end();
            const bytes = Buffer.concat(seen);
            Object.assign(entry, {upstream_ms: performance.now() - started, response_sha256: sha(bytes), response_bytes: bytes.length, timing: timingOf(bytes)});
            // A rejected rewrite (for example an unsupported tool option) must be diagnosable from the log.
            if (status >= 400) entry.error_body = bytes.toString('utf8').slice(0, 600);
            log(entry);
          });
        });
        upstreamReq.on('error', error => {
          entry.error = 'upstream: ' + error.message;
          log(entry);
          if (!res.headersSent) res.writeHead(502, {'content-type': 'application/json'});
          res.end(JSON.stringify({error: {message: 'relay upstream error', type: 'relay_error'}}));
        });
        upstreamReq.end(forwarded);
      };
      send(0);
    });
  });
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const args = Object.fromEntries(process.argv.slice(2).map(a => a.replace(/^--/, '').split('=')));
  const port = Number(args.port || 19871);
  const root = args.root;
  if (!root) throw Error('usage: request_relay.mjs --root=<cache>/relay [--port=19871] [--upstream=https://api.cerebras.ai]');
  const relay = createRelay({upstream: args.upstream || 'https://api.cerebras.ai', bindings: path.join(root, 'bindings'), logs: path.join(root, 'logs')});
  relay.listen(port, '127.0.0.1', () => console.log(JSON.stringify({listening: port, relay_sha256: SOURCE_SHA256})));
}
