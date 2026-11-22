# Git ledger verification

Invocation: `python3 .omo/evidence/git-ledger/qa.py`

Binary observable: exit 0 and result.json passed=true. Each subprocess command, return code, stdout and stderr is captured in qa-log.json. Assertions in qa.py enforce each scenario.

Artifacts:
- workspace/.omo/evidence/git-ledger/qa.py
- workspace/.omo/evidence/git-ledger/qa-log.json
- workspace/.omo/evidence/git-ledger/result.json

Disposable Git repository: ${TMPDIR}/ledger-qa-8pbp7tf4

Scenarios:
- real D0001 plan and historical finish
- exact raw SHA binding
- idempotent finish unchanged commit
- unrelated staged file preserved
- privacy excluded history/profile/reasoning keys
- tampered validation SHA rejected
- synthetic 1800 TPS missing media provisional
- 61-second demo rejected then recovered
- synthetic playable media completion and hashes
- unscored rejected run traceability
- git fsck and only runs paths committed

Real provider input: D0001-native-links.json paired with initial-check.json. Synthetic high-speed/video cases test ledger behavior only and are not benchmark claims. No network or real-repository Git commits were performed.
