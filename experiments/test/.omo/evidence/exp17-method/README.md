# Method checks evidence

Invocation: `python3 -B .omo/evidence/exp17-method/check.py`

Binary observable: exit 0; `results.json` has `passed: true` and all 29 scenarios have `observed == expected`.

Scenario coverage and exact outputs: `results.json`. Reproducible offline harness: `check.py`.

The real D5009 private raw SHA256 was checked against its archived evidence and its recomputed official mean matched 1301.275477944986 TPS. All four arms, out-of-order tool results, optional native sorted-arm arguments, accompanying batch text, and additional non-tool measured turns pass. Wrong category arguments, split batches, missing/duplicate pages, duplicate/missing candidates, rejected/truncated/cached sources, incorrect final order, cross-run batching, missing measured calls, wrong URL and absent sorting are rejected.

The extra-turn scenario has three measured calls and checks the official mean includes all three. No scorer changes were made.

Independent product HTTP GETs are explicitly stubbed for offline structural testing; these artifacts do not claim new live merchant verification. Six-candidate variants are synthetic method fixtures. No network requests were issued.

No active attempt directory existed (`ulw-loop status --json`: ULW_LOOP_PLAN_MISSING), so evidence is recorded here.
