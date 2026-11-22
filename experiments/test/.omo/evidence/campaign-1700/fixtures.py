import copy
import json
from pathlib import Path
import sys
import tempfile
sys.path.insert(0, str(Path.cwd() / 'tools'))
import campaign_1700 as c

checks = []
def check(name, condition):
    assert condition, name
    checks.append(name)

with tempfile.TemporaryDirectory() as temporary:
    repo = Path(temporary)
    rows = []
    for i in range(16):
        phase = i // 8
        side = c.ORDER[i % 8]
        name = c.PHASES[phase]['AB'.index(side)]
        row = {'id': f'run{i}', 'label': f'D{6000+i}-{name}', 'arm': c.arm_key(c._arm(name)),
               'valid': True, 'method_valid': True, 'recorded_video': False,
               'score': 1000 + (150 if phase == 0 else 250) * (side == 'B'), 'ui': 1000}
        rows.append(row)
        if phase == 1:
            directory = repo / 'runs' / row['id']
            directory.mkdir(parents=True)
            urls = ['https://merchant/catalog?p=0'] if side == 'A' else ['https://merchant/catalog?p=0', 'https://merchant/catalog?p=3']
            candidates = [f'https://merchant/product/{n}' for n in range(6)]
            sources = [{'url': url, 'accepted': True, 'products': candidates if side == 'A' else candidates[j*3:(j+1)*3]} for j, url in enumerate(urls)]
            (directory/'plan.json').write_text(json.dumps({'prompt':'Fetch\n'+'\n'.join(json.dumps({'url':url}) for url in urls)}))
            (directory/'evidence.json').write_text(json.dumps({'retail_sources':sources[::-1]}))
    for i in range(16):
        got, _ = c.decision(repo, 6000, rows[:i][::-1])
        check(f'resume_slot_{i+1}', got == c._arm(c.PHASES[i//8]['AB'.index(c.ORDER[i%8])]))
    result = c.summary(repo, 6000, rows)
    check('strongest_candidate', result['promotion'] == c.PHASES[1][1])
    check('parallel_result_order', result['phases'][1]['valid_pairs'] == 4)
    check('phase3_control', result['next_arm'] == c._arm(c.CONTROL))
    for i in range(4):
        arm, _ = c.decision(repo, 6000, rows)
        check(f'phase3_slot_{i+1}', arm == c._arm(c.CONTROL if c.ORDER[i] == 'A' else c.PHASES[1][1]))
        rows.append(dict(rows[0], id=f'run{16+i}', label=f'D{6016+i}-{arm[0]}', arm=c.arm_key(arm)))
    check('max20', c.decision(repo,6000,rows)[0] is None)
    rows = rows[:16]
    broken = copy.deepcopy(rows)
    broken[3]['arm'] = 'unexpected|0.2|low'
    check('unexpected_arm_stops', 'unexpected arm' in c.decision(repo,6000,broken)[1])
    check('duplicate_stops', 'duplicate' in c.decision(repo,6000,rows+[rows[0]])[1])
    check('old_rows_ignored', c.decision(repo,6001,rows[:1])[0] == c._arm(c.CONTROL))
    target = dict(rows[0], score=1700., ui=1700, recorded_video=True)
    check('target_inclusive', c.decision(repo,6000,[target])[0] is None)
    for key, value in [('score',1699.99),('ui',1699),('method_valid',None),('method_valid',1),('valid',False),('recorded_video',False),('score',float('nan'))]:
        bad = dict(target, **{key:value})
        check('reject_target_'+key+'_'+str(value), c.decision(repo,6000,[bad])[0] is not None)
    no_gain = [dict(row,score=1000) for row in rows]
    check('no_promotion_stops16', c.decision(repo,6000,no_gain)[0] is None)
    invalid = copy.deepcopy(rows)
    invalid[1]['valid'] = False
    check('validity_regression_blocks', not c.summary(repo,6000,invalid)['phases'][0]['qualified'])
    weak = copy.deepcopy(rows)
    weak[1]['score'] = 900
    weak[2]['score'] = 900
    check('two_wins_block', not c.summary(repo,6000,weak)['phases'][0]['qualified'])
    malformed = copy.deepcopy(rows)
    malformed[1]['method_valid'] = False
    malformed[2]['method_valid'] = False
    check('two_valid_pairs_block', not c.summary(repo,6000,malformed)['phases'][0]['qualified'])
    changed = repo/'runs/run9/evidence.json'
    evidence = json.loads(changed.read_text())
    evidence['retail_sources'][0]['products'][0] = 'https://merchant/product/changed'
    changed.write_text(json.dumps(evidence))
    result = c.summary(repo,6000,rows)
    check('candidate_change_excludes_pair', result['phases'][1]['valid_pairs'] == 3)
    check('candidate_change_audit', result['phases'][1]['pairs'][0]['audit'] == ['ordered candidates differ'])
    evidence['retail_sources'][0]['products'] = evidence['retail_sources'][1]['products']
    changed.write_text(json.dumps(evidence))
    check('duplicate_candidates_rejected', c._candidates(repo,rows[9])[0] is None)
    (repo/'runs/run10/evidence.json').unlink()
    check('missing_evidence_excludes_pair', c.summary(repo,6000,rows)['phases'][1]['valid_pairs'] == 2)
    check('fallback_qualified_candidate', c.summary(repo,6000,rows)['promotion'] == c.PHASES[0][1])
    print(json.dumps({'status':'PASS','count':len(checks),'scenarios':checks,'provider_calls':0},indent=2))
