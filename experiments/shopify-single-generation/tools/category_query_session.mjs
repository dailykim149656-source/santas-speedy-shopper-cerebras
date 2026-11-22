import fs from 'node:fs/promises';
import path from 'node:path';
import {setTimeout as delay} from 'node:timers/promises';
import {pathToFileURL} from 'node:url';
import {DatabaseSync} from 'node:sqlite';
import {zstdDecompressSync} from 'node:zlib';

// Private gateway state configures the SDK's local operator identity, outside the shared profile.
const [checkout, state, port, directory, label] = process.argv.slice(2);
const plan = JSON.parse(await fs.readFile(path.join(directory, 'plan.json'), 'utf8'));
const slot = plan.trials.find(trial => trial.label === label);
if (!slot) throw Error('Slot is missing from the sealed plan');
process.env.OPENCLAW_STATE_DIR = state;
process.env.OPENCLAW_CONFIG_PATH = path.join(state, 'openclaw.json');
const {GatewayClient} = await import(pathToFileURL(path.join(checkout, 'dist/plugin-sdk/gateway-runtime.js')));
const {generationSpeed, formatTokensPerSecond} = await import(pathToFileURL(
  path.join(checkout, 'ui/src/pages/chat/chat-generation-speed.ts')));
const connected = Promise.withResolvers();
const token = await fs.readFile(path.join(state, 'gateway-token'), 'utf8');
const client = new GatewayClient({
  url: 'ws://127.0.0.1:' + port, token: token.trim(), clientName: 'cli', mode: 'cli',
  role: 'operator', scopes: ['operator.admin', 'operator.read', 'operator.write'],
  onHelloOk: () => connected.resolve(), onConnectError: error => connected.reject(error),
});
const rpc = (name, args, timeoutMs = 20000) => client.request(name, args, {timeoutMs});
const key = slot.sessionKey;
const readHistory = () => rpc('chat.history', {
  sessionKey: key, limit: 100, toolResultMaxChars: 60000, maxBytes: 1500000,
});
const run = {...slot, startedWall: Date.now()};
const output = path.join(directory, label + '.json');
const deadlineTime = plan.deadline ? Date.parse(plan.deadline) : Infinity;
function upstreamFailures() {
  const db = new DatabaseSync(path.join(state, 'agents/main/agent/openclaw-agent.sqlite'), {readOnly: true});
  try {
    const events = db.prepare(`SELECT t.event_json,t.event_zstd FROM transcript_events t
      JOIN session_nodes n ON n.current_session_id=t.session_id WHERE n.session_key=? ORDER BY t.seq`).all(key);
    const failures = [];
    let stage = 'first';
    for (const event of events) {
      const msg = JSON.parse(event.event_json || zstdDecompressSync(event.event_zstd).toString()).message;
      if (msg?.role === 'toolResult') stage = 'final';
      if (msg?.provider !== 'cerebras' || msg.role !== 'assistant' || msg.stopReason !== 'error') continue;
      const status = /^429\b/.test(msg.errorMessage ?? '') || msg.errorCode === 'queue_exceeded'
        || msg.errorType === 'too_many_requests_error' ? 429 :
        /^(401|403)\b/.test(msg.errorMessage ?? '') ? Number(msg.errorMessage.slice(0,3)) : null;
      failures.push({status, stage});
    }
    return failures;
  } finally { db.close(); }
}
let terminal = false;
let finishedAt;
try {
  client.start();
  const timer = setTimeout(() => connected.reject(Error('Gateway connection timeout')), 20000);
  try { await connected.promise; } finally { clearTimeout(timer); }
  const created = await rpc('sessions.create', {key, agentId: 'main', model: slot.model, thinkingLevel: slot.thinking});
  if (created.key !== key || created.runStarted || (await readHistory()).messages.length !== 0) {
    throw Error('Expected a fresh empty session');
  }
  if (plan.protocol === 'simethan-shopify-v1') {
    const {prepareShoppingSession} = await import('./simethan_session.mjs');
    await prepareShoppingSession({slot, state, port, directory, deadlineTime});
  }
  if (Date.now() >= deadlineTime) throw Error('Deadline before send');
  run.sentAt = Date.now();
  await fs.writeFile(output, JSON.stringify({...run, pending: true}), {flag: 'wx', mode: 0o600, flush: true});
  if (Date.now() >= deadlineTime) {
    delete run.sentAt;
    throw Error('Deadline before send');
  }
  const ack = await rpc('chat.send', {
    sessionKey: key, message: slot.prompt, thinking: slot.thinking, deliver: false, idempotencyKey: slot.id,
  }, Math.min(20000, Math.max(1, deadlineTime - Date.now())));
  if (ack.runId !== slot.id) throw Error('Unexpected acknowledged run ID');
  const stop = Math.min(Date.now() + 180000, deadlineTime);
  while (Date.now() < stop) {
    const waitMs = Math.min(20000, Math.max(1, Math.floor(stop - Date.now())));
    const wait = await rpc('agent.wait', {runId: slot.id, timeoutMs: waitMs},
      Math.max(1, Math.min(waitMs + 5000, deadlineTime - Date.now())));
    if (wait.status !== 'timeout') {
      terminal = true;
      run.waitStatus = wait.status;
      finishedAt = Date.now();
      break;
    }
  }
  if (!terminal) throw Error('Trial reached its deadline');
  for (let attempt = 0; attempt < 6; ++attempt) {
    run.history = await readHistory();
    if (run.history.messages.some(m => m.role === 'assistant' && ['stop','error','aborted'].includes(m.stopReason))) break;
    if (attempt < 5) await delay(500);
  }
} catch (error) {
  run.error = String(error.message ?? error);
  if (run.sentAt && !terminal) {
    await rpc('chat.abort', {sessionKey: key, runId: slot.id}).catch(() => {});
    const ack = await rpc('agent.wait', {runId: slot.id, timeoutMs: 20000}, 25000).catch(() => null);
    run.unconfirmedTermination = !ack || ack.status === 'timeout';
  }
  run.history ??= await readHistory().catch(() => ({messages: []}));
} finally {
  await client.stop();
}
run.endedAt = finishedAt ?? Date.now();
run.wallSeconds = run.sentAt ? (run.endedAt - run.sentAt) / 1000 : null;
const assistants = run.history.messages.filter(m => m.role === 'assistant');
const last = assistants.at(-1);
run.ended = {time: run.endedAt, terminal: !run.error && run.waitStatus !== 'error' && last?.stopReason === 'stop' ? 'final' :
  (last?.stopReason === 'aborted' ? 'aborted' : 'error')};
run.official = generationSpeed(run.history.messages) ?? null;
run.officialDisplay = run.official ? formatTokensPerSecond(run.official.meanTokensPerSecond) : null;
try { run.providerFailures = upstreamFailures(); }
catch { run.providerDiagnosticsAvailable = false; }
await fs.writeFile(output + '.writing', JSON.stringify(run, null, 2) + '\n', {mode: 0o600, flag: 'wx', flush: true});
await fs.rename(output + '.writing', output);
console.log(JSON.stringify({label, terminal: run.ended.terminal, officialMean: run.officialDisplay, calls: run.official?.calls}));
if (!run.sentAt || run.unconfirmedTermination) process.exitCode = 2;
