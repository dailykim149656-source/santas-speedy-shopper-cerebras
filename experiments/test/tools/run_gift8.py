#!/usr/bin/env python3
"""Bounded eight-send native gift lookup comparison on the isolated test profile."""
import argparse
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid

import loop
from first5027 import terminal_429
from ledger import commit, plan as commit_plan
from preflight_recovery import seal_unsent
from run_first5027 import reservation, foreign_end, exp_finished

START = 5051
ORDER = "ABBABAAB"
CAMPAIGN = loop.CACHE / "gift8-5051"
MANIFESTS = CAMPAIGN / "manifests"
RECEIPTS = CAMPAIGN / "receipts"
HISTORY = CAMPAIGN / "iterations.jsonl"
RESERVATIONS = CAMPAIGN / "reservation.jsonl"
PLUGIN = loop.TOOLS / "gift8-plugin"
IDS = [21951, 23345, 11125, 11141, 20209]


def sha(data):
    return hashlib.sha256(data).hexdigest()


def append(path, record):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as output:
        output.write(json.dumps(record, ensure_ascii=False) + "\n")
        output.flush()
        os.fsync(output.fileno())
    print(json.dumps(record, ensure_ascii=False), flush=True)


def read_rows():
    return [json.loads(line) for line in HISTORY.read_text().splitlines() if line] if HISTORY.exists() else []


def record_result(row):
    rows = read_rows()
    for index, previous in enumerate(rows):
        if previous["id"] != row["id"]:
            continue
        for key in ("label", "arm", "score", "started_wall", "ended_wall"):
            if previous[key] != row[key]:
                raise ValueError("A revalidation changed original run identity or score: " + key)
        if previous != row:
            append(CAMPAIGN / "validation-revisions.jsonl",
                   dict(at_ms=time.time_ns() // 1_000_000, previous=previous, current=row))
            rows[index] = row
            temporary = HISTORY.with_suffix(".writing")
            temporary.write_text("".join(json.dumps(value, ensure_ascii=False) + "\n" for value in rows))
            temporary.replace(HISTORY)
        return
    append(HISTORY, row)


def plugin_digest():
    return sha(b"".join((PLUGIN / name).read_bytes()
                       for name in sorted(("index.cjs", "openclaw.plugin.json", "package.json"))))


def prompt(ident):
    return (
        "Christmas gifts. Requested product IDs in order: " + ", ".join(map(str, IDS)) + ".\n"
        "Use the current live gift data if provided. Otherwise call gift_lookup for each requested ID "
        "in parallel, then use the returned live cards. Return only one JSON object "
        '{"gifts":[the five complete returned cards in the requested order]}. '
        "Copy every card field and value exactly.\n_run=" + ident[:8]
    )


def require_profile():
    if (not loop.TEST_SCHEDULE or loop.ROOT != loop.MAIN_ROOT.with_name("2026-11-22-test")
            or os.environ.get("BOUNTY_GATEWAY_PORT") != "19863"
            or subprocess.check_output(["git", "-C", str(loop.REPO), "branch", "--show-current"],
                                       text=True).strip() != "test"):
        raise RuntimeError("Use the isolated test branch, profile, archive and port 19863")


def prepare():
    """Persist a reversible dedicated-profile change before the native gateway starts."""
    path = loop.ROOT / "shopper-test/openclaw.json"
    before = loop.get(path)
    backup = CAMPAIGN / "profile-before.json"
    if backup.exists():
        raise RuntimeError("A profile backup already exists; reconcile or restore it before preparing again")
    updated = json.loads(json.dumps(before))
    updated["plugins"] = {
        "enabled": True,
        "allow": ["gift8"],
        "load": {"paths": [str(PLUGIN)]},
        "entries": {"gift8": {
            "enabled": True,
            "config": {"campaignRoot": str(CAMPAIGN), "timeoutMs": 15000},
            "hooks": {"allowPromptInjection": True, "allowConversationAccess": True,
                      "timeouts": {"before_prompt_build": 60000}},
        }},
    }
    updated["tools"]["allow"] = ["gift_lookup"]
    updated["tools"]["toolSearch"] = {"enabled": False}
    defaults = updated["agents"]["defaults"]
    defaults["thinkingDefault"] = "low"
    defaults["params"] = dict(defaults.get("params", {}), temperature=0.2, maxTokens=1024)
    defaults["params"].pop("topP", None)
    if defaults["model"]["primary"] != loop.BENCH["model"]:
        raise RuntimeError("The dedicated model differs from the official Kimi trial")
    loop.put(backup, before)
    loop.put(CAMPAIGN / "profile-prepared.json", updated)
    loop.put(path, updated)
    print("Dedicated gift8 profile prepared", flush=True)


def restore():
    path = loop.ROOT / "shopper-test/openclaw.json"
    before = loop.get(CAMPAIGN / "profile-before.json")
    expected = loop.get(CAMPAIGN / "profile-prepared.json")
    current = loop.get(path)
    # Preserve edits outside the profile fields owned by this study.
    for key in ("plugins", "tools"):
        if current.get(key) != expected.get(key):
            raise RuntimeError("Profile field changed during the study: " + key)
    for key in ("thinkingDefault", "params"):
        if current["agents"]["defaults"].get(key) != expected["agents"]["defaults"].get(key):
            raise RuntimeError("Model defaults changed during the study: " + key)
    for key in ("plugins", "tools"):
        if key in before:
            current[key] = before[key]
        else:
            current.pop(key, None)
    for key in ("thinkingDefault", "params"):
        if key in before["agents"]["defaults"]:
            current["agents"]["defaults"][key] = before["agents"]["defaults"][key]
        else:
            current["agents"]["defaults"].pop(key, None)
    loop.put(path, current)
    print("Dedicated gift8 profile restored", flush=True)


def campaign_plans():
    plans = []
    for path in (loop.REPO / "runs").glob("*/plan.json"):
        value = loop.get(path)
        if value.get("variant") in ("gift8-tool", "gift8-prefetch"):
            plans.append(value)
    return sorted(plans, key=lambda value: int(value["label"].split("-")[0][1:]))


def sent_plans():
    return [p for p in campaign_plans() if (loop.RUNS / (p["label"] + ".send-intent.json")).exists()]


def create_trial(side):
    ident = str(uuid.uuid4())
    number = loop.next_trial_number()
    arm = "tool" if side == "A" else "prefetch"
    label = f"D{number:04d}-gift8-{arm}"
    session = "agent:main:shop-" + label.lower() + "-" + ident[:8]
    text = prompt(ident)
    manifest = dict(id=ident, sessionKey=session, arm=arm, prompt_sha256=sha(text.encode()),
                    created_ms=time.time_ns() // 1_000_000, ids=IDS, protocol="gift8-v1",
                    plugin_sha256=plugin_digest())
    manifest_path = MANIFESTS / (ident + ".json")
    loop.put(manifest_path, manifest)
    public_manifest = loop.REPO / "runs" / ident / "gift-manifest.json"
    loop.put(public_manifest, manifest)
    manifest_sha = sha(manifest_path.read_bytes())
    value = dict(id=ident, label=label, sessionKey=session, variant="gift8-" + arm,
                 thinking="low", temperature=0.2, top_p=None, max_completion_tokens=1024,
                 capturePolicy="score-first", video_threshold_tps=1700,
                 experiment=f"gift8-v1 {arm}; manifest-sha256={manifest_sha}",
                 prompt=text, official_commit=loop.BENCH["patch_source_commit"],
                 official_patch_sha256=loop.BENCH["patch_sha256"],
                 benchmark_sha256=sha((loop.REPO / "benchmark.json").read_bytes()),
                 organizer_reproduction_request=loop.BENCH["organizer_reproduction_request"])
    result = commit_plan(loop.REPO, value)
    commit(loop.REPO, [public_manifest], "Bind live gift manifest " + ident)
    plan = loop.get(loop.REPO / "runs" / ident / "plan.json")
    scratch = loop.CACHE / "capture" / ident
    loop.put(scratch / "plan.json", plan)
    loop.put(scratch / "run.json", plan)
    loop.status("gift8_measuring", label=label, id=ident, plan_commit=result)
    return plan, scratch


def finish_trial(plan):
    from gift8_evidence import validate, finish
    ident, label = plan["id"], plan["label"]
    raw = loop.RUNS / (label + ".json")
    loop.preserve_raw(raw, ident)
    validation = validate(loop.REPO, raw, RECEIPTS / ident, MANIFESTS / (ident + ".json"), PLUGIN)
    loop.put(loop.CACHE / "capture" / ident / "validation.json", validation)
    finish(loop.REPO, raw, validation, RECEIPTS / ident, MANIFESTS / (ident + ".json"), PLUGIN)
    data = loop.get(raw)
    calls = validation["calls"]
    score = validation["score"]
    row = dict(id=ident, label=label, arm="A" if plan["variant"] == "gift8-tool" else "B",
               variant=plan["variant"], valid=validation["valid"], method_valid=validation["valid"],
               score=score.get("mean_exact_tps"), ui=score.get("ui_rounded_tps"),
               first_tps=calls[0].get("tokensPerSecond") if calls else None,
               final_tps=calls[-1].get("tokensPerSecond") if calls else None,
               call_count=len(calls), started_wall=data["startedWall"], ended_wall=data["ended"]["time"],
               measured_call_count=score.get("call_count"),
               structure_expected=validation.get("structure_expected"),
               terminal_429=terminal_429(data, loop.ROOT / "gateway.log"),
               product_urls=[p["url"] for p in validation["products"] if p.get("verified")],
               rejection=validation.get("reject_reasons", []))
    record_result(row)
    loop.status("gift8_result", **row)
    return row


def reconcile():
    complete = {row["id"] for row in read_rows()}
    for value in campaign_plans():
        if value["id"] in complete:
            continue
        raw = loop.RUNS / (value["label"] + ".json")
        intent = loop.RUNS / (value["label"] + ".send-intent.json")
        if raw.exists():
            finish_trial(value)
        elif intent.exists():
            raise RuntimeError("A sent trial needs terminal reconciliation: " + value["label"])
        elif not (loop.REPO / "runs" / value["id"] / "preflight.json").exists():
            seal_unsent(loop.REPO, loop.CACHE, value["id"], "interrupted_before_send")


def run():
    exp = loop.MAIN_ROOT.with_name("2026-11-22-exp2000") / "mean-2000"
    locks = [("exp-tps-2000", exp / "loop.lock", fcntl.LOCK_SH),
             ("main", loop.MAIN_ROOT / "mean-2000/loop.lock", fcntl.LOCK_SH),
             ("test", loop.CACHE / "loop.lock", fcntl.LOCK_EX)]
    with reservation(locks, RESERVATIONS, exp_ready=exp_finished) as fds:
        latest_foreign = max(foreign_end(exp), foreign_end(loop.MAIN_ROOT / "mean-2000"))
        reconcile()
        while True:
            rows = read_rows()
            sent = sent_plans()
            if len(rows) != len(sent):
                raise RuntimeError("Sent trials and completed rows differ; reconcile before proceeding")
            for index, plan in enumerate(sent):
                if plan["variant"] != ("gift8-tool" if ORDER[index] == "A" else "gift8-prefetch"):
                    raise RuntimeError("The committed send order differs from the approved schedule")
            if any(r["valid"] and r["score"] is not None and r["score"] >= 1700 for r in rows):
                loop.status("gift8_target_pending_verification", sent=len(sent))
                return
            if len(sent) >= len(ORDER):
                loop.status("gift8_stopped", sent=len(sent), reason="completed eight actual sends")
                return
            if (loop.CACHE / "stop-requested").exists():
                loop.status("user_stop", campaign="gift8-5051", sent=len(sent))
                return
            deadline = latest_foreign + 60
            if rows:
                last = rows[-1]
                streak = 0
                for row in reversed(rows):
                    if row["valid"]:
                        break
                    streak += 1
                deadline = max(deadline, last["ended_wall"] / 1000 + max(60, 30 * 2 ** min(streak, 4)))
                backoff_path = CAMPAIGN / "backoff.json"
                backoff = loop.get(backoff_path) if backoff_path.exists() else {}
                if (len(rows) >= 2 and all(row["terminal_429"] for row in rows[-2:])
                        and len(rows) - backoff.get("after_slot", 0) >= 2):
                    backoff = dict(after_slot=len(rows), until=last["ended_wall"] / 1000 + 600)
                    loop.put(backoff_path, backoff)
                    append(CAMPAIGN / "events.jsonl", dict(event="terminal_429_pause", **backoff))
                deadline = max(deadline, backoff.get("until", 0))
            if time.time() < deadline:
                time.sleep(min(30, deadline - time.time()))
                continue
            plan, scratch = create_trial(ORDER[len(sent)])
            with (scratch / "run.log").open("w") as out:
                child = subprocess.Popen([str(loop.NODE), str(loop.TOOLS / "run.mjs"),
                                          str(scratch / "run.json")],
                                         stdout=out, stderr=subprocess.STDOUT, pass_fds=fds)
                try:
                    result = child.wait(timeout=865)
                except subprocess.TimeoutExpired:
                    loop.stop_child(child)
                    raise RuntimeError("Native sender timed out; reconcile this exact run before another send")
            raw = loop.RUNS / (plan["label"] + ".json")
            if not raw.exists():
                intent = loop.RUNS / (plan["label"] + ".send-intent.json")
                if intent.exists():
                    raise RuntimeError("Sender exited after send intent without raw terminal evidence")
                seal_unsent(loop.REPO, loop.CACHE, plan["id"], "gateway_preflight_exit_" + str(result))
                time.sleep(45)
                continue
            finish_trial(plan)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--prepare", action="store_true")
    mode.add_argument("--restore", action="store_true")
    args = parser.parse_args()
    os.umask(0o077)
    require_profile()
    CAMPAIGN.mkdir(parents=True, exist_ok=True)
    if args.prepare:
        prepare()
        return
    if args.restore:
        restore()
        return
    try:
        run()
    except Exception as error:
        loop.status("gift8_needs_attention", error=str(error)[:500])
        raise


if __name__ == "__main__":
    main()
