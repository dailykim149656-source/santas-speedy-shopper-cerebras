# Repeat the 1,623 TPS shopping run

This package contains the staged OpenClaw plugin used for the recorded run. The launcher resolves its SDK import against your own OpenClaw checkout and writes an isolated gateway profile. The five search terms are configured in the plugin. The first Kimi call supplies them to `search_catalog`, which makes live Shopify Global Catalog requests and saves their receipts. The second call returns five product lines from those results.

## Requirements

- A built OpenClaw checkout at `8b18b5578f66eab1501cba4cef2310d88bfb9a41` with [the organizer's patch](https://github.com/wkasekende/openclaw-speed-patch/blob/e40e9f7b7ec41ad3fa68181ad297db119e755171/README.md#setup). The patched Git tree is `aec08de95dc279d3c2a5ef46c641ae31b7a0e219`.
- Python 3 and either Node 24.22.1 or later in the 24.x series, or Node 26.12.1 or later. Export your own `CEREBRAS_API_KEY` with access to `moonshotai-kimi-k3.1-pro-trial`.

## Run

From this `reproduce` directory, set `openclaw_dir` to your built checkout and start the dedicated gateway. Use an unused port if 19883 is occupied, and pass that port to both commands.

```sh
openclaw_dir=/absolute/path/to/openclaw
replay_state=$(mktemp -d)
python3 launch.py --openclaw "$openclaw_dir" --state "$replay_state" --port 19883 &
replay_pid=$!
```

After the gateway is listening on `127.0.0.1:19883`, send one fresh request with the [recorded prompt](prompt.txt).

```sh
node --experimental-transform-types run.mjs \
  --openclaw "$openclaw_dir" --state "$replay_state" --port 19883 \
  --out "$replay_state/results" --count 1 --label replay \
  --examples "$PWD/scripted-copy-plugin/examples.json" \
  --prompt "$(cat prompt.txt)" --require-price --verify-receipt-text
```

The runner prints the official session mean and each call's generation rate. It checks that both model calls completed, all five links match the saved catalog receipts, the product lines are copied exactly, and each line has a price. Detailed history is written to `results/replay-001.json` inside the replay state. The product pages can also be opened independently to check their current availability. Stop your replay gateway with `kill "$replay_pid"`.

[Recorded settings](openclaw.template.json) include temperature 0, low thinking effort, one example turn, three copies of the live product lines, and a 512-token completion cap. The input examples illustrate the prompt and are excluded from final product validation. The live results and server-measured speed will vary across runs. This headless replay does not create a video.
