#!/usr/bin/env python3
"""Score fresh, two-call search_catalog sessions and check their live retail links."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import ipaddress
import json
import math
from pathlib import Path
import re
import socket
from statistics import median
from urllib.error import HTTPError
from urllib.parse import unquote, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from scoring import call_rate, mean_rate, round_rate
from validate import MODEL, Page, answer_links, finite, text_content

TARGET = 1673
ENDPOINT = "https://catalog.shopify.com/api/ucp/mcp"


def product_identity(url):
    parts = urlsplit(url)
    if (parts.scheme not in {"http", "https"} or not parts.hostname or
            parts.username or parts.password or parts.port not in (None, 80, 443)):
        raise ValueError("invalid retail URL")
    match = re.fullmatch(r"(?:/[^/]+)*/products/([^/]+)/?", unquote(parts.path))
    if not match:
        raise ValueError("URL does not identify an individual catalog product")
    return parts.hostname.removeprefix("www.").lower(), match.group(1)


def public_product(url):
    host, slug = product_identity(url)
    name = urlsplit(url).hostname
    addresses = socket.getaddrinfo(name, None, type=socket.SOCK_STREAM)
    if not addresses or not all(ipaddress.ip_address(entry[4][0]).is_global for entry in addresses):
        raise ValueError("retail hostname has a non-public address")
    return host, slug


class ProductRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if public_product(newurl) != product_identity(req.full_url):
            raise ValueError("redirect changes merchant or product")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def check_page(url):
    result = {"url": url, "verified": False, "checked_at": datetime.now(timezone.utc).isoformat()}
    try:
        public_product(url)
        req = Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept": "text/html"})
        with build_opener(ProductRedirect()).open(req, timeout=12) as response:
            result.update(http=response.status, final_url=response.geturl())
            if response.status != 200 or response.headers.get_content_type() not in ("text/html", "application/xhtml+xml"):
                raise ValueError("not a successful HTML response")
            sample = response.read(2_000_000)
            page = Page()
            page.feed(sample.decode(response.headers.get_content_charset() or "utf-8", errors="replace"))
        og_type = page.meta.get("og:type", "").lower()
        structured = any("Product" in (obj.get("@type") if isinstance(obj.get("@type"), list)
                                       else [obj.get("@type")]) for obj in page.schemas)
        result.update(title=page.meta.get("og:title") or next(iter(page.titles), ""),
                      og_type=og_type, product_schema=structured)
        if not (og_type.startswith("product") or structured or page.meta.get("product:price:amount")):
            raise ValueError("no product metadata in merchant HTML")
        result["verified"] = True
    except Exception as exc:
        result["error"] = str(exc)
        if isinstance(exc, HTTPError):
            result["http"] = exc.code
            exc.close()
    return result


def text_products(message):
    products = []
    previous = ""
    for line in text_content(message).splitlines():
        line = line.strip()
        if not line:
            continue
        links, bad = answer_links(line)
        if links and not bad:
            md_title = re.search(r"\[([^\]]+)\]\(", line)
            title = md_title.group(1) if md_title else line.split(links[0], 1)[0].strip(" -:<>") or previous
            title = re.sub(r"^\s*(?:[-*]|\d+[.)])\s+", "", title)
            products.extend({"title": title.strip("* "), "url": u} for u in links)
        previous = line
    return products


def assess(path, receipts=None):
    row = {"path": str(path), "errors": [], "calls": [], "products": [], "final_links": []}
    errors = row["errors"]
    try:
        data = path.read_bytes()
        raw = json.loads(data)
        row.update(id=raw.get("id"), label=raw.get("label"), sessionKey=raw.get("sessionKey"),
                   sha256=hashlib.sha256(data).hexdigest(), wall_seconds=raw.get("wallSeconds"),
                   wait_status=raw.get("waitStatus"), official=raw.get("official"),
                   official_display=raw.get("officialDisplay"))
        if raw.get("error"):
            errors.append("run error: " + str(raw["error"])[:500])
        ended = raw.get("ended")
        if isinstance(ended, dict) and ended.get("terminal") not in ("final", None):
            errors.append("terminal event: " + str(ended.get("terminal")))
        messages = raw["history"]["messages"]
        if not row["id"] or not isinstance(messages, list):
            raise ValueError("missing trial id or history messages")
        roles = [m.get("role") for m in messages if m.get("role") in {"user", "assistant", "toolResult"}]
        if roles != ["user", "assistant", "toolResult", "assistant"]:
            errors.append(f"unexpected session roles {roles}")
        users = [m for m in messages if m.get("role") == "user"]
        if len(users) != 1 or not raw.get("prompt") or raw["prompt"] not in text_content(users[0]):
            errors.append("fresh user message does not contain the recorded prompt")
        for m in messages:
            run = (m.get("__openclaw") or {}).get("runId")
            if run and run != row["id"]:
                errors.append("session contains an event from another run")
                break
        assistants = [m for m in messages if m.get("role") == "assistant"]
        for m in assistants:
            timing = m.get("serverGeneration") or {}
            n, ms = timing.get("outputTokens"), timing.get("completionMs")
            call = {k: m.get(k) for k in ("provider", "model", "responseId", "stopReason", "timestamp")}
            call.update(outputTokens=n, completionMs=ms, tps=None)
            if m.get("errorMessage"):
                call["error"] = str(m["errorMessage"])[:500]
            elif m.get("stopReason") in {"error", "aborted"}:
                call["error"] = text_content(m)[:500]
            if finite(n) and finite(ms) and n >= 1 and ms > 0:
                call["tps"] = call_rate(n, ms)
            else:
                errors.append("missing valid serverGeneration metrics")
            if m.get("provider") != "cerebras" or m.get("model") != MODEL or not m.get("responseId"):
                errors.append("missing Cerebras Kimi identity or response ID")
            row["calls"].append(call)
        rates = [c["tps"] for c in row["calls"] if c["tps"] is not None]
        if rates:
            rate = mean_rate(rates)
            row.update(mean_tps=rate, ui_tps=round_rate(rate),
                       p90_tps=sorted(rates)[(9 * len(rates) + 9) // 10 - 1])
        if "official" in raw and rates:
            official = raw.get("official") or {}
            if (official.get("calls") != len(rates) or not finite(official.get("meanTokensPerSecond")) or
                    not math.isclose(official["meanTokensPerSecond"], row["mean_tps"], rel_tol=1e-12) or
                    not finite(official.get("p90TokensPerSecond")) or
                    not math.isclose(official["p90TokensPerSecond"], row["p90_tps"], rel_tol=1e-12)):
                errors.append("independent per-call calculations differ from official patch output")
        if len(assistants) != 2:
            raise ValueError("expected exactly two assistant calls")
        first, last = assistants
        if (not first.get("responseId") or first.get("responseId") == last.get("responseId") or
                first.get("stopReason") != "toolUse" or last.get("stopReason") != "stop"):
            errors.append("unexpected assistant call IDs or stop reasons")
        uses = [part for part in first.get("content", []) if isinstance(part, dict) and part.get("type") == "toolCall"]
        if len(uses) != 1 or uses[0].get("name") != "search_catalog" or not uses[0].get("id"):
            raise ValueError("first response did not request exactly one search_catalog")
        if any(isinstance(part, dict) and part.get("type") == "toolCall" for part in last.get("content", [])):
            errors.append("final response requested additional tools")
        use = uses[0]
        row["tool"] = {k: use.get(k) for k in ("id", "name", "arguments")}
        results = [m for m in messages if m.get("role") == "toolResult"]
        if (len(results) != 1 or results[0].get("toolCallId") != use["id"] or
                results[0].get("toolName") != "search_catalog" or results[0].get("isError") is not False):
            raise ValueError("missing successful catalog tool result bound to the tool call")
        result = results[0]
        details = result.get("details") or {}
        transcript_cards = details.get("products") or text_products(result)
        row["receipt_source"] = "toolResult.details" if details.get("products") else "toolResult.content"
        if receipts is not None:
            matching = receipts.get(use["id"], [])
            if finite(raw.get("sentAt")) and finite(raw.get("endedAt")):
                matching = [
                    receipt for receipt in matching
                    if finite(receipt.get("startedMs")) and finite(receipt.get("completedMs"))
                    and raw["sentAt"] <= receipt["startedMs"] <= receipt["completedMs"] <= raw["endedAt"]
                ]
            if len(matching) != 1:
                errors.append("missing or duplicate live catalog receipt for this run")
            else:
                receipt = matching[0]
                if receipt.get("products") != transcript_cards:
                    errors.append("live catalog receipt does not match transcript products")
                details = receipt
                row["receipt_source"] += " + plugin receipt"
        if "httpStatus" in details:
            row["catalog_receipt"] = {k: details.get(k) for k in (
                "httpStatus","requestCount","callId","startedMs","completedMs","endpoint","query",
                "returnedProductCount","responseSha256")}
            if (details["httpStatus"] != 200 or details.get("requestCount") != 1 or
                    details.get("endpoint") != ENDPOINT or details.get("callId") != use["id"] or
                    details.get("query") != use.get("arguments", {}).get("query", "").strip() or
                    not finite(details.get("startedMs")) or not finite(details.get("completedMs")) or
                    details["completedMs"] < details["startedMs"] or
                    not re.fullmatch(r"[a-f0-9]{64}", str(details.get("responseSha256", "")))):
                errors.append("catalog receipt failed HTTP, request count, endpoint, or binding check")
            if (finite(raw.get("sentAt")) and finite(raw.get("endedAt")) and
                    (not finite(details.get("startedMs")) or not finite(details.get("completedMs")) or
                     not raw["sentAt"] <= details["startedMs"] <= details["completedMs"] <= raw["endedAt"])):
                errors.append("catalog receipt timestamps outside the model run")
        for card in transcript_cards:
            if not isinstance(card, dict) or not isinstance(card.get("title"), str) or not card["title"].strip():
                raise ValueError("empty catalog product title")
            product_identity(card["url"])
            row["products"].append({"title": card["title"], "url": card["url"]})
        urls = [p["url"] for p in row["products"]]
        if len(urls) != 5 or len({product_identity(u) for u in urls}) != 5:
            errors.append("catalog did not return five distinct product pages")
        row["final_links"], bad = answer_links(text_content(last))
        if bad or len(row["final_links"]) != 5 or set(row["final_links"]) != set(urls):
            errors.append("five displayed links did not match catalog products")
    except (KeyError, TypeError, ValueError, OSError, AttributeError, IndexError) as exc:
        errors.append(str(exc))
    row["structure_valid"] = not errors
    return row


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--receipts", type=Path, help="Directory of live plugin receipts keyed by callId")
    opts = parser.parse_args()
    receipts = None
    if opts.receipts:
        receipts = {}
        for p in opts.receipts.glob("*.json"):
            if not p.name.startswith("."):
                receipt = json.loads(p.read_bytes())
                receipts.setdefault(receipt["callId"], []).append(receipt)
    rows = [assess(p, receipts) for p in opts.paths]
    for key in ("id", "sessionKey"):
        vals = [r.get(key) for r in rows]
        for r in rows:
            if r.get(key) and vals.count(r[key]) > 1:
                r["errors"].append("duplicate " + key)
                r["structure_valid"] = False
    all_ids = [c["responseId"] for r in rows for c in r["calls"] if c.get("responseId")]
    for row in rows:
        if any(c.get("responseId") and all_ids.count(c["responseId"]) > 1 for c in row["calls"]):
            row["errors"].append("duplicate provider response ID")
            row["structure_valid"] = False
    urls = {p["url"] for r in rows if r["structure_valid"] for p in r["products"]}
    with ThreadPoolExecutor(max_workers=8) as pool:
        checks = dict(zip(sorted(urls), pool.map(check_page, sorted(urls))))
    for row in rows:
        row["pages"] = [checks[p["url"]] for p in row["products"] if p["url"] in checks]
        if row["structure_valid"] and not all(c["verified"] for c in row["pages"]):
            row["errors"].append("retail page verification incomplete")
        row["valid"] = not row["errors"]
        row["exceeds_raw_target"] = row["valid"] and row["mean_tps"] > TARGET
        row["exceeds_ui_target"] = row["valid"] and row["ui_tps"] > TARGET
    valid = [r for r in rows if r["valid"]]
    rates = [r["mean_tps"] for r in valid]
    stats = dict(attempts=len(rows), structure_valid=sum(r["structure_valid"] for r in rows), valid=len(valid),
                 best_mean_tps=max(rates, default=None), mean_of_run_means=mean_rate(rates) if rates else None,
                 median_of_run_means=median(rates) if rates else None, target=TARGET,
                 above_raw=sum(r["exceeds_raw_target"] for r in rows), above_ui=sum(r["exceeds_ui_target"] for r in rows))
    opts.output.parent.mkdir(parents=True, exist_ok=True)
    opts.output.write_text(json.dumps({"trials": rows, "summary": stats}, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(stats, ensure_ascii=False))


if __name__ == "__main__":
    main()
