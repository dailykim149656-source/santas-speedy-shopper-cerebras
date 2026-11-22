# Campaign scheduler QA

Owned production file: `tools/campaign_1700.py` (new). No provider requests, marker writes, or commits were performed. The module reads local JSON only. No active ulw attempt was found by `omo-agent-toolkit ulw-loop status --json` (ULW_LOOP_PLAN_MISSING), so evidence is stored here.

Invocation from `speed-bounty-evidence-test`:

```sh
python3 -B .omo/evidence/campaign-1700/fixtures.py > .omo/evidence/campaign-1700/results.json
```

Observed exit code: **0**. Captured binary observable: `results.json` contains `"status": "PASS"`, `"count": 44`. Every named scenario is listed in that artifact. Fixture implementation is preserved in `fixtures.py` and creates disposable local evidence, not provider calls.

| Success criterion | Exact scenarios | Observable/artifact |
|---|---|---|
| First/second 8 slots, ABBA BAAB, resume by completed row count | resume_slot_1 through resume_slot_16, old_rows_ignored | All assertions passed; results.json |
| Four-slot phase 3 versus original control, max 20 | phase3_control, phase3_slot_1 through phase3_slot_4, max20 | All assertions passed; results.json |
| Strongest eligible median improvement, 3 valid pairs, 3 wins, shopping validity count | strongest_candidate, no_promotion_stops16, validity_regression_blocks, two_wins_block, two_valid_pairs_block, fallback_qualified_candidate | All assertions passed; results.json |
| Six actual candidates in planned page URL order; changed candidates audited/excluded | parallel_result_order, candidate_change_excludes_pair, candidate_change_audit, duplicate_candidates_rejected, missing_evidence_excludes_pair | All assertions passed; results.json |
| Fail closed on mismatched arms or duplicated trial numbers | unexpected_arm_stops, duplicate_stops | All assertions passed; results.json |
| Inclusive 1700 threshold, strict booleans, raw and UI, finite scores | target_inclusive, all reject_target_* scenarios | All assertions passed; results.json |

Scope: scheduling does not independently verify private raw hashes or video bytes. Its target reason explicitly requests final raw/hash/video verification; the parent runner owns that verification and recovery of sent-but-missing evidence. Completed invalid rows consume a slot. Unsent preflight plans must not be supplied as completed rows.
