"""Export a disclosure-safe provider-error summary from planned catalog sessions (Python 3.14+)."""

import argparse
from compression import zstd
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sqlite3


def classify(message):
    text = str(message.get("errorMessage") or "")
    code = message.get("errorCode")
    category = message.get("errorType")
    if re.match(r"^429\b", text) or category == "too_many_requests_error" or code == "queue_exceeded":
        if "experiencing high traffic" in text.lower() or code == "queue_exceeded":
            return 429, "High traffic (provider queue exceeded)" if code == "queue_exceeded" else "High traffic"
        return 429, "Provider rate limit"
    # Always use fixed vocabulary. Provider errors can contain request or credential details.
    if re.match(r"^(401|403)\b", text) or category in {"authentication_error", "permission_error"}:
        return None, "Authentication or permission error"
    if re.match(r"^5\d\d\b", text):
        return None, "Provider server error"
    return None, "Other provider error"


def summarize(state, plan):
    database = (state / "agents/main/agent/openclaw-agent.sqlite").resolve()
    connection = sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)
    errors = []
    counts = []
    try:
        connection.execute("PRAGMA query_only=1")
        connection.execute("BEGIN")
        for trial in plan["trials"]:
            key, label = trial["sessionKey"], trial["label"]
            if (not re.fullmatch(r"agent:main:shop-catalog-[0-9a-f-]{36}", key)
                    or not re.fullmatch(r"catalog-[0-9]+", label)):
                raise ValueError("Unexpected catalog session key or trial label")
            node = connection.execute("SELECT current_session_id FROM session_nodes WHERE session_key=?", (key,)).fetchone()
            previous = len(errors)
            call_number = 0
            if node:
                rows = connection.execute(
                    "SELECT event_json,event_zstd,created_at FROM transcript_events WHERE session_id=? ORDER BY seq",
                    (node[0],),
                )
                for plain, compressed, created_at in rows:
                    event = json.loads(plain or zstd.decompress(compressed))
                    message = event.get("message") or {}
                    if message.get("role") != "assistant" or message.get("provider") != "cerebras":
                        continue
                    call_number += 1
                    if message.get("stopReason") != "error":
                        continue
                    status, reason = classify(message)
                    timestamp = datetime.fromtimestamp(created_at / 1000, timezone.utc).isoformat(timespec="milliseconds")
                    errors.append(dict(label=label, sessionKey=key, timestamp=timestamp, call=call_number,
                                       status=status, reason=reason))
            counts.append(dict(label=label, sessionKey=key, sessionObserved=bool(node),
                               errorCount=len(errors) - previous))
    finally:
        connection.close()
    return dict(count=len(errors), count429=sum(error["status"] == 429 for error in errors),
                trials=counts, errors=errors)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--out", type=Path, help="New JSON file. Defaults to stdout.")
    args = parser.parse_args()
    report = summarize(args.state, json.loads(args.plan.read_text()))
    output = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.out:
        with args.out.open("x", encoding="utf-8") as file:
            file.write(output)
    else:
        print(output, end="")


if __name__ == "__main__":
    main()
