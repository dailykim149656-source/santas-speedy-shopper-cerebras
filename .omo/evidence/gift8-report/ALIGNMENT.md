# Prefetch extra-generation report alignment

Owned source: `tools/gift8_report.py` only. A valid B run may make additional same-run `gift_lookup` calls and later complete successfully. Each such call must match an actual successful native result, exact approved arguments, exact source card, call-before-result-before-final ordering, and its original plugin `calls/<sha256(callID)>.json` receipt. The private receipt must match the committed public copy byte-for-byte, declared evidence/validation hashes, run/session/product/card identity and valid timing after original fetch and first native model input.

All actual same-run assistant generations remain in independently computed official arithmetic. No generation is removed to fit the one-generation hypothesis. The report now separates B single-generation successes (`valid && actual_generation_count == 1`) from valid extra-generation successes; both remain in the ordinary success denominator. Structural expectations are diagnostics, not an extra-generation validity rejection.

| Scenario | Invocation | Binary observable | Artifact |
| --- | --- | --- | --- |
| Full prior regression plus valid two-generation B, five actual bound native followups, full all-call mean 1200, B 4/4 success vs 3/4 single-generation success | `python3 .omo/evidence/gift8-report/offline-qa.py` | exit0, all31 scenarios passed | `offline-results.json`, `offline-qa.log`, `prefetch-extra-generation.json`, `prefetch-extra-generation.md` |
| Missing source-binding receipt | same invocation | audit_passed=false | `prefetch-missing-binding.json` |
| Matching private/public/evidence hashes but call receipt preceding first native model input | same invocation | audit_passed=false, explicit pre-first-input rejection | `prefetch-stale-binding.json` |
| Consistent archived raw hashes but altered native result card | same invocation | audit_passed=false, exact native-card mismatch | `prefetch-wrong-native-card.json` |
| Actual completed D5053 remains invalid429 | direct `gift8_report.audit_trial` against current persisted D5053 row, pinned commit and raw-test archive | audit_passed=true, valid=false, terminal_429=true, score749.5641521562239, actual_generation_count2, native_tool_call_count5, structure_expected=false, single_generation_success=false | `d5053-alignment-audit.json` |
| Syntax/whitespace | `python3 -m py_compile tools/gift8_report.py`; `git diff --check -- tools/gift8_report.py` | exit0 | `alignment-syntax.json` |

Only explicitly synthetic local fixtures were extended. Existing actual videos were not modified, re-encoded, or refreshed. The previous partial live report snapshot remains intentionally unchanged; the final live report should be refreshed after the study ends. No provider/model requests or merchant HTTP calls were made.
