'use strict';

const { createHash } = require('node:crypto');
const fs = require('node:fs/promises');
const path = require('node:path');

const ENDPOINT = 'https://catalog.shopify.com/api/ucp/mcp';
const PROFILE = 'https://shopify.dev/ucp/agent-profiles/examples/2026-08-25/valid-with-capabilities.json';
const GIFT_COUNT = 5;

function productLink(variant) {
  if (!variant?.availability?.available || variant.price?.currency !== 'USD') return null;
  if (typeof variant.url !== 'string' || !URL.canParse(variant.url)) return null;
  const url = new URL(variant.url);
  if (url.protocol !== 'https:' || url.username || url.password || !/\/products\/[^/]+/.test(url.pathname)) return null;
  const variantId = url.searchParams.get('variant');
  url.search = '';
  url.hash = '';
  if (variantId) url.searchParams.set('variant', variantId);
  return url;
}

function selectProducts(products) {
  const seenProducts = new Set();
  const seenStores = new Set();
  const preferred = [];
  const extra = [];
  for (const product of products) {
    const title = product.title?.replace(/\s+/g, ' ').trim();
    const link = (product.variants ?? []).map(productLink).find(Boolean);
    if (!title || !link) continue;
    const identity = link.origin + link.pathname;
    if (seenProducts.has(identity)) continue;
    seenProducts.add(identity);
    const card = { title, url: link.href };
    if (seenStores.has(link.hostname)) {
      extra.push(card);
    } else {
      preferred.push(card);
      seenStores.add(link.hostname);
    }
  }
  return [...preferred, ...extra].slice(0, GIFT_COUNT);
}

async function saveReceipt(details) {
  const directory = process.env.CATALOG_RECEIPT_DIR;
  if (!directory) return;
  if (!path.isAbsolute(directory)) throw new Error('CATALOG_RECEIPT_DIR must be an absolute path.');
  await fs.mkdir(directory, { recursive: true, mode: 0o700 });
  const key = createHash('sha256').update(details.callId).digest('hex');
  const filename = path.join(directory, details.startedMs + '-' + key + '.json');
  const temporary = filename + '.writing';
  await fs.writeFile(temporary, JSON.stringify(details), { flag: 'wx', mode: 0o600 });
  await fs.rename(temporary, filename);
}

async function execute(callId, args, signal) {
  const query = typeof args?.query === 'string' && args.query.trim();
  if (!query || query.length > 240) throw new Error('A catalog query must contain 1 to 240 characters.');
  const startedMs = Date.now();
  const timeout = AbortSignal.timeout(20000);
  const response = await fetch(ENDPOINT, {
    method: 'POST',
    redirect: 'error',
    signal: signal ? AbortSignal.any([signal, timeout]) : timeout,
    headers: { 'Content-Type': 'application/json', Accept: 'application/json, text/event-stream' },
    body: JSON.stringify({
      jsonrpc: '2.0',
      id: 1,
      method: 'tools/call',
      params: {
        name: 'search_catalog',
        arguments: {
          meta: { 'ucp-agent': { profile: PROFILE } },
          catalog: {
            query,
            context: { address_country: 'US', currency: 'USD' },
            filters: { ships_to: { country: 'US' }, available: true },
            pagination: { limit: 20 }
          }
        }
      }
    })
  });
  if (!response.ok) throw new Error('Shopify catalog returned HTTP ' + response.status);
  const raw = Buffer.from(await response.arrayBuffer());
  const completedMs = Date.now();
  const payload = JSON.parse(raw.toString('utf8'));
  const listing = payload.result?.structuredContent?.products;
  if (!Array.isArray(listing) || payload.result?.isError || payload.error) throw new Error('Invalid catalog response.');
  const products = selectProducts(listing);
  if (products.length !== GIFT_COUNT) throw new Error('Fewer than five distinct in-stock products in the catalog response.');

  const details = {
    products, httpStatus: response.status, requestCount: 1, callId, startedMs, completedMs,
    endpoint: ENDPOINT, query, returnedProductCount: listing.length,
    responseSha256: createHash('sha256').update(raw).digest('hex')
  };
  await saveReceipt(details);
  return { content: [{ type: 'text', text: products.map(p => p.title + '\n' + p.url).join('\n\n') }], details };
}

module.exports = {
  id: 'shopper-catalog-search',
  name: 'Shopper catalog search',
  register(api) {
    api.registerTool({
      name: 'search_catalog',
      label: 'Search Catalog',
      description: 'Search the live shopping catalog once for five in-stock Christmas gift ideas. Returns titles and direct US-shipping retail product links.',
      parameters: {
        type: 'object',
        properties: { query: { type: 'string', minLength: 1, maxLength: 240 } },
        required: ['query'],
        additionalProperties: false
      },
      execute
    });
  }
};
