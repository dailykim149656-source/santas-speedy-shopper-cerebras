# Reasoning-arm code review

codeQualityStatus: WATCH
recommendation: REQUEST_CHANGES

Scope: uncommitted reasoning-arm changes only. Separate preflight recovery code was excluded. No source, evidence, runtime, or process was modified by this review. The official objective remains a verified official mean above 2,000 tok/s with five real products and authentic recorded evidence.

## CRITICAL

None found.

## HIGH

None found in the scoped runtime changes. No scorer/model switch, prefilled product answer, video-threshold weakening, or current secret-bearing payload was found. The pre-send recorder gate and score computation remain unchanged. This is not an approval of the separate recovery patch or proof that the new prompt treatment improves TPS.

## MEDIUM

1. `tools/reasoning_report.py:2`, `:6`, `:8`, `:163` and `tools/variants.py:108` overstate causality. The report calls reasoning length a load-independent speed proxy, says pairing cancels slow load drift, and attributes observed identical-answer variation to server load alone. The code only observes text length and nearest-time score ratios; it measures no provider load and does no controlled load comparison. This can turn a correlation into a recorded optimization claim, contrary to the requested test-based conclusions. Describe these as hypotheses/observations, explicitly retain uncertainty, and do not treat reasoning length as a substitute for the official mean.

2. `tools/reasoning_report.py:92` through `:102` mixes cohorts: first/final TPS and reasoning percentages include invalid shopping runs, while official mean includes only valid runs. An offline probe with one valid 1,000-TPS run and one invalid 100-TPS run prints stage median 550 beside official mean 1,000. Filtering must be consistent or the failed-run cohort must be separately labeled. The report also uses only shopping `valid` and does not apply the first-five method check used by the optimizer/comparison report.

3. `tools/variants.py:187` through `:191` unconditionally overrides the existing measured-leader/research schedule while the three new treatments are pending. Against the current actual history, a deterministic probe found the already-planned direct-fetch comparison is delayed by 30 additional successful trials (and longer with failures). This is a substantial unannounced experiment-plan change; it prevents the pending single-variable experiment from being tested promptly. Include the pending treatment or explicitly reconcile the schedule with the active plan before deployment.

4. `tools/reasoning_report.py:154` through `:157` labels workspace injection as confirmed solely when the injected AGENTS.md character count exceeds a threshold. Any unrelated longer file passes. The receipt contains intended text but this check does not prove that text was injected. Label it as a length observation or bind confirmation to actual source content/hash at the relevant run boundary.

## LOW

`tools/reasoning_report.py:160` prints arm keys containing literal `|` into a Markdown table without escaping them. Running the report yields extra columns such as `synth-first-five|0.2|low`. Escape the delimiter or display structured condition labels.

## Validation and skill perspectives

Loaded `programming`, its Python reference, and `remove-ai-slops`. The relevant perspectives ran: evidence boundaries, meaningful behavior checks, unsupported causal comments, and unnecessary complexity. No new deletion-only, tautological, or prose-pinning test was found in the reviewed arm diff. The report's unsupported claims and mixed-cohort parsing violate the goal's evidence boundary; these are substantive reporting issues rather than a request for broad refactoring. Existing large ledger/loop modules were not treated as new blockers.

Read all scoped diffs and the new report, ran `git diff --check` successfully, ran the read-only report against the private archive (numeric aggregates only), and ran two in-memory behavior probes: mixed-validity summaries and scheduler progression. No provider request, browser launch, mutation of benchmark data, or test of prompt prose occurred.

The `omo-agent-toolkit ulw-loop status --json` command returned `ULW_LOOP_PLAN_MISSING`, so this report uses the required fallback evidence path.

## Required changes before approval

Correct or remove the unsupported causal/proxy claims; distinguish valid/method-valid and failed cohorts; explicitly resolve the priority schedule against the pending direct-fetch trial; and stop calling a length-only injection observation confirmed content. The runtime treatment itself can remain a legitimate experiment once those evidence/scheduling issues are addressed. No evidence in this review proves a TPS gain.

Reviewed HEAD: da1e30bb650411b4375284bd6622a364be2d180a

Snapshot SHA-256:

- tools/variants.py: fd5be689ec37da39eaf0fe744c91b328475c0980bd01806ac7b38ae5f8cf7717
- tools/loop.py: c63fd68d84ed07fd211e6516ca1dae5eab30d28d4935a2bd4bde2ce503a96e4f
- tools/ledger.py: 95cb69c19c584c3839b79419344348bd8ac4b3189fcd3753f5716a56f3107cd5
- tools/public_snapshot.py: c07a81dd4ae4827aab5b5d291a34eaf504b60fb668406bbf05e7c2047c506307
- tools/run.mjs: 139ba338cd1d8809e02471263b983b23387a235e94e9eea06e39041e20fe32b1
- tools/replay_run.py: df1f9dc85664cf2f5d0196ff16f7fe5745af46d1aff94edba1ec0ed92f0a897f
- tools/research_report.py: 3fc5c2246f4d216d567fa54113986dd8fd418d92dabc011444ef32659fd5d8d0
- tools/reasoning_report.py: 1850a63bf64438639be417ec255418739cae1ded83a7a83ffda1126cd9b9df7c
