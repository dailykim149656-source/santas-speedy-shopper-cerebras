import { appendFileSync, mkdirSync, writeFileSync } from "node:fs";
import { createHash } from "node:crypto";
import path from "node:path";

export const TOOL = "search_catalog";
export const ENDPOINT = "https://catalog.shopify.com/api/ucp/mcp";
export const PROFILE =
  "https://shopify.dev/ucp/agent-profiles/examples/2026-08-25/valid-with-capabilities.json";
export const DEFAULT_THOUGHT_CALL = "Call search_catalog now with the exact queries.";
export const DEFAULT_THOUGHT_ANSWER = "Copy the result lines exactly.";
export const REPEAT_HEADER = "\n\nAnswer with exactly these lines:\n";

const COUNTRY_TLD_OK = new Set(["us", "co", "io", "me", "tv", "ai"]);
const HTML_ENTITIES = {
  amp: "&",
  nbsp: " ",
  quot: '"',
  apos: "'",
  "#39": "'",
  rsquo: "’",
  mdash: "—",
  ndash: "–",
};

export const tidy = (v) => String(v ?? "").replace(/\s+/g, " ").trim();

/**
 * Format a Shopify Global Catalog price object (`amount` in USD cents) as `$XX.XX`.
 */
export function formatPrice(priceObj) {
  if (!priceObj || priceObj.currency !== "USD") return null;
  const amount = priceObj.amount;
  if (typeof amount !== "number" || !Number.isFinite(amount) || amount <= 0) return null;
  return `$${(amount / 100).toFixed(2)}`;
}

/**
 * Validate that a Shopify product URL is clean (no ellipsis truncation, HTTPS, `/products/` path, US-friendly TLD).
 */
export function isCleanProductUrl(rawUrl) {
  if (typeof rawUrl !== "string" || !rawUrl) return false;
  if (rawUrl.includes("…") || rawUrl.includes("...")) return false;
  let url;
  try {
    url = new URL(rawUrl);
  } catch {
    return false;
  }
  if (url.protocol !== "https:" || url.username || url.password) return false;
  if (!/\/products\/[^/]+/.test(url.pathname)) return false;
  const tld = url.hostname.split(".").pop()?.toLowerCase() ?? "";
  if (tld.length === 2 && !COUNTRY_TLD_OK.has(tld)) return false;
  return true;
}

/**
 * Normalize a short product description to plain, single-line copy-safe text (max ~95 chars).
 */
export function tidyBlurb(raw, maxLen = 95) {
  const source =
    typeof raw === "string"
      ? raw
      : typeof raw?.plain === "string"
        ? raw.plain
        : typeof raw?.html === "string"
          ? raw.html
          : "";
  if (!source) return "";
  const cleaned = source
    .replace(/<[^>]*>/g, " ")
    .replace(/&([\w#]+);/g, (_, key) => HTML_ENTITIES[key] ?? " ")
    .replace(/https?:\/\/\S+/gi, "")
    .replace(/[<>*_`\[\]#]/g, "")
    .replace(/[\u0000-\u001f\u007f]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
  if (cleaned.length <= maxLen) return cleaned;
  const head = cleaned.slice(0, maxLen);
  const lastSpace = head.lastIndexOf(" ");
  return (lastSpace > 20 ? head.slice(0, lastSpace) : head).trimEnd();
}

export function asLines(items, config = {}) {
  const includePrice = config.includePrice !== false;
  const includeBlurb = config.includeBlurb === true;
  return items
    .map((it, i) => {
      const safeName = tidy(it.name).replace(/[\[\]]/g, "");
      const safeStore = tidy(it.store);
      let line = `${i + 1}. [${safeName}](${it.url})`;
      if (includePrice && it.price) line += ` — ${it.price}`;
      line += ` — ${safeStore}`;
      if (includeBlurb && it.blurb) line += ` — ${tidyBlurb(it.blurb)}`;
      return line;
    })
    .join("\n");
}

export function asResult(items, copies = 3, config = {}) {
  const n = Math.max(1, Math.min(8, Number(copies) || 3));
  const lines = asLines(items, config);
  return Array.from({ length: n }, () => lines).join(REPEAT_HEADER);
}

export function buildArgsObject(queries, config = {}) {
  if (config.richToolArgs === true) {
    return {
      queries,
      country: "US",
      currency: "USD",
      max_price_usd: 100,
      categories: ["apparel", "games", "drinkware", "pantry", "pets"],
    };
  }
  return { queries };
}

export function buildArgsString(queries, config = {}) {
  const obj = buildArgsObject(queries, config);
  const parts = [`"queries": [${obj.queries.map((q) => JSON.stringify(q)).join(", ")}]`];
  if (config.richToolArgs === true) {
    parts.push(`"country": ${JSON.stringify(obj.country)}`);
    parts.push(`"currency": ${JSON.stringify(obj.currency)}`);
    parts.push(`"max_price_usd": ${obj.max_price_usd}`);
    parts.push(
      `"categories": [${obj.categories.map((c) => JSON.stringify(c)).join(", ")}]`,
    );
  }
  return `{${parts.join(", ")}}`;
}

export function resolveThoughts(config = {}) {
  // Nullish coalescing preserves explicit empty string "" for zero-thought tests.
  return {
    thoughtCall: config.thoughtCall ?? DEFAULT_THOUGHT_CALL,
    thoughtAnswer: config.thoughtAnswer ?? DEFAULT_THOUGHT_ANSWER,
  };
}

export function promptPrefix(config = {}, queries = []) {
  if (config.scripted === false) return null;
  const args = buildArgsString(queries, config);
  const { thoughtCall, thoughtAnswer } = resolveThoughts(config);
  const repeat = Math.max(1, Math.min(4, Number(config.call1RepeatPrompt) || 1));
  const callCue = `For any gift or shopping request, immediately call search_catalog with exactly these arguments: ${args}`;
  const repeatedCues =
    repeat > 1
      ? [callCue, ...Array.from({ length: repeat - 1 }, () => `Exact JSON arguments: ${args}`)].join("\n")
      : callCue;
  const callThoughtLine =
    thoughtCall === ""
      ? "Keep your reasoning before that call empty."
      : `Your reasoning before that call must be exactly: ${thoughtCall}`;
  const answerThoughtLine =
    thoughtAnswer === ""
      ? "After the tool result arrives, keep your reasoning empty. Then output the result lines exactly once, with nothing before or after them."
      : `After the tool result arrives, your reasoning must be exactly: ${thoughtAnswer} Then output the result lines exactly once, with nothing before or after them.`;
  return `## Gift search\n${repeatedCues}\n${callThoughtLine}\n${answerThoughtLine}`;
}

export function slimSystemText(config = {}, queries = []) {
  const prefix = promptPrefix(config, queries);
  const header =
    "You are a fast US holiday gift shopping assistant. Use search_catalog once, then copy the returned lines verbatim.";
  return prefix ? `${header}\n\n${prefix}` : header;
}

export function exampleTurn(config = {}, queries = [], exampleItems = []) {
  const { thoughtCall, thoughtAnswer } = resolveThoughts(config);
  const args = buildArgsString(queries, config);
  const copies = config.copies ?? 3;
  const turns = Math.max(1, Math.min(3, Number(config.fewShotTurns) || 1));
  const messages = [];
  for (let i = 0; i < turns; i++) {
    const id = `functions.search_catalog:${i}`;
    messages.push(
      { role: "user", content: "Some holiday gift ideas from US shops, with links." },
      {
        role: "assistant",
        content: "",
        reasoning: thoughtCall,
        tool_calls: [{ id, type: "function", function: { name: TOOL, arguments: args } }],
      },
      { role: "tool", tool_call_id: id, content: asResult(exampleItems, copies, config) },
      { role: "assistant", content: asLines(exampleItems, config), reasoning: thoughtAnswer },
    );
  }
  return messages;
}

export function saveReceipt(entry) {
  const dir = process.env.CATALOG_RECEIPT_DIR;
  if (!dir) return;
  try {
    mkdirSync(dir, { recursive: true, mode: 0o700 });
    const name = `${entry.startedMs}-${createHash("sha256").update(entry.callId).digest("hex").slice(0, 16)}.json`;
    writeFileSync(path.join(dir, name), JSON.stringify(entry), { flag: "wx", mode: 0o600 });
  } catch {}
}

export async function searchOne(query, usedHosts, signal, config = {}, fetchImpl = fetch) {
  const started = Date.now();
  const catalogParams = {
    query,
    pagination: { limit: 8 },
    context: { address_country: "US", currency: "USD" },
    filters: { ships_to: { country: "US" }, available: true },
  };
  if (config.includeBlurb !== true) {
    catalogParams.view = "compact";
  }
  const response = await fetchImpl(ENDPOINT, {
    method: "POST",
    headers: { "content-type": "application/json", accept: "application/json, text/event-stream" },
    body: JSON.stringify({
      jsonrpc: "2.0",
      id: 1,
      method: "tools/call",
      params: {
        name: "search_catalog",
        arguments: {
          meta: { "ucp-agent": { profile: PROFILE } },
          catalog: catalogParams,
        },
      },
    }),
    signal: AbortSignal.any([AbortSignal.timeout(10000), ...(signal ? [signal] : [])]),
  });
  const raw = await response.text();
  const receipt = {
    query,
    httpStatus: response.status,
    ms: Date.now() - started,
    sha256: createHash("sha256").update(raw).digest("hex"),
  };
  if (!response.ok) return { receipt, item: null };
  const json = raw.trimStart().startsWith("{")
    ? JSON.parse(raw)
    : JSON.parse(raw.split("\n").filter((l) => l.startsWith("data:")).at(-1).slice(5));
  const products = json?.result?.structuredContent?.products ?? [];
  receipt.returned = products.length;
  const requirePrice = config.includePrice !== false;
  for (const [rank, product] of products.entries()) {
    const variant = product?.variants?.[0];
    if (!variant?.url || variant.availability?.available === false) continue;
    const price = formatPrice(variant.price);
    if (requirePrice && !price) continue;
    if (!isCleanProductUrl(variant.url)) continue;
    const url = new URL(variant.url);
    if (usedHosts.has(url.hostname)) continue;
    url.search = "";
    url.hash = "";
    const item = {
      name: tidy(product.title),
      store: tidy(variant.seller?.name),
      url: url.href,
      ...(price ? { price } : {}),
      ...(config.includeBlurb === true
        ? { blurb: tidyBlurb(product.description ?? product.shortDescription ?? "") }
        : {}),
    };
    receipt.rank = rank;
    receipt.price = variant.price;
    receipt.item = item;
    return { receipt, item };
  }
  return { receipt, item: null };
}

export function searchTool(config = {}, data = {}) {
  const includePrice = config.includePrice !== false;
  const includeBlurb = config.includeBlurb === true;
  const formatHint = includePrice
    ? includeBlurb
      ? "N. [name](url) — $price — store — blurb"
      : "N. [name](url) — $price — store"
    : "N. [name](url) — store";
  const properties = {
    queries: { type: "array", items: { type: "string" }, minItems: 1, maxItems: 5 },
  };
  if (config.richToolArgs === true) {
    properties.country = { type: "string" };
    properties.currency = { type: "string" };
    properties.max_price_usd = { type: "number" };
    properties.categories = { type: "array", items: { type: "string" } };
  }
  return {
    name: TOOL,
    label: "Search Shopify Catalog",
    description:
      `Live search of US Shopify stores. Call once with 5 short queries. Returns one in-stock product page per ` +
      `query as numbered lines ${formatHint}. Reply with those lines copied exactly.`,
    parameters: {
      type: "object",
      required: ["queries"],
      properties,
    },
    async execute(callId, params, signal) {
      const startedMs = Date.now();
      const queries = (Array.isArray(params?.queries) ? params.queries : [params?.queries])
        .map(tidy)
        .filter(Boolean)
        .slice(0, 5);
      // Parallel fetch, then pick in query order so stores stay distinct.
      const settled = await Promise.allSettled(
        queries.map((q) => searchOne(q, new Set(), signal, config)),
      );
      const used = new Set();
      const items = [];
      const receipts = [];
      for (const [i, r] of settled.entries()) {
        let found =
          r.status === "fulfilled"
            ? r.value
            : { receipt: { query: queries[i], error: String(r.reason) }, item: null };
        if (found.item && used.has(new URL(found.item.url).hostname)) {
          found = await searchOne(queries[i], used, signal, config).catch((e) => ({
            receipt: { query: queries[i], error: String(e) },
            item: null,
          }));
        }
        receipts.push(found.receipt);
        if (found.item) {
          used.add(new URL(found.item.url).hostname);
          items.push(found.item);
        }
      }
      saveReceipt({
        callId,
        startedMs,
        completedMs: Date.now(),
        endpoint: ENDPOINT,
        queries,
        receipts,
        items,
      });
      const liveResultCopies = config.liveResultCopies ?? config.copies ?? 3;
      return {
        content: [{ type: "text", text: asResult(items, liveResultCopies, config) }],
        details: { items, receipts },
      };
    },
  };
}

export function appendLog(filePath, entry) {
  if (!filePath) return;
  try {
    appendFileSync(filePath, `${JSON.stringify({ at: Date.now(), ...entry })}\n`, {
      mode: 0o600,
    });
  } catch {}
}

export function shapePayload(payload, config = {}, data = {}, logFn = appendLog) {
  if (!payload || typeof payload !== "object") return;
  const tools = Array.isArray(payload.tools) ? payload.tools : [];
  const messages = Array.isArray(payload.messages) ? payload.messages : [];
  let answerCall = false;
  for (let i = messages.length - 1; i >= 0; i--) {
    const m = messages[i];
    if (m?.role === "assistant" && !m.tool_calls?.length) break;
    if (m?.role === "tool") {
      answerCall = true;
      break;
    }
  }
  if (!tools.some((t) => t?.function?.name === TOOL) && !answerCall) return;

  if (config.slimSystemPrompt === true) {
    let leadSysCount = 0;
    while (
      leadSysCount < messages.length &&
      (messages[leadSysCount]?.role === "system" || messages[leadSysCount]?.role === "developer")
    ) {
      leadSysCount++;
    }
    const sysRole = leadSysCount > 0 ? messages[0].role : "system";
    messages.splice(0, leadSysCount, {
      role: sysRole,
      content: slimSystemText(config, data.queries ?? []),
    });
  }

  if (answerCall) {
    delete payload.tool_choice;
    if (config.stripFinalTools === true) {
      delete payload.tools;
    }
  } else {
    payload.tool_choice = "required";
  }

  payload.max_completion_tokens = config.maxCompletionTokens ?? 512;
  delete payload.max_tokens;

  if (config.fewShot !== false) {
    const first = messages.findIndex((m) => m?.role !== "system" && m?.role !== "developer");
    const turns = exampleTurn(config, data.queries ?? [], data.example ?? []);
    if (first >= 0) messages.splice(first, 0, ...turns);
    else messages.push(...turns);
  }

  logFn(config.shapeLog, {
    phase: answerCall ? "answer" : "call",
    roles: messages.map((m) => m?.role),
    chars: JSON.stringify(messages).length,
    temperature: payload.temperature,
    reasoning_effort: payload.reasoning_effort,
    tool_choice: payload.tool_choice ?? null,
    toolsCount: Array.isArray(payload.tools) ? payload.tools.length : 0,
  });

  if (config.payloadLog) {
    logFn(config.payloadLog, {
      phase: answerCall ? "answer" : "call",
      model: payload.model,
      temperature: payload.temperature,
      max_completion_tokens: payload.max_completion_tokens,
      tool_choice: payload.tool_choice ?? null,
      toolsCount: Array.isArray(payload.tools) ? payload.tools.length : 0,
      messages,
    });
  }
}
