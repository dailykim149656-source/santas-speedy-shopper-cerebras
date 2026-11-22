# First-call scheduler evidence

Owned implementation: `speed-bounty-evidence-test/tools/first5027.py` only. No network or model calls were made.

Invocation (workspace root): `python3 /tmp/test_first5027_offline.py` (reproducible copy: `.omo/evidence/first5027/offline-tests.py`). Captured output: `.omo/evidence/first5027/offline-tests.log`.

Binary observable: all 10 unittest scenarios return `ok`, summary `OK`, exit 0.

Scenarios: all 16 scheduled slots including legitimate numeric-label gaps; duplicate trial/run identities and incorrect arms stop; 15-minute exact boundary accepted and excess excluded; changed ordered products excluded; qualification failure stops at 12; server-time tie-break selects C and exact tie selects B; failed confirmation rejects repeated improvement; valid raw 1700 stops before media; terminal failures count as sends and pause is advisory to allow controller-authorized resume; recovered 429 is not terminal failure; real D5027 447 tokens/304 thinking characters/1035.39 first TPS and response-identity mutation rejection; real D5032 measured first-call diagnostics survive an unmeasured terminal error.

Gateway classification follow-up: invocation `python3 /tmp/test_first5027_gateway.py`, reproducible copy `gateway-tests.py`. Captured `gateway-tests.log`: two tests and seven subcases pass (OK), plus the full original ten-scenario suite rerun passes. `gateway-fixtures.json` records the actual last provider-end log line and true classification for D5029, D5032, D5035. `gateway-synthetic-fixtures.json` captures recovered success, generic trailing errors, different final provider failure, true abort, aborted=false, wrong run suffix, and wrong provider cases. Last correlated provider end controls classification; a later generic lane failure does not erase explicit 429. A real subsequent abort prevents 429 classification. Terminal success always returns false.

Controller owns durable pause and acknowledgement, and must gate next_arm when a new pause event is observed.
