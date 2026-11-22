# Focused 1200 target verification

Invocation: `python3 .omo/evidence/target-1200/verify.py`
Binary observables: all five PASS lines and exit 0 in `verification.log`.
Scenarios: compare every preexisting prompt and arm list plus 100 scheduler decisions against HEAD before this change; exact new JSON object and unchanged url-only category objects; four-arm balanced cycle with category priority, invalid attempt accounting, independent settings and separate validation lists; inclusive score/UI thresholds and explicit true evidence flags; invoke real loop.main with isolated temporary filesystem and mocked trial execution for main/test schedule, marker absent/present, qualifying/nonqualifying history. Production controller, markers, and network untouched.

Invocation: `python3 -m unittest discover -s tools -p 'test_*.py'`
Binary observable: 4 tests, OK, exit 0; artifact `unittest.log`.

Invocation: `python3 -m py_compile tools/variants.py tools/loop.py`
Binary observable: exit 0; artifact `compile.log`.

Invocation: `git diff --check`
Binary observable: exit 0; artifact `diff-check.log`.

Change artifact: `change.diff`. Commit artifact: `commit.log`.
