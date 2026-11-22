'use strict';

const { createHash } = require('node:crypto');
const fs = require('node:fs/promises');
const { createRequire } = require('node:module');
const path = require('node:path');
const { pathToFileURL } = require('node:url');

const categories = ['filter', 'mixer', 'oscillator', 'echo', 'cable'];
const sessionPattern = /^agent:main:category-ab-b-([a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})$/;
const origin = 'https://aisynthesis.com';
const writeOptions = { flag: 'wx', mode: 0o600, flush: true };

async function loadWebFetch(openclawRoot) {
  // Use the factory from the same patched checkout as the control gateway.
  const manifest = path.join(openclawRoot, 'package.json');
  const { tsImport } = createRequire(manifest)('tsx/esm/api');
  const { createWebFetchTool } = await tsImport('./src/agents/tools/web-fetch.ts', {
    parentURL: pathToFileURL(manifest).href,
    tsconfig: path.join(openclawRoot, 'tsconfig.json')
  });
  return createWebFetchTool;
}

function readRetailResult(result, url, startedMs, completedMs) {
  const page = result.details;
  const fetchedMs = Date.parse(page?.fetchedAt);
  if (result.isError || page?.url !== url || page.finalUrl !== url ||
      page.status !== 200 || page.cached || page.truncated || page.extractor !== 'json' ||
      page.externalContent?.source !== 'web_fetch' || !page.externalContent?.untrusted ||
      page.externalContent?.provider ||
      !Number.isFinite(fetchedMs) || fetchedMs < startedMs || fetchedMs > completedMs) {
    throw new Error('Expected a fresh, complete HTTP 200 response from the requested retail search.');
  }
  const envelope = typeof page.text === 'string' && page.text.match(
    /<<<EXTERNAL_UNTRUSTED_CONTENT id="([a-f0-9]+)">>>\r?\nSource: Web Fetch\r?\n---\r?\n([\s\S]*?)\r?\n<<<END_EXTERNAL_UNTRUSTED_CONTENT id="\1">>>\s*$/
  );
  if (!envelope) throw new Error('Missing native web_fetch JSON envelope.');
  const body = envelope[2];
  const rows = JSON.parse(body);
  if (!Array.isArray(rows) || rows.length !== 1 || typeof rows[0]?.name !== 'string' ||
      !rows[0].name.trim() || typeof rows[0].permalink !== 'string') {
    throw new Error('The in-stock category search did not return one named product.');
  }
  const product = { name: rows[0].name, permalink: rows[0].permalink };
  const link = new URL(product.permalink);
  if (link.origin !== origin || link.username || link.password || link.search || link.hash ||
      !/^\/product\/[^/]+\/?$/.test(link.pathname)) {
    throw new Error('The retail result has no direct product link.');
  }
  return { body, product };
}

function createFactory(config, getWebFetch = loadWebFetch) {
  if (!path.isAbsolute(config.receiptDir) || !path.isAbsolute(config.openclawRoot)) {
    throw new Error('Set absolute receiptDir and openclawRoot paths for category-query.');
  }
  let nativeFactory;
  return ctx => ({
    name: 'search_category',
    label: 'Search category',
    description: 'Fetch one current in-stock AI Synthesis product matching the category.',
    parameters: {
      type: 'object',
      properties: { query: { type: 'string', enum: categories } },
      additionalProperties: false,
      required: ['query']
    },
    resultContentSource: 'network',
    async execute(callId, args, signal) {
      const runId = sessionPattern.exec(ctx.sessionKey || '')?.[1];
      if (!runId || typeof callId !== 'string' || !callId ||
          !args || Object.keys(args).length !== 1 || !Object.hasOwn(args, 'query') || !categories.includes(args.query)) {
        throw new Error('Expected a bound B session, a tool call ID and one planned query.');
      }
      const query = args.query;
      const url = origin + '/wp-json/wc/store/v1/products?search=' + query +
        '&per_page=1&stock_status=instock&_fields=name,permalink&_run=' + runId.slice(0, 8);
      const directory = path.join(config.receiptDir, runId);
      await fs.mkdir(directory, { recursive: true, mode: 0o700 });
      await fs.writeFile(path.join(directory, query + '.claim'), callId, writeOptions);
      const record = { runId, sessionKey: ctx.sessionKey, callId, query, url, startedMs: Date.now() };
      const receipt = path.join(directory, query + '.json');
      try {
        nativeFactory ??= getWebFetch(config.openclawRoot);
        const tool = (await nativeFactory)({ config: ctx.runtimeConfig ?? ctx.config, sandboxed: ctx.sandboxed });
        if (!tool) throw new Error('Native web_fetch is disabled.');
        const result = await tool.execute(callId, { url }, signal);
        record.completedMs = Date.now();
        record.status = result.details?.status ?? null;
        record.finalUrl = result.details?.finalUrl ?? null;
        const { body, product } = readRetailResult(result, url, record.startedMs, record.completedMs);
        record.product = product;
        record.bodySha256 = createHash('sha256').update(body).digest('hex');
        await fs.writeFile(path.join(directory, 'body-' + query + '.txt'), body, writeOptions);
        await fs.writeFile(receipt, JSON.stringify(record), writeOptions);
        return result;
      } catch (error) {
        record.completedMs ??= Date.now();
        record.error = String(error.message ?? error);
        await fs.writeFile(receipt, JSON.stringify(record), writeOptions).catch(e => {
          if (e.code !== 'EEXIST') throw e;
        });
        throw error;
      }
    }
  });
}

module.exports = {
  id: 'category-query',
  name: 'D5027 category lookup',
  register(api) {
    api.registerTool(createFactory(api.pluginConfig), { name: 'search_category' });
  },
  createFactory,
  loadWebFetch
};
