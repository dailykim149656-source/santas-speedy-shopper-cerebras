import json, statistics as st, sys
raw = {r["id"]: r for r in json.load(open(sys.argv[1]))}
ev = json.load(open(sys.argv[2]))
phases = [("P1 16:18-17:26 (best)", "D5004", "D5028"), ("P2 17:27-18:10 six-sorted", "D5029", "D5036"),
          ("P3 18:13-18:45 exp2000", "D6001", "D6007"), ("P4 19:12-19:54 first5027", "D5039", "D5050"), ("P5 20:12-20:37 gift8", "D5051", "D5058")]
def num(l): return l[:5]
for name, a, b in phases:
    rs = [r for r in ev if r["label"] and a <= num(r["label"]) <= b and r["label"][0]=="D" and num(r["label"])[1]==a[1]]
    valid = [r for r in rs if r["valid"] and r["mean"]]
    means = [r["mean"] for r in valid]
    pol = 0; n1 = 0
    for r in rs:
        rr = raw.get(r["id"]); 
        if not rr or not rr["calls"] or not rr["calls"][0]["inp"]: continue
        n1 += 1
    print(f"{name:28} sent={len(rs):2} valid={len(valid):2} " + (f"median={st.median(means):6.0f} max={max(means):6.0f}" if means else "-"))
# average decomposition: pre-best valid five-cat vs post-best valid five-cat family
fam = lambda l: ("five-categories-cap" in l) or ("first5027" in l) or ("exp2k" in l)
pre=[r for r in ev if r["label"] and fam(r["label"]) and r["valid"] and r["started"] and r["started"]<=1795335856859]
post=[r for r in ev if r["label"] and fam(r["label"]) and r["valid"] and r["started"] and r["started"]>1795335856859]
def comp(rs):
    f=[r["calls"][0]["tps"] for r in rs]; g=[r["calls"][-1]["tps"] for r in rs]; m=[r["mean"] for r in rs]
    return st.mean(f), st.mean(g), st.mean(m), len(rs)
a=comp(pre); b=comp(post)
print(f"pre-best valid  n={a[3]} first={a[0]:.0f} final={a[1]:.0f} mean={a[2]:.0f}")
print(f"post-best valid n={b[3]} first={b[0]:.0f} final={b[1]:.0f} mean={b[2]:.0f}")
print(f"delta mean={b[2]-a[2]:.0f}: first contrib={(b[0]-a[0])/2:.0f}, final contrib={(b[1]-a[1])/2:.0f}")
