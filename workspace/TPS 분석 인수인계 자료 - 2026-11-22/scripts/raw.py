import json, glob, os, datetime, sys
base = os.path.expanduser("~/Library/Application Support/Cerebras Speed Bounty/2026-11-22")
out = []
for f in sorted(glob.glob(base + "/raw*/*.json")):
    try: d = json.load(open(f))
    except Exception: continue
    if "history" not in d or not isinstance(d.get("history"), dict): continue
    msgs = d["history"].get("messages", [])
    calls = []
    for m in msgs:
        if m.get("role") != "assistant": continue
        th = sum(len(c.get("thinking","")) for c in m.get("content",[]) if c.get("type")=="thinking")
        tx = sum(len(c.get("text","")) for c in m.get("content",[]) if c.get("type")=="text")
        tc = [c for c in m.get("content",[]) if c.get("type")=="toolCall"]
        targ = sum(len(json.dumps(c.get("arguments",{}))) for c in tc)
        sg = m.get("serverGeneration") or {}
        u = m.get("usage") or {}
        calls.append(dict(ts=m.get("timestamp"), stop=m.get("stopReason"), err=(m.get("errorMessage") or "")[:80],
            out=sg.get("outputTokens"), ms=sg.get("completionMs"), inp=u.get("input"), cache=u.get("cacheRead"),
            think=th, text=tx, ntool=len(tc), targ=targ))
    out.append(dict(file=f.split("2026-11-22/")[1], id=d.get("id"), label=d.get("label"), variant=d.get("variant"),
        temp=d.get("temperature"), thinking=d.get("thinking"), started=d.get("startedWall"), ackMs=d.get("ackMs"),
        elapsed=(d.get("ended") or {}).get("elapsedMs"), nmsg=len(msgs), calls=calls))
json.dump(out, open(sys.argv[1],"w"), indent=1)
def t(ms): return datetime.datetime.fromtimestamp(ms/1000, datetime.timezone(datetime.timedelta(hours=9))).strftime("%H:%M:%S") if ms else "?"
out.sort(key=lambda r: r["started"] or 0)
for r in out:
    cs=[]
    for c in r["calls"]:
        if c["ms"]:
            cs.append(f"{c['out']}t {c['ms']:.0f}ms {c['out']/c['ms']*1000:.0f}tps th{c['think']} tx{c['text']} tool{c['ntool']}/{c['targ']} in{c['inp']}")
        else:
            cs.append(f"ERR[{c['stop']}:{c['err'][:40]}]")
    print(f"{t(r['started'])} {str(r['label'])[:40]:40} n{r['nmsg']:2} || " + " | ".join(cs))
