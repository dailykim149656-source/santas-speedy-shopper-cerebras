# Bounded D5027 post-success cooldown

Source assignment: `tools/loop.py`, `tools/test_focus_d5027.py`. Existing focus-selector edits retained. No live request, real trial dispatch, operational marker, environment, provider configuration, scoring, staging, or commit changes performed. Tests exclusively use temporary directories and a mocked `run_trial`.

CLI: `python3 tools/loop.py --d5027-post-success-seconds {30,60}`; default `60`. Optional `--once` retains its existing meaning. This syntax documents a launch option; no real loop was launched.

The 30-second interval applies only when the current schedule is test, the selected mode is focus-d5027, no campaign is active. The immediately preceding history row must have the exact canonical arm `synth-five-categories-cap|0.2|low`, `valid=true`, `method_valid=true`, explicit `rate_limited=false`, integer `call_count=2`, absent/empty relay phases or exactly `["passthrough", "passthrough"]`, and an absent/null capture policy. An older successful row cannot bypass a newer failure. Manual stop is checked first. Existing failure/429 backoff calculations are unchanged.

Validation invocation for every scenario below: `python3 -m unittest discover -s tools -p test_focus_d5027.py -v`. Binary observable: each named test reports `ok`, suite exit code 0, `Ran 15 tests`, final `OK`. Captured artifact: `offline-tests.log` in this directory.

| Criterion/scenario | Exact test and binary assertion |
| --- | --- |
| Default 60 and explicit choices | `test_valid_prior_default_and_opt_in`: mocked sleep exactly 60, 60, and 30 seconds |
| Full 30-second window | `test_opt_in_dispatches_only_after_full_30_seconds`: at 29 seconds sleep exactly 1 and dispatch count 0; at 30 seconds sleep count 0 and mock dispatch count 1 |
| Prior success cannot hide failures | `test_failures_keep_backoff_after_older_success`: sleep 60 then 120 |
| Zero-token 429 preservation | `test_zero_token_429_keeps_existing_windows`: call_count=0 and sleep 60, 60, 120 |
| Main/other modes | `test_main_and_other_selectors_keep_default`: sleep 60 for default test, relay focus, category focus, main schedule |
| Campaign | `test_campaign_keeps_default`: sleep 60 |
| Approved retry-only relay | `test_d5102_retry_only_passthrough_allows_opt_in`: authentic redacted D5102 row and relay-control marker, default sleep 60 and explicit option sleep 30 |
| Historic mixed variant, invalid method, missing fields, absent/extra samples, rewrite/prewarm/suppressed/error relay phases and non-null capture policy | `test_ineligible_prior_results_keep_default`: every subcase sleeps 60 |
| Manual stop | `test_manual_stop_precedes_override`: no sleep or dispatch; phase `user_stop` |
| Bounds | `test_cli_rejects_unbounded_values`: parser exit code 2 for 0,29,31,59,61,120 |
| Existing selector behavior | Five `D5027FocusTests` all pass, including target and manual-stop branches |

Additional checks: `python3 tools/loop.py --help` exited 0, option/choices/default captured in `cli-help.txt`; `git diff --check -- tools/loop.py` exited 0, captured in `diff-check.json`. Validated source SHA-256 values are in `source-hashes.json`.

Safe source fields were read directly from D5102 history and `runs/8cc80670-9e66-4a59-9e74-fd3bfeadcf7e/plan.json`: canonical arm, two valid measured calls, non-rate-limited, passthrough/passthrough, capturePolicy absent, request_relay suffix retry-only. No raw prompt or credential fields were printed. The external supervisor independently checks the committed plan/current relay SHA; this loop guard checks the prior row and current normal selector.
