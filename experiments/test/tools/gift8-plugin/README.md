# Gift8 native plugin (gift8-v1)

Verified against local OpenClaw 2026.10.9 native contracts: `src/plugins/hook-agent-context.types.ts`, `hook-types.ts`, `hooks.ts`, and canvas `openclaw.plugin.json`. No runtime patch or dependencies.

Load this directory through native `plugins.load.paths`; enable entry `gift8` with config `{ "campaignRoot": "/absolute/BOUNTY_ROOT/mean-2000/gift8-5051", "timeoutMs": 15000 }`. Include `gift_lookup` in the applicable native tool policy and enable prompt injection for this plugin. Manifest declares `contracts.tools`; package declares `openclaw.extensions`. Both arms preserve the same tool and system prompt.

Before send, exclusively commit `manifests/<runId>.json`:

```
{id,sessionKey,arm:"tool"|"prefetch",prompt_sha256,plugin_sha256,created_ms,ids:[21951,23345,11125,11141,20209],protocol:"gift8-v1"}
```

Use a fresh session per run. `prompt_sha256` is SHA256 UTF8 of the exact ordinary text sent, with no attachment, reset, room event, directive transformation or inter-session provenance. Native fixture executes the real prompt-envelope functions and native hook runner to verify this path. No substring matching. Missing/mismatched bindings cannot fetch. Native hooks may fail open: the harness MUST reject runs without receipts and binding/injection evidence.

`pluginSha256()` hashes concatenated raw file bytes of precisely `index.cjs`, `openclaw.plugin.json`, `package.json`, sorted by filename. It excludes tests/docs; export is available to the runner. Every binding checks this digest and every event records it.

Tool `gift_lookup` takes scalar `{id:integer}`. Its text is `JSON.stringify(card)`; details are `{card,receipt_file}`. Export `canonicalCard(product)` defines ordered fields `id,name,url,price_minor,price_range_minor,currency,stock,options`: raw product name; permalink; integer prices.price; null or integer pair `[min_amount,max_amount]`; currency_code; boolean is_in_stock; sorted unique strings from every variation attribute value. No HTML decoding, inferred stock, synthetic option, or per-option price. `card_sha256` hashes UTF8 `JSON.stringify(card)`. Final output is exactly `{gifts:[cards]}` in requested ID order.

Each real fetch writes `receipts/<id>/body-<product_id>.bin` and `fetch-<product_id>.json`. Receipt fields are `protocol,id,sessionKey,arm,prompt_sha256,product_id,tool_call_id,started_ms,completed_ms,url,final_url,status,body_sha256,body_file,card,card_sha256`. Failure adds error and may have null status/final_url/card. Body is original response bytes (empty if transport/body read failed). All failed/missing evidence is invalid for scoring. Original call ID is null only for prefetch. `calls/<sha256(callId)>.json` links each tool invocation to its run-local receipt with fields `id,sessionKey,arm,product_id,tool_call_id,receipt_file,card_sha256,timestamp_ms`. Repeated calls reuse only this run's verified bytes; no previous-run cache.

Writes use exclusive `.claim` creation followed by atomic rename, compatible with exFAT without hard links. Per-product exclusive `.lock` reserves real fetch identity. Locks/claims intentionally remain: crashes fail closed and must not be repaired into a scored run. In-process retries share one promise; same-run runtime restart verifies receipt bytes before reuse. Cross-process simultaneous lookup fails closed.

Events are exclusive files `events/<ms>-<uuid>.json` with `type,runId,sessionKey,timestamp_ms,plugin_sha256`:

- `prompt_binding`: prompt_sha256, arm, system_prompt_sha256.
- `prefetch_injection`: context, context_sha256, prompt_sha256. Context is `Current merchant cards: ` + JSON.stringify({gifts:cards}). Authority `allows` and `assertActive` checked before work and `assertActive` checked after all fetches.
- `llm_input`: event (native event with thinking/reasoning content removed), prompt_sha256 (native event prompt), bound_prompt_sha256 (committed user prompt). Native event tools/history/systemPrompt retained; no output/reasoning hook registered.

Artifacts are private mode where supported. Ignore platform `._*` sidecars and `.claim`/`.lock` files when collecting JSON events.

Offline validation from repository root:

```
node --check tools/gift8-plugin/index.cjs
node tools/gift8-plugin/fixture-test.cjs
$OPENCLAW/node_modules/.bin/tsx --tsconfig $OPENCLAW/tsconfig.json tools/gift8-plugin/native-fixture.mts $OPENCLAW
```

Fixtures use local merchant HTTP and the real exported handlers. Native fixture imports unmodified pinned source and invokes native hook registration/dispatch; it is not a full provider/gateway run. No provider sends occur.
