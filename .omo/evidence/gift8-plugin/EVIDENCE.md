# Gift8 plugin verification

All invocations run from repository root; no paid/model sends, no runtime patch.

| Criterion/scenario | Invocation | Binary observable | Artifact |
|---|---|---|---|
| CJS syntax | `node --check tools/gift8-plugin/index.cjs` | exit 0, PASS recorded | `syntax.log` |
| Five parallel HTTP tool fetches; canonical prefetch parity; denied authority; foreign session/prompt; retries/duplicates; receipt alteration; restart; digest mismatch; foreign redirect; sanitized input evidence | `node tools/gift8-plugin/fixture-test.cjs` | passed=true; exactly 10 local HTTP requests, provider_sends=0; all assertions passed | `fixture-report.json`, `fixture.log`, fixture root recorded therein with original receipt/body/event bytes |
| Native prompt preservation + actual native hook registration/dispatch | `$OPENCLAW/node_modules/.bin/tsx --tsconfig $OPENCLAW/tsconfig.json tools/gift8-plugin/native-fixture.mts $OPENCLAW` | passed=true; prompt_preserved=true; native system and allowlist equal plugin expected; provider_sends=0 | `native-report.json`, `native.log`, native root recorded therein |

OPENCLAW=~/Library/Caches/cerebras-speed-bounty/2026-11-22/openclaw; version 2026.10.9. Final passing reports pin the same plugin digest. The native check invokes source functions and the real hook runner, not a whole provider/gateway send. Failed exploratory fixtures remain but are not claimed as passing; only paths named by the final reports are evidence for this attempt.
