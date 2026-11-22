# Santa’s Speedy Shopper

This benchmark asks Cerebras Kimi K3.1 Pro, through OpenClaw, to choose five Christmas gifts from live retail catalogs and link to their product pages. The official OpenClaw patch reports the mean server-side decoding speed in tokens per second. Each row in the [run index](RESULTS.md) links to the request and its evidence.

## Verify a recorded run offline

Clone this repository and run the following from its root with Python 3.10 or newer and Git. The example is run C1, which displayed **717 tok/s**. It contains three timed model calls and five independently checked product pages.

Run D0013 displayed **746 tok/s** with five verified product links. Its two timed calls ran at 1,063 and 429 tok/s, respectively. The dashboard screenshot was captured after the run by reopening that session. The capture record includes the timestamp, region, full link destinations and SHA-256. [D0013 dashboard](review-assets/d0013-dashboard.png) · [Capture details](review-assets/d0013-dashboard.json)

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
2. Open a fresh session in the patched web chat. Enable `web_fetch`. The numbered D runs use `tools.allow = ["web_fetch"]` and direct tool exposure via `tools.toolSearch.enabled = false`. Historical C1 used tool discovery. Use the temperature and thinking level recorded in the chosen plan when present. For a plan with a numeric `top_p`, set `agents.defaults.params.topP` to that value. An omitted or null value uses the service default. C1 has no archived sampling settings in its plan. The organizer’s suggested starting settings are temperature 1.0 and low reasoning effort. [Organizer’s parameter guide](https://github.com/wkasekende/openclaw-speed-patch/blob/e40e9f7b7ec41ad3fa68181ad297db119e755171/README.md#suggested-parameters) · [Cerebras sampling parameters](https://inference-docs.cerebras.ai/api-reference/chat-completions#param-top-p)
3. Generate the same shopping request with a fresh catalog query ID, then paste it into the new chat. Replace the example ID below with any run ID listed in the index. The command prints the request and makes no network calls.

```sh
python3 tools/verify_run.py 694ee975-2931-4496-af62-38fc6650d6a6 --prompt
```

4. Wait for the final answer. Open each of its five product links, compare each with the fetched catalog, and record the official **mean tok/s** beside the message box. For a video, show the speed, the five products and their links within 60 seconds. Stocks, responses and service load can change between runs. [Official submission and scoring instructions](https://github.com/wkasekende/openclaw-speed-patch/blob/e40e9f7b7ec41ad3fa68181ad297db119e755171/README.md#entering-the-speed-bounty)

## Provenance and event updates

The public Git history records when the evidence was exported. Each public result references its public plan commit and the corresponding source-history commits. A historical flag identifies runs first archived after they took place. The private source ledger also retains the original traces and locally recorded dashboard images. The public index identifies the evidence available for each run. No organization has certified these scores.

The organizers announced limits of 50,000 uncached tokens and 500,000 total tokens per minute. This benchmark runs one shopping request at a time. On November 22 at 12:04 KST an organizer said the team intended to verify results after the event under more stable service conditions and requested reproducible GitHub repositories. The archived measurements use the published patch’s mean. [Rate-limit announcement](https://discord.com/channels/1085960591052644463/1572277577429549216/1573846340054814861) · [Organizer’s verification update](https://discord.com/channels/1085960591052644463/1573839018964029450/1573896905308774414) · [Pinned forum rules](https://discord.com/channels/1085960591052644463/1573839018964029450/1573839018964029450)


---
Public export provenance: this repository contains a sanitized export, not the original private Git history. Public plan/result commit dates are export dates; use source plan mappings for original chronology. Original source commit mappings and private trace digests are retained in JSON. Unreviewed media is withheld pending review.
