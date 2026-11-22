# gift8 independent report executor evidence

Owned source: `tools/gift8_report.py` only. Existing sources were read, not edited. The tool generates a Korean Markdown report, sibling `.audit.json` and `.sha256.json`, per-attempt inspection JSON, and byte-identical copies of playable demos. It never invokes provider/model requests, HTTP merchant validation, or media regeneration. The reused hook verifier only reads local files. Film inspection writes are redirected to the report artifact directory; source recordings and receipts are not rewritten.

| Criterion/scenario | Exact invocation | Binary observable | Artifact |
| --- | --- | --- | --- |
| Eight-send ABBABAAB, 4 adjacent pairs, exact all-call arithmetic, failed-send denominator/429, URL-order and 15-minute boundaries, forged metrics/archive rejection | `python3 .omo/evidence/gift8-report/offline-qa.py` | exit 0, all 24 explicit scenarios true | `offline-results.json`, `offline-qa.log`, `eight-fixture.audit.json`, `failed-run-denominator.json`, `terminal-429.json` |
| Closed reservation same PID with correct main/exp/test lock paths; wrong PID/open reservation/missing locks rejected | same offline invocation | assertion success; fixture coverage contains 8 sends | `eight-fixture.audit.json`, `offline-results.json` |
| Current gift8 versus every local main/exp raw span; overlapping/incomplete sends block; old same-root test exclusions documented | same offline invocation | overlap and incomplete fixtures fail audit; historical exclusion fixture passes with explicit exclusion | `overlap.json`, `incomplete-send.json`, `legacy-scope.json`, `offline-results.json` |
| >=1700 score without actual same-run UI/5 URLs/full clip never passes | same offline invocation | `passed=false` and target-video rejection | `target-without-video.json` |
| Real partial current campaign, raw/UUID archives/committed plans/evidence/manifests/receipts/hooks, ffprobe/SHA256/viewport inspection and unchanged copied demos | `python3 .omo/evidence/gift8-report/check-current.py` | exit 0; completed rows pass integrity; all copied source/destination hashes and manifest readback match | `current-results.json`, `current-qa.log`, `current.md`, `current.audit.json`, `current.sha256.json`, `current-media-inspections/`, `demos/` |
| Python syntax and whitespace | `python3 -m py_compile tools/gift8_report.py`; `git diff --check -- tools/gift8_report.py` | exit 0 | `validation-commands.json` |

The saved actual snapshot has 3 sent/completed rows and 3 copied playable demos. The campaign is not complete, and its current reservation is still open: the report truthfully returns exit 2 / `incomplete_or_blocked`. No >=1700 success or full eight-send completion is claimed. Historical test runs, including old D5003, appear as explicit exclusions from the gift8-versus-main/exp scope; a current gift8 unresolved intent still blocks audit.

Fixtures are explicitly synthetic and contain no campaign UI/video proof. Actual media was only read, ffprobed and copied; hashes were read back. The report describes persisted merchant-validation evidence and does not claim a fresh merchant check. No hardware or legal conclusions are drawn.

Usage from the test worktree:

`python3 tools/gift8_report.py --output <project-path>/gift8.md --copy-demos <project-path>/gift8-demos`

The CLI requires the isolated test cache/root, raw-test archive and test branch. Exit 0 means eight rows/sends and every mandatory audit passes; exit 2 means artifacts were generated but the campaign or audit remains incomplete/blocked. Output paths stay inside the shared project. Re-running reuses identical copied demo bytes and refuses to overwrite a differing media destination.
