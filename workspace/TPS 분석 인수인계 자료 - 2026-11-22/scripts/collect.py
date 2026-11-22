import json, os, glob, sys, datetime, hashlib
root = "workspace"
rows = []
seen = {}
for d in ["speed-bounty-evidence", "speed-bounty-evidence-test", "speed-bounty-evidence-2000"]:
    for ev in glob.glob(f"{root}/{d}/runs/*/evidence.json"):
        if "/._" in ev: continue
        rid = ev.split("/")[-2]
        try:
            e = json.load(open(ev)); p = json.load(open(ev.replace("evidence.json","plan.json")))
        except Exception as ex:
            continue
        calls = e.get("calls", [])
        cs = []
        for c in calls:
            sg = c.get("serverGeneration") or {}
            u = c.get("usage") or {}
            tps = sg["outputTokens"]/(sg["completionMs"]/1000) if sg.get("completionMs") else None
            cs.append(dict(ts=c.get("timestamp"), stop=c.get("stopReason"), out=sg.get("outputTokens"), ms=sg.get("completionMs"), tps=tps, inp=u.get("input"), cache=u.get("cacheRead"), ntools=len(c.get("tool_inputs") or [])))
        sc = e.get("score", {})
        val = e.get("validation", {})
        r = dict(dir=d, id=rid, label=p.get("label"), variant=p.get("variant"), protocol=e.get("protocol") or p.get("protocol"),
                 temp=p.get("temperature"), thinking=p.get("thinking"), top_p=p.get("top_p"), maxtok=p.get("max_completion_tokens"),
                 started=e.get("startedWall"), mean=sc.get("mean_exact_tps"), valid=val.get("valid"), status=val.get("status"),
                 nprod=sum(1 for x in e.get("products",[]) if x.get("verified")), calls=cs,
                 agents_md_sha=hashlib.sha256((p.get("workspace_agents_md") or "").encode()).hexdigest()[:8],
                 prompt_len=len(p.get("prompt") or ""), final_len=len((e.get("final_text") or "").encode()))
        key = (r["label"], rid)
        if rid in seen:
            # keep the one with more info
            continue
        seen[rid]=1
        rows.append(r)
def t(ms):
    if not ms: return "?"
    return datetime.datetime.fromtimestamp(ms/1000, datetime.timezone(datetime.timedelta(hours=9))).strftime("%H:%M:%S")
rows.sort(key=lambda r: (r["started"] or (r["calls"][0]["ts"] if r["calls"] and r["calls"][0]["ts"] else 0)))
json.dump(rows, open(sys.argv[1],"w"), indent=1, default=str)
for r in rows:
    st = r["started"] or (r["calls"][0]["ts"] if r["calls"] else None)
    cstr = " | ".join(f"{c['out']}t/{c['ms']:.0f}ms={c['tps']:.0f} in{c['inp']} c{c['cache']}" if c['tps'] else f"ERR({c['stop']})" for c in r["calls"])
    m = f"{r['mean']:.0f}" if r['mean'] else "-"
    print(f"{t(st)} {r['dir'][21:] or 'base':5} {str(r['label'])[:44]:44} T{r['temp']} {r['thinking']} md{r['agents_md_sha']} mean={m:>5} v={r['valid']} p{r['nprod']} || {cstr}")
