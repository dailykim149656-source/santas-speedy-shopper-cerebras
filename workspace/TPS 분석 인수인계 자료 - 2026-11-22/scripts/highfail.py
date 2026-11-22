import json, os, glob, datetime
REPO = "experiments/test"
T = os.path.expanduser('~/Library/Caches/cerebras-speed-bounty/2026-11-22-test/mean-2000')
KST = datetime.timezone(datetime.timedelta(hours=9))
rows = []
for ev in glob.glob(REPO + '/runs/*/evidence.json'):
    e = json.load(open(ev)); p = json.load(open(ev.replace('evidence.json', 'plan.json')))
    lab = p.get('label', '')
    if not lab.startswith('D50') or lab < 'D5039': continue
    calls = [c for c in e.get('calls', []) if (c.get('serverGeneration') or {}).get('completionMs')]
    tps = [c['serverGeneration']['outputTokens'] / c['serverGeneration']['completionMs'] * 1000 for c in calls]
    sc = (e.get('score') or {}).get('mean_exact_tps')
    v = e.get('validation', {})
    rows.append(dict(label=lab, t=e.get('startedWall') or 0, score=sc, n=len(calls), tps=[round(x) for x in tps],
                     out=[c['serverGeneration']['outputTokens'] for c in calls], valid=v.get('valid'), reasons=v.get('reject_reasons', []),
                     nprod=sum(1 for x in e.get('products', []) if x.get('verified')), final_len=len((e.get('final_text') or '')), id=e['id']))
rows.sort(key=lambda r: r['t'])
print('runs since D5039:', len(rows))
print('\n== runs whose official mean or any call >= 1300 TPS')
for r in rows:
    if (r['score'] or 0) >= 1300 or any(x >= 1300 for x in r['tps']):
        t = datetime.datetime.fromtimestamp(r['t']/1000, KST).strftime('%H:%M') if r['t'] else '?'
        print(f"{r['label'][:24]:24} {t} score={r['score'] and round(r['score'])} calls={r['n']} tps={r['tps']} out={r['out']} valid={r['valid']} products={r['nprod']} finalchars={r['final_len']}")
        for x in r['reasons'][:4]: print('     -', x[:150])
json.dump(rows, open('${TMPDIR}/claude-501/-Users-local--claude-spares-spare-session/e6acc846-d4ec-4b8c-923f-bd4e3dd4e348/scratchpad/rows_recent.json','w'))
