"""Stage the recorded plugin and start an isolated patched OpenClaw gateway."""

import argparse
import json
import os
from pathlib import Path
from secrets import token_hex
from shutil import copytree, which


ROOT = Path(__file__).resolve().parent


def stage(openclaw, state, port):
    sdk = openclaw / "dist/plugin-sdk/llm.js"
    for path in (sdk, openclaw / "dist/plugin-sdk/gateway-runtime.js", openclaw / "openclaw.mjs"):
        if not path.is_file():
            raise ValueError(f"Build the officially patched OpenClaw checkout first: missing {path}")

    marker = state / ".scripted-replay"
    state.mkdir(parents=True, exist_ok=True)
    if any(state.iterdir()) and not marker.is_file():
        raise ValueError("Use an empty directory for the dedicated replay state")
    marker.touch()
    plugin = state / "plugins/scripted-copy"
    copytree(ROOT / "scripted-copy-plugin", plugin, dirs_exist_ok=True)
    index = plugin / "index.mjs"
    index.write_text(index.read_text().replace("__SCRIPTED_COPY_LLM_SDK__", sdk.as_uri()))

    config = json.loads((ROOT / "openclaw.template.json").read_text())
    workspace = state / "workspace"
    workspace.mkdir(exist_ok=True)
    config["agents"]["defaults"]["workspace"] = str(workspace)
    config["plugins"]["load"]["paths"] = [str(plugin)]
    config["plugins"]["entries"]["scripted-copy"]["config"]["shapeLog"] = str(state / "shape-log.jsonl")
    config["gateway"]["port"] = port
    config_path = state / "openclaw.json"
    config_path.write_text(json.dumps(config, indent=2) + "\n")

    settings = state / "agents/main/agent/settings.json"
    settings.parent.mkdir(parents=True, exist_ok=True)
    settings.write_text('{"retry":{"provider":{"maxRetries":0}}}\n')
    receipts = state / "catalog-receipts"
    receipts.mkdir(exist_ok=True)

    token_path = state / "gateway-token"
    if not token_path.exists():
        token_path.write_text(token_hex(32) + "\n")
    return dict(
        os.environ,
        OPENCLAW_CONFIG_PATH=str(config_path),
        OPENCLAW_STATE_DIR=str(state),
        OPENCLAW_GATEWAY_PORT=str(port),
        OPENCLAW_GATEWAY_TOKEN=token_path.read_text().strip(),
        OPENCLAW_SKIP_CHANNELS="1",
        OPENCLAW_SKIP_CRON="1",
        CATALOG_RECEIPT_DIR=str(receipts),
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--openclaw", type=Path, required=True, help="Built, officially patched checkout")
    parser.add_argument("--state", type=Path, required=True, help="Dedicated replay state directory")
    parser.add_argument("--port", type=int, default=19883)
    parser.add_argument("--node", default="node", help="Node name on PATH or absolute path")
    parser.add_argument("--prepare-only", action="store_true", help="Write replay files without running a gateway")
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        parser.error("--port must be an unprivileged TCP port")
    if not args.prepare_only and not os.environ.get("CEREBRAS_API_KEY"):
        parser.error("Export your own CEREBRAS_API_KEY before launching")

    os.umask(0o077)
    openclaw = args.openclaw.resolve()
    try:
        env = stage(openclaw, args.state.resolve(), args.port)
    except ValueError as exc:
        parser.error(str(exc))
    if args.prepare_only:
        return
    node = which(args.node)
    if node is None:
        parser.error("Node was not found")
    os.chdir(openclaw)
    os.execve(node, [node, str(openclaw / "openclaw.mjs"), "gateway", "run"], env)


if __name__ == "__main__":
    main()
