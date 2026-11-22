# first5027 private film watcher

Changed only `tools/first5027_film.py` (plus offline QA evidence). No live recorder or model request was launched. No commit was made.

Default start invocation from the test checkout:

```sh
python3 tools/first5027_film.py --start 5037
```

Default private output: `~/Library/Caches/cerebras-speed-bounty/2026-11-22-test/mean-2000/film-first5027-5037/`.
Completion signal: `~/Library/Caches/cerebras-speed-bounty/2026-11-22-test/mean-2000/recording-complete-5037` (root writes only once no campaign sends remain pending).
Inspect and retry: `python3 tools/first5027_film.py --inspect 5037` or `--retry 5037`.

Recording is independent of the controller. Full coverage is not guaranteed: setup may lose the race to send or wait for another recording; receipts classify this as partial/post-run. A post-run retry cannot upgrade full-run timing. Existing record.mjs provides timestamped real-time encoding and final UI capture; this watcher independently probes media, checks timeline durations, verifies the existing bounded viewport proof, and hashes timing provenance. These offline fixtures test classification logic, not authentic live UI content.

Verification command: `python3 .omo/evidence/newfilm-5037/qa.py`.
Binary observable: exit status 0 and all 38 scenario `passed` values true in `results.json`; captured execution log: `qa.log`.
CLI command: `python3 tools/first5027_film.py --help`; observable exit status 0, inspect/retry/start usage present; artifact `cli-help.txt`.
Compilation command: `python3 -m py_compile tools/first5027_film.py`; observable exit status 0; artifact `compile.json` includes final source SHA256.

| Success criterion / exact scenario | Binary observable | Artifact |
| --- | --- | --- |
| Watch idle before controller starts; ignore previous stopped phase | idle sleep reached, queued committed plan | results.json; qa.log |
| Restrict to committed A/B/C score-first plans >=5037; discover before session write | three allowed arms accepted; old/other/altered/mismatched plans rejected | results.json |
| Completion sentinel exits an empty watcher | main returned | results.json; qa.log |
| Completed directories skip Git subprocess | subprocess configured to fail if called; queue empty | results.json |
| Capture same run before send, with matching raw/session/terminal provenance | full_run_verified and target_1700_verified true | full-fixture.json |
| Late/post-run, rehearsal, stale UI and mismatched readiness rejected as full runs | full_run_verified false | late.json; post-run.json; rehearsal.json; stale-ui.json; stale-ready.json |
| Real-time timeline and matching raw start are required | full_run_verified false on altered timing | retimed.json; raw-time-mismatch.json |
| Exact 1700 and five unique verified URLs required for target | target_1700_verified false for wrong UI/duplicates/1699/invalid validation | wrong-score.json; duplicate-url.json; below-threshold.json; invalid-shopping.json |
| Playable original and demo <=60 seconds | playable false for corrupt or 61-second demo | corrupt-demo.json; overlong-demo.json |
| Authentic invocation has no rehearsal flag, uses isolated port, does not send | captured Popen arguments; stub process only | launcher.json; results.json |
| --inspect recomputes receipt; --retry selects same session | successful CLI paths | results.json |
| Main branch/main cache forbidden; local private JSON mode 0600 | unsafe runtime exits 2; mode 0600 | results.json |

All media under `fixtures/` are generated black test movies. They are never campaign video evidence. The external repository volume reports fixed 0700 modes; the private-file permission check runs on the local filesystem where actual capture output is stored.
