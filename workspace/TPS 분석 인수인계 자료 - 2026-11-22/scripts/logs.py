import json, re, os, datetime, sys
files = ["${TMPDIR}/openclaw/openclaw-2026-11-22.log", os.path.expanduser("~/.openclaw/logs/openclaw-2026-11-22.log")]
ev = []
for f in files:
    for line in open(f, errors="replace"):
        try: j = json.loads(line)
        except Exception: continue
        dt = j.get("_meta",{}).get("date") or j.get("time")
        s = json.dumps(j)
        ev.append((dt, f.split("/")[-3] if "tmp" in f else "home", s))
print("ranges:")
for src in ("openclaw","home"):
    ds = sorted(e[0] for e in ev if e[1]==src and e[0])
    print(src, ds[0] if ds else None, ds[-1] if ds else None, len(ds))
fetch = []
for dt, src, s in ev:
    m = re.search(r"\[model-fetch\] response provider=cerebras .*?status=(\d+) elapsedMs=(\d+)", s)
    if m: fetch.append((dt, int(m.group(1)), int(m.group(2))))
fetch = sorted(set(fetch))
print("model-fetch responses:", len(fetch))
rows = json.load(open(sys.argv[1]))
def ms2iso(ms): return datetime.datetime.fromtimestamp(ms/1000, datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3]+"Z"
for r in sorted(rows, key=lambda r: r["started"] or 0):
    if not r["started"] or not r.get("elapsed"): continue
    a = ms2iso(r["started"]); b = ms2iso(r["started"] + r["elapsed"] + 500)
    fs = [x for x in fetch if a <= x[0] <= b]
    if not fs: continue
    seq = " ".join(f"{st}" for _,st,_ in fs)
    c0 = r["calls"][0] if r["calls"] else {}
    print(f"{r['label'][:38]:38} fetches: {seq:40} firstcall_in={c0.get('inp')} th={c0.get('think')}")
