import json, random, statistics as st, datetime, sys
rows = json.load(open(sys.argv[1]))
KST = datetime.timezone(datetime.timedelta(hours=9))
def hm(ms): return datetime.datetime.fromtimestamp(ms/1000, KST).strftime("%H:%M")
fam = lambda r: r["label"] and (("five-categories-cap" in r["label"]) or ("first5027" in r["label"]) or ("exp2k" in r["label"]))
F = [r for r in rows if fam(r) and r["started"]]
F.sort(key=lambda r: r["started"])
BEST = [r for r in F if r["label"].startswith("D5027")][0]["started"]
firsts, finals = [], []
for r in F:
    cs = [c for c in r["calls"] if c["ms"]]
    if not cs: continue
    c0 = cs[0]
    tps0 = c0["out"]/c0["ms"]*1000
    polluted = c0["inp"] > 1200
    firsts.append(dict(run=r["label"][:5], t=r["started"], tps=tps0, ms=c0["ms"], out=c0["out"], th=c0["think"], inp=c0["inp"], pol=polluted, after=r["started"]>BEST))
    if len(cs) >= 2 and cs[-1]["stop"]=="stop":
        c1 = cs[-1]
        finals.append(dict(run=r["label"][:5], t=r["started"], tps=c1["out"]/c1["ms"]*1000, ms=c1["ms"], out=c1["out"], th=c1["think"], inp=c1["inp"], after=r["started"]>BEST, pol=polluted))
def summ(name, xs):
    if not xs: print(name, "n=0"); return
    print(f"{name:42} n={len(xs):2} median={st.median(xs):7.1f} min={min(xs):7.1f} max={max(xs):7.1f}")
print("=== FIRST CALL TPS (five-cat family) ===")
summ("before/at best, clean", [f["tps"] for f in firsts if not f["after"] and not f["pol"]])
summ("before/at best, polluted", [f["tps"] for f in firsts if not f["after"] and f["pol"]])
summ("after best, clean", [f["tps"] for f in firsts if f["after"] and not f["pol"]])
summ("after best, polluted", [f["tps"] for f in firsts if f["after"] and f["pol"]])
print("pollution rate before/at:", sum(f["pol"] for f in firsts if not f["after"]), "/", sum(1 for f in firsts if not f["after"]))
print("pollution rate after:", sum(f["pol"] for f in firsts if f["after"]), "/", sum(1 for f in firsts if f["after"]))
summ("reasoning chars clean", [f["th"] for f in firsts if not f["pol"]])
summ("reasoning chars polluted", [f["th"] for f in firsts if f["pol"]])
# simple OLS: ms ~ a + b*out_nonreason + c*th + d*pol  -> use numpy-free solve
import itertools
X = [[1.0, f["th"], 1.0 if f["pol"] else 0.0] for f in firsts]
y = [f["ms"] for f in firsts]
def ols(X, y):
    n=len(X[0]); A=[[sum(X[k][i]*X[k][j] for k in range(len(X))) for j in range(n)] for i in range(n)]; b=[sum(X[k][i]*y[k] for k in range(len(X))) for i in range(n)]
    # gaussian elimination
    M=[A[i]+[b[i]] for i in range(n)]
    for i in range(n):
        p=max(range(i,n), key=lambda r: abs(M[r][i])); M[i],M[p]=M[p],M[i]
        for r in range(n):
            if r!=i:
                f=M[r][i]/M[i][i]; M[r]=[M[r][c]-f*M[i][c] for c in range(n+1)]
    return [M[i][n]/M[i][i] for i in range(n)]
co = ols(X, y)
pred=[sum(a*b for a,b in zip(x,co)) for x in X]; ss=sum((a-b)**2 for a,b in zip(y,pred)); sst=sum((a-st.mean(y))**2 for a in y)
print(f"OLS first-call ms = {co[0]:.0f} + {co[1]:.3f}*reasoning_chars + {co[2]:.0f}*polluted   R2={1-ss/sst:.2f}  n={len(y)}")
co2 = ols([[1.0, f["th"]] for f in firsts], y); print(f"   ms ~ reasoning only: {co2[0]:.0f} + {co2[1]:.3f}*chars")
co3 = ols([[1.0, 1.0 if f['pol'] else 0.0] for f in firsts], y); print(f"   ms ~ polluted only: {co3[0]:.0f} + {co3[1]:.0f}*pol")
print("\n=== FINAL CALL (five-cat family) ===")
z = [f for f in finals if f["th"]==0]
print("zero-reasoning finals:", len(z), "/", len(finals))
for f in sorted(z, key=lambda f: f["ms"]):
    print(f"  {f['run']} {hm(f['t'])} out={f['out']} ms={f['ms']:.0f} tps={f['tps']:.0f} {'AFTER' if f['after'] else 'before'} {'pol' if f['pol'] else 'clean'}")
fast = [f for f in z if f["ms"] < 140]
print("fast-mode (<140ms) among zero-reasoning:", len(fast), "/", len(z))
summ("finals with reasoning>0 tps", [f["tps"] for f in finals if f["th"]>0])
summ("finals zero-reasoning tps", [f["tps"] for f in z])
print("\n=== RECORD-BREAK PROBABILITY (bootstrap, independent first/final) ===")
def p_break(fs, gs, target=1354.66, n=200000):
    random.seed(1); k=0
    for _ in range(n):
        if (random.choice(fs)+random.choice(gs))/2 > target: k+=1
    return k/n
# include failed final as 'no record' via run success rate
pre_f = [f["tps"] for f in firsts if not f["after"]]
pre_g = [f["tps"] for f in finals if not f["after"]]
post_f = [f["tps"] for f in firsts if f["after"]]
post_g = [f["tps"] for f in finals if f["after"]]
all_f=[f["tps"] for f in firsts]; all_g=[f["tps"] for f in finals]
for nm, a, b in [("pre-best pool", pre_f, pre_g), ("post-best pool", post_f, post_g), ("all", all_f, all_g)]:
    p=p_break(a,b); print(f"{nm:16} first n={len(a)} final n={len(b)}  P(mean>1354.66)={p*100:.2f}%  -> expected breaks in 20 runs={20*p:.2f}")
clean_f=[f["tps"] for f in firsts if not f["pol"]]
p=p_break(clean_f, all_g); print(f"clean-first + all finals P={p*100:.2f}%")
# correlation first vs final within run
pairs=[(a["tps"], b["tps"]) for a in firsts for b in finals if a["run"]==b["run"]]
xs,ys=zip(*pairs); mx,my=st.mean(xs),st.mean(ys)
r=sum((x-mx)*(y-my) for x,y in pairs)/((sum((x-mx)**2 for x in xs)*sum((y-my)**2 for y in ys))**0.5)
print(f"corr(first tps, final tps) within run: r={r:.2f} n={len(pairs)}")
# what final is required given first
print("\nrequired final tps to beat 1354.66 given first:", {f0: round(2*1354.66-f0) for f0 in (800,900,1000,1035,1100,1262)})
print("max observed final:", round(max(all_g)), " max observed first:", round(max(all_f)), " theoretical best pair:", round((max(all_g)+max(all_f))/2))
