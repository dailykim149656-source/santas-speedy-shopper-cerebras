"""Prepare the native five-category shopping arm and validate its actual merchant and model inputs."""
import concurrent.futures
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import time
from uuid import UUID

from gift8_evidence import bounded_file, score_raw
import validate as retail
from variants import catalogs, SYNTH_CATEGORIES


PLUGIN = Path(__file__).resolve().with_name("speed1500-plugin")
PROTOCOL = "speed1500-native-v1"
CONTEXT_PREFIX = "Current live merchant results in requested category order: "


def sha(data):
    return hashlib.sha256(data).hexdigest()


def plugin_sha():
    return sha(b"".join((PLUGIN / name).read_bytes() for name in ("index.cjs", "openclaw.plugin.json", "package.json")))


def prompt(run_id_or_first8):
    nonce = str(run_id_or_first8)[:8]
    if not re.fullmatch(r"[0-9a-f]{8}", nonce):
        raise ValueError("Invalid run nonce")
    return ("Christmas gifts. Use the current live merchant results for filter, mixer, oscillator, echo, "
            "and cable, in that order. Return only five numbered [exact name](exact product URL) links, "
            "one per line.\n_run=" + nonce)


def prepare(plan, receipt_dir):
    directory = Path(receipt_dir)
    ident = plan["id"]
    if (str(UUID(ident)) != ident or directory.name != ident or plan["variant"] != "speed1500-prefetch"
            or plan["prompt"] != prompt(ident) or not plan["sessionKey"]):
        raise ValueError("Wrong prefetch plan")
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    manifest = dict(protocol=PROTOCOL, id=ident, sessionKey=plan["sessionKey"], prompt=plan["prompt"],
                    prompt_sha256=sha(plan["prompt"].encode()), plugin_sha256=plugin_sha(),
                    urls=catalogs(ident[:8], 1, shops="synth-categories"))
    f = directory / "manifest.json"
    if f.exists():
        existing = json.loads(bounded_file(directory, f.name).read_bytes())
        if any(existing.get(k) != v for k, v in manifest.items()):
            raise ValueError("Another trial already bound these receipts")
        return existing
    manifest["created_ms"] = time.time_ns() // 1_000_000
    with f.open("x") as out:
        json.dump(manifest, out, ensure_ascii=False)
    return manifest


def require(condition, message):
    if not condition:
        raise ValueError(message)


def audit_receipts(directory, plan, raw, start, end):
    ident = raw["id"]
    session = raw["sessionKey"]
    encoded = bounded_file(directory, "manifest.json").read_bytes()
    manifest_hash = sha(encoded)
    m = json.loads(encoded)
    urls = catalogs(ident[:8], 1, shops="synth-categories")
    require(directory.name == ident and str(UUID(ident)) == ident and
            plan["variant"] == "speed1500-prefetch" and plan["prompt"] == prompt(ident) and
            all(raw.get(k) == plan.get(k) for k in (
                "id", "sessionKey", "label", "variant", "prompt", "thinking", "temperature", "top_p", "max_completion_tokens")),
            "Native run differs from its planned task")
    require(m.get("id") == ident and m.get("sessionKey") == session and m.get("protocol") == PROTOCOL
            and m.get("plugin_sha256") == plugin_sha() and m.get("urls") == urls
            and m.get("prompt") == plan["prompt"] and m.get("prompt_sha256") == sha(plan["prompt"].encode())
            and m["created_ms"] <= start <= end, "Foreign, late or changed native manifest")
    rows, receipts, sources = [], [], []
    for category, url in zip(SYNTH_CATEGORIES, urls):
        r = json.loads(bounded_file(directory, category + ".json").read_bytes())
        body = bounded_file(directory, category + ".bin").read_bytes()
        require(all(r.get(k) == v for k, v in dict(id=ident, sessionKey=session, category=category, url=url,
                    final_url=url, status=200, manifest_sha256=manifest_hash, body_sha256=sha(body)).items())
                and start <= r["started"] <= r["ended"] <= end, "Foreign, stale or altered category receipt")
        products = json.loads(body)
        require(isinstance(products, list) and len(products) == 1, "Expected one live product")
        product = products[0]
        name, permalink = product["name"], product["permalink"]
        require(isinstance(name, str) and bool(name.strip()) and retail.merchant(permalink, product=True)
                and permalink.startswith("https://aisynthesis.com/product/"), "Invalid live product")
        rows.append(dict(name=name, permalink=permalink))
        receipts.append(r)
        sources.append(dict(url=url, accepted=True, status=200, reasons=[], cached=False, products=[permalink],
                            fetched_at=datetime.fromtimestamp(r["ended"] / 1000, timezone.utc).isoformat()))
    require(len({r["permalink"] for r in rows}) == 5, "Non-distinct live category products")
    proof = dict(protocol=PROTOCOL, manifest_sha256=manifest_hash, plugin_sha256=m["plugin_sha256"], receipts=receipts)
    return rows, sources, proof


def audit_dispatch(directory, plan, raw, rows, proof):
    ident, session = raw["id"], raw["sessionKey"]
    end = raw["ended"]["time"]
    context = CONTEXT_PREFIX + json.dumps(rows, separators=(",", ":"), ensure_ascii=False)
    events = [json.loads(s) for s in bounded_file(directory, "events.jsonl").read_text().splitlines() if s]
    inputs, injections = [], []
    for e in events:
        require(e.get("id") == ident and e.get("sessionKey") == session and e.get("manifest_sha256") == proof["manifest_sha256"]
                and max(r["ended"] for r in proof["receipts"]) <= e["at"] <= end, "Wrong run or time in hook evidence")
        require(e.get("context_sha256") == sha(context.encode()), "Native hook lost live inputs")
        if e["type"] == "injection":
            injections.append(e)
        elif e["type"] == "model_input":
            require(injections and e["provider"] == "cerebras" and e["model"] == retail.MODEL
                    and e["sessionId"] and injections[-1]["at"] <= e["at"]
                    and isinstance(e.get("prompt"), str) and e["prompt"].count(context) == 1
                    and (inputs or (plan["prompt"] in e["prompt"] and
                         e["prompt"].index(context) < e["prompt"].index(plan["prompt"]))),
                    "Missing live categories or wrong model in native dispatch")
            inputs.append(e)
        else:
            raise ValueError("Unexpected hook evidence type")
    require(inputs and len({e["sessionId"] for e in inputs}) == 1, "Missing consistent actual model input")
    proof.update(context_sha256=sha(context.encode()), model_input_count=len(inputs),
                 model_input_sha256=[sha(e["prompt"].encode()) for e in inputs])


def validate(repo, raw, plan, receipt_dir):
    body = Path(raw).read_bytes()
    data = json.loads(body)
    calls, score, reasons = score_raw(data)
    rates = sorted(c["tokensPerSecond"] for c in calls if c.get("timed_sample"))
    score["p90_tps"] = rates[(9 * len(rates) - 1) // 10] if rates else None
    score["official_patch_sha256"] = sha(retail.OFFICIAL.read_bytes()) if retail.OFFICIAL.is_file() else None
    sources, products, proof, final = [], [], {}, ""
    product_valid = method_valid = False
    try:
        ident = data["id"]
        require(str(UUID(ident)) == ident, "Invalid run ID")
        expected = subprocess.check_output(["git", "-C", str(repo), "show", "HEAD:runs/" + ident + "/plan.json"])
        committed = json.loads(expected)
        require(all(committed.get(k) == plan.get(k) for k in
                    ("id", "sessionKey", "label", "variant", "prompt", "thinking", "temperature",
                     "top_p", "max_completion_tokens", "experiment", "official_patch_sha256")), "Uncommitted native plan")
        require(score["official_patch_sha256"] == committed["official_patch_sha256"], "Unexpected official scorer")
        require(("plugin=" + plugin_sha()) in committed["experiment"], "Unpinned native plugin")
        rows, sources, proof = audit_receipts(Path(receipt_dir), plan, data, data["startedWall"], data["ended"]["time"])
        assistants = [m for m in data["history"]["messages"] if m.get("role") == "assistant"
                      and m.get("__openclaw", {}).get("runId") == ident]
        require(data["ended"]["terminal"] == "final" and assistants and assistants[-1]["stopReason"] == "stop",
                "No successful final assistant output")
        require(len({c["response_id"] for c in calls}) == len(calls), "Repeated provider response identity")
        final = retail.text_content(assistants[-1]).strip()
        urls, misleading = retail.answer_links(final)
        by_url = {row["permalink"]: row for row in rows}
        require(not misleading and len(urls) == 5 and set(urls) == set(by_url), "Final links differ from five live products")
        expected_lines = [f"{i}. [{r['name']}]({r['permalink']})" for i, r in enumerate(rows, 1)]
        candidates = [dict(url=url, catalog_name=by_url[url]["name"]) for url in urls]
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
            products = list(pool.map(retail.verify_product, candidates))
        require(all(p["verified"] for p in products), "Independent merchant detail GET failed")
        product_valid = not reasons
        proof["actual_generation_count"] = score["call_count"]
        proof["single_generation"] = score["call_count"] == 1
        audit_dispatch(Path(receipt_dir), plan, data, rows, proof)
        require(final.splitlines() == expected_lines, "Five numbered lines differ from the planned format")
        method_valid = True
    except (OSError, ValueError, KeyError, TypeError, IndexError, subprocess.CalledProcessError) as exc:
        reasons.append(str(exc))
    valid = product_valid and method_valid
    target = bool(rates and score["mean_exact_tps"] > 2000 and score["ui_rounded_tps"] > 2000)
    return dict(run_id=data["id"], input_path=str(Path(raw).resolve()), input_sha256=sha(body),
                valid=valid, product_valid=product_valid, method_valid=method_valid, status="rejected" if not valid else "passed" if target else "valid_below_target",
                target_met=valid and target, target_reasons=[] if target else ["exact mean and rounded UI must both be strictly greater than 2000 TPS"],
                reject_reasons=reasons, calls=[c for c in calls if c.get("timed_sample")], score=score, retail_sources=sources, products=products,
                final_text=final, native_prefetch=proof)
