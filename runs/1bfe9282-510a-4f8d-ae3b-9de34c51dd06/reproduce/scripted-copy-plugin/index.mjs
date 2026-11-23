// Scripted-copy shopper: live Shopify Global Catalog search plus request shaping
// that makes every token of the shopping turn copyable from the context.
// Server-side timing (usage, time_info) is never touched.
import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
// The stream class must come from the gateway's own module instance; the launcher
// replaces this placeholder with the file URL of the gateway's dist/plugin-sdk/llm.js.
import { createAssistantMessageEventStream } from "__SCRIPTED_COPY_LLM_SDK__";
import { appendLog, promptPrefix, searchTool, shapePayload } from "./core.mjs";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const DATA = JSON.parse(readFileSync(path.join(HERE, "examples.json"), "utf8"));

// Retry a request that Cerebras rejected with a full queue, or that produced nothing
// within stallMs, before any output reaches OpenClaw. Nothing streamed is replayed.
const QUEUE_FULL = /\b429\b|queue_exceeded|high traffic/i;
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, Math.max(0, ms)));

function withQueueRetry(streamFn, config) {
  const maxAttempts = config.queueRetryAttempts ?? 120;
  const delayMs = config.queueRetryDelayMs ?? 1000;
  const stallMs = config.queueStallMs ?? 8000;
  return (model, context, options) => {
    const out = createAssistantMessageEventStream();
    const outer = options?.signal;
    (async () => {
      for (let attempt = 1; ; attempt++) {
        const ctl = new AbortController();
        const relay = () => ctl.abort(outer?.reason);
        outer?.addEventListener("abort", relay, { once: true });
        const held = [];
        let forwarding = false;
        let retry = null;
        try {
          const inner = await streamFn(model, context, { ...options, signal: ctl.signal });
          const it = inner[Symbol.asyncIterator]();
          const deadline = Date.now() + stallMs;
          for (;;) {
            let next;
            if (!forwarding && attempt < maxAttempts && stallMs > 0) {
              let timer;
              const timeout = new Promise((resolve) => {
                timer = setTimeout(() => resolve(null), Math.max(0, deadline - Date.now()));
              });
              next = await Promise.race([it.next(), timeout]);
              clearTimeout(timer);
              if (next === null) {
                retry = "stall";
                ctl.abort(new Error("scripted-copy: no first token, resending"));
                break;
              }
            } else {
              next = await it.next();
            }
            if (next.done) break;
            const event = next.value;
            if (!forwarding) {
              if (
                event?.type === "error" &&
                attempt < maxAttempts &&
                !outer?.aborted &&
                QUEUE_FULL.test(String(event.error?.errorMessage ?? ""))
              ) {
                retry = "429";
                break;
              }
              if (event?.type === "start") {
                held.push(event);
                continue;
              }
              for (const h of held) out.push(h);
              held.length = 0;
              forwarding = true;
            }
            out.push(event);
          }
        } finally {
          outer?.removeEventListener("abort", relay);
        }
        if (retry) {
          appendLog(config.shapeLog, { phase: `retry-${retry}`, attempt });
          if (retry === "429") await sleep(delayMs);
          if (outer?.aborted) throw new Error("aborted while waiting for the provider queue");
          continue;
        }
        for (const h of held) out.push(h);
        out.end();
        return;
      }
    })().catch((error) => {
      out.push({
        type: "error",
        reason: outer?.aborted ? "aborted" : "error",
        error: {
          role: "assistant",
          content: [],
          api: model?.api,
          provider: model?.provider,
          model: model?.id,
          usage: {
            input: 0,
            output: 0,
            cacheRead: 0,
            cacheWrite: 0,
            totalTokens: 0,
            cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, total: 0 },
          },
          stopReason: outer?.aborted ? "aborted" : "error",
          errorMessage: String(error?.message ?? error),
          timestamp: Date.now(),
        },
      });
      out.end();
    });
    return out;
  };
}

export default {
  id: "scripted-copy",
  name: "Scripted Copy Shopper",
  description: "Live Shopify catalog search with copy-friendly request shaping.",
  register(api) {
    const config = api.pluginConfig ?? {};
    api.registerTool(searchTool(config, DATA));
    api.registerProvider({
      id: "cerebras",
      label: "Cerebras",
      auth: [],
      resolveSystemPromptContribution: () => {
        const stablePrefix = promptPrefix(config, DATA.queries);
        return stablePrefix ? { stablePrefix } : null;
      },
      wrapStreamFn(ctx) {
        const streamFn = ctx.streamFn;
        if (!streamFn) return undefined;
        const shaped = (model, context, options) =>
          streamFn(model, context, {
            ...options,
            onPayload: (payload, payloadModel) => {
              if (payload && typeof payload === "object") shapePayload(payload, config, DATA);
              return options?.onPayload?.(payload, payloadModel);
            },
          });
        return Object.assign(withQueueRetry(shaped, config), { preservesGenericCompatibility: true });
      },
    });
  },
};
