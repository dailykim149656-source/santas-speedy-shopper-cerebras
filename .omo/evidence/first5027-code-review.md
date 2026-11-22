# First5027 safety and integrity code review

codeQualityStatus: WATCH
recommendation: APPROVE
blockers: []

Scope: tools/run_first5027.py, first5027.py, first5027_film.py, HEAD diff in loop.py, method_1700.py and variants.py. User-owned category-focus changes were inspected only for interactions, not proposed for alteration. No plan/notepad was supplied; ulw-loop status returned ULW_LOOP_PLAN_MISSING, so this report uses the fallback evidence path.

## Findings

### CRITICAL
None.

### HIGH
None within the requested pre-run safety scope.

### MEDIUM
- `.omo/evidence/first5027-arms/verify.py:52-53,80-86`: several offline checks pin complete prompt/workspace prose or compare fixtures built directly from implementation constants. These are experiment-configuration checks, not evidence of model behavior, and should not be represented as behavioral coverage. Keep the meaningful raw-identity, measured-turn, call-order and product-binding checks; document frozen experiment inputs separately. The skill perspective flags these prose/implementation-mirroring assertions. No demonstrated runtime correctness failure, so this is nonblocking for this run.
- `tools/first5027.py:176`, `tools/run_first5027.py:82`, and the film watcher use mostly untyped dictionary contracts. This violates the programming skill's typed-boundary perspective and makes future schema evolution harder. Current artifact boundary guards and negative checks mitigate the immediate risk; no new abstraction or migration is required before the authorized experiment.

### LOW
- `tools/loop.py:234-245`: score-first deliberately starts without a recorder-ready handshake. `tools/first5027_film.py:193-211` requires pre-send timing for full-run verification and rejects late capture for that claim. Starting the watcher first improves odds but cannot guarantee full-run capture. A successful score must remain provisional until same-run verified video is available; post-run retries cannot retroactively supply pre-send footage.

## Verified evidence

- Independently inspected full changed/new modules and native main/exp exclusive-lock sites. Controller holds shared foreign reservations plus exclusive test reservation for its entire campaign; these block the native loops' exclusive flock. Agent child inherits the reservation descriptors. Foreign pending runs lacking terminal evidence refuse a new campaign.
- Live read-only lock probe on `~/Library/Caches/cerebras-speed-bounty/2026-11-22-exp2000/mean-2000/loop.lock` returned BlockingIOError while native exp PID 8352 was active. This verifies no concurrent entry through these loop entrypoints; it does not claim to police arbitrary direct gateway clients.
- Independently executed `.omo/evidence/first5027-arms/verify.py` through its checks, stopping before its results-file write: 36 checks passed, with socket connections prohibited. Raw digest and source/measurement checks were recomputed against historical fixtures. No model requests, product requests, live configuration changes or production writes were performed.
- Parsed all six scoped Python modules with ast.parse. Synthetic in-memory 12-send comparison selected B and confirmation A; changing a valid row to raw score 1700 stopped further sends.
- Summary counts completed sends including invalid outcomes, refuses orphan plans, validates ordering, uses shared-control blocks then A/winner/winner/A confirmation, and retains all official assistant measurements. Fallback provider/model invalidation remains in validate.py. Terminal-429 recognition is same-run and rejects recovered success.
- Film inspection binds IDs/session, validation, actual playable media, viewport, hashes and real-time duration; partial/post-run classification is not elevated to full-run success.

## Skill perspective and limits

Loaded programming/SKILL.md, its Python reference, and remove-ai-slops/SKILL.md. Ran their review perspective over production code and evidence checks. Violations are the MEDIUM findings above; no deletion-only tests, removal-only tests, or unnecessary production extraction were found in scope. Identity, inventory and timing extraction serve the stated experimental-integrity goal.

The existing film fixture results were inspected, but no recording was launched. This is an offline safety review, not fresh end-to-end performance/video proof. Full project lint/typecheck/security scans were not run in this bounded read-only review. No production code was edited. Only this required report artifact was written.
