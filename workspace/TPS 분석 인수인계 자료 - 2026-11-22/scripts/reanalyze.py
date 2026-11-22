import json, os, glob, datetime, statistics as st, collections
REPO = "experiments/test"
RAW = os.path.expanduser('~/Library/Application Support/Cerebras Speed Bounty/2026-11-22/raw-test')
KST = datetime.timezone(datetime.timedelta(hours=9))
runs = []
for ev in glob.glob(REPO + '/runs/*/evidence.json'):
    e = json.load(open(ev)); p = json.load(open(ev.replace('evidence.json', 'plan.json')))
    lab = p.get('label', '')
    if not (lab >= 'D5059' and lab < 'D5100'): continue
    arm = ('relay-short' if 'relay' in lab else 'speed-A' if lab.endswith('-a') else 'speed-F' if lab.endswith('-f')
           else 'speed-P' if lab.endswith('-p') else 'ctl-retry' if 'relay-control' in str(p.get('request_relay', '')) or str(p.get('request_relay','')).endswith('retry-only') else 'ctl-direct')
    raw = os.path.join(RAW, e['id'] + '.json')
    th = []
    if os.path.exists(raw):
        d = json.load(open(raw))
        for m in d['history']['messages']:
            if m.get('role') == 'assistant' and (m.get('serverGeneration') or {}).get('completionMs'):
                th.append(sum(len(c.get('thinking', '')) for c in m.get('content', []) if c.get('type') == 'thinking'))
    calls = [c for c in e.get('calls', []) if (c.get('serverGeneration') or {}).get('completionMs')]
    cs = [dict(out=c['serverGeneration']['outputTokens'], ms=c['serverGeneration']['completionMs'], stop=c.get('stopReason')) for c in calls]
    for c, t in zip(cs, th): c['th'] = t
    for c in cs: c['tps'] = c['out'] / c['ms'] * 1000
    t = datetime.datetime.fromtimestamp((e.get('startedWall') or p.get('startedWall') or 0) / 1000, KST) if e.get('startedWall') else None
    runs.append(dict(label=lab, arm=arm, t=t, valid=e['validation']['valid'], score=(e.get('score') or {}).get('mean_exact_tps'), calls=cs, req=p.get('request_relay')))
runs.sort(key=lambda r: r['label'])
print('runs', len(runs), collections.Counter(r['arm'] for r in runs))
# death phase
def phase(r):
    if r['label'].startswith('D5059'): return 'relay-bug'
    if r['valid']: return 'valid'
    n = len(r['calls'])
    return 'died-before-first' if n == 0 else 'died-at-final' if n == 1 and r['calls'][0]['stop'] == 'toolUse' else 'other-invalid'
tab = collections.defaultdict(collections.Counter)
for r in runs: tab[r['arm']][phase(r)] += 1
for a, c in tab.items(): print(f"{a:12}", dict(c))
tot = collections.Counter(phase(r) for r in runs); print('ALL', dict(tot))
# by half-hour
half = collections.defaultdict(collections.Counter)
for r in runs:
    if r['t']: half[r['t'].strftime('%H:') + ('00' if r['t'].minute < 30 else '30')][phase(r)] += 1
for k in sorted(half): print('  ', k, dict(half[k]))
# first and final calls (exclude prefetch P single-call and relay-short for finals separately)
firsts = [(r['arm'], r['calls'][0]) for r in runs if r['calls'] and r['calls'][0]['stop'] == 'toolUse']
finals = [(r['arm'], r['calls'][-1]) for r in runs if len(r['calls']) >= 2 and r['calls'][-1]['stop'] == 'stop']
print('\nfirst calls (tool) n=%d median=%.0f max=%.0f' % (len(firsts), st.median(c['tps'] for _, c in firsts), max(c['tps'] for _, c in firsts)))
print('  >=1200:', sorted(round(c['tps']) for _, c in firsts if c['tps'] >= 1200))
print('final calls n=%d median=%.0f max=%.0f' % (len(finals), st.median(c['tps'] for _, c in finals), max(c['tps'] for _, c in finals)))
for a in ('ctl-direct', 'ctl-retry', 'speed-A', 'speed-F', 'relay-short'):
    f = [c for arm, c in finals if arm == a]
    if f: print(f"  {a:12} n={len(f)} tps={sorted(round(c['tps']) for c in f)} reasoning={[c.get('th') for c in f]} out={[c['out'] for c in f]}")
z = [c for _, c in finals if c.get('th') == 0]
print('zero-reasoning finals:', len(z), '/', len(finals), [(c['out'], round(c['ms'])) for c in z])
print('finals >= 1300:', sum(c['tps'] >= 1300 for _, c in finals))
P = [r for r in runs if r['arm'] == 'speed-P' and r['calls']]
print('prefetch single calls:', [(c['out'], round(c['ms']), round(c['tps']), c.get('th')) for r in P for c in r['calls']])
# F vs A first call (identical requests)
for a in ('speed-A', 'speed-F', 'ctl-retry', 'ctl-direct', 'relay-short'):
    f = [round(c['tps']) for arm, c in firsts if arm == a]
    if f: print(f"first {a:12} {sorted(f)}")
