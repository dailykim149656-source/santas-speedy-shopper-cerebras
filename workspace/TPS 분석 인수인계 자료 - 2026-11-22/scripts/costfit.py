import json, os, glob, datetime, statistics as st
KST = datetime.timezone(datetime.timedelta(hours=9))
base = os.path.expanduser('~/Library/Application Support/Cerebras Speed Bounty/2026-11-22')
rows = []
for f in glob.glob(base + '/raw*/*.json'):
    try: d = json.load(open(f))
    except Exception: continue
    if not isinstance(d.get('history'), dict) or not d.get('startedWall'): continue
    t = datetime.datetime.fromtimestamp(d['startedWall']/1000, KST)
    lab = str(d.get('label',''))
    for m in d['history']['messages']:
        if m.get('role') != 'assistant': continue
        sg = m.get('serverGeneration') or {}
        if not sg.get('completionMs'): continue
        th = sum(len(c.get('thinking','')) for c in m.get('content',[]) if c.get('type')=='thinking')
        rows.append(dict(lab=lab, t=t, stop=m.get('stopReason'), out=sg['outputTokens'], ms=sg['completionMs'], th=th))
def ols(X, y):
    n=len(X[0]); A=[[sum(X[k][i]*X[k][j] for k in range(len(X))) for j in range(n)] for i in range(n)]; b=[sum(X[k][i]*y[k] for k in range(len(X))) for i in range(n)]
    M=[A[i]+[b[i]] for i in range(n)]
    for i in range(n):
        p=max(range(i,n), key=lambda r: abs(M[r][i])); M[i],M[p]=M[p],M[i]
        for r in range(n):
            if r!=i:
                f=M[r][i]/M[i][i]; M[r]=[M[r][c]-f*M[i][c] for c in range(n+1)]
    return [M[i][n]/M[i][i] for i in range(n)]
def fit(name, rs):
    # reasoning tokens ~ chars/4 ; copy tokens = out - reasoning tokens
    X=[[1.0, max(r['out']-r['th']/4,0), r['th']/4] for r in rs]; y=[r['ms'] for r in rs]
    a,b,c=ols(X,y)
    pred=[a+b*x[1]+c*x[2] for x in X]; ss=sum((p-q)**2 for p,q in zip(y,pred)); sst=sum((q-st.mean(y))**2 for q in y)
    print(f"{name:34} n={len(rs):3} fixed={a:6.1f}ms  per answer-token={b:.3f}ms ({1000/b:.0f} tok/s)  per reasoning-token={c:.2f}ms ({1000/c:.0f} tok/s)  R2={1-ss/sst:.2f}")
    return a,b,c
finals=[r for r in rows if r['stop']=='stop']
firsts=[r for r in rows if r['stop']=='toolUse']
print('calls', len(rows), 'finals', len(finals), 'tool calls', len(firsts))
fit('all final calls', finals)
fit('final calls 14:00-19:00', [r for r in finals if 14<=r['t'].hour<19])
fit('final calls 19:00-', [r for r in finals if r['t'].hour>=19])
fit('tool calls (first)', firsts)
a,b,c = fit('final calls 16:00-19:00 (record era)', [r for r in finals if 16<=r['t'].hour<19])
print('\npredicted final TPS with record-era costs:')
for out, rt in ((161,0),(176,15),(236,70),(460,10),(460,40),(550,15)):
    ms = a + b*(out-rt) + c*rt
    print(f"   {out} tokens with {rt} reasoning tokens -> {ms:.0f} ms = {out/ms*1000:.0f} TPS")
