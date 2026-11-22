#!/usr/bin/env python3
"""Validate a saved real shopping run. Usage: validate.py RUN.json

JSON only on stdout. Exit 0: valid evidence (possibly below speed target).
Exit 1: rejected evidence. Exit 2: malformed input or validator failure.
The speed target is strictly >2000 for both exact mean and rounded UI.
"""

import concurrent.futures
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import hashlib
import html
from html.parser import HTMLParser
from http.client import IncompleteRead
import json
import math
from pathlib import Path
import re
import socket
import sys
from time import sleep
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from scoring import call_rate, mean_rate, round_rate


MERCHANTS = {
    "mercantile.wordpress.org": "/product/",
    "raspberrypi.dk": "/produkt/",
    "aisynthesis.com": "/product/",
}
MODEL = "moonshotai-kimi-k3.1-pro-trial"
OFFICIAL = Path.home() / "Library/Caches/cerebras-speed-bounty/2026-11-22/official.patch"


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def text_content(message):
    content = message.get("content", [])
    if isinstance(content, str):
        return content
    return "\n".join(c.get("text", "") for c in content
                     if isinstance(c, dict) and c.get("type") == "text")


WEB_URL = re.compile(r'https?://[^\s<>)\]"`\\]+')
MARKDOWN_TOKEN = re.compile(
    r"(?P<code>`+|~{3,})[\s\S]*?(?P=code)|"
    r"""(!?)\[([^\[\]\n]*)\]\(\s*(?:<([^<>\s]+)>|([^\s<>\)]+))(?:[ \t]+(?:"[^"\n]*"|'[^'\n]*'))?\s*\)"""
)


def answer_links(text):
    def visible_urls(fragment):
        return [html.unescape(url.rstrip(".,;!?")) for url in WEB_URL.findall(fragment)]

    urls, misleading, offset = [], False, 0
    for match in MARKDOWN_TOKEN.finditer(text):
        urls.extend(visible_urls(text[offset:match.start()]))
        offset = match.end()
        code, image, label, angled, plain = match.groups()
        if code or image:
            continue
        destination = html.unescape(angled or plain)
        if any(shown != destination for shown in visible_urls(label)):
            misleading = True
        urls.append(destination)
    urls.extend(visible_urls(text[offset:]))
    return urls, misleading


def unwrap_json(value):
    """Decode only JSON or a known OpenClaw external-content envelope."""
    value = value.strip()
    if "\n---\n" in value and ("<<<EXTERNAL_UNTRUSTED_CONTENT" in value
                                     or "[[MARKER_SANITIZED]]" in value):
        value = value.split("\n---\n", 1)[1]
        value = re.split(r"\n(?:<<<END_EXTERNAL_UNTRUSTED_CONTENT|\[\[END_MARKER_SANITIZED\]\])", value, maxsplit=1)[0]
    return json.loads(value)


def merchant(url, product=False):
    try:
        parsed = urlsplit(url)
        return (parsed.scheme == "https" and parsed.hostname in MERCHANTS
                and parsed.username is None and parsed.password is None
                and parsed.port in (None, 443)
                and (not product or (parsed.path.startswith(MERCHANTS[parsed.hostname])
                                    and len(parsed.path.strip("/").split("/")) == 2
                                    and not parsed.query and not parsed.fragment)))
    except (ValueError, TypeError):
        return False


def identity(url):
    parsed = urlsplit(url)
    return parsed.hostname, parsed.path.rstrip("/")


def normalized(value):
    return " ".join(html.unescape(value).casefold().split())


def objects(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from objects(child)
    elif isinstance(value, list):
        for child in value:
            yield from objects(child)


class Page(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.meta, self.canonical, self.titles, self.schemas = {}, None, [], []
        self.heading, self.script = None, None
        self.product_heading = False
        self.sticky_title, self.sticky_price, self.add_to_cart = False, False, False
        self.password_protected = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        classes = attrs.get("class", "").split()
        self.sticky_title |= "storefront-sticky-add-to-cart__content-title" in classes
        self.sticky_price |= "storefront-sticky-add-to-cart__content-price" in classes
        self.add_to_cart |= tag == "a" and "add-to-cart=" in attrs.get("href", "")
        self.password_protected |= "post-password-form" in classes
        if tag == "meta":
            self.meta[attrs.get("property") or attrs.get("name")] = attrs.get("content", "")
        if tag == "link" and "canonical" in attrs.get("rel", "").split():
            self.canonical = attrs.get("href")
        if tag in ("h1", "title"):
            self.heading = []
            if tag == "h1" and "product_title" in attrs.get("class", "").split():
                self.product_heading = True
        if tag == "script" and attrs.get("type") == "application/ld+json":
            self.script = []

    def handle_endtag(self, tag):
        if tag in ("h1", "title") and self.heading is not None:
            self.titles.append("".join(self.heading).strip())
            self.heading = None
        if tag == "script" and self.script is not None:
            try:
                self.schemas.extend(objects(json.loads("".join(self.script))))
            except (ValueError, TypeError):
                pass
            self.script = None

    def handle_data(self, data):
        if self.heading is not None:
            self.heading.append(data)
        if self.script is not None:
            self.script.append(data)


class RetailRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not merchant(newurl, product=True) or urlsplit(newurl).hostname != urlsplit(req.full_url).hostname:
            raise ValueError("redirect outside original merchant product")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def product_retry_delay(error):
    if isinstance(error, HTTPError):
        if error.code not in (502, 503, 504):
            return None
        retry_after = error.headers.get('Retry-After') if error.headers is not None else None
        if retry_after is None:
            return 1
        value = retry_after.strip()
        try:
            if value.isascii() and value.isdigit():
                delay = int(value)
            else:
                retry_at = parsedate_to_datetime(value)
                if retry_at.tzinfo is None:
                    return None
                delay = max(0, (retry_at - datetime.now(timezone.utc)).total_seconds())
        except (ValueError, TypeError, OverflowError):
            return None
        # Leave room for both connection attempts within the validator deadline.
        return delay if delay <= 10 else None
    reason = error.reason if isinstance(error, URLError) else error
    if (isinstance(reason, (ConnectionError, TimeoutError, IncompleteRead))
            or isinstance(reason, socket.gaierror) and reason.errno == socket.EAI_AGAIN):
        return 1
    return None


def read_product_page(request):
    opener = build_opener(RetailRedirect())
    for attempt in range(2):
        try:
            with opener.open(request, timeout=25) as response:
                return (response.read(4_000_001), response.status, response.geturl(),
                        response.headers.get_content_charset() or 'utf-8')
        except (URLError, ConnectionError, TimeoutError, socket.gaierror, IncompleteRead) as error:
            delay = product_retry_delay(error) if attempt == 0 else None
            if delay is None:
                raise
            if isinstance(error, HTTPError):
                error.close()
            sleep(delay)


def verify_product(item):
    result = dict(item, verified=False, reasons=[])
    url, name = item["url"], item["catalog_name"]
    try:
        request = Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept": "text/html",
                                        "Cache-Control": "no-cache"}, method="GET")
        body, status, final_url, charset = read_product_page(request)
        result.update(http=status, final_url=final_url,
                      html_bytes_read=len(body), html_sha256=hashlib.sha256(body).hexdigest(),
                      checked_at=datetime.now(timezone.utc).isoformat())
        if len(body) > 4_000_000 or status != 200:
            raise ValueError("unexpected response status or oversized HTML")
        page = Page()
        page.feed(body.decode(charset, "replace"))
        canonical = urljoin(result["final_url"], page.canonical) if page.canonical else None
        titles = [page.meta.get("og:title", "")] + page.titles
        schema_products = [s for s in page.schemas if "Product" in
                           (s.get("@type") if isinstance(s.get("@type"), list) else [s.get("@type")])]
        matching_schema = [s for s in schema_products if normalized(s.get("name", "")) == normalized(name)]
        title_match = any(normalized(name) in normalized(t) for t in titles)
        result.update(canonical=canonical, merchant=urlsplit(url).hostname,
                      title=next((t for t in titles if t), ""), title_matches_catalog=title_match,
                      product_evidence={"matching_schema_product": bool(matching_schema),
                                        "woocommerce_product_heading": page.product_heading,
                                        "woocommerce_sticky_product_price_and_cart": page.sticky_title and page.sticky_price and page.add_to_cart},
                      password_protected=page.password_protected)
        if not canonical or not merchant(canonical, product=True) or identity(canonical) != identity(url):
            result["reasons"].append("canonical does not identify submitted merchant product")
        if identity(result["final_url"]) != identity(url):
            result["reasons"].append("GET redirected to a different product")
        if not title_match:
            result["reasons"].append("merchant title does not match fetched catalog name")
        if not matching_schema and not page.product_heading and not (page.sticky_title and page.sticky_price and page.add_to_cart):
            result["reasons"].append("no matching Product schema or WooCommerce product commerce evidence")
    except Exception as exc:
        result["reasons"].append("independent GET failed: " + type(exc).__name__)
    result["verified"] = not result["reasons"]
    return result


def catalog_price(product):
    prices = product.get('prices')
    if not isinstance(prices, dict):
        return None
    amount = prices.get('price')
    currency = prices.get('currency_code')
    decimals = prices.get('currency_minor_unit')
    if (type(amount) in (str,int) and re.fullmatch(r'[0-9]{1,12}',str(amount))
            and isinstance(currency,str) and re.fullmatch(r'[A-Z]{3}',currency)
            and type(decimals) is int and 0 <= decimals <= 4):
        return {'minor_units':int(amount),'currency':currency,'decimals':decimals}
    return None


def validate(data):
    run_id = data["id"]
    messages = data["history"]["messages"]
    started, ended = data.get("startedWall"), data.get("ended", {})
    reasons, calls, sources, catalog, pending = [], [], [], {}, {}
    run_messages = [(i, m) for i, m in enumerate(messages)
                    if m.get("__openclaw", {}).get("runId") == run_id]
    assistants = [(i, m) for i, m in run_messages if m.get("role") == "assistant"]
    if ended.get("terminal") != "final":
        reasons.append("run has no successful final terminal event")
    if not assistants or assistants[-1][1].get("stopReason") != "stop" or not text_content(assistants[-1][1]).strip():
        reasons.append("run has no successful final assistant text")
    final_index, final = assistants[-1] if assistants else (-1, {})
    for index, message in assistants:
        if message.get("provider") != "cerebras" or message.get("model") != MODEL:
            reasons.append("non-Cerebras Kimi trial assistant call")
        if not message.get("responseId") or message.get("stopReason") not in ("stop", "toolUse"):
            reasons.append("assistant call missing response identity or has unsuccessful stop")
        server = message.get("serverGeneration", {})
        ms, tokens = server.get("completionMs"), server.get("outputTokens")
        if not finite(ms) or ms <= 0 or not finite(tokens) or tokens < 1:
            reasons.append("assistant call missing valid serverGeneration")
        else:
            calls.append({"message_index": index, "response_id": message.get("responseId"),
                          "completionMs": ms, "outputTokens": tokens,
                          "tokensPerSecond": call_rate(tokens, ms), "stopReason": message.get("stopReason")})
        for part in message.get("content", []) if isinstance(message.get("content"), list) else []:
            if part.get("type") == "toolCall":
                args = part.get("arguments", {})
                if part.get("name") == "tool_call" and args.get("id") in ("openclaw:core:web_fetch", "web_fetch"):
                    short_alias = args["id"] == "web_fetch"
                    pending[part["id"]] = (index, args.get("args", {}).get("url"), short_alias)
                elif part.get("name") == "web_fetch":
                    pending[part["id"]] = (index, args.get("url"), False)
    for index, message in run_messages:
        if message.get("role") != "toolResult" or message.get("toolCallId") not in pending:
            continue
        call_index, requested_url, short_alias = pending[message["toolCallId"]]
        source = {"tool_call_id": message["toolCallId"], "url": requested_url, "accepted": False, "reasons": []}
        sources.append(source)
        try:
            if message.get("isError") is not False or not call_index < index < final_index:
                raise ValueError("unsuccessful or out-of-order retail tool result")
            if message.get("__openclaw", {}).get("resultContentSource") not in (None, "network"):
                raise ValueError("retail tool result was not fetched from network")
            payload = message.get("details") or unwrap_json(text_content(message))
            if short_alias:
                tool = payload.get("tool", {})
                if (not isinstance(tool, dict) or tool.get("id") != "openclaw:core:web_fetch"
                        or tool.get("source") != "openclaw"):
                    raise ValueError("short tool alias lacks a successful canonical OpenClaw web_fetch result")
            if "tool" in payload:
                if payload["tool"].get("id") != "openclaw:core:web_fetch":
                    raise ValueError("unexpected wrapped tool identity")
                wrapped = payload["result"]
                if wrapped.get("isError"):
                    raise ValueError("wrapped tool failed")
                payload = wrapped.get("details") or unwrap_json(text_content(wrapped))
            source.update(status=payload.get("status"), fetched_at=payload.get("fetchedAt"), cached=payload.get("cached", False))
            if payload.get("status") != 200 or payload.get("cached") or payload.get("truncated"):
                raise ValueError("retail payload unsuccessful, cached, or truncated")
            if not merchant(requested_url) or payload.get("url") != requested_url:
                raise ValueError("retail payload URL does not match allowed tool request")
            if not merchant(payload.get("finalUrl")) or urlsplit(payload["finalUrl"]).hostname != urlsplit(requested_url).hostname:
                raise ValueError("retail fetch final URL leaves original merchant")
            fetched_ms = datetime.fromisoformat(payload["fetchedAt"].replace("Z", "+00:00")).timestamp() * 1000
            if not finite(started) or not finite(ended.get("time")) or not started <= fetched_ms <= ended["time"]:
                raise ValueError("retail payload was not fetched during this run")
            products = unwrap_json(payload["text"])
            if not isinstance(products, list):
                raise ValueError("retail payload is not a product catalog array")
            accepted = []
            for product in products:
                if (isinstance(product, dict) and isinstance(product.get("name"), str) and product["name"].strip()
                        and merchant(product.get("permalink"), product=True)
                        and urlsplit(product["permalink"]).hostname == urlsplit(requested_url).hostname):
                    catalog[product["permalink"]] = {"catalog_name": html.unescape(product["name"]),
                                                      "source_tool_call_id": message["toolCallId"]}
                    price = catalog_price(product)
                    if price is not None:
                        catalog[product["permalink"]]["catalog_price"] = price
                    accepted.append(product["permalink"])
            if not accepted:
                raise ValueError("no real merchant product records in retail payload")
            source.update(accepted=True, products=accepted)
        except (ValueError, TypeError, KeyError, AttributeError) as exc:
            source["reasons"].append(str(exc) if type(exc) is ValueError and not isinstance(exc, json.JSONDecodeError)
                                      else "malformed retail tool payload")
    urls, misleading = answer_links(text_content(final))
    if misleading:
        reasons.append("visible product URL in link label differs from its destination")
    if len(urls) != 5 or len({identity(u) for u in urls if merchant(u, product=True)}) != 5:
        reasons.append("final must contain exactly five distinct product links")
    candidates = []
    for url in dict.fromkeys(urls):
        if not merchant(url, product=True):
            reasons.append("final contains unsupported merchant or non-product URL")
        elif url not in catalog:
            reasons.append("final product absent from same-run fresh successful retail payload: " + url)
        else:
            candidates.append(dict(url=url, **catalog[url]))
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
        products = list(pool.map(verify_product, candidates))
    if len(products) != 5 or not all(p["verified"] for p in products):
        reasons.append("five independent merchant product GET verifications did not pass")
    rates = [c["tokensPerSecond"] for c in calls]
    mean = mean_rate(rates) if rates else None
    rounded = round_rate(mean) if mean is not None else None
    target = mean is not None and mean > 2000 and rounded > 2000
    valid = not reasons
    return {"run_id": run_id, "valid": valid, "status": "passed" if valid and target else "valid_below_target" if valid else "rejected",
            "target_met": valid and target, "reject_reasons": list(dict.fromkeys(reasons)),
            "target_reasons": [] if target else ["exact mean and rounded UI must both be strictly greater than 2000 TPS"],
            "score": {"mean_exact_tps": mean, "ui_rounded_tps": rounded,
                      "ui_display": (f"{rounded:,}" if mean >= 100 else f"{mean:.1f}") if mean is not None else None,
                      "p90_tps": sorted(rates)[max(0, math.ceil(.9 * len(rates)) - 1)] if rates else None,
                      "output_tokens": sum(c["outputTokens"] for c in calls),
                      "generation_ms": sum(c["completionMs"] for c in calls), "call_count": len(calls),
                      "formula": "arithmetic mean of outputTokens / (completionMs / 1000)",
                      "official_patch": str(OFFICIAL),
                      "official_patch_sha256": hashlib.sha256(OFFICIAL.read_bytes()).hexdigest() if OFFICIAL.is_file() else None},
            "calls": calls, "retail_sources": sources, "products": products,
            "final_text": text_content(final)}


def main():
    try:
        if len(sys.argv) != 2:
            raise ValueError("usage: validate.py RUN.json")
        path = Path(sys.argv[1])
        raw = path.read_bytes()
        result = validate(json.loads(raw))
        result.update(input_path=str(path.resolve()), input_sha256=hashlib.sha256(raw).hexdigest())
        code = 0 if result["valid"] else 1
    except Exception as exc:
        result = {"valid": False, "status": "error", "reject_reasons": ["validator input/error: " + type(exc).__name__]}
        code = 2
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    return code


if __name__ == "__main__":
    sys.exit(main())
