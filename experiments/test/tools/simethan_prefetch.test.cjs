'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const os = require('node:os');
const {randomUUID, createHash} = require('node:crypto');
const {prefetch, QUERIES} = require('./simethan_prefetch.cjs');

const hash = data => createHash('sha256').update(data).digest('hex');
async function fixture(t) {
  const base = await fs.mkdtemp(path.join(os.tmpdir(), 'catalog-prefetch-offline-'));
  t.after(() => fs.rm(base, {force: true, recursive: true}));
  return base;
}
function listing(query, i) {
  const variant = {url: 'https://shop.example/products/item-' + i + '?source=ad&variant=1001#top',
    price: {currency: 'USD', amount: 2599}, availability: {available: true}, seller: {name: 'Gift shop'}};
  return {title: query, description: {html: '<p>Maker &amp; craft. ' + 'A varied long sentence. '.repeat(60) + '</p>'},
    variants: [variant]};
}
function envelope(products) {
  return JSON.stringify({jsonrpc: '2.0', id: 1, result: {structuredContent: {products}}});
}

test('dispatches all five freshly on every run and ties receipts to the exact returned bytes', async t => {
  const base = await fixture(t);
  let calls = [];
  async function fetcher(url, options) {
    assert.equal(url, 'https://catalog.shopify.com/api/ucp/mcp');
    const payload = JSON.parse(options.body).params.arguments.catalog;
    const {query} = payload, i = QUERIES.indexOf(query);
    assert.deepEqual(payload.filters,{ships_to:{country:'US'},available:true});
    assert.equal(options.cache,'no-store');
    const gate = Promise.withResolvers();
    calls.push(gate);
    if (calls.length === 5) calls.forEach(c => c.resolve());
    await gate.promise;
    const correct = listing(query, i);
    const stockout = structuredClone(correct);stockout.variants[0].availability.available=false;
    const expensive = structuredClone(correct);expensive.variants[0].price.amount=5001;
    const nonusd = structuredClone(correct);nonusd.variants[0].price.currency='EUR';
    const badLink = structuredClone(correct);badLink.variants[0].url='https://shop.example/';
    const unrelated = structuredClone(correct);unrelated.title='Leather wallet';
    const raw = envelope([stockout,expensive,nonusd,badLink,unrelated,correct]);
    return new Response(i === 2 ? 'event: message\ndata: '+raw+'\n\n' : raw);
  }
  for (let n=0; n<2; n++) {
    calls = [];
    const id = randomUUID();
    const r = await prefetch(base,id,{fetcher});
    assert.equal(calls.length,5);
    assert.equal(r.valid,true);
    assert.equal(r.id,id);
    assert.equal(r.list,r.rendered);
    assert.equal(r.products.length,5);
    for (const [i,p] of r.products.entries()) {
      assert.equal(p.query,QUERIES[i]);
      assert.equal(p.productIndex,5);
      assert.equal(p.price,25.99);
      assert.ok(p.description.length<=700);
      assert.match(p.description,/Maker & craft/);
      assert.equal(p.url,'https://shop.example/products/item-'+i+'?variant=1001');
      assert.ok(r.list.includes(p.url));
      const row = r.lookups[i];
      assert.equal(row.id,id);
      assert.ok(row.startedMs>=r.startedMs && row.completedMs>=row.startedMs && row.completedMs<=r.completedMs);
      assert.equal(hash(await fs.readFile(path.join(base,id,row.rawFile))),p.bodySha256);
      assert.equal(hash(await fs.readFile(path.join(base,id,row.requestFile))),row.requestSha256);
    }
    await assert.rejects(prefetch(base,id,{fetcher}),{code:'EEXIST'});
    assert.equal(calls.length,5);
  }
});

test('HTTP limit, transport failure, invalid body and duplicate products leave five identified receipts',async t => {
  const base=await fixture(t), id=randomUUID();
  const r=await prefetch(base,id,{fetcher:async (_url,options)=>{
    const q=JSON.parse(options.body).params.arguments.catalog.query;
    const i=QUERIES.indexOf(q);
    if(i===0) return new Response('quota',{status:429,headers:{'retry-after':'21'}});
    if(i===1) throw Error('network interrupted');
    if(i===2) return new Response('unparseable');
    const raw=listing(q,1);
    raw.variants[0].url='https://shop.example/products/same?variant='+i;
    return new Response(envelope([raw]));
  }});
  assert.equal(r.valid,false);
  assert.equal(r.rendered,'');
  assert.equal(r.lookups.length,5);
  assert.equal(r.lookups[0].status,429);
  assert.equal(r.lookups[0].retryAfter,'21');
  assert.equal(r.lookups[0].bodySha256,hash('quota'));
  assert.equal(r.lookups[1].status,null);
  assert.equal(r.lookups[2].ok,false);
  assert.equal(r.products.length,1);
});
test('expired absolute deadline sends zero requests and seals all five outcomes', async t => {
  const base=await fixture(t),id=randomUUID();
  let sends=0;
  const r=await prefetch(base,id,{fetcher:()=>{sends++; throw Error('unexpected send');},deadlineMs:Date.now()-1});
  assert.equal(sends,0);
  assert.equal(r.valid,false);
  assert.ok(r.lookups.every(l=>l.startedMs===null && l.error.includes('Deadline')));
});
