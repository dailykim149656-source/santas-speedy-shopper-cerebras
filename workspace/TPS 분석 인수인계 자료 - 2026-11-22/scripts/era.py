import json, os, glob, datetime, statistics as st
KST = datetime.timezone(datetime.timedelta(hours=9))
base = os.path.expanduser('~/Library/Application Support/Cerebras Speed Bounty/2026-11-22')
runs = []
for f in glob.glob(base + '/raw*/*.json'):
    try: d = json.load(open(f))
    except Exception: continue
    lab = str(d.get('label', ''))
    if not d.get('startedWall') or not isinstance(d.get('history'), dict): continue
    fam = ('five-categories' in lab or 'first5027' in lab or 'exp2k' in lab or 'speed1500' in lab)
    if not fam: continue
    calls = []
    for m in d['history']['messages']:
        if m.get('role') != 'assistant': continue
        sg = m.get('serverGeneration') or {}
        u = m.get('usage') or {}
        th = sum(len(c.get('thinking', '')) for c in m.get('content', []) if c.get('type') == 'thinking')
        if sg.get('completionMs'):
            calls.append(dict(out=sg['outputTokens'], ms=sg['completionMs'], th=th, stop=m.get('stopReason'),
                              prompt=(u.get('input') or 0) + (u.get('cacheRead') or 0)))
    t = datetime.datetime.fromtimestamp(d['startedWall'] / 1000, KST)
    runs.append(dict(label=lab, t=t, calls=calls))
def era(t):
    h = t.hour + t.minute / 60
    if h < 17.45: return '1 16:18-17:26 record era'
    if h < 19: return '2 18:13-18:45'
    if h < 20.5: return '3 19:12-19:54'
    return '4 21:15-now'
import collections
E = collections.defaultdict(lambda: collections.defaultdict(list))
for r in runs:
    if r['t'].hour < 16: continue
    e = era(r['t'])
    cs = r['calls']
    if cs and cs[0]['stop'] == 'toolUse':
        c = cs[0]; E[e]['first_tps'].append(c['out'] / c['ms'] * 1000); E[e]['first_th'].append(c['th'])
        if c['prompt'] <= 3300: E[e]['first_tps_clean'].append(c['out'] / c['ms'] * 1000)
    for c in cs[1:]:
        if c['stop'] != 'stop': continue
        tps = c['out'] / c['ms'] * 1000
        E[e]['final_tps'].append(tps); E[e]['final_th'].append(c['th'])
        if c['th'] == 0 and 155 <= c['out'] <= 165: E[e]['final0_ms'].append(c['ms']); E[e]['final0_tps'].append(tps)
    E[e]['runs'].append(r['label'][:5])
for e in sorted(E):
    d = E[e]
    def s(k, f='{:.0f}'):
        x = d[k]
        return f"n={len(x)} med={f.format(st.median(x))} max={f.format(max(x))}" if x else 'n=0'
    print(f"== {e}  runs={len(d['runs'])}")
    print('   first call TPS        ', s('first_tps'), '| clean only', s('first_tps_clean'))
    print('   first reasoning chars ', s('first_th'))
    print('   final call TPS        ', s('final_tps'))
    print('   final reasoning chars ', s('final_th'), f"| zero-reasoning finals {len(d['final0_ms'])}/{len(d['final_tps'])}")
    print('   zero-reasoning finals ms', sorted(round(x) for x in d['final0_ms']), 'TPS', sorted(round(x) for x in d['final0_tps']))
