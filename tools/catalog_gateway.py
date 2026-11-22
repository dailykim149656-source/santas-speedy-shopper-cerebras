"""Start a dedicated loopback gateway for the one-catalog-call experiment."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import socket
import subprocess
import tempfile


TOOLS = Path(__file__).resolve().parent
RUNTIME = Path.home() / "Library/Caches/cerebras-speed-bounty/2026-11-22"
STATE = RUNTIME.with_name("2026-11-22-catalog") / "shopper-test"
PLUGIN = "shopper-catalog-search"
# git am can assign fresh committer timestamps; an identical official patched tree is sufficient.
PATCHED_TREE = "aec08de95dc279d3c2a5ef46c641ae31b7a0e219"


def private_write(path, content):
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as temp:
        temp.write(content)
        temp.flush()
        os.fsync(temp.fileno())
    os.replace(temp.name, path)


def verify_runtime(runtime, benchmark):
    repo = runtime / "openclaw"
    patch = (runtime / "official.patch").read_bytes()
    tree = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD^{tree}"], text=True).strip()
    dirty = subprocess.check_output(["git", "-C", str(repo), "status", "--porcelain", "--untracked-files=no"])
    if (hashlib.sha256(patch).hexdigest() != benchmark["patch_sha256"]
            or tree != PATCHED_TREE or dirty):
        raise ValueError("The benchmark's recorded official patch and clean OpenClaw build are required")


def credentials(runtime):
    if os.environ.get("CEREBRAS_API_KEY"):
        return os.environ["CEREBRAS_API_KEY"]
    source = """
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import { pathToFileURL } from 'node:url';
const dir = path.join(os.homedir(), '.openclaw');
const { resolveApiKeyForProvider } = await import(pathToFileURL(process.argv[1]));
const cfg = JSON.parse(fs.readFileSync(path.join(dir,'openclaw.json'),'utf8'));
const r = await resolveApiKeyForProvider({provider:'cerebras',cfg,
  agentDir:path.join(dir,'agents/main/agent'),modelId:'moonshotai-kimi-k3.1-pro-trial'});
if (typeof r.apiKey !== 'string' || !r.apiKey) process.exit(1);
process.stdout.write(r.apiKey);
"""
    installed_node = Path(shutil.which("node") or runtime / "bin/node").resolve()
    resolver = installed_node.parent.parent / "lib/node_modules/openclaw/dist/plugin-sdk/provider-auth-runtime.js"
    if not resolver.is_file():
        resolver = runtime / "openclaw/dist/plugin-sdk/provider-auth-runtime.js"
    result = subprocess.run([str(installed_node), "--input-type=module", "-e", source, str(resolver)],
                            capture_output=True, timeout=35)
    if result.returncode or not result.stdout.strip() or b"\n" in result.stdout.strip():
        raise RuntimeError("Provide CEREBRAS_API_KEY or configure the local Cerebras profile.")
    return result.stdout.decode().strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime", type=Path, default=RUNTIME)
    parser.add_argument("--state", type=Path, default=STATE)
    parser.add_argument("--port", type=int, default=19867)
    args = parser.parse_args()
    os.umask(0o077)
    runtime, state = args.runtime.resolve(), args.state.resolve()
    if state in {runtime / "shopper-test", Path.home() / ".openclaw"}:
        raise ValueError("This launcher requires a dedicated catalog state directory.")
    # Refuse to change an existing unrelated profile or a live gateway.
    if state.exists() and any(state.iterdir()) and not (state / ".catalog-gateway").is_file():
        raise ValueError("The provided directory contains another profile.")
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", args.port))

    benchmark = json.loads((TOOLS.parent / "benchmark.json").read_text())
    verify_runtime(runtime, benchmark)
    credential = credentials(runtime)
    state.mkdir(mode=0o700, parents=True, exist_ok=True)
    (state / ".catalog-gateway").touch(mode=0o600, exist_ok=True)
    token_path = state / "gateway-token"
    if not token_path.exists():
        private_write(token_path, secrets.token_hex(32).encode())

    source = TOOLS / "catalog-search-plugin"
    plugin_path = state / "plugins" / PLUGIN
    for name in ("package.json", "openclaw.plugin.json", "index.cjs"):
        private_write(plugin_path / name, (source / name).read_bytes())
    workspace = state / "workspace"
    workspace.mkdir(mode=0o700, exist_ok=True)
    # Use the direct provider's published example-compatible model definition.
    baseline = json.loads((runtime / "openclaw/dev/cerebras-kimi/openclaw.json").read_text())
    provider = baseline["models"]["providers"]["cerebras"]
    if provider["baseUrl"] != "https://api.cerebras.ai/v1" or provider["apiKey"] != "${CEREBRAS_API_KEY}":
        raise ValueError("The baseline must use the direct Cerebras endpoint and an environment reference.")
    config = {
        "models": {"mode": "merge", "providers": {"cerebras": provider}},
        "agents": {"defaults": {"model": {"primary": benchmark["model"]},
                              "workspace": str(workspace), "skipBootstrap": True, "timeoutSeconds": 180,
                              "thinkingDefault": "low", "params": {"temperature": 0.2, "maxTokens": 1024}}},
        "plugins": {"enabled": True, "allow": ["cerebras", PLUGIN], "load": {"paths": [str(plugin_path)]},
                    "entries": {PLUGIN: {"enabled": True}}},
        "tools": {"allow": ["search_catalog"], "toolSearch": {"enabled": False}},
        "gateway": {"mode": "local", "bind": "loopback", "port": args.port,
                    "auth": {"mode": "token", "token": "${OPENCLAW_GATEWAY_TOKEN}"}, "controlUi": {"enabled": True}},
        "meta": {"migrations": {"modelPolicyAllowlist": True, "utilityModelSeparation": True},
                 "lastTouchedVersion": "2026.10.9"},
    }
    private_write(state / "openclaw.json", (json.dumps(config, indent=2) + "\n").encode())
    private_write(state / "agents/main/agent/settings.json", b'{"retry":{"provider":{"maxRetries":0}}}\n')
    receipts = Path(os.environ.get("CATALOG_RECEIPT_DIR", state / "catalog-receipts")).resolve()
    receipts.mkdir(mode=0o700, parents=True, exist_ok=True)
    env = dict(os.environ, CEREBRAS_API_KEY=credential, OPENCLAW_GATEWAY_TOKEN=token_path.read_text().strip(),
               CATALOG_RECEIPT_DIR=str(receipts),
               OPENCLAW_STATE_DIR=str(state), OPENCLAW_CONFIG_PATH=str(state / "openclaw.json"),
               OPENCLAW_GATEWAY_PORT=str(args.port), OPENCLAW_SKIP_CHANNELS="1", OPENCLAW_SKIP_CRON="1",
               PATH=str(runtime / "bin") + os.pathsep + os.environ.get("PATH", ""))
    node = runtime / "bin/node"
    print(f"Starting catalog gateway at 127.0.0.1:{args.port} with state {state}", flush=True)
    os.chdir(runtime / "openclaw")
    os.execve(node, [str(node), str(runtime / "openclaw/openclaw.mjs"), "gateway", "run"], env)


if __name__ == "__main__":
    main()
