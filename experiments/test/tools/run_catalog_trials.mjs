import fs from 'node:fs/promises';
import path from 'node:path';
import {randomUUID} from 'node:crypto';
import {setTimeout as delay} from 'node:timers/promises';
import {parseArgs} from 'node:util';
import {pathToFileURL} from 'node:url';

const {values} = parseArgs({options: {
  openclaw: {type: 'string'}, state: {type: 'string'}, port: {type: 'string'},
  out: {type: 'string'}, count: {type: 'string', default: '10'},
  'pause-seconds': {type: 'string', default: '10'},
}});
const count = Number(values.count);
const pause = Number(values['pause-seconds']);
if (!values.openclaw || !values.state || !values.out || !/^\d{4,5}$/.test(values.port ?? '')
    || !Number.isInteger(count) || count < 1 || !Number.isFinite(pause) || pause < 0) {
  throw Error('Use --openclaw PATH --state PATH --port PORT --out NEW_DIRECTORY [--count 10] [--pause-seconds 10]');
}
process.env.OPENCLAW_STATE_DIR = path.resolve(values.state);
process.env.OPENCLAW_CONFIG_PATH = path.resolve(values.state, 'openclaw.json');
const {GatewayClient} = await import(pathToFileURL(path.resolve(values.openclaw, 'dist/plugin-sdk/gateway-runtime.js')));
const {generationSpeed, formatTokensPerSecond} = await import(pathToFileURL(path.resolve(values.openclaw,
  'ui/src/pages/chat/chat-generation-speed.ts')));
const model = 'cerebras/moonshotai-kimi-k3.1-pro-trial';
const prompt = 'Find five Christmas gifts that ship to the US. Search the live catalog once for Christmas gifts. Give five Markdown links using the exact product titles and URLs.';
const save = (file, body) => fs.writeFile(path.join(values.out, file), JSON.stringify(body, null, 2) + '\n',
  {flag: 'wx', mode: 0o600, flush: true});
const ready = Promise.withResolvers();
const client = new GatewayClient({
  url: 'ws://127.0.0.1:' + values.port, token: (await fs.readFile(path.join(values.state, 'gateway-token'), 'utf8')).trim(),
  clientName: 'cli', mode: 'cli', role: 'operator', scopes: ['operator.admin', 'operator.read', 'operator.write'],
  onHelloOk: () => ready.resolve(), onConnectError: err => ready.reject(err),
});
const rpc = (name, params, timeoutMs = 20000) => client.request(name, params, {timeoutMs});
const history = key => rpc('chat.history', {sessionKey: key, limit: 100, toolResultMaxChars: 60000, maxBytes: 1500000});
const plans = Array.from({length: count}, (_, i) => {
  const id = randomUUID();
  return {id, label: 'catalog-' + String(i + 1).padStart(2, '0'), sessionKey: 'agent:main:shop-catalog-' + id,
    model, thinking: 'low', prompt};
});
await fs.mkdir(values.out, {recursive: true, mode: 0o700});
await save('plan.json', {startedAt: new Date().toISOString(), pauseSeconds: pause, threshold: 1673, trials: plans});

async function trial(plan) {
  const key = plan.sessionKey;
  const row = {...plan, startedWall: Date.now()};
  let sent = false;
  let terminal = false;
  try {
    const session = await rpc('sessions.create', {key, agentId: 'main', model, thinkingLevel: 'low'});
    if (session.key !== key || session.runStarted) throw Error('Expected an idle, new session');
    if ((await history(key)).messages.length > 0) throw Error('Session was not empty before the prompt');
    row.sentAt = Date.now();
    sent = true;
    const ack = await rpc('chat.send', {sessionKey: key, message: prompt, thinking: 'low', deliver: false, idempotencyKey: plan.id});
    if (ack.runId !== plan.id) throw Error('Unexpected run ID');
    const until = Date.now() + 165000;
    while (Date.now() < until) {
      const wait = await rpc('agent.wait', {runId: plan.id, timeoutMs: 20000}, 25000);
      if (wait.status !== 'timeout') {
        row.waitStatus = wait.status;
        terminal = true;
        break;
      }
    }
    row.endedAt = Date.now();
    if (!terminal) throw Error('Run exceeded its deadline');
    for (let i = 0; i < 6; i++) {
      row.history = await history(key);
      if (row.history.messages.some(m => m.role === 'assistant' && ['stop', 'error', 'aborted'].includes(m.stopReason))) break;
      await delay(500);
    }
  } catch (err) {
    row.error = String(err?.message ?? err);
    if (sent && !terminal) {
      await rpc('chat.abort', {sessionKey: key, runId: plan.id}).catch(() => {});
      const stopped = await rpc('agent.wait', {runId: plan.id, timeoutMs: 25000}, 30000).catch(() => null);
      if (!stopped || stopped.status === 'timeout') row.unconfirmedTermination = true;
    }
    row.history = await history(key).catch(() => ({messages: []}));
  }
  row.endedAt ??= Date.now();
  row.wallSeconds = row.sentAt ? (row.endedAt - row.sentAt) / 1000 : null;
  row.official = generationSpeed(row.history.messages);
  row.officialDisplay = row.official ? formatTokensPerSecond(row.official.meanTokensPerSecond) : null;
  await save(plan.label + '.json', row);
  console.log(JSON.stringify({trial: plan.label, status: row.waitStatus ?? row.error, wallSeconds: row.wallSeconds,
    officialMean: row.officialDisplay, calls: row.official?.calls ?? 0,
    tools: row.history.messages.filter(m => m.role === 'toolResult').map(m => m.toolName)}));
  if (row.unconfirmedTermination) throw Error('Prior run did not confirm termination; investigate before continuing');
}

try {
  client.start();
  const timer = setTimeout(() => ready.reject(Error('Gateway connection timed out')), 25000);
  try { await ready.promise; } finally { clearTimeout(timer); }
  for (const [i, plan] of plans.entries()) {
    if (i) await delay(pause * 1000);
    await trial(plan);
  }
} finally {
  await client.stop();
}
