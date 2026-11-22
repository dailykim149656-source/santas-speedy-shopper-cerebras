"""Count observed AI Synthesis requests in a trailing hour across D5027 operating modes."""
from datetime import datetime
import fcntl
from functools import lru_cache
import json
import math
import os
from pathlib import Path
import time
from urllib.parse import urlsplit

HERE=Path(__file__).resolve().parent
CACHE=HERE.parent
RUNS=(Path(os.environ.get("BOUNTY_TEST_REPO", Path.cwd())) / 'runs')
RAW=Path.home()/'Library/Application Support/Cerebras Speed Bounty/2026-11-22/raw-test'
LIMIT=400
def shop(url):
    return (urlsplit(url or '').hostname or '').removeprefix('www.')=='aisynthesis.com'

@lru_cache(maxsize=512)
def lookups(path, mtime):
    data=json.loads(path.read_bytes())
    times=[]
    for m in data['history']['messages']:
        if m.get('role')!='assistant' or m.get('__openclaw',{}).get('runId')!=data['id']:
            continue
        for part in m.get('content') or []:
            if isinstance(part,dict) and part.get('type')=='toolCall' and part.get('name')=='web_fetch' and shop((part.get('arguments') or {}).get('url')):
                times.append((m.get('timestamp') or data['ended']['time'])/1000)
    return tuple(times)

@lru_cache(maxsize=512)
def detailed(path, mtime):
    e=json.loads(path.read_bytes())
    return tuple(datetime.fromisoformat(p['checked_at']).timestamp() if p.get('checked_at') else path.stat().st_mtime
                 for p in e.get('products',[]) if shop(p.get('url')))

def events(now):
    since=now-3600
    times=[]
    for path in RAW.glob('*.json'):
        stamp=path.stat().st_mtime
        if stamp < since-5:
            continue
        times.extend(lookups(path,stamp))
    for path in RUNS.glob('*/evidence.json'):
        stamp=path.stat().st_mtime
        if stamp < since-5:
            continue
        # Deferred receipts use actual attempt reservations, including network failures and redirects.
        if (HERE/'pending'/(path.parent.name+'.json')).exists() or (HERE/'finalized'/(path.parent.name+'.json')).exists():
            continue
        times.extend(detailed(path,stamp))
    tracker=HERE/'detail-starts.jsonl'
    if tracker.exists():
        times.extend(float(x) for x in tracker.read_text().splitlines() if x)
    return sorted(t for t in times if t>since)

def next_slot_at(reserve=15):
    now=time.time()
    history=events(now)
    n=len(history)+reserve-LIMIT
    return history[n-1]+3600.05 if n>0 else now

def wait_for_detail_budget():
    # Called on each actual validation GET, also after redirects and before retries.
    with (HERE/'detail-traffic.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        while True:
            wait=next_slot_at(1)-time.time()
            if wait<=0:
                break
            time.sleep(min(wait,5))
        with (HERE/'detail-starts.jsonl').open('a') as output:
            print(time.time(),file=output,flush=True)
            os.fsync(output.fileno())
