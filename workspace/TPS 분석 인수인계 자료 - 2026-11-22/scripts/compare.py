import json, os, datetime, statistics as st
T = os.path.expanduser('~/Library/Caches/cerebras-speed-bounty/2026-11-22-test/mean-2000')
rows = [json.loads(l) for l in open(T + '/iterations.jsonl') if l.strip()]
rows = [r for r in rows if r['label'] >= 'D5059']
KST = datetime.timezone(datetime.timedelta(hours=9))
out = []
for r in rows:
    raw = json.load(open(f"{T}/runs/{r['label']}.json"))
    calls = []
    for m in raw['history']['messages']:
        if m.get('role') != 'assistant': continue
        sg = m.get('serverGeneration') or {}
        th = sum(len(c.get('thinking', '')) for c in m.get('content', []) if c.get('type') == 'thinking')
        if sg.get('completionMs'):
            calls.append(dict(out=sg['outputTokens'], ms=sg['completionMs'], tps=sg['outputTokens'] / sg['completionMs'] * 1000, th=th, stop=m.get('stopReason')))
    arm = 'relay' if 'relay' in r['label'] else ('control-retry' if r.get('relay_phases') else 'control-direct')
    t = datetime.datetime.fromtimestamp(raw['startedWall'] / 1000, KST).strftime('%H:%M')
    out.append(dict(label=r['label'][:5], arm=arm, t=t, valid=r['valid'], score=r['score'], rl=r.get('rate_limited'), calls=calls, bug=r['label'].startswith('D5059')))
for o in out:
    cs = ' | '.join(f"{c['out']}t/{c['ms']:.0f}ms={c['tps']:.0f} th{c['th']}" for c in o['calls'])
    print(f"{o['label']} {o['t']} {o['arm']:14} valid={str(o['valid'])[0]} score={o['score'] and round(o['score'])} rl={str(o['rl'])[0]} || {cs}")
print()
def summ(name, xs):
    xs = [x for x in xs if x is not None]
    if not xs: print(f"{name:44} n=0"); return
    print(f"{name:44} n={len(xs):2} median={st.median(xs):7.0f} mean={st.mean(xs):7.0f} min={min(xs):6.0f} max={max(xs):6.0f}")
for arm in ('relay', 'control-retry', 'control-direct'):
    g = [o for o in out if o['arm'] == arm and not o['bug']]
    print(f"== {arm}: sent={len(g)} valid={sum(o['valid'] for o in g)} rate-limited-fail={sum(1 for o in g if o['rl'] and not o['valid'])}")
    summ('  score (valid)', [o['score'] for o in g if o['valid']])
    firsts = [o['calls'][0] for o in g if o['calls']]
    finals = [o['calls'][1] for o in g if len(o['calls']) > 1]
    summ('  first TPS (all measured)', [c['tps'] for c in firsts])
    summ('  first out tokens', [c['out'] for c in firsts])
    summ('  first reasoning chars', [c['th'] for c in firsts])
    summ('  final TPS', [c['tps'] for c in finals])
    summ('  final ms', [c['ms'] for c in finals])
    summ('  final out tokens', [c['out'] for c in finals])
    summ('  final reasoning chars', [c['th'] for c in finals])
    print(f"  zero-reasoning finals: {sum(1 for c in finals if c['th']==0)}/{len(finals)}; fast finals (<140ms): {sum(1 for c in finals if c['ms']<140)}/{len(finals)}")
