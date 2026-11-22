import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const deadline = Date.parse('2026-11-23T02:35:00+09:00');
const root = path.join(os.homedir(), 'Library/Caches/cerebras-speed-bounty/2026-11-22-test');
const cache = path.join(root, 'mean-2000');
const folder = path.join(cache, 'd5027-fast2-0235');
const repo = (process.env.BOUNTY_TEST_REPO || process.cwd());
const variants = new Set(['synth-five-categories-cap', 'mercantile-five-categories-cap']);

async function readJSON(file) {
  try {
    return JSON.parse(await fs.readFile(file, 'utf8'));
  } catch (error) {
    if (error.code === 'ENOENT') return null;
    throw error;
  }
}

async function pendingRun() {
  const campaign = await readJSON(path.join(folder, 'campaign.json'));
  const slot = campaign?.slots?.at(-1);
  if (!slot || slot.result || !Number.isSafeInteger(slot.number) || slot.number < 5130 || !variants.has(slot.arm)) return null;
  const label = 'D' + slot.number + '-' + slot.arm;
  const status = await readJSON(path.join(cache, 'status.json'));
  if (!status || !['preparing_video', 'recording_trial'].includes(status.phase) || status.label !== label) return null;
  const id = status.id;
  if (typeof id !== 'string' || !/^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/.test(id)) return null;
  if (slot.id && slot.id !== id) return null;
  const sessionKey = 'agent:main:shop-' + label.toLowerCase() + '-' + id.slice(0, 8);
  const [plan, pending, terminal] = await Promise.all([
    readJSON(path.join(repo, 'runs', id, 'plan.json')),
    readJSON(path.join(cache, 'runs', label + '.pending.json')),
    readJSON(path.join(repo, 'runs', id, 'evidence.json')),
  ]);
  if (terminal || ![plan, pending].every(p => p?.id === id && p.label === label
      && p.variant === slot.arm && p.sessionKey === sessionKey) || plan.prompt !== pending.prompt) return null;
  return { id, sessionKey };
}

async function main() {
  if (fileURLToPath(import.meta.url) !== path.join(folder, 'abort_active.mjs')) throw Error('unexpected location');
  if (Date.now() < deadline) {
    const signal = await readJSON(path.join(folder, 'competing-sender.json'));
    if (!signal?.senders?.length || Date.now()-Date.parse(signal.at)>20000) return console.log('before-deadline');
  }
  const original = await pendingRun();
  if (!original) return console.log('no-matching-pending-run');
  const state = path.join(root, 'shopper-test');
  process.env.OPENCLAW_STATE_DIR = state;
  process.env.OPENCLAW_CONFIG_PATH = path.join(state, 'openclaw.json');
  const { GatewayClient } = await import(pathToFileURL(path.join(root, 'openclaw/dist/plugin-sdk/gateway-runtime.js')));
  const ready = Promise.withResolvers();
  const client = new GatewayClient({
    url: 'ws://127.0.0.1:19863', token: (await fs.readFile(path.join(state, 'gateway-token'), 'utf8')).trim(),
    clientName: 'cli', mode: 'cli', role: 'operator', scopes: ['operator.read', 'operator.write', 'operator.admin'],
    onHelloOk: () => ready.resolve(), onConnectError: () => ready.reject(Error('local connection failed')),
  });
  const timer = setTimeout(() => ready.reject(Error('local connection timeout')), 7000);
  try {
    client.start();
    await ready.promise;
    const current = await pendingRun();
    if (!current || current.id !== original.id || current.sessionKey !== original.sessionKey) return console.log('pending-run-changed');
    const result = await client.request('chat.abort', {sessionKey: current.sessionKey, runId: current.id}, {timeoutMs: 8000});
    console.log(JSON.stringify({id: current.id, acknowledged: result?.ok === true, aborted: result?.aborted === true}));
  } finally {
    clearTimeout(timer);
    await client.stop();
  }
}

main().catch(() => { console.error('deadline-guard-failed'); process.exitCode = 1; });
