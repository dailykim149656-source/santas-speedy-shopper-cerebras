"""Capture an already-created local shopping session using record.mjs."""
import argparse
from datetime import datetime
import json
import math
import os
from pathlib import Path
import signal
import subprocess
import time
from urllib.parse import urlsplit
from uuid import UUID


TOOLS = Path(__file__).resolve().parent
RUNTIME = Path.home() / "Library/Caches/cerebras-speed-bounty/2026-11-22"


def read(path):
    try:
        return json.loads(path.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def save(path, data):
    temp = path.with_suffix(".film-tmp")
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    temp.replace(path)


def millisecond_time(value):
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp() * 1000
        except ValueError:
            return None
    if type(value) in (float, int) and math.isfinite(value) and value > 0:
        return value
    return None


def recorder_finish(result, ident):
    if result.get("run_id", result.get("id")) != ident:
        raise ValueError("Finish marker does not match the recorded run")
    score = result.get("mean")
    score_ok = type(score) in (int, float) and math.isfinite(score) and score > 0
    urls = result.get("urls", [])
    qualifying = result.get("qualifying") is True
    if qualifying and not (score_ok and isinstance(urls, list) and len(urls) == 5 and
                           all(isinstance(u, str) and urlsplit(u).scheme == "https" for u in urls)
                           and len(set(urls)) == 5):
        raise ValueError("Qualifying run needs its official mean and five distinct product links")
    return {"run_id": ident, "qualifying": qualifying,
            "mean": math.floor(score + 0.5) if score_ok else None, "urls": urls,
            "video_threshold_tps": 1, "discard_unverified": not qualifying}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("out", "state"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--port", type=int, required=True, choices=[19873])
    parser.add_argument("--id", required=True)
    parser.add_argument("--session-key", required=True)
    parser.add_argument("--post-run", action="store_true",
                        help="Reopen a completed run and retain its separate post-run recording")
    args = parser.parse_args()
    os.umask(0o077)
    if str(UUID(args.id)) != args.id or not args.session_key.startswith("agent:main:"):
        parser.error("Expected a canonical run UUID and main agent session key")
    directory = args.out.resolve() / args.id
    session = read(directory / "session.json") or {}
    if (session.get("id"), session.get("sessionKey")) != (args.id, args.session_key):
        parser.error("Expected the matching fresh session marker")
    if args.post_run:
        completed = read(directory / "finish.json") or {}
        if not recorder_finish(completed, args.id)["qualifying"]:
            parser.error("Post-run capture requires a qualifying completed session")
    media = directory / ("media-post-run" if args.post_run else "media")
    if args.post_run and media.exists():
        media = directory / ("media-post-run-" + str(time.time_ns()))
    media.mkdir(mode=0o700, exist_ok=False)
    env = {k: os.environ[k] for k in ("HOME", "PATH", "TMPDIR", "LANG") if k in os.environ}
    env.update(BOUNTY_ROOT=str(media / ".capture"), BOUNTY_GATEWAY_PORT=str(args.port),
               BOUNTY_BROWSER_RUNTIME=str(TOOLS / "simethan_browser.mjs"),
               SIMETHAN_PLAYWRIGHT=str(RUNTIME / "openclaw/node_modules/playwright-core/index.mjs"),
               SIMETHAN_STATE=str(args.state.resolve()),
               RECORDER_AUTH_NODE="/usr/bin/false")
    cmd = [str(RUNTIME / "bin/node"), str(TOOLS / "record.mjs"),
           "--dir", str(media), "--session-key", args.session_key]
    # Credentials are read by the incognito dashboard adapter only. Do not save child diagnostics.
    child = subprocess.Popen(cmd, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    def stop(signum, frame):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, stop)
    result = None
    try:
        deadline = time.monotonic() + 1800
        while child.poll() is None and time.monotonic() < deadline:
            if result is None and (media / "ready.json").is_file():
                candidate = read(directory / "finish.json")
                if candidate is not None:
                    save(media / "finish.json", recorder_finish(candidate, args.id))
                    result = candidate
                    deadline = time.monotonic() + 240
            time.sleep(0.2)
    finally:
        if child.poll() is None:
            child.terminate()
            try:
                child.wait(timeout=15)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()
    metadata = read(media / "recording.json") or {}
    ready = read(media / "ready.json") or {}
    sent = millisecond_time((result or {}).get("sentAt"))
    first = millisecond_time(ready.get("readyAt"))
    full = bool(not args.post_run and metadata.get("full_run") and sent and first and first <= sent)
    if metadata.get("full_run") and not full:
        metadata.update(full_run=False, full_run_timing="first frame after send or send time unavailable")
        save(media / "recording.json", metadata)
    save(media / "film.json", {"run_id": args.id, "sessionKey": args.session_key,
                                "full_run": full, "post_run_requested": args.post_run,
                                "readyAt": ready.get("readyAt"), "sentAt": sent,
                                "demo": (media / "demo.mp4").is_file(),
                                "viewport_verified": bool((read(media / "viewport-evidence.json") or {}).get("verified")),
                                "recorder_exit": child.returncode})
    return child.returncode


if __name__ == "__main__":
    raise SystemExit(main())
