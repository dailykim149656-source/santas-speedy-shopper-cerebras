# Gift8 target-clip criterion correction

The previous report incorrectly inherited `target_1700_verified` from the older study inspector. That field requires `full_run_verified` and a first frame before the send; this was an extra report-imposed requirement, not the gift8 goal criterion. Only `tools/gift8_report.py` changes. The old study, film adapter, recorder and all actual movies remain unchanged.

Gift8 now separately requires: a valid independently audited raw run with exact mean >=1700; its matching official UI integer >=1700 actually verified in the viewport; matching run ID and session; exactly the same five distinct verified product URLs; playable real-time media; and an ffprobed demo duration greater than0 and <=60seconds. The inspector's strict `full_run_verified`, original first-frame timing and partial/post-run classification are preserved and displayed separately. The report explicitly makes no organizer-acceptance claim.

A verified target plus the other required source/reservation/no-overlap audits can set `goal_complete=true` before eight sends. `comparison_complete` separately records whether all eight sends finished. A raw target without matching media remains `target_needs_attention`, even after eight sends. An unrelated audit error still prevents a completion claim.

| Scenario | Invocation | Binary observable | Artifact |
| --- | --- | --- | --- |
| Partial during-run1700 target accepted while full-run remains false; old inherited full-run target flag does not block | `python3 .omo/evidence/gift8-report/goalcriterion-qa.py` | predicate true; full_run_verified=false unchanged | `goalcriterion-results.json`, `goalcriterion-qa.log` |
| Wrong score, URL, session, run ID, invalid raw audit, duplicate URLs, unverified/retimed/unplayable or over60second clip | same invocation | each predicate false | `goalcriterion-results.json` |
| Early verified target completes goal before8; missing target media remains attention even at8; other audit failure still blocks | same invocation | explicit completion-state assertions pass | `goalcriterion-results.json` |
| Existing report arithmetic, native-call provenance, failure/429, pair, overlap and reservation regression | `python3 .omo/evidence/gift8-report/offline-qa.py` | all31 scenarios pass | `offline-results.json`, `offline-qa.log` |
| Source syntax and old study/adapter/recorder preservation | `python3 -m py_compile tools/gift8_report.py`; `git diff --check -- tools/gift8_report.py`; byte comparison to committed old source | exit0 and unchanged source SHA256 checks | `goalcriterion-syntax.json` |

The target-criterion scenarios are pure predicate unit inputs, explicitly marked as such. They generate no movie, screenshot or viewport proof and do not claim an actual1700 campaign record. No model/provider/merchant requests were issued. Final live report snapshots remain for the parent to refresh after the study closes.
