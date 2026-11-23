// Headless trials against the scripted-copy gateway. Each trial is a fresh session;
// the score is the official patch's generationSpeed over that session's history.
import fs from 'node:fs/promises';
import path from 'node:path';
import {randomUUID} from 'node:crypto';
import {setTimeout as delay} from 'node:timers/promises';
import {parseArgs} from 'node:util';
import {pathToFileURL} from 'node:url';
import {existsSync} from 'node:fs';
import {asLines} from './scripted-copy-plugin/core.mjs';

const {values} = parseArgs({options: {
  openclaw: {type: 'string'}, state: {type: 'string'}, port: {type: 'string'},
  out: {type: 'string'}, count: {type: 'string', default: '10'}, label: {type: 'string', default: 'sc'},
  'label-start': {type: 'string', default: '1'},
  'pause-seconds': {type: 'string', default: '5'}, examples: {type: 'string'},
  arm: {type: 'string', default: ''}, 'stop-file': {type: 'string'},
  'deadline-epoch-ms': {type: 'string'}, 'verify-receipt-text': {type: 'boolean', default: false},
  'require-price': {type: 'boolean', default: false},
  prompt: {type: 'string', default: 'Find 5 Christmas gifts from US online stores, with a direct product link for each.'},
}});
const count = Number(values.count);
const labelStart = Math.max(1, Number(values['label-start'] ?? '1') || 1);
const pause = Number(values['pause-seconds']);
const requirePrice = values['require-price'] === true;
if (!values.openclaw || !values.state || !values.out || !/^\d{4,5}$/.test(values.port ?? '')) {
  throw Error('Use --openclaw PATH --state PATH --port PORT --out DIR [--count N] [--label L] [--examples FILE]');
}
const stopFile = values['stop-file'] ? path.resolve(values['stop-file']) : path.join(values.out, 'STOP');
const deadlineMs = values['deadline-epoch-ms'] === undefined ? Infinity : Number(values['deadline-epoch-ms']);
if (values['deadline-epoch-ms'] !== undefined && (!Number.isSafeInteger(deadlineMs) || deadlineMs < 1)) {
  throw Error('Expected a positive millisecond timestamp for --deadline-epoch-ms');
}
const canDispatch = () => Date.now() < deadlineMs && !existsSync(stopFile);
process.env.OPENCLAW_STATE_DIR = path.resolve(values.state);
process.env.OPENCLAW_CONFIG_PATH = path.resolve(values.state, 'openclaw.json');
const {GatewayClient} = await import(pathToFileURL(path.resolve(values.openclaw, 'dist/plugin-sdk/gateway-runtime.js')));
const {generationSpeed, formatTokensPerSecond} = await import(pathToFileURL(path.resolve(values.openclaw,
  'ui/src/pages/chat/chat-generation-speed.ts')));
const examples = values.examples ? JSON.parse(await fs.readFile(values.examples, 'utf8')) : {};
const exampleUrls = new Set((examples.example ?? []).map(e => e.url));
const model = 'cerebras/moonshotai-kimi-k3.1-pro-trial';
const prompt = values.prompt;
await fs.mkdir(values.out, {recursive: true, mode: 0o700});
const ready = Promise.withResolvers();
const client = new GatewayClient({
  url: 'ws://127.0.0.1:' + values.port, token: (await fs.readFile(path.join(values.state, 'gateway-token'), 'utf8')).trim(),
  clientName: 'cli', mode: 'cli', role: 'operator', scopes: ['operator.admin', 'operator.read', 'operator.write'],
  onHelloOk: () => ready.resolve(), onConnectError: err => ready.reject(err),
});
const rpc = (name, params, timeoutMs = 20000) => client.request(name, params, {timeoutMs});
const history = key => rpc('chat.history', {sessionKey: key, limit: 100, toolResultMaxChars: 60000, maxBytes: 1500000});
const textOf = m => typeof m.content === 'string' ? m.content
  : (m.content ?? []).filter(b => b.type === 'text').map(b => b.text).join('\n');
const thinkingOf = m => (Array.isArray(m.content) ? m.content : []).filter(b => b.type === 'thinking')
  .map(b => b.thinking ?? '').join('\n');
const linksOf = text => [...text.matchAll(/\]\((https?:\/\/[^)\s]+)\)/g)].map(x => x[1]);

const receiptDir = path.resolve(values.state, 'catalog-receipts');
const receipts = new Map();
async function loadReceipts() {
  for (const name of await fs.readdir(receiptDir).catch(() => [])) {
    if (!name.endsWith('.json')) continue;
    const r = JSON.parse(await fs.readFile(path.join(receiptDir, name), 'utf8'));
    receipts.set(r.callId, r);
  }
}
const receiptFor = callId => (callId ? receipts.get(callId) : null) ?? null;

function summarize(row) {
  const msgs = row.history?.messages ?? [];
  const calls = msgs.filter(m => m.role === 'assistant' && m.serverGeneration).map(m => ({
    tokens: m.serverGeneration.outputTokens, ms: m.serverGeneration.completionMs,
    tps: m.serverGeneration.outputTokens / (m.serverGeneration.completionMs / 1000),
    stop: m.stopReason, reasoning: thinkingOf(m), responseId: m.responseId ?? null,
    in: m.usage?.input ?? 0, cr: m.usage?.cacheRead ?? 0,
  }));
  const tool = msgs.find(m => m.role === 'toolResult');
  const toolLinks = [...new Set(linksOf(tool ? textOf(tool) : ''))];
  const final = msgs.filter(m => m.role === 'assistant').at(-1);
  const finalText = final ? textOf(final) : '';
  const finalLinks = linksOf(finalText);
  const hosts = new Set(finalLinks.map(u => {
    try { return new URL(u).hostname; } catch { return ''; }
  }).filter(Boolean));
  const priceLines = finalText.split('\n').filter(l => /\]\(https?:\/\//.test(l) && /\$\d+(?:\.\d{2})?/.test(l));
  const priceOk = priceLines.length === 5;
  // The plugin's receipt holds the URLs exactly as the catalog returned them.
  const receipt = receiptFor(tool?.toolCallId ?? tool?.tool_call_id ?? tool?.id);
  const receiptLinks = receipt?.items?.map(it => it.url) ?? [];
  const exactReceiptText = receiptLinks.length === 5 && receipt.receipts?.length === 5
    && receipt.receipts.every(item => item.httpStatus === 200)
    && JSON.stringify(receipt.queries) === JSON.stringify(examples.queries)
    && finalText.trim() === asLines(receipt.items, {includePrice: requirePrice});
  const linksOk = finalLinks.length === 5 && hosts.size === 5 && toolLinks.length === 5
    && finalLinks.every(u => toolLinks.includes(u) && receiptLinks.includes(u) && !u.includes('…') && !u.includes('...'));
  const valid = linksOk && calls.length === 2 && final?.stopReason === 'stop'
    && !finalLinks.some(u => exampleUrls.has(u)) && (!requirePrice || priceOk)
    && (!values['verify-receipt-text'] || exactReceiptText);
  return {calls, toolLinks, finalLinks, receiptLinks, receiptFound: Boolean(receipt), linksOk, priceOk,
    exactReceiptText: Boolean(exactReceiptText), toolResultChars: tool ? textOf(tool).length : 0,
    exampleOverlap: finalLinks.filter(u => exampleUrls.has(u)),
    finalStop: final?.stopReason, valid};
}

function callSnapshot(call) {
  if (!call) return null;
  return {
    tok: call.tokens, ms: Math.round(call.ms * 10) / 10, tps: Math.round(call.tps), exactTps: call.tps,
    rchars: call.reasoning.length, in: call.in, cr: call.cr, responseId: call.responseId,
  };
}

async function trial(i) {
  const id = randomUUID();
  const labelNum = labelStart + i;
  const label = `${values.label}-${String(labelNum).padStart(3, '0')}`;
  const key = `agent:main:scripted-${id}`;
  const row = {id, label, arm: values.arm, sessionKey: key, prompt, startedWall: Date.now()};
  let sent = false, terminal = false;
  try {
    const session = await rpc('sessions.create', {key, agentId: 'main', model, thinkingLevel: 'low'});
    if (session.key !== key || session.runStarted) throw Error('Expected an idle, new session');
    if ((await history(key)).messages.length > 0) throw Error('Session was not empty before the prompt');
    if (!canDispatch()) return false;
    row.sentAt = Date.now();
    sent = true;
    const ack = await rpc('chat.send', {sessionKey: key, message: prompt, thinking: 'low', deliver: false, idempotencyKey: id});
    if (ack.runId !== id) throw Error('Unexpected run ID');
    const until = Date.now() + 170000;
    while (Date.now() < until) {
      const wait = await rpc('agent.wait', {runId: id, timeoutMs: 20000}, 25000);
      if (wait.status !== 'timeout') { row.waitStatus = wait.status; terminal = true; break; }
    }
    row.endedAt = Date.now();
    if (!terminal) throw Error('Run exceeded its deadline');
    for (let k = 0; k < 6; k++) {
      row.history = await history(key);
      if (row.history.messages.some(m => m.role === 'assistant' && ['stop', 'error', 'aborted'].includes(m.stopReason))) break;
      await delay(500);
    }
  } catch (err) {
    row.error = String(err?.message ?? err);
    if (sent && !terminal) {
      await rpc('chat.abort', {sessionKey: key, runId: id}).catch(() => {});
      await rpc('agent.wait', {runId: id, timeoutMs: 25000}, 30000).catch(() => null);
    }
    row.history = await history(key).catch(() => ({messages: []}));
  }
  row.endedAt ??= Date.now();
  row.wallSeconds = row.sentAt ? (row.endedAt - row.sentAt) / 1000 : null;
  row.official = generationSpeed(row.history.messages);
  row.officialDisplay = row.official ? formatTokensPerSecond(row.official.meanTokensPerSecond) : null;
  await loadReceipts();
  row.summary = summarize(row);
  await fs.writeFile(path.join(values.out, label + '.json'), JSON.stringify(row, null, 2) + '\n', {mode: 0o600});
  const uncachedIn = row.summary.calls.reduce((acc, c) => acc + c.in, 0);
  const totalIn = row.summary.calls.reduce((acc, c) => acc + c.in + c.cr, 0);
  const line = {
    label, arm: values.arm, id, sessionKey: key, at: new Date().toISOString(), wall: row.wallSeconds,
    sentAt: row.sentAt ?? null,
    mean: row.official?.meanTokensPerSecond ?? null, display: row.officialDisplay,
    p90: row.official?.p90TokensPerSecond ?? null,
    valid: row.summary.valid, linksOk: row.summary.linksOk, priceOk: row.summary.priceOk,
    exactReceiptText: row.summary.exactReceiptText, toolResultChars: row.summary.toolResultChars,
    receipt: row.summary.receiptFound, overlap: row.summary.exampleOverlap.length,
    c0: callSnapshot(row.summary.calls[0]), c1: callSnapshot(row.summary.calls[1]),
    uncachedIn, totalIn, finalLinks: row.summary.finalLinks,
    calls: row.summary.calls.map(c => ({tok: c.tokens, ms: Math.round(c.ms * 10) / 10, tps: Math.round(c.tps),
      rchars: c.reasoning.length, in: c.in, cr: c.cr, responseId: c.responseId})),
    error: row.error ?? null,
  };
  await fs.appendFile(path.join(values.out, 'results.jsonl'), JSON.stringify(line) + '\n');
  console.log(JSON.stringify(line));
  return true;
}

try {
  client.start();
  const timer = setTimeout(() => ready.reject(Error('Gateway connection timed out')), 25000);
  try { await ready.promise; } finally { clearTimeout(timer); }
  for (let i = 0; i < count; i++) {
    if (i) await delay(pause * 1000);
    if (!canDispatch() || !await trial(i)) break;
  }
} finally {
  await client.stop();
}
