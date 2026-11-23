# Santa’s Speedy Shopper

[Shopify 선조회 실험 결과와 최고 회차 영상](results/shopify-single-generation-2026-11-23/README.md) · 32회 전송, 11회 유효, 최고 1,255.33 TPS.

This benchmark asks Cerebras Kimi K3.1 Pro, through OpenClaw, to choose five Christmas gifts from live retail catalogs and link to their product pages. The official OpenClaw patch reports the mean server-side decoding speed in tokens per second. Each row in the [run index](RESULTS.md) links to the request and its evidence.

The [experiment archive](experiments/README.md) includes the final Shopify and category-query trials, source code, verification records, and project reports.

## Fastest measured run — 1,623 mean tok/s · 1,694 p90

On November 23, OpenClaw with Kimi K3.1 Pro on Cerebras returned five products from five stores. The first model call sent five configured gift queries in a single `search_catalog` call. The tool searched Shopify Global Catalog live, and Kimi used the results to write the final five links. The plugin provides one example conversation and puts three copies of this run's catalog result in the prompt to the final call.

The official patch displayed **1,623 mean tok/s · 1,694 p90**. The exact mean was **1,623.271854 tok/s**, from **1,552.210421** on the tool call and **1,694.333287** on the final answer. Five product pages opened successfully in a browser. The **12.68-second** video shows the run from before submission through the completed speed display and linked products.

[Live recording](runs/1bfe9282-510a-4f8d-ae3b-9de34c51dd06/demo.mp4) · [Timings and product checks](runs/1bfe9282-510a-4f8d-ae3b-9de34c51dd06/evidence.json) · [Shopify query receipt](runs/1bfe9282-510a-4f8d-ae3b-9de34c51dd06/receipt.json) · [Exact settings and reproduction](runs/1bfe9282-510a-4f8d-ae3b-9de34c51dd06/reproduce/README.md)

## Earlier measured runs — 1,355 and 1,301 mean tok/s

D5027 completed five live AI Synthesis catalog searches through Cerebras Kimi K3.1 Pro. The official patch displayed **1,355 mean tok/s · 1,674 p90**. Its two calls averaged 1,354.662598 tok/s. The **9.52-second video** shows the five linked products and the speed in the completed session. Recording began 29 minutes 17.851 seconds after generation ended. [D5027 video](runs/cd75e5e0-be7c-471f-a9ab-c9e6f0d1bd77/demo.mp4) · [Timings and five product links](runs/cd75e5e0-be7c-471f-a9ab-c9e6f0d1bd77/evidence.json) · [Exact prompt and settings](runs/cd75e5e0-be7c-471f-a9ab-c9e6f0d1bd77/plan.json)

D5009 was recorded from before sending the prompt through the final answer. Its **22.64-second video** shows the shopping task and **1,301 mean tok/s** (1,301.275478 exact). [D5009 video](runs/a9530b69-3aed-4ea9-8fd9-9ee1fcb36b51/demo.mp4) · [D5009 timings and media checks](runs/a9530b69-3aed-4ea9-8fd9-9ee1fcb36b51/evidence.json)

Verify the record from a full Git clone with Python 3.10+ and Git. The first command checks D5027’s two calls, five product pages as recorded, and the clip’s digest. Its `pending_video` status refers to the missing start-to-finish capture. The last command checks D5009’s complete recording.

```sh
run_id=cd75e5e0-be7c-471f-a9ab-c9e6f0d1bd77
python3 tools/verify_run.py "$run_id"
python3 tools/replay_run.py "$run_id" --dry-run
python3 tools/verify_run.py a9530b69-3aed-4ea9-8fd9-9ee1fcb36b51
```

For a live replay, start the officially patched gateway with access to `cerebras/moonshotai-kimi-k3.1-pro-trial`. Use temperature 0.2, low thinking, a 1,024-token completion limit, the plan’s exact workspace `AGENTS.md`, and direct access to `web_fetch` with tool search disabled. Then run `python3 tools/replay_run.py "$run_id"` in the same shell. The prompt fixes five search terms (filter, mixer, oscillator, echo and cable). Each product name and URL comes from the current retailer response. [Gateway setup](https://github.com/wkasekende/openclaw-speed-patch/blob/e40e9f7b7ec41ad3fa68181ad297db119e755171/README.md#setup)

## Verify earlier recorded runs offline

Clone this repository and run the following from its root with Python 3.10 or newer and Git. The example is run C1, which displayed **717 tok/s**. It contains three timed model calls and five independently checked product pages.

Run D0013 displayed **746 tok/s** with five verified product links. Its two timed calls ran at 1,063 and 429 tok/s, respectively. The dashboard screenshot was captured after the run by reopening that session. The capture record includes the timestamp, region, full link destinations and SHA-256. [D0013 dashboard](review-assets/d0013-dashboard.png) · [Capture details](review-assets/d0013-dashboard.json)

Run D0024 used the AI Synthesis catalog and displayed **827 tok/s** with five verified product links. The post-run screenshot was captured from the same OpenClaw session. [D0024 dashboard](review-assets/d0024-dashboard.png) · [Capture details](review-assets/d0024-dashboard.json)

The historical C1 session was also reopened after it finished. Its dashboard shows its five product links, 717 mean, 1,278 p90 and the Kimi model. [C1 dashboard](review-assets/c1-dashboard.png) · [Capture details](review-assets/c1-dashboard.json)

```sh
python3 tools/verify_run.py 694ee975-2931-4496-af62-38fc6650d6a6
```

The verifier reads the committed request, recalculates each call’s rate from the provider’s output token count and generation time, and takes the arithmetic mean. It also checks the recorded relationships between the five returned links, that run’s merchant catalog fetches, and the independent product-page checks. The output includes the exact and displayed means, number of calls, verified product count, and run status. The `result` field distinguishes a successful shopping result from an incomplete run. A zero exit code means that the archive is internally consistent. The evidence contains timestamps and digests for the original responses. An independent reviewer can also pass a privately supplied original file with `--raw FILE` to check its digest.

## Repeat the shopping task

With your officially patched gateway running, the following repeats C1 once in a fresh session. It prints the session identifier, the final five links and the server-reported mean. Add `--dry-run` to preview the request without contacting the gateway. Pass `--cli PATH` if your patched OpenClaw checkout uses a different CLI entry point.

```sh
python3 tools/replay_run.py 694ee975-2931-4496-af62-38fc6650d6a6
```

1. Use an account with current access to `cerebras/moonshotai-kimi-k3.1-pro-trial`. Build OpenClaw at `8b18b5578f66eab1501cba4cef2310d88bfb9a41` with the organizer’s patch from commit `e40e9f7b7ec41ad3fa68181ad297db119e755171`. Follow its build and provider setup with your own credentials. This checkout uses Node 24.22.1 or later in the 24.x series, or Node 26.12.1 or later, and pnpm 12.15.0. The patch digest and model are in [benchmark.json](benchmark.json). [Pinned setup instructions](https://github.com/wkasekende/openclaw-speed-patch/blob/e40e9f7b7ec41ad3fa68181ad297db119e755171/README.md#setup)
2. Open a fresh session in the patched web chat. Enable `web_fetch`. The numbered D runs use `tools.allow = ["web_fetch"]` and direct tool exposure via `tools.toolSearch.enabled = false`. Historical C1 used tool discovery. Use the temperature and thinking level recorded in the chosen plan when present. For a plan with a numeric `top_p`, set `agents.defaults.params.topP` to that value. An omitted or null value uses the service default. A plan with `workspace_agents_md` ran with exactly that text as `AGENTS.md` in the agent workspace, and every other plan ran without that file. `replay_run.py` prints the text. C1 has no archived sampling settings in its plan. The organizer’s suggested starting settings are temperature 1.0 and low reasoning effort. [Organizer’s parameter guide](https://github.com/wkasekende/openclaw-speed-patch/blob/e40e9f7b7ec41ad3fa68181ad297db119e755171/README.md#suggested-parameters) · [Cerebras sampling parameters](https://inference-docs.cerebras.ai/api-reference/chat-completions#param-top-p)
3. Generate the same shopping request with a fresh catalog query ID, then paste it into the new chat. Replace the example ID below with any run ID listed in the index. The command prints the request and makes no network calls.

```sh
python3 tools/verify_run.py 694ee975-2931-4496-af62-38fc6650d6a6 --prompt
```

4. Wait for the final answer. Open each of its five product links, compare each with the fetched catalog, and record the official **mean tok/s** beside the message box. For a video, show the speed, the five products and their links within 60 seconds. Stocks, responses and service load can change between runs. [Official submission and scoring instructions](https://github.com/wkasekende/openclaw-speed-patch/blob/e40e9f7b7ec41ad3fa68181ad297db119e755171/README.md#entering-the-speed-bounty)

Recording starts before every request. For a verified result, a displayed mean of **900 tok/s** or a new exact verified record qualifies the video for review. A higher verified recording replaces the prior local clip, with older scores, product checks and recording digests preserved in Git. A replay of a completed session is labeled as post-run evidence. Earlier records use their own recorded retention policy. The target remains a verified mean above 2,000 tok/s.

A plan with numeric `max_completion_tokens` uses `agents.defaults.params.maxTokens` in OpenClaw. The capped comparison uses 2,048 tokens per call and the same shopping prompt, temperature and reasoning as the control. Cerebras uses the request’s completion limit when estimating quota consumption. The score still comes from server-reported generation time and output tokens for every model call, including both the catalog lookup and the final answer. [Cerebras token rate limits](https://inference-docs.cerebras.ai/support/rate-limits#token-rate-limiting)

## Controlled performance comparisons

Each trial chooses five Christmas gifts and checks the selected links against the live catalog and the merchant’s product pages. Retailer comparisons keep the request text, inventory filter and result count fixed. The single-store comparison uses WordPress Mercantile and AI Synthesis. The two-store comparison keeps WordPress Mercantile and swaps RaspberryPi.dk for AI Synthesis. [AI Synthesis shop](https://aisynthesis.com/diy-synthesizer-module-shop/)

The format comparison asks for the same linked product titles and prices as either a five-row table or five short sentences. The arithmetic comparison also requests a running subtotal. Other pairs vary catalog size, reasoning level, completion budget or sampling. The planned repetitions rotate the order of these settings and use one active request at a time. The index keeps the official score and product checks for each trial, including unsuccessful trials. Compare the median and sample count alongside the best record.

The [Korean comparison report](RESEARCH.md) summarizes recorded runs. Regenerate it from the current checkout with `python3 tools/research_report.py`.

The runner prioritizes a repeat of a promising single result. Two of every three trials retest the best recent median among repeated valid results. The third trial covers a pending comparison, including catalog size and output format on the fastest observed retailer. A single record remains an observation until it is repeated.

The archive records observed cache reads when OpenClaw reports them. Cached input and total elapsed time are separate from the official server decode speed. A comparison of output formats can demonstrate a performance difference under the tested settings. Identifying the provider’s internal decoding algorithm would require provider-side evidence. [Cerebras prompt caching](https://inference-docs.cerebras.ai/capabilities/prompt-caching)

## Provenance and event updates

The public Git history records when the evidence was exported. Each public result references its public plan commit and the corresponding source-history commits. A historical flag identifies runs first archived after they took place. The private source ledger also retains the original traces and locally recorded dashboard images. The public index identifies the evidence available for each run. No organization has certified these scores.

The organizers announced limits of 50,000 uncached tokens and 500,000 total tokens per minute. This benchmark runs one shopping request at a time. On November 22 at 12:04 KST an organizer said the team intended to verify results after the event under more stable service conditions and requested reproducible GitHub repositories. The archived measurements use the published patch’s mean. [Rate-limit announcement](https://discord.com/channels/1085960591052644463/1572277577429549216/1573846340054814861) · [Organizer’s verification update](https://discord.com/channels/1085960591052644463/1573839018964029450/1573896905308774414) · [Pinned forum rules](https://discord.com/channels/1085960591052644463/1573839018964029450/1573839018964029450)


---
Public export provenance: this repository contains a sanitized export, not the original private Git history. Public plan/result commit dates are export dates; use source plan mappings for original chronology. Original source commit mappings and private trace digests are retained in JSON. Unreviewed media is withheld pending review.
