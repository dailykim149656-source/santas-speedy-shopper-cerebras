#!/usr/bin/env python3
"""Kimi K3.1 Pro on Cerebras — TPS 측정 도구 (표준 라이브러리만 사용).

하위 명령
  check      짧은 요청으로 접근 여부와 응답에 오는 usage/time_info 필드를 확인
  run        프롬프트 × 추론 강도 × 모드 × 반복 계획을 섞어서 한 건씩 실행하고 모두 기록
  summarize  하나 이상의 run 결과를 조건별 중앙값·최고값 표로 집계

경로(--path)
  direct         Cerebras API 직접 호출. 서버 time_info로 decode TPS 계산 (주 측정용)
  openclaw-http  OpenClaw 게이트웨이의 /v1/chat/completions 경유 (에이전트 실행, 스트리밍 시각 측정)
  openclaw-cli   `openclaw infer model run --json` 경유 (CLI 기동 시간 포함, 규정 충족 증빙용)
"""
from __future__ import annotations

import argparse
import collections
import csv
import datetime as dt
import hashlib
import json
import os
import random
import re
import shutil
import statistics
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

VERSION = "0.1.0"
HERE = Path(__file__).resolve().parent
DEFAULT_MODEL = "moonshotai-kimi-k3.1-pro-trial"
DEFAULT_BASE_URL = "https://api.cerebras.ai/v1"
DEFAULT_GATEWAY_URL = "http://127.0.0.1:18789/v1"
KST = dt.timezone(dt.timedelta(hours=9))
CHECK_PROMPT = {
    "id": "CHECK",
    "version": "v1",
    "label": "access check",
    "validator": {"type": "none"},
    "text": "Reply with OK.",
}
SECRET_RE = re.compile(r"(csk-|sk-|Bearer\s+)[A-Za-z0-9._\-]{6,}")


# ───────────────────────────── 공통 유틸 ─────────────────────────────

def now_kst() -> str:
    return dt.datetime.now(KST).isoformat(timespec="milliseconds")


def log(msg: str) -> None:
    print(f"[{dt.datetime.now(KST).strftime('%H:%M:%S')}] {msg}", file=sys.stderr, flush=True)


def redact(text: str) -> str:
    return SECRET_RE.sub(lambda m: m.group(1) + "***", text or "")


def sha12(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


def fnum(x, digits=1):
    if x is None:
        return "-"
    if isinstance(x, float):
        return f"{x:.{digits}f}"
    return str(x)


def safe_div(a, b):
    try:
        if a is None or b is None or b <= 0:
            return None
        return a / b
    except TypeError:
        return None


def load_prompts(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    return {p["id"]: p for p in data["prompts"]}


# ───────────────────────────── 출력 완성도 검사 ─────────────────────────────

def strip_fences(text: str) -> str:
    return "\n".join(l for l in text.splitlines() if not l.strip().startswith("```"))


def validate(spec: dict, content: str) -> tuple[float | None, str]:
    """(완성도 0~1, 설명)을 돌려준다. 검사가 없는 프롬프트는 (None, '')."""
    kind = spec.get("type", "none")
    text = strip_fences(content or "")
    n = int(spec.get("n", 0) or 0)
    if kind == "none" or n <= 0:
        return None, ""
    if kind == "arith_pairs":
        add, mul = set(), set()
        for a, b, r in re.findall(r"(\d+)\s*\+\s*(\d+)\s*=\s*(\d+)", text):
            if a == b and int(r) == 2 * int(a):
                add.add(int(a))
        for a, r in re.findall(r"(\d+)\s*[×xX*]\s*2\s*=\s*(\d+)", text):
            if int(r) == 2 * int(a):
                mul.add(int(a))
        good = sum(1 for k in range(1, n + 1) if k in add and k in mul)
        return good / n, f"{good}/{n} n값의 두 등식 정답"
    if kind == "py_calc_funcs":
        pat = re.compile(
            r"def\s+calc_(\d{3})\s*\(\s*x\s*(?::\s*\w+)?\s*\)[^:\n]*:\s*\n"
            r"(?:\s*(?:\"\"\"|''').*?(?:\"\"\"|''')\s*\n)?"
            r"\s*return\s*\(\s*x\s*\+\s*(\d+)\s*\)\s*\*\s*2",
            re.S,
        )
        good = {int(a) for a, k in pat.findall(text) if int(a) == int(k) and 1 <= int(a) <= n}
        return len(good) / n, f"{len(good)}/{n} 함수 정답"
    if kind == "jsonl_records":
        ids = set()
        for line in text.splitlines():
            line = line.strip()
            if not line.startswith("{"):
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if (
                isinstance(obj, dict)
                and set(obj) == {"id", "status", "value"}
                and obj["status"] == "ok"
                and obj["value"] == 100
                and isinstance(obj["id"], int)
                and 1 <= obj["id"] <= n
            ):
                ids.add(obj["id"])
        return len(ids) / n, f"{len(ids)}/{n} 레코드 정답"
    if kind == "repeat_seq":
        seq = spec.get("seq", "")
        count = re.sub(r"\s+", " ", text).count(seq)
        return min(count / n, 1.0), f"{count}/{n} 반복"
    return None, f"알 수 없는 검사 {kind}"


# ───────────────────────────── 요청 속도 조절 ─────────────────────────────

class Pacer:
    """분당 요청 수(RPM)와 분당 토큰 수(TPM) 한도 안에서 요청 간격을 조절한다.

    서버가 max_completion_tokens를 미리 차감하는지 확인되지 않았으므로
    (입력 추정 + 출력 상한)을 보수적으로 예약한다.
    """

    def __init__(self, rpm: int, tpm: int, gap: float):
        self.rpm, self.tpm, self.gap = rpm, tpm, gap
        self.events: collections.deque = collections.deque()
        self.last_end: float | None = None

    def wait(self, reserve: int) -> None:
        if reserve > self.tpm:
            log(f"경고: 한 요청 예약량 {reserve}이 TPM 예산 {self.tpm}보다 큽니다. 직전 1분이 비면 보냅니다.")
        while True:
            now = time.monotonic()
            while self.events and now - self.events[0][0] >= 60:
                self.events.popleft()
            used = sum(t for _, t in self.events)
            fits_tpm = used + reserve <= self.tpm or not self.events
            if len(self.events) < self.rpm and fits_tpm:
                break
            pause = 60 - (now - self.events[0][0]) + 0.05
            log(f"속도 조절: {pause:.1f}초 대기 (최근 1분 {len(self.events)}건, 예약 {used}+{reserve}/{self.tpm} 토큰)")
            time.sleep(max(pause, 0.05))
        if self.last_end is not None and self.gap > 0:
            rest = self.gap - (time.monotonic() - self.last_end)
            if rest > 0:
                time.sleep(rest)
        self.events.append((time.monotonic(), reserve))

    def done(self) -> None:
        self.last_end = time.monotonic()


# ───────────────────────────── 경로별 호출 ─────────────────────────────

def gateway_token() -> str | None:
    tok = os.environ.get("OPENCLAW_GATEWAY_TOKEN")
    if tok:
        return tok
    cfg = Path.home() / ".openclaw" / "openclaw.json"
    try:
        val = json.loads(cfg.read_text())["gateway"]["auth"]["token"]
        return val if isinstance(val, str) and val else None
    except Exception:
        return None


def build_body(cfg, model_field: str, prompt_text: str, effort: str, stream: bool) -> dict:
    body = {
        "model": model_field,
        "messages": [{"role": "user", "content": prompt_text}],
        "max_completion_tokens": cfg.max_tokens,
    }
    if effort != "omit":
        body["reasoning_effort"] = effort
    if stream:
        body["stream"] = True
        if not cfg.no_stream_usage:
            body["stream_options"] = {"include_usage": True}
    body.update(cfg.extra_body)
    return body


def http_request(url: str, headers: dict, body: dict, stream: bool, timeout: float) -> dict:
    """HTTP 호출 1회. 클라이언트 시각과 응답 필드를 모아 dict로 돌려준다."""
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Accept": "text/event-stream" if stream else "application/json",
            "User-Agent": f"tps-bench/{VERSION}",
            **headers,
        },
    )
    out = {
        "http_status": None, "error": None, "retry_after": None,
        "response_id": None, "model_returned": None, "finish_reason": None,
        "usage": None, "time_info": None, "content": "", "reasoning": "",
        "n_events": 0, "n_token_events": 0,
        "t_first_any": None, "t_first_content": None, "t_last": None,
        "raw": None,
    }
    t0 = time.perf_counter()
    try:
        resp = urllib.request.urlopen(req, timeout=timeout)
    except urllib.error.HTTPError as e:
        out["http_status"] = e.code
        out["retry_after"] = e.headers.get("Retry-After") if e.headers else None
        try:
            detail = e.read().decode("utf-8", "replace")[:2000]
        except Exception:
            detail = ""
        out["error"] = redact(f"HTTP {e.code}: {detail}")
        out["wall_s"] = time.perf_counter() - t0
        return out
    except Exception as e:  # 연결 실패, 타임아웃 등
        out["error"] = redact(f"{type(e).__name__}: {e}")
        out["wall_s"] = time.perf_counter() - t0
        return out

    with resp:
        out["http_status"] = resp.status
        if not stream:
            raw = resp.read()
            t_end = time.perf_counter()
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                out["error"] = f"JSON 파싱 실패: {raw[:300]!r}"
                out["wall_s"] = t_end - t0
                return out
            out["raw"] = payload
            out["response_id"] = payload.get("id")
            out["model_returned"] = payload.get("model")
            out["usage"] = payload.get("usage")
            out["time_info"] = payload.get("time_info")
            ch = (payload.get("choices") or [{}])[0]
            msg = ch.get("message") or {}
            out["content"] = msg.get("content") or ""
            out["reasoning"] = msg.get("reasoning") or msg.get("reasoning_content") or ""
            out["finish_reason"] = ch.get("finish_reason")
            if payload.get("error"):
                out["error"] = redact(json.dumps(payload["error"])[:2000])
            out["wall_s"] = t_end - t0
            return out

        content, reasoning, last_events = [], [], collections.deque(maxlen=3)
        for raw_line in resp:
            line = raw_line.decode("utf-8", "replace").strip()
            if not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if data == "[DONE]":
                break
            now = time.perf_counter()
            try:
                ev = json.loads(data)
            except json.JSONDecodeError:
                continue
            out["n_events"] += 1
            last_events.append(ev)
            if ev.get("error"):
                out["error"] = redact(json.dumps(ev["error"])[:2000])
            out["response_id"] = ev.get("id") or out["response_id"]
            out["model_returned"] = ev.get("model") or out["model_returned"]
            if ev.get("usage"):
                out["usage"] = ev["usage"]
            if ev.get("time_info"):
                out["time_info"] = ev["time_info"]
            for ch in ev.get("choices") or []:
                d = ch.get("delta") or {}
                c = d.get("content") or ""
                r = d.get("reasoning") or d.get("reasoning_content") or ""
                if c or r:
                    out["n_token_events"] += 1
                    if out["t_first_any"] is None:
                        out["t_first_any"] = now - t0
                    out["t_last"] = now - t0
                if c:
                    if out["t_first_content"] is None:
                        out["t_first_content"] = now - t0
                    content.append(c)
                if r:
                    reasoning.append(r)
                if ch.get("finish_reason"):
                    out["finish_reason"] = ch["finish_reason"]
        out["wall_s"] = time.perf_counter() - t0
        out["content"] = "".join(content)
        out["reasoning"] = "".join(reasoning)
        out["raw"] = {"last_events": list(last_events)}
        return out


def call_http(cfg, prompt: dict, effort: str, mode: str) -> dict:
    stream = mode == "stream"
    if cfg.path == "direct":
        key = os.environ.get(cfg.api_key_env) or ("mock" if "127.0.0.1" in cfg.base_url or "localhost" in cfg.base_url else None)
        if not key:
            raise SystemExit(f"{cfg.api_key_env} 환경변수가 없습니다. README의 '키 준비'를 보세요.")
        url = cfg.base_url.rstrip("/") + "/chat/completions"
        headers = {"Authorization": f"Bearer {key}"}
        body = build_body(cfg, cfg.model, prompt["text"], effort, stream)
    else:  # openclaw-http
        tok = gateway_token()
        if not tok:
            raise SystemExit("OpenClaw 게이트웨이 토큰을 찾지 못했습니다. OPENCLAW_GATEWAY_TOKEN을 설정하세요.")
        url = cfg.gateway_url.rstrip("/") + "/chat/completions"
        headers = {"Authorization": f"Bearer {tok}", "x-openclaw-model": cfg.openclaw_model}
        body = build_body(cfg, cfg.openclaw_agent, prompt["text"], effort, stream)
    res = http_request(url, headers, body, stream, cfg.timeout)
    if cfg.path == "openclaw-http" and res["http_status"] == 404:
        res["error"] += " (게이트웨이 chatCompletions 엔드포인트가 꺼져 있을 수 있음. README 참고)"
    return res


def call_openclaw_cli(cfg, prompt: dict, effort: str, mode: str) -> dict:
    out = {
        "http_status": None, "error": None, "retry_after": None,
        "response_id": None, "model_returned": None, "finish_reason": None,
        "usage": None, "time_info": None, "content": "", "reasoning": "",
        "n_events": 0, "n_token_events": 0,
        "t_first_any": None, "t_first_content": None, "t_last": None, "raw": None,
    }
    exe = cfg.openclaw_bin or shutil.which("openclaw")
    if not exe:
        raise SystemExit("openclaw 실행 파일을 찾지 못했습니다. --openclaw-bin으로 지정하세요.")
    cmd = [exe, "infer", "model", "run", "--gateway", "--model", cfg.openclaw_model,
           "--prompt", prompt["text"], "--json"]
    if effort != "omit":
        cmd += ["--thinking", effort]
    t0 = time.perf_counter()
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=cfg.timeout)
    except subprocess.TimeoutExpired:
        out["error"] = f"openclaw CLI가 {cfg.timeout}초 안에 끝나지 않음"
        out["wall_s"] = time.perf_counter() - t0
        return out
    out["wall_s"] = time.perf_counter() - t0
    stdout = p.stdout or ""
    try:
        payload = json.loads(stdout[stdout.index("{"):])
    except (ValueError, json.JSONDecodeError):
        out["error"] = redact(f"exit {p.returncode}: {(p.stderr or stdout)[-1500:]}")
        return out
    out["raw"] = payload
    out["model_returned"] = f"{payload.get('provider')}/{payload.get('model')}"
    if not payload.get("ok"):
        out["error"] = redact(json.dumps(payload.get("error") or payload)[:2000])
    lcu = payload.get("lastCallUsage") or payload.get("usage") or {}
    out["usage"] = {
        "prompt_tokens": lcu.get("input"),
        "completion_tokens": lcu.get("output"),
        "total_tokens": lcu.get("total"),
        "completion_tokens_details": {"reasoning_tokens": lcu.get("reasoningTokens")},
        "prompt_tokens_details": {"cached_tokens": lcu.get("cacheRead")},
        "_source": "openclaw lastCallUsage",
    }
    out["content"] = "".join((o or {}).get("text") or "" for o in payload.get("outputs") or [])
    return out


def execute_one(cfg, prompt: dict, effort: str, mode: str, pacer: Pacer) -> tuple[dict, dict]:
    """재시도 포함 한 계획 항목을 실행하고 (기록 한 줄, 원문 저장용 dict)를 돌려준다."""
    reserve = len(prompt["text"]) // 3 + 50 + cfg.max_tokens
    attempts, waits = 0, []
    while True:
        attempts += 1
        pacer.wait(reserve)
        ts = now_kst()
        if cfg.path == "openclaw-cli":
            res = call_openclaw_cli(cfg, prompt, effort, mode)
        else:
            res = call_http(cfg, prompt, effort, mode)
        pacer.done()
        retryable = res["http_status"] in (429, 500, 502, 503, 504) or (
            res["http_status"] is None and res["error"] and cfg.path != "openclaw-cli"
        )
        if res["error"] and retryable and attempts <= cfg.max_retries:
            try:
                wait = float(res["retry_after"]) if res["retry_after"] else None
            except ValueError:
                wait = None
            wait = wait if wait is not None else min(60.0, 5.0 * 2 ** (attempts - 1))
            waits.append(round(wait, 1))
            log(f"  재시도 {attempts}/{cfg.max_retries}: {res['error'][:120]} → {wait:.0f}초 뒤")
            time.sleep(wait)
            continue
        break

    usage = res["usage"] or {}
    ti = res["time_info"] or {}
    ct = usage.get("completion_tokens")
    rt = ((usage.get("completion_tokens_details") or {}).get("reasoning_tokens"))
    cached = ((usage.get("prompt_tokens_details") or {}).get("cached_tokens"))
    completeness, comp_note = validate(prompt.get("validator", {}), res["content"])
    stream_span = None
    if res["t_first_any"] is not None and res["t_last"] is not None:
        stream_span = res["t_last"] - res["t_first_any"]
    rec = {
        "ts_start": ts,
        "path": cfg.path,
        "mode": mode,
        "model_requested": cfg.model if cfg.path == "direct" else cfg.openclaw_model,
        "model_returned": res["model_returned"],
        "prompt_id": prompt["id"],
        "prompt_version": prompt["version"],
        "prompt_sha": sha12(prompt["text"]),
        "reasoning_effort": effort,
        "max_completion_tokens": cfg.max_tokens,
        "extra_body": cfg.extra_body or None,
        "http_status": res["http_status"],
        "attempts": attempts,
        "retry_waits_s": waits or None,
        "error": res["error"],
        "response_id": res["response_id"],
        "finish_reason": res["finish_reason"],
        "prompt_tokens": usage.get("prompt_tokens"),
        "completion_tokens": ct,
        "reasoning_tokens": rt,
        "cached_tokens": cached,
        "total_tokens": usage.get("total_tokens"),
        "queue_time": ti.get("queue_time"),
        "prompt_time": ti.get("prompt_time"),
        "completion_time": ti.get("completion_time"),
        "total_time": ti.get("total_time"),
        "client_wall_s": round(res["wall_s"], 4),
        "client_ttft_s": res["t_first_any"],
        "client_ttft_content_s": res["t_first_content"],
        "client_stream_span_s": stream_span,
        "n_events": res["n_events"] or None,
        "n_token_events": res["n_token_events"] or None,
        "content_chars": len(res["content"]),
        "reasoning_chars": len(res["reasoning"]),
        "completeness": None if completeness is None else round(completeness, 4),
        "completeness_note": comp_note or None,
        # 지표 — 공식 산식이 공지되면 summarize에서 그 기준을 우선한다
        "server_decode_tps": safe_div(ct, ti.get("completion_time")),
        "server_total_tps": safe_div(ct, ti.get("total_time")),
        "client_wall_tps": safe_div(ct, res["wall_s"]),
        "stream_tps": safe_div((ct - 1) if ct else None, stream_span),
        "usage_raw": res["usage"],
        "time_info_raw": res["time_info"],
    }
    detail = {"content": res["content"], "reasoning": res["reasoning"], "raw": res["raw"]}
    return rec, detail


# ───────────────────────────── run / check ─────────────────────────────

def make_plan(prompt_ids, efforts, modes, reps, seed) -> list[dict]:
    plan = [
        {"prompt_id": p, "effort": e, "mode": m, "rep": r}
        for p in prompt_ids for e in efforts for m in modes for r in range(1, reps + 1)
    ]
    random.Random(seed).shuffle(plan)
    for i, item in enumerate(plan, 1):
        item["seq"] = i
    return plan


def read_records(run_dir: Path) -> list[dict]:
    f = run_dir / "requests.jsonl"
    if not f.exists():
        return []
    rows = []
    for line in f.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return rows


def progress_line(i, total, item, rec) -> str:
    if rec["error"]:
        return f"[{i}/{total}] {item['prompt_id']} {item['effort']} {item['mode']} → 오류: {rec['error'][:140]}"
    return (
        f"[{i}/{total}] {item['prompt_id']} {item['effort']} {item['mode']} → "
        f"{fnum(rec['completion_tokens'])} tok (추론 {fnum(rec['reasoning_tokens'])}), "
        f"서버 {fnum(rec['server_decode_tps'])} TPS, 스트림 {fnum(rec['stream_tps'])}, "
        f"벽시계 {fnum(rec['client_wall_tps'])}, finish={rec['finish_reason']}, "
        f"완성도 {fnum(rec['completeness'], 2)}"
    )


def apply_meta_args(args, meta_args: dict) -> None:
    for k, v in meta_args.items():
        if k not in ("cmd", "resume", "func"):
            setattr(args, k, v)


def cmd_run(args) -> int:
    if args.resume:
        run_dir = Path(args.resume)
        meta = json.loads((run_dir / "run_meta.json").read_text(encoding="utf-8"))
        apply_meta_args(args, meta["args"])
        plan = meta["plan"]
        prompts = meta["prompts"]
        done = {r["seq"] for r in read_records(run_dir) if not r.get("error")}
        log(f"이어서 실행: {run_dir} (완료 {len(done)}/{len(plan)})")
    else:
        all_prompts = load_prompts(Path(args.prompts_file))
        ids = [p.strip() for p in args.prompts.split(",") if p.strip()]
        missing = [p for p in ids if p not in all_prompts]
        if missing:
            raise SystemExit(f"prompts.json에 없는 프롬프트: {missing}")
        prompts = {p: all_prompts[p] for p in ids}
        efforts = [e.strip() for e in args.efforts.split(",") if e.strip()]
        modes = [m.strip() for m in args.modes.split(",") if m.strip()]
        if args.path == "openclaw-cli":
            modes = ["cli"]
        seed = args.seed if args.seed is not None else int(time.time())
        args.seed = seed
        plan = make_plan(ids, efforts, modes, args.reps, seed)
        reserve = sum(len(prompts[i["prompt_id"]]["text"]) // 3 + 50 + args.max_tokens for i in plan)
        log(f"계획 {len(plan)}건 (프롬프트 {ids} × 추론 {efforts} × 모드 {modes} × {args.reps}회), seed={seed}")
        log(f"최대 예약 토큰 {reserve:,} → TPM {args.tpm:,} 기준 최소 {reserve / args.tpm:.1f}분")
        if args.dry_run:
            for item in plan:
                print(f"{item['seq']:>3}  {item['prompt_id']}  {item['effort']:<6} {item['mode']:<8} rep{item['rep']}")
            return 0
        label = f"_{args.label}" if args.label else ""
        run_dir = Path(args.out_dir) / (dt.datetime.now(KST).strftime("%Y%m%d-%H%M%S") + f"_{args.path}{label}")
        (run_dir / "outputs").mkdir(parents=True, exist_ok=True)
        meta = {
            "tool_version": VERSION,
            "created_at": now_kst(),
            "args": {k: v for k, v in vars(args).items() if k not in ("func",)},
            "prompts": prompts,
            "plan": plan,
        }
        (run_dir / "run_meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        done = set()
        log(f"기록 위치: {run_dir}")

    (run_dir / "outputs").mkdir(parents=True, exist_ok=True)
    pacer = Pacer(args.rpm, args.tpm, args.gap)
    todo = [i for i in plan if i["seq"] not in done]
    try:
        with open(run_dir / "requests.jsonl", "a", encoding="utf-8") as fh:
            for item in todo:
                prompt = prompts[item["prompt_id"]]
                rec, detail = execute_one(args, prompt, item["effort"], item["mode"], pacer)
                rec = {"run_id": run_dir.name, "seq": item["seq"], "rep": item["rep"], **rec}
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
                fh.flush()
                (run_dir / "outputs" / f"{item['seq']:04d}.json").write_text(
                    json.dumps({"seq": item["seq"], **detail}, ensure_ascii=False, indent=1), encoding="utf-8"
                )
                log(progress_line(item["seq"], len(plan), item, rec))
                if rec["error"] and args.stop_on_error:
                    log("오류로 중단 (--stop-on-error).")
                    break
    except KeyboardInterrupt:
        log(f"중단됨. 이어서 실행: python3 tps_bench.py run --resume '{run_dir}'")
        return 130
    log(f"끝. 집계: python3 tps_bench.py summarize '{run_dir}'")
    return 0


def cmd_check(args) -> int:
    efforts = [e.strip() for e in args.efforts.split(",") if e.strip()]
    modes = ["cli"] if args.path == "openclaw-cli" else ["nostream", "stream"]
    args.max_tokens = args.check_max_tokens
    pacer = Pacer(args.rpm, args.tpm, 1.0)
    run_dir = Path(args.out_dir) / (dt.datetime.now(KST).strftime("%Y%m%d-%H%M%S") + f"_{args.path}_check")
    run_dir.mkdir(parents=True, exist_ok=True)
    ok_all = True
    with open(run_dir / "requests.jsonl", "a", encoding="utf-8") as fh:
        seq = 0
        for effort in efforts:
            for mode in modes:
                seq += 1
                rec, detail = execute_one(args, CHECK_PROMPT, effort, mode, pacer)
                rec = {"run_id": run_dir.name, "seq": seq, "rep": 1, **rec}
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
                print(f"\n── {args.path} · effort={effort} · {mode}")
                if rec["error"]:
                    ok_all = False
                    print(f"  오류: {rec['error'][:600]}")
                    continue
                print(f"  HTTP {rec['http_status']} · 모델 {rec['model_returned']} · finish={rec['finish_reason']} · 응답 ID {rec['response_id']}")
                print(f"  본문: {detail['content'][:80]!r}  (추론 {len(detail['reasoning'])}자)")
                print(f"  usage 필드: {sorted((rec['usage_raw'] or {}).keys())}")
                print(f"  time_info 필드: {sorted((rec['time_info_raw'] or {}).keys()) or '없음'}")
                print(f"  completion_tokens={rec['completion_tokens']} reasoning_tokens={rec['reasoning_tokens']} "
                      f"completion_time={rec['completion_time']} 벽시계 {rec['client_wall_s']}s TTFT {fnum(rec['client_ttft_s'], 3)}s")
    print(f"\n기록: {run_dir}")
    return 0 if ok_all else 1


# ───────────────────────────── summarize ─────────────────────────────

SUMMARY_METRICS = ("server_decode_tps", "stream_tps", "client_wall_tps", "server_total_tps")


def cmd_summarize(args) -> int:
    dirs = [Path(d) for d in args.runs] or sorted(p for p in Path(args.out_dir).glob("*") if (p / "requests.jsonl").exists())
    if not dirs:
        raise SystemExit("집계할 run이 없습니다.")
    latest: dict = {}
    for d in dirs:
        for r in read_records(d):
            latest[(r.get("run_id"), r.get("seq"))] = r  # 같은 seq는 마지막 기록만 사용
    rows = [r for r in latest.values() if r.get("prompt_id") != "CHECK"]
    if not rows:
        raise SystemExit("기록이 없습니다.")
    metric = args.metric

    groups = collections.defaultdict(list)
    for r in rows:
        key = (r["path"], r["mode"], r["prompt_id"], r["prompt_version"], r["reasoning_effort"], r["max_completion_tokens"])
        groups[key].append(r)

    def stats(vals):
        vals = [v for v in vals if isinstance(v, (int, float))]
        if not vals:
            return None, None, None
        return statistics.median(vals), max(vals), (statistics.stdev(vals) if len(vals) > 1 else 0.0)

    table = []
    for key, rs in groups.items():
        ok = [r for r in rs if not r.get("error")]
        valid = [r for r in ok if not args.complete_only or (r.get("finish_reason") == "stop" and (r.get("completeness") in (None, 1.0)))]
        med, mx, sd = stats([r.get(metric) for r in valid])
        row = {
            "path": key[0], "mode": key[1], "prompt": f"{key[2]}/{key[3]}" if key[3] else key[2],
            "effort": key[4], "max_tok": key[5],
            "n": len(rs), "ok": len(ok), "used": len(valid),
            "length_capped": sum(1 for r in ok if r.get("finish_reason") == "length"),
            f"{metric}_median": med, f"{metric}_max": mx, f"{metric}_stdev": sd,
            "completion_tokens_median": stats([r.get("completion_tokens") for r in ok])[0],
            "reasoning_tokens_median": stats([r.get("reasoning_tokens") for r in ok])[0],
            "completeness_median": stats([r.get("completeness") for r in ok])[0],
            "ttft_median_s": stats([r.get("client_ttft_s") for r in ok])[0],
        }
        for m in SUMMARY_METRICS:
            if m != metric:
                row[f"{m}_median"] = stats([r.get(m) for r in valid])[0]
        table.append(row)
    table.sort(key=lambda r: (r[f"{metric}_median"] is None, -(r[f"{metric}_median"] or 0)))

    head = ["path", "mode", "prompt", "effort", "max_tok", "n", "ok", "used", "length_capped",
            f"{metric}_median", f"{metric}_max", f"{metric}_stdev",
            "completion_tokens_median", "reasoning_tokens_median", "completeness_median", "ttft_median_s"]
    # 표 정렬이 깨지지 않도록 머리글은 ASCII로 둔다
    short = {f"{metric}_median": "median", f"{metric}_max": "max", f"{metric}_stdev": "stdev",
             "completion_tokens_median": "out_tok", "reasoning_tokens_median": "reason_tok",
             "completeness_median": "complete", "ttft_median_s": "ttft_s", "length_capped": "capped"}
    print(f"\n기준 지표: {metric}" + ("  (finish=stop이고 완성도 1인 요청만)" if args.complete_only else ""))
    widths = [max(len(short.get(h, h)), *(len(fnum(r[h], 2 if h in ('completeness_median', 'ttft_median_s') else 1)) for r in table)) for h in head]
    print("  ".join(short.get(h, h).ljust(w) for h, w in zip(head, widths)))
    for r in table:
        print("  ".join(fnum(r[h], 2 if h in ("completeness_median", "ttft_median_s") else 1).ljust(w) for h, w in zip(head, widths)))

    best = [r for r in rows if not r.get("error") and isinstance(r.get(metric), (int, float))]
    if args.complete_only:
        best = [r for r in best if r.get("finish_reason") == "stop" and r.get("completeness") in (None, 1.0)]
    if best:
        b = max(best, key=lambda r: r[metric])
        print(f"\n단일 최고: {fnum(b[metric])} ({metric}) · {b['run_id']} seq {b['seq']} · {b['prompt_id']} "
              f"{b['reasoning_effort']} {b['mode']} · {b['completion_tokens']} tok · finish={b['finish_reason']} · "
              f"응답 ID {b.get('response_id')}")

    out = Path(args.csv) if args.csv else dirs[-1] / "summary.csv"
    keys = list(table[0].keys())
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        w.writerows(table)
    print(f"\nCSV: {out}")
    return 0


# ───────────────────────────── CLI ─────────────────────────────

def add_common(p: argparse.ArgumentParser) -> None:
    p.add_argument("--path", choices=["direct", "openclaw-http", "openclaw-cli"], default="direct")
    p.add_argument("--model", default=DEFAULT_MODEL, help="direct 경로에서 보낼 모델 ID")
    p.add_argument("--base-url", default=DEFAULT_BASE_URL, help="direct 경로 API 주소 (모의 서버 리허설 시 변경)")
    p.add_argument("--api-key-env", default="CEREBRAS_API_KEY", help="API 키를 담은 환경변수 이름")
    p.add_argument("--gateway-url", default=DEFAULT_GATEWAY_URL)
    p.add_argument("--openclaw-model", default=f"cerebras/{DEFAULT_MODEL}")
    p.add_argument("--openclaw-agent", default="openclaw/default", help="openclaw-http의 model 필드(에이전트 대상)")
    p.add_argument("--openclaw-bin", default=None)
    p.add_argument("--extra-body", type=json.loads, default={}, help='요청 본문에 덧붙일 JSON. 예: \'{"temperature":1.0}\'')
    p.add_argument("--no-stream-usage", action="store_true", help="스트리밍 때 stream_options.include_usage를 보내지 않음")
    p.add_argument("--timeout", type=float, default=300.0)
    p.add_argument("--max-retries", type=int, default=3, help="429·5xx·연결 오류 재시도 횟수")
    p.add_argument("--rpm", type=int, default=90, help="분당 요청 예산 (행사 한도 100)")
    p.add_argument("--tpm", type=int, default=90_000, help="분당 토큰 예산 (행사 한도 100K)")
    p.add_argument("--out-dir", default=str(HERE / "runs"))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    pc = sub.add_parser("check", help="접근 확인과 응답 필드 점검")
    add_common(pc)
    pc.add_argument("--efforts", default="omit", help="쉼표 구분. omit은 reasoning_effort를 보내지 않음")
    pc.add_argument("--check-max-tokens", type=int, default=256)
    pc.set_defaults(func=cmd_check)

    pr = sub.add_parser("run", help="실험 계획 실행")
    add_common(pr)
    pr.add_argument("--prompts-file", default=str(HERE / "prompts.json"))
    pr.add_argument("--prompts", default="P1,P2,P3,P4")
    pr.add_argument("--efforts", default="low,max", help="쉼표 구분. omit은 reasoning_effort를 보내지 않음")
    pr.add_argument("--modes", default="stream", help="stream,nostream 중 선택(쉼표 구분)")
    pr.add_argument("--reps", type=int, default=5)
    pr.add_argument("--max-tokens", type=int, default=2048)
    pr.add_argument("--seed", type=int, default=None)
    pr.add_argument("--gap", type=float, default=1.0, help="요청 사이 최소 간격(초)")
    pr.add_argument("--label", default="")
    pr.add_argument("--dry-run", action="store_true", help="요청 없이 계획만 출력")
    pr.add_argument("--stop-on-error", action="store_true")
    pr.add_argument("--resume", default=None, help="중단된 run 폴더를 이어서 실행")
    pr.set_defaults(func=cmd_run)

    ps = sub.add_parser("summarize", help="결과 집계")
    ps.add_argument("runs", nargs="*", help="run 폴더(생략하면 runs/ 전체)")
    ps.add_argument("--metric", default="server_decode_tps", choices=list(SUMMARY_METRICS))
    ps.add_argument("--complete-only", action="store_true", help="finish=stop이고 완성도 1인 요청만 집계")
    ps.add_argument("--csv", default=None)
    ps.add_argument("--out-dir", default=str(HERE / "runs"))
    ps.set_defaults(func=cmd_summarize)

    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
