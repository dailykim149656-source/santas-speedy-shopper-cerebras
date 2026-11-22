# Gift8 validator implementation evidence

Offline invocation: `python3 .omo/evidence/gift8-validator/offline_check.py`.
Binary observable: all 24 named scenarios passed; `results.json` contains explicit boolean outcomes and `offline.log` captures stdout. Independent merchant verification is deliberately mocked in these offline fixtures; no live run or HTTP success is claimed.

Scenarios cover both native arms, exact all-call arithmetic, >=1700 target, absent first-input proof, native normalization, foreign prior assistant history, foreign/stale/spoofed receipts, reordered final cards and native result, missing prefetch injection, invalid generation with retained authentic score, and finish retaining exact original bytes plus committed receipt/evidence files in temporary fixture repositories.

Syntax invocation: `python3 -m py_compile tools/gift8_evidence.py`; binary observable exit 0 in `syntax.json`.
Scope comparison: byte equality to HEAD of canonical validate.py, ledger.py, scoring.py, run.mjs, with SHA256 captured in `scope.json`.

Source-based normalization: pinned OpenClaw `src/agents/embedded-agent-runner/run/attempt-prompt-build.ts` normalizes first hook prompt at lines 592/606, adds model identity at lines 330+, while `attempt-llm-boundary.ts:198` excludes current user prompt from historical snapshot. `src/agents/system-prompt.ts:246` adds the exact model identity suffix. Validator permits native user/system/custom context carriers, rejects previous assistant/tool messages, requires manifest prompt and prefetch context exact contiguous once, and permits only exact native model identity suffix after the bound system prompt SHA.

API: `validate(repo, raw_path, receipt_dir, manifest_path=None, plugin_dir=None)` returns report. `finish(repo, raw_path, validation, receipt_dir, manifest_path=None, plugin_dir=None)` accepts report or JSON report path, revalidates (including independent HTTP), archives exact raw in private receipt directory, and commits dedicated gift evidence and exact public receipt/body bytes. CLI: `python3 tools/gift8_evidence.py validate|finish --repo ... --raw ... --receipt-dir ... [--manifest ...] [--plugin-dir ...] [--validation ...]`.
