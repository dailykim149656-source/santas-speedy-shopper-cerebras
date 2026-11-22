# Historical experiment controllers and operations

This archive preserves the campaign-specific Python and Node programs, slot journals, configuration, result summaries and receipts that accompanied the five-gift benchmarking experiments. It includes 71 source files from D5027 pure, original, accelerated and resumed campaigns, the required-tool and long-gap experiments, gift8, speed1500 and Mercantile. [Campaign index](campaign-index.json) · [File provenance](source-digests.json)

The original and accelerated D5027 campaigns shared a queue for deferred merchant-detail validation. At 2026-11-23T03:01:40+09:00 the queue contained 27 records, of which 27 had terminal verification. Each final record is matched to its original run ID and the number of confirmed product pages. [Deferred validation results](deferred-finalization.json)

## Reading the archive

Start with the campaign's `campaign.json`, `trials.json`, `iterations.jsonl` or `report.json` where present. The Python and JavaScript sources are historical operator tools. They contain the original November 2026 stopping conditions, so executing an old controller now cannot reproduce its historical timing. For a new run, begin with the maintained repository tools and review the experiment settings.

Campaign paths in JSON and notes use `$OPERATIONS_ROOT` for the original `mean-2000` directory, `$BOUNTY_CACHE` for the Cerebras cache, `$BOUNTY_ARCHIVE` for the private raw-results archive and `$BOUNTY_TEST_REPO` for the experiment checkout. For historical source inspection set `BOUNTY_TEST_REPO` to an absolute checkout path containing the campaign's `tools/`, and `BOUNTY_PROJECT_ROOT` to the parent containing the workspace documents. Controllers originally run in a date-stamped runtime under the user's home directory; these project tools still need the matching OpenClaw build, speed patch and configured Node runtime. Never copy live locks, active approval markers or credentials into this archive.

Public receipts and verified results are retained. Browser profiles, operator login configuration, running service logs, raw authentication material and duplicate recording frames are machine-local. Content digests identify the retained source artifacts; sanitized JSON or path-portable source can differ from the original SHA-256.

The historical deadline field in the deferred verification records refers to 03:00 KST. Of the 27 five-product checks, 23 finished before that cutoff and four finished afterward. All 27 finished before the newly announced 10:00 KST submission deadline. [Organizer announcement channel](https://discord.com/channels/1085960591052644463/1572277577429549216)
