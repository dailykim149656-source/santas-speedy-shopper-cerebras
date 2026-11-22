'use strict';

const fs = require('node:fs/promises');
const path = require('node:path');
const { createHash } = require('node:crypto');

const ENDPOINT = 'https://catalog.shopify.com/api/ucp/mcp';
const PROFILE = 'https://shopify.dev/ucp/agent-profiles/examples/2026-08-25/valid-with-capabilities.json';
const QUERIES = ['collapsible coffee dripper', 'cast iron skillet', 'enamel camp mug', 'leather pocket journal', 'leather keychain'];
const TYPES = [/dripper|pour[ -]?over/i, /skillet|frying pan|fry pan/i, /\bmugs?\b/i, /journal|notebook/i, /key[ -]?(?:chain|ring|fob)/i];
const sha = bytes => createHash('sha256').update(bytes).digest('hex');
const write = (file, bytes) => fs.writeFile(file, bytes, {flag: 'wx', mode: 0o600, flush: true});
const writeJson = (file, value) => write(file, JSON.stringify(value, null, 2) + '\n');

function plain(input) {
  if (typeof input !== 'string') return '';
  const entities = {amp: '&', nbsp: ' ', quot: '"', apos: "'", '#39': "'", rsquo: '’', mdash: '—', ndash: '–'};
  return input.replace(/<[^>]*>/g, ' ').replace(/&([\w#]+);/g, (_, key) => entities[key] ?? ' ')
    .replace(/https?:\/\/\S+/gi, '').replace(/[<>*_\x60\[\]#]/g, '')
    .replace(/[\u0000-\u001f\u007f]/g, ' ').replace(/\s+/g, ' ').trim();
}

function description(text) {
  const cleaned = plain(text);
  if (cleaned.length <= 700) return cleaned;
  const head = cleaned.slice(0, 700);
  const sentence = Math.max(head.lastIndexOf('. '), head.lastIndexOf('! '), head.lastIndexOf('? '));
  if (sentence >= 0) return head.slice(0, sentence + 1);
  return head.slice(0, head.lastIndexOf(' ') > 0 ? head.lastIndexOf(' ') : head.length).trimEnd();
}

function directLink(text) {
  if (typeof text !== 'string' || !URL.canParse(text)) return null;
  const u = new URL(text);
  if (u.protocol !== 'https:' || u.username || u.password || u.port ||
      !/(?:^|\/)products\/[^/]+\/?$/.test(u.pathname)) return null;
  const variant = u.searchParams.get('variant');
  if (variant && !/^\d+$/.test(variant)) return null;
  u.pathname = u.pathname.replace(/\/$/, '');
  u.search = '';
  u.hash = '';
  if (variant) u.searchParams.set('variant', variant);
  return u.href;
}

function catalogRows(raw) {
  const text = raw.toString('utf8');
  let payload;
  try { payload = JSON.parse(text); }
  catch {
    const blocks = text.split(/\r?\n\r?\n/);
    for (const block of blocks) {
      const data = block.split(/\r?\n/).filter(line => line.startsWith('data:'))
        .map(line => line.slice(5).trimStart()).join('\n');
      if (!data || data === '[DONE]') continue;
      const candidate = JSON.parse(data);
      if (candidate.result || candidate.error) payload = candidate;
    }
  }
  if (payload?.error || payload?.result?.isError || !Array.isArray(payload?.result?.structuredContent?.products)) {
    throw Error('Shopify returned no usable product list');
  }
  return payload.result.structuredContent.products;
}

function candidates(items, index) {
  const query = QUERIES[index];
  const tokens = query.split(' ');
  const result = [];
  for (const [productIndex, p] of items.entries()) {
    const v = p?.variants?.[0];
    const name = plain(p?.title);
    const seller = plain(v?.seller?.name);
    const url = directLink(v?.url);
    const amount = v?.price?.amount;
    const about = description(p?.description?.plain || p?.description?.html);
    if (!TYPES[index].test(name) || tokens.filter(t => name.toLowerCase().includes(t)).length * 2 < tokens.length) continue;
    if (!seller || !url || !about || v.availability?.available !== true || v.price?.currency !== 'USD' ||
        !Number.isSafeInteger(amount) || amount < 1 || amount > 5000) continue;
    result.push({query, name, seller, price: amount / 100, currency: 'USD', url, description: about,
      productIndex, variantIndex: 0});
  }
  return result;
}

function requestBody(query) {
  return {jsonrpc: '2.0', id: 1, method: 'tools/call',
    params: {name: 'search_catalog', arguments: {meta: {'ucp-agent': {profile: PROFILE}},
      catalog: {query, context: {address_country: 'US', currency: 'USD'},
        filters: {ships_to: {country: 'US'}, available: true}, pagination: {limit: 10}}}}};
}

async function lookup(dir, id, index, fetcher, deadlineMs) {
  const query = QUERIES[index];
  const prefix = 'lookup-' + (index + 1);
  const body = JSON.stringify(requestBody(query));
  const row = {id, index, query, endpoint: ENDPOINT, requestFile: prefix + '.request.json', requestSha256: sha(body),
    startedMs: null, completedMs: null, status: null, rawFile: null, bodySha256: null, ok: false};
  let choices = [];
  try {
    await write(path.join(dir, row.requestFile), body);
    const timeout = Math.min(11000, Math.floor(deadlineMs - Date.now()));
    if (timeout <= 0) throw Error('Deadline before lookup');
    row.startedMs = Date.now();
    const response = await fetcher(ENDPOINT, {method: 'POST', body, redirect: 'error', cache: 'no-store',
      headers: {'content-type': 'application/json', accept: 'application/json, text/event-stream', 'cache-control': 'no-cache'},
      signal: AbortSignal.timeout(timeout)});
    row.status = response.status;
    row.retryAfter = response.headers?.get('retry-after') ?? null;
    const raw = Buffer.from(await response.arrayBuffer());
    row.completedMs = Date.now();
    row.rawFile = prefix + '.response.bin';
    row.bodySha256 = sha(raw);
    await write(path.join(dir, row.rawFile), raw);
    if (response.status !== 200) throw Error('Shopify HTTP ' + response.status);
    choices = candidates(catalogRows(raw), index);
    row.candidateCount = choices.length;
    if (!choices.length) throw Error('No matching in-stock product with seller, price, description, and direct link');
    row.ok = true;
  } catch (error) {
    row.error = String(error?.message ?? error).slice(0, 300);
  }
  row.completedMs ??= Date.now();
  await writeJson(path.join(dir, prefix + '.json'), row);
  return {row, choices};
}

function render(products) {
  return products.map((p,i) => (i + 1) + '. **' + p.name + '** — ' + p.seller + ' — $' + p.price.toFixed(2)
    + '\n   ' + p.url + '\n   ' + p.description).join('\n');
}

async function prefetch(out, id, {fetcher = fetch, deadlineMs = Infinity} = {}) {
  if (!/^[\da-f]{8}-(?:[\da-f]{4}-){3}[\da-f]{12}$/i.test(id) ||
      (deadlineMs !== Infinity && !Number.isFinite(deadlineMs))) throw Error('Invalid run ID or deadline');
  const dir = path.resolve(out, id);
  const startedMs = Date.now();
  await fs.mkdir(dir, {mode: 0o700, recursive: true});
  await writeJson(path.join(dir, 'prefetch.intent.json'), {id, startedMs, queries: QUERIES, endpoint: ENDPOINT,
    codeSha256: sha(await fs.readFile(__filename))});
  const settled = await Promise.allSettled(QUERIES.map((_,i) => lookup(dir, id, i, fetcher, deadlineMs)));
  const lookups = [], products = [], used = new Set();
  for (const [i, result] of settled.entries()) {
    if (result.status !== 'fulfilled') {
      lookups.push({id, index: i, query: QUERIES[i], ok: false, error: 'Lookup receipt write failed'});
      continue;
    }
    lookups.push(result.value.row);
    const chosen = result.value.choices.find(p => !used.has(p.url.split('?')[0]));
    if (chosen) {
      used.add(chosen.url.split('?')[0]);
      products.push({...chosen, lookupIndex: i, bodySha256: result.value.row.bodySha256});
    }
  }
  const valid = products.length === QUERIES.length && lookups.every(r => r.ok);
  const list = valid ? render(products) : '';
  const result = {id, valid, startedMs, completedMs: Date.now(), queries: QUERIES, products, rendered: list, list, lookups};
  await writeJson(path.join(dir, 'prefetch.json.writing'), result);
  await fs.rename(path.join(dir, 'prefetch.json.writing'), path.join(dir, 'prefetch.json'));
  return result;
}

module.exports = {prefetch, QUERIES};

if (require.main === module) {
  const [out, id] = process.argv.slice(2);
  if (!out || !id) { console.error('Usage: node simethan_prefetch.cjs OUT_DIR UUID'); process.exitCode = 2; }
  else prefetch(out, id, {deadlineMs: process.env.PREFETCH_DEADLINE_MS ? Number(process.env.PREFETCH_DEADLINE_MS) : Infinity})
    .then(r => { console.log(JSON.stringify({id, valid: r.valid, products: r.products.length})); process.exitCode = r.valid ? 0 : 1; })
    .catch(e => { console.error(e.message); process.exitCode = 2; });
}
