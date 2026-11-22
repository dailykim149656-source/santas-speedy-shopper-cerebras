# Speed Bounty experiment archive

The November 23 Shopify campaigns found five fresh gifts in every attempt. Cerebras returned HTTP 429 on 21 of the 32 model requests. The 11 completed sessions reached a mean of 966.98 TPS across sessions, a median of 962.12 and a best of 1,255.33. These experiments left D5027 as the submitted record at **1,355 mean tok/s · 1,674 p90**. [Submission and original verification](../README.md)

| Campaign | Sessions sent | Sessions with Cerebras 429 | Sessions with a verified final answer | Best session mean |
|---|---:|---:|---:|---:|
| Search terms sent by Kimi | 17 | 17 | 0 | — |
| Shopify prefetch followed by one Kimi generation | 32 | 21 | 11 | 1,255.33 TPS |

Both campaigns include failed attempts. Shopify lookup responses, model generation timings, and recorded product links are associated with the same run ID. The first campaign completed all five tool lookups twice before the final generation received a 429. [Attempt records, original model responses and recordings](campaigns/README.md)

At 03:00 KST on November 23, organizers extended submissions to Sunday, November 22 at 5 p.m. Pacific (November 23 at 10 a.m. KST). The 02:35, 02:50 and 03:00 cutoffs in the logs record the original experiment schedule. [Organizer announcement channel](https://discord.com/channels/1085960591052644463/1572277577429549216)

## Source and reports

| Directory | Contents |
|---|---|
| [Baseline](baseline/) | Original benchmark runner, recorded plans and results |
| [Test](test/) | Experimental runners, parsing and validation changes, catalog queries, prefetch, and recording tools |
| [2,000 TPS experiments](exp-tps-2000/) | Fast-probe source, settings and results |
| [Campaign operations](operations/) | Campaign controllers, schedules and finalization records |
| [Project workspace](../workspace/) | Project analyses, comparison reports, handoff material, submission evidence and benchmark code |

The three source snapshots are also available as branches named `research-baseline`, `test`, and `exp-tps-2000`. To use source-branch commands that refer to Git history, check out the corresponding branch in a full clone. The public export records its plan commits separately from the local run chronology. The official submission verifier still runs at the root of `main`.

To verify the checksums of the exported November 23 campaign records, run this from the repository root on macOS or Linux.

```sh
(cd experiments/campaigns && shasum -a 256 -c SHA256SUMS)
```
