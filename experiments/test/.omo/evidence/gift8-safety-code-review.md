# Gift8 paused-run code review

codeQualityStatus: CLEAR
recommendation: APPROVE
blockers: []

Scope: read-only audit of tools/run_gift8.py, gift8_evidence.py, gift8_report.py, gift8_film.py, run.mjs, preflight_recovery.py, tools/gift8-plugin/index.cjs; relevant reservation implementation and plugin fixture also consulted. Pinned HEAD: 68f90a6c38d2251e8e5cced4500e2b2896a00409. Reviewed validator/report follow-up diffs 28b89ba and 68f90a6. Approval applies to continuing this bounded experiment, not completed eight-send success.

## Findings
CRITICAL: none.
HIGH: none.
MEDIUM: no criterion-backed blocking findings in this bounded audit.
LOW: existing .omo/evidence/gift8-report/current-results.json is a three-send snapshot; it cannot establish current four-send or final completion. This is an artifact freshness limit, not evidence corruption.

## Independently observed evidence
Read current cache at ~/Library/Caches/cerebras-speed-bounty/2026-11-22-test/mean-2000/gift8-5051. Called offline audit_trial for each current row, which reads committed plan/evidence/manifest, raw, private raw, raw-test archive, receipts, hook events and scores without network. D5051: valid, mean 954.8250045940329, 2 assistant calls; D5052: valid, mean 1059.6152757733082, 1 call; D5053: rejected, measured mean 749.5641521562239, 2 assistant records including terminal failure; D5054: rejected, no measured mean, 1 terminal failure record. All four audit_errors were empty. Failed slots remain in ABBA sequence; original raw/archive bytes match. Rejected calls without server timing are not fabricated as measured samples.

Offline span_audit found zero campaign overlaps, zero incomplete sends, zero errors across 306 campaign-related comparisons. Independent nonblocking exclusive flock attempts using read-only descriptors failed with BlockingIOError on all three actual test/main/exp loop.lock files, demonstrating current native contention rather than trusting reservation JSON. Current reservation is intentionally still open. Persisted backoff after slot 4 ends at epoch 1795347109.78.

Controller admits only next ORDER[len(sent)] and stops at eight sent intents; sent failures consume slots, missing raw after intent halts instead of retrying a new slot. Unsent preflight recovery cannot pass when intent/ack/terminal exists. Valid >=1700 causes return before further sends; film/UI verification remains external and cannot be claimed yet. Prefetch follow-up acceptance requires genuine native paired calls/results plus bound call receipt and exact source card; all measured assistant calls feed mean. Current successful A/B records have expected 2/1 generation structure.

## Skill-perspective check
Loaded programming and remove-ai-slops SKILL.md and applied their existence, boundary-validation, overfit-test and unnecessary-complexity criteria. No goal-relevant needless parsing: receipt/card parsing is the evidence boundary. No deletion-only or removal-prose tests found. Inspected plugin fixture: meaningful adversarial identity/receipt/redirect checks and fetch-count behavior exist; canonical-card equality alone is implementation-coupled and is not treated as independent proof. No blocking violation of either perspective identified in the focused diffs. This audit does not certify full skill style conformance of existing large untyped scripts.

## Limits
No live provider/network/model requests, source modifications, fixture execution or video regeneration. No current target >=1700 exists; actual same-UI five-link/video success was not re-certified. Full test/lint/typecheck suites were not run. Follow-up valid-B paths are inspected, not observed in the current successful B run. Live state may advance after this snapshot. No notepad path was supplied. ulw-loop status reported ULW_LOOP_PLAN_MISSING, so fallback report location is used. Unrelated tools/loop.py and tools/variants.py edits were preserved.
