import assert from 'node:assert/strict';
import {once} from 'node:events';
import fs from 'node:fs';
import http from 'node:http';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';
import {createRelay, nonceOf, PROTOCOL, rewrite, SOURCE_SHA256} from './request_relay.mjs';

const nonce = 'ab12cd34';
const urls = ['filter', 'mixer', 'oscillator', 'echo', 'cable'].map(name =>
  `https://aisynthesis.com/wp-json/wc/store/v1/products?search=${name}&_run=${nonce}`);
const binding = {protocol: PROTOCOL, mode: 'final-only', nonce, id: 'fixture', relay_sha256: SOURCE_SHA256, urls};
const first = {
  model: 'fixture', temperature: 0.2, max_completion_tokens: 1024, stream: true,
  messages: [{role: 'system', content: 'Original system message'}, {role: 'user', content: urls.join('\n')}],
  tools: [{type: 'function', function: {name: 'web_fetch'}}], tool_choice: 'auto', parallel_tool_calls: true
};
const calls = urls.map((url, i) => ({id: String(i), type: 'function', function: {name: 'web_fetch', arguments: JSON.stringify({url})}}));
const results = urls.map((url, i) => {
  const product = [{name: 'Gift ' + i, permalink: 'https://aisynthesis.com/product/gift-' + i + '/'}];
  const text = '<<<EXTERNAL_UNTRUSTED_CONTENT id="abc">>>\nSource: Web Fetch\n---\n'
    + JSON.stringify(product) + '\n<<<END_EXTERNAL_UNTRUSTED_CONTENT id="abc">>>';
  return {role: 'tool', tool_call_id: String(i), content: JSON.stringify({url, finalUrl: url, status: 200, text})};
});
const final = {...first, messages: [...first.messages, {role: 'assistant', tool_calls: calls}, ...results]};
const repair = {...final, messages: final.messages.slice(0, -1)};
const {tools: unusedTools, tool_choice: unusedChoice, parallel_tool_calls: unusedParallel, ...withoutTools} = final;

test('final-only keeps original system and permits another fetch after an incomplete or stale result', () => {
  assert.deepEqual(rewrite(first, binding), {body: first, phase: 'first', reasons: [], changes: []});
  assert.deepEqual(rewrite(final, binding), {
    body: withoutTools, phase: 'final', reasons: [],
    changes: ['removed_tools', 'removed_tool_choice', 'removed_parallel_tool_calls']
  });
  const duplicate = structuredClone(final);
  duplicate.messages.at(-1).content = duplicate.messages.at(-1).content.replaceAll('gift-4/', 'gift-0/');
  const invalid = structuredClone(final);
  invalid.messages.at(-1).content = invalid.messages.at(-1).content.replace('"status":200', '"status":503');
  const stale = {...final, messages: [...final.messages, {role: 'user', content: 'Try a different search.'}]};
  for (const input of [repair, duplicate, invalid, stale]) {
    assert.equal(rewrite(input, binding).phase, 'repair');
    assert.deepEqual(rewrite(input, binding).body, input);
  }
  const legacy = rewrite(first, {...binding, mode: 'rewrite', system_prompt: 'Legacy prompt'});
  assert.equal(legacy.body.messages[0].content, 'Legacy prompt');
  assert.equal(legacy.body.tool_choice, 'required');
});

test('bound requests and upstream response bytes survive a 429, for A, F and a prefetch-only P prompt', async t => {
  const temp = fs.mkdtempSync(path.join(os.tmpdir(), 'relay-test-'));
  t.after(() => fs.rmSync(temp, {recursive: true, force: true}));
  const bindings = path.join(temp, 'bindings');
  const logs = path.join(temp, 'logs');
  fs.mkdirSync(bindings);
  const received = [];
  const sse = Buffer.from('data: {"usage":{"completion_tokens":161},"time_info":{"completion_time":0.09618}}\r\n\r\ndata: [DONE]\r\n\r\n');
  let statuses = [];
  const upstream = http.createServer(async (req, res) => {
    const chunks = [];
    for await (const chunk of req) chunks.push(chunk);
    received.push(Buffer.concat(chunks));
    const status = statuses.shift() ?? 200;
    res.writeHead(status, {'Content-Type': status === 429 ? 'application/json' : 'text/event-stream'});
    res.end(status === 429 ? '{"error":"busy"}' : sse);
  });
  const listen = async server => {
    server.listen(0, '127.0.0.1');
    await once(server, 'listening');
    t.after(() => new Promise(resolve => { server.close(resolve); server.closeAllConnections(); }));
    return 'http://127.0.0.1:' + server.address().port;
  };
  const relay = createRelay({upstream: await listen(upstream), bindings, logs});
  const url = await listen(relay) + '/v1/chat/completions';
  const p = {...first, messages: [{role: 'user', content: [{type: 'text', text: 'Show the gifts. _run=' + nonce}]}]};
  assert.equal(nonceOf(p), nonce);
  for (const [mode, body, phase, retry] of [
    ['retry-only', first, 'passthrough', true], ['retry-only', p, 'passthrough', false],
    ['final-only', first, 'first', false], ['final-only', repair, 'repair', false], ['final-only', final, 'final', true]
  ]) {
    fs.writeFileSync(path.join(bindings, nonce + '.json'), JSON.stringify({...binding, mode}));
    const wire = Buffer.from('  ' + JSON.stringify(body, null, 2) + '\n');
    const start = received.length;
    statuses = retry ? [429, 200] : [200];
    const response = await fetch(url, {method: 'POST', body: wire});
    assert.equal(response.status, 200);
    assert.deepEqual(Buffer.from(await response.arrayBuffer()), sse);
    const expected = phase === 'final' ? Buffer.from(JSON.stringify(withoutTools)) : wire;
    assert.equal(received.length - start, retry ? 2 : 1);
    for (const bytes of received.slice(start)) assert.deepEqual(bytes, expected);
    const log = JSON.parse(fs.readFileSync(path.join(logs, 'requests.jsonl'), 'utf8').trimEnd().split('\n').at(-1));
    assert.equal(log.phase, phase);
    assert.equal(log.run_id, binding.id);
    assert.equal(log.attempts.length, retry ? 1 : 0);
  }
});
