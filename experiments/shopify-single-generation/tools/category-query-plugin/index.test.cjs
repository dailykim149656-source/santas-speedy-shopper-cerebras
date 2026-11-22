'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const os = require('node:os');
const path = require('node:path');
const { createHash } = require('node:crypto');
const { createFactory } = require('./index.cjs');

const runId = '1652a48c-29a5-4946-8b17-e56fe078817b';
const sessionKey = 'agent:main:category-ab-b-' + runId;
const queries = ['filter', 'mixer', 'oscillator', 'echo', 'cable'];

async function setup(t, alter = () => {}) {
  const directory = await fs.mkdtemp(path.join(os.tmpdir(), 'category-query-'));
  t.after(() => fs.rm(directory, { recursive: true, force: true }));
  const seen = [];
  async function execute(callId, { url }, signal) {
    const parsed = new URL(url);
    const query = parsed.searchParams.get('search');
    const body = JSON.stringify([{ name: query + ' sample', permalink: parsed.origin + '/product/sample-' + query + '/' }], null, 2);
    const page = {
      status: 200, url, finalUrl: url, extractor: 'json', fetchedAt: new Date().toISOString(),
      externalContent: { source: 'web_fetch', untrusted: true },
      text: '<<<EXTERNAL_UNTRUSTED_CONTENT id="abc123">>>\nSource: Web Fetch\n---\n' + body + '\n<<<END_EXTERNAL_UNTRUSTED_CONTENT id="abc123">>>'
    };
    alter(page);
    const result = { content: [{ type: 'text', text: JSON.stringify(page) }], details: page };
    seen.push({ callId, url, result, signal, body });
    return result;
  }
  const factory = createFactory({ receiptDir: directory, openclawRoot: directory }, async () => () => ({ execute }));
  return { directory, seen, factory, tool: factory({ sessionKey }) };
}

test('all five query-only calls retain native results, nonce, receipts and fresh metadata', async t => {
  const { directory, seen, tool } = await setup(t);
  const signal = new AbortController().signal;
  const results = await Promise.all(queries.map(q => tool.execute(q + '-call', { query: q }, signal)));
  assert.equal(seen.length, 5);
  for (const [i, query] of queries.entries()) {
    const call = seen.find(c => c.callId === query + '-call');
    assert.strictEqual(call.signal, signal);
    assert.strictEqual(results[i], call.result);
    assert.equal(call.url, 'https://aisynthesis.com/wp-json/wc/store/v1/products?search=' + query +
      '&per_page=1&stock_status=instock&_fields=name,permalink&_run=1652a48c');
    const receipt = JSON.parse(await fs.readFile(path.join(directory, runId, query + '.json')));
    const savedBody = await fs.readFile(path.join(directory, runId, 'body-' + query + '.txt'), 'utf8');
    assert.equal(savedBody, call.body);
    assert.equal(receipt.bodySha256, createHash('sha256').update(savedBody).digest('hex'));
    assert.deepEqual(receipt.product, JSON.parse(savedBody)[0]);
    assert.equal(receipt.callId, call.callId);
    assert.equal(receipt.runId, runId);
    assert.equal(receipt.sessionKey, sessionKey);
  }
  await assert.rejects(tool.execute('repeated-call', { query: 'filter' }), { code: 'EEXIST' });
  assert.equal(seen.length, 5);
});

test('refuses unrelated sessions, unknown queries and extra arguments before fetching', async t => {
  const { tool, factory, seen } = await setup(t);
  await assert.rejects(factory({ sessionKey: sessionKey.replace('-b-', '-a-') }).execute('call', { query: 'filter' }));
  await assert.rejects(tool.execute('call', { query: 'unexpected' }));
  await assert.rejects(tool.execute('call', { query: 'filter', url: 'unused' }));
  assert.equal(seen.length, 0);
});

test('a cached response leaves an error receipt and never yields a verified product', async t => {
  const { directory, tool } = await setup(t, page => { page.cached = true; });
  await assert.rejects(tool.execute('call', { query: 'mixer' }), /fresh/);
  const receipt = JSON.parse(await fs.readFile(path.join(directory, runId, 'mixer.json')));
  assert.match(receipt.error, /fresh/);
  assert.equal(receipt.product, undefined);
});
