#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

export BOUNTY_ROOT="${BOUNTY_ROOT:-$HOME/Library/Caches/cerebras-speed-bounty/2026-11-22-exp2000}"
export BOUNTY_RAW_ARCHIVE="${BOUNTY_RAW_ARCHIVE:-$HOME/Library/Application Support/Cerebras Speed Bounty/2026-11-22/raw-exp2000}"
export BOUNTY_GATEWAY_PORT="${BOUNTY_GATEWAY_PORT:-19864}"
export BOUNTY_SCHEDULE="${BOUNTY_SCHEDULE:-test}"
export BOUNTY_LABEL_BASE="${BOUNTY_LABEL_BASE:-6000}"

MAIN_CACHE="$HOME/Library/Caches/cerebras-speed-bounty/2026-11-22/mean-2000"
TEST_CACHE="$HOME/Library/Caches/cerebras-speed-bounty/2026-11-22-test/mean-2000"
EXP_CACHE="$BOUNTY_ROOT/mean-2000"
CAMPAIGN_START=$((BOUNTY_LABEL_BASE + 1))

AUTH_NODE="${RECORDER_AUTH_NODE:-$HOME/.nvm/versions/node/v24.20.0/bin/node}"
if [[ ! -x "$AUTH_NODE" ]]; then
  AUTH_NODE="$(command -v node)"
fi

is_lock_held() {
  local lock_file="$1"
  python3 - "$lock_file" <<'PY'
import fcntl, sys
from pathlib import Path
p = Path(sys.argv[1])
if not p.exists():
    sys.exit(1)
with p.open('rb') as f:
    try:
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        sys.exit(0)
sys.exit(1)
PY
}

gateway_healthy() {
  python3 - "$BOUNTY_GATEWAY_PORT" <<'PY'
import http.client, json, sys
port = int(sys.argv[1])
conn = http.client.HTTPConnection('127.0.0.1', port, timeout=2)
try:
    conn.request('GET', '/health')
    resp = conn.getresponse()
    body = json.loads(resp.read(512))
    sys.exit(0 if resp.status == 200 and body.get('ok') is True else 1)
except Exception:
    sys.exit(1)
finally:
    conn.close()
PY
}

start_gateway() {
  if gateway_healthy; then
    echo "Gateway on 127.0.0.1:${BOUNTY_GATEWAY_PORT} is already healthy."
    return 0
  fi
  if [[ ! -f "$EXP_CACHE/profile.mjs" ]]; then
    echo "Missing $EXP_CACHE/profile.mjs" >&2
    return 1
  fi
  echo "Starting isolated exp2000 gateway on port ${BOUNTY_GATEWAY_PORT}..."
  nohup "$AUTH_NODE" "$EXP_CACHE/profile.mjs" gateway run > "$BOUNTY_ROOT/gateway.log" 2>&1 < /dev/null &
  local gw_pid=$!
  for _ in $(seq 1 240); do
    if gateway_healthy; then
      echo "Gateway on 127.0.0.1:${BOUNTY_GATEWAY_PORT} is ready."
      return 0
    fi
    if ! kill -0 "$gw_pid" 2>/dev/null; then
      echo "Gateway process exited prematurely; check $BOUNTY_ROOT/gateway.log" >&2
      return 1
    fi
    sleep 0.5
  done
  echo "Timed out waiting for gateway on port ${BOUNTY_GATEWAY_PORT}; check $BOUNTY_ROOT/gateway.log" >&2
  return 1
}

next_trial_number() {
  python3 - "$REPO_DIR" "$BOUNTY_LABEL_BASE" <<'PY'
import json, re, sys
from pathlib import Path
repo, base = Path(sys.argv[1]), int(sys.argv[2])
seen = [base]
for path in (repo / 'runs').glob('*/plan.json'):
    label = json.loads(path.read_text()).get('label', '')
    match = re.fullmatch(r'D(\d+)-.+', label)
    if match:
        seen.append(int(match[1]))
print(max(seen) + 1)
PY
}

show_status() {
  local main_state="idle" test_state="idle" exp_state="idle" gw_state="offline"
  is_lock_held "$MAIN_CACHE/loop.lock" && main_state="RUNNING"
  is_lock_held "$TEST_CACHE/loop.lock" && test_state="RUNNING"
  is_lock_held "$EXP_CACHE/loop.lock" && exp_state="RUNNING"
  gateway_healthy && gw_state="healthy"

  echo "Repo:          $REPO_DIR (branch: $(git -C "$REPO_DIR" branch --show-current))"
  echo "BOUNTY_ROOT:   $BOUNTY_ROOT"
  echo "Raw archive:   $BOUNTY_RAW_ARCHIVE"
  echo "Locks:         main=$main_state | test=$test_state | exp2000=$exp_state"
  echo "Gateway 19864: $gw_state"
  if [[ -f "$EXP_CACHE/stop-requested" ]]; then
    echo "Stop marker:   present ($EXP_CACHE/stop-requested)"
  fi
  if [[ -f "$EXP_CACHE/fast-probe-start" ]]; then
    echo "Fast probe:    start=D$(printf '%04d' "$(cat "$EXP_CACHE/fast-probe-start")")"
  fi
  if [[ -f "$TEST_CACHE/status.json" ]]; then
    echo "Test status:   $(tr '\n' ' ' < "$TEST_CACHE/status.json")"
  fi
  if [[ -f "$EXP_CACHE/status.json" ]]; then
    echo "Exp status:    $(tr '\n' ' ' < "$EXP_CACHE/status.json")"
  fi
  if [[ -f "$EXP_CACHE/fast-probe-start" ]]; then
    python3 -B "$REPO_DIR/tools/campaign_2000.py" \
      --repo "$REPO_DIR" \
      --start "$(cat "$EXP_CACHE/fast-probe-start")" \
      --rows "$EXP_CACHE/iterations.jsonl" \
      --raw-dir "$BOUNTY_RAW_ARCHIVE" \
      --fast \
      --report
    echo ""
  fi
  python3 -B "$REPO_DIR/tools/campaign_2000.py" \
    --repo "$REPO_DIR" \
    --start "$CAMPAIGN_START" \
    --rows "$EXP_CACHE/iterations.jsonl" \
    --raw-dir "$BOUNTY_RAW_ARCHIVE" \
    --report
}

usage() {
  cat <<EOF
Usage: $(basename "$0") <mode> [--start D_NUMBER] [--allow-concurrent]

Modes:
  --status           Show lock states, isolated port 19864 gateway health, and campaign_2000 progress
  --start-gateway    Start isolated OpenClaw gateway on port $BOUNTY_GATEWAY_PORT if offline
  --wait-for-test    Poll until 2026-11-22-test (and 2026-11-22) loop.lock are released, then run campaign_2000
  --once             Run a single campaign_2000 trial (blocks if test loop is active unless --allow-concurrent)
  --fast-probe       Run the 6-trial interleaved fast probe (5-word cap, 15s valid / 30-60s fail, 1350 threshold)
  --fast-report      Print Markdown report for the 6-trial fast-probe schedule
  --report           Print Markdown report with per-call diagnostics
EOF
}

mode=""
start_override=""
allow_concurrent=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --status|--start-gateway|--wait-for-test|--once|--fast-probe|--fast-report|--report)
      mode="$1"
      shift
      ;;
    --start)
      if [[ $# -lt 2 || ! "$2" =~ ^[0-9]+$ ]]; then
        echo "--start requires a numeric D_NUMBER" >&2
        exit 2
      fi
      start_override="$2"
      shift 2
      ;;
    --start=*)
      start_override="${1#--start=}"
      if [[ ! "$start_override" =~ ^[0-9]+$ ]]; then
        echo "--start requires a numeric D_NUMBER" >&2
        exit 2
      fi
      shift
      ;;
    --allow-concurrent)
      allow_concurrent=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

case "$mode" in
  --status)
    show_status
    ;;
  --start-gateway)
    start_gateway
    ;;
  --report)
    python3 -B "$REPO_DIR/tools/campaign_2000.py" \
      --repo "$REPO_DIR" \
      --start "$CAMPAIGN_START" \
      --rows "$EXP_CACHE/iterations.jsonl" \
      --raw-dir "$BOUNTY_RAW_ARCHIVE" \
      --report
    ;;
  --fast-report)
    if [[ -n "$start_override" ]]; then
      fast_start="$start_override"
    elif [[ -f "$EXP_CACHE/fast-probe-start" ]]; then
      fast_start="$(cat "$EXP_CACHE/fast-probe-start")"
    else
      fast_start="$(next_trial_number)"
    fi
    python3 -B "$REPO_DIR/tools/campaign_2000.py" \
      --repo "$REPO_DIR" \
      --start "$fast_start" \
      --rows "$EXP_CACHE/iterations.jsonl" \
      --raw-dir "$BOUNTY_RAW_ARCHIVE" \
      --fast \
      --report
    ;;
  --fast-probe)
    if [[ "$allow_concurrent" -ne 1 ]] && { is_lock_held "$TEST_CACHE/loop.lock" || is_lock_held "$MAIN_CACHE/loop.lock"; }; then
      echo "Refusing to send while test/main loop.lock is active (50k uncached TPM limit). Use --allow-concurrent to override." >&2
      exit 1
    fi
    if [[ -n "$start_override" ]]; then
      fast_start="$start_override"
    elif [[ -f "$EXP_CACHE/fast-probe-start" ]]; then
      fast_start="$(cat "$EXP_CACHE/fast-probe-start")"
    else
      fast_start="$(next_trial_number)"
    fi
    mkdir -p "$EXP_CACHE"
    echo "$fast_start" > "$EXP_CACHE/fast-probe-start"
    rm -f "$EXP_CACHE/stop-requested"
    start_gateway
    cd "$REPO_DIR"
    exec python3 -B -u "$REPO_DIR/tools/loop.py" --fast-probe-2000-start "$fast_start"
    ;;
  --wait-for-test)
    while is_lock_held "$TEST_CACHE/loop.lock" || is_lock_held "$MAIN_CACHE/loop.lock"; do
      echo "[$(date '+%H:%M:%S')] Waiting for active loop lock(s) (test/main) to clear..."
      sleep 15
    done
    start_gateway
    cd "$REPO_DIR"
    exec python3 -B -u "$REPO_DIR/tools/loop.py" --campaign-2000-start "$CAMPAIGN_START"
    ;;
  --once)
    if [[ "$allow_concurrent" -ne 1 ]] && { is_lock_held "$TEST_CACHE/loop.lock" || is_lock_held "$MAIN_CACHE/loop.lock"; }; then
      echo "Refusing to send while test/main loop.lock is active (50k uncached TPM limit). Use --wait-for-test or --allow-concurrent." >&2
      exit 1
    fi
    start_gateway
    cd "$REPO_DIR"
    exec python3 -B -u "$REPO_DIR/tools/loop.py" --campaign-2000-start "$CAMPAIGN_START" --once
    ;;
  *)
    usage >&2
    exit 2
    ;;
esac
