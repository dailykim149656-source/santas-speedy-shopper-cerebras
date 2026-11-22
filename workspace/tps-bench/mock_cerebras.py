#!/usr/bin/env python3
"""리허설용 Cerebras Chat Completions 모의 서버 (표준 라이브러리만 사용).

실제 모델 접근 없이 tps_bench.py의 전체 흐름(스트리밍, 재시도, 기록, 집계)을 점검한다.
응답 수치는 가짜이며 실제 Kimi·Cerebras 성능과 무관하다.

  python3 mock_cerebras.py --port 8765 --fail-every 7
  python3 tps_bench.py run --base-url http://127.0.0.1:8765/v1 --reps 1
"""
from __future__ import annotations

import argparse
import json
import random
import re
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

FAKE_TPS = {"P1": 2400, "P2": 2200, "P3": 2000, "P4": 1800, "OTHER": 1500}
REASONING_TOKENS = {"low": 20, "medium": 60, "high": 120, "max": 200}


def answer_for(prompt: str) -> tuple[str, str]:
    if "arithmetic identities" in prompt:
        return "P1", "\n".join(f"{n} + {n} = {2*n}\n{n} × 2 = {2*n}" for n in range(1, 201))
    if "calc_001" in prompt:
        return "P2", "\n\n".join(f"def calc_{n:03d}(x):\n    return (x + {n}) * 2" for n in range(1, 101))
    if "JSONL" in prompt:
        return "P3", "\n".join(json.dumps({"id": n, "status": "ok", "value": 100}, separators=(",", ":")) for n in range(1, 201))
    if "ALPHA BETA GAMMA DELTA" in prompt:
        return "P4", "\n".join(["ALPHA BETA GAMMA DELTA"] * 300)
    if "Reply with OK" in prompt:
        return "OTHER", "OK"
    return "OTHER", "This is a mock answer. " * 50


class Handler(BaseHTTPRequestHandler):
    counter = 0
    fail_every = 0

    def log_message(self, fmt, *args):  # 조용히
        pass

    def _json(self, code, obj, headers=None):
        data = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        if not self.path.endswith("/chat/completions"):
            return self._json(404, {"error": {"message": "not found"}})
        if not self.headers.get("Authorization"):
            return self._json(401, {"error": {"message": "missing key"}})
        Handler.counter += 1
        if Handler.fail_every and Handler.counter % Handler.fail_every == 0:
            return self._json(429, {"error": {"message": "mock rate limit", "type": "too_many_requests"}}, {"Retry-After": "1"})
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
        prompt = body["messages"][-1]["content"]
        pid, text = answer_for(prompt)
        effort = body.get("reasoning_effort")
        cap = int(body.get("max_completion_tokens") or body.get("max_tokens") or 4096)

        r_tok = [f"think{i} " for i in range(REASONING_TOKENS.get(effort, 0))]
        c_tok = re.findall(r"\S+\s*|\s+", text)
        finish = "stop"
        if len(r_tok) + len(c_tok) > cap:
            keep = max(cap - len(r_tok), 0)
            r_tok = r_tok[:cap]
            c_tok = c_tok[:keep]
            finish = "length"
        n = len(r_tok) + len(c_tok)
        tps = FAKE_TPS[pid] * random.uniform(0.85, 1.15)
        queue, prefill = random.uniform(0.001, 0.02), 0.002 + len(prompt) / 4 / 50000
        completion_time = n / tps
        usage = {
            "prompt_tokens": len(prompt) // 4,
            "completion_tokens": n,
            "total_tokens": len(prompt) // 4 + n,
            "completion_tokens_details": {"reasoning_tokens": len(r_tok)},
            "prompt_tokens_details": {"cached_tokens": 0},
        }
        time_info = {"queue_time": queue, "prompt_time": prefill, "completion_time": completion_time,
                     "total_time": queue + prefill + completion_time, "created": time.time()}
        rid = f"chatcmpl-mock-{Handler.counter}"
        model = body.get("model")

        if not body.get("stream"):
            time.sleep(queue + prefill + completion_time)
            msg = {"role": "assistant", "content": "".join(c_tok)}
            if r_tok:
                msg["reasoning"] = "".join(r_tok)
            return self._json(200, {"id": rid, "object": "chat.completion", "model": model,
                                    "choices": [{"index": 0, "message": msg, "finish_reason": finish}],
                                    "usage": usage, "time_info": time_info})

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()

        def emit(obj):
            self.wfile.write(b"data: " + json.dumps(obj).encode() + b"\n\n")
            self.wfile.flush()

        time.sleep(queue + prefill)
        emit({"id": rid, "model": model, "choices": [{"index": 0, "delta": {"role": "assistant"}}]})
        step = 8
        for key, toks in (("reasoning", r_tok), ("content", c_tok)):
            for i in range(0, len(toks), step):
                time.sleep(len(toks[i:i + step]) / tps)
                emit({"id": rid, "model": model, "choices": [{"index": 0, "delta": {key: "".join(toks[i:i + step])}}]})
        emit({"id": rid, "model": model, "choices": [{"index": 0, "delta": {}, "finish_reason": finish}],
              "usage": usage, "time_info": time_info})
        self.wfile.write(b"data: [DONE]\n\n")
        self.wfile.flush()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--fail-every", type=int, default=0, help="N번째 요청마다 429 반환 (재시도 점검용)")
    a = ap.parse_args()
    Handler.fail_every = a.fail_every
    srv = ThreadingHTTPServer(("127.0.0.1", a.port), Handler)
    print(f"mock Cerebras on http://127.0.0.1:{a.port}/v1 (fail_every={a.fail_every})", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
