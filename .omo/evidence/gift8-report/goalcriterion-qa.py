"""Pure predicate unit inputs only: no fabricated media, UI proof, or campaign achievement."""
import copy,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3];OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'tools'))
import gift8_report as r
checks=[]
def check(name,value,observable):
 assert value,(name,observable)
 checks.append(dict(scenario=name,passed=True,observable=observable));print('PASS',name)
urls=[f'https://fixture.invalid/product/{i}' for i in range(5)]
row=dict(id='UNIT-INPUT-ONLY',sessionKey='unit:fixture',valid=True,audit_passed=True,score=1700.25,ui=1700,product_urls=urls)
inspection=dict(id=row['id'],sessionKey=row['sessionKey'],displayedMean=1700,verifiedProductURLs=urls,viewportVerified=True,real_time_verified=True,playable=True,
                media={'demo.mp4':{'ffprobe':{'format':{'duration':'55.0'}}}},full_run_verified=False,target_1700_verified=False,timing='first_frame_during_run',classification='partial_or_post_run')
accepted=r.target_clip_verified(row,inspection)
check('partial during-run1700 clip accepted independently of full-run flag',accepted and inspection['full_run_verified'] is False,dict(target_clip_verified=accepted,full_run_verified=inspection['full_run_verified'],timing=inspection['timing']))
check('inherited old-study full-run target flag is not a gift8 blocker',accepted and inspection['target_1700_verified'] is False,dict(gift8_target=True,inherited_full_run_target=False))
for name,change in [('wrong UI score',dict(displayedMean=1701)),('wrong URLs',dict(verifiedProductURLs=urls[:-1]+['https://fixture.invalid/wrong'])),('wrong session',dict(sessionKey='different')),('wrong rawid',dict(id='different')),('unverified viewport',dict(viewportVerified=False)),('retimed clip',dict(real_time_verified=False)),('unplayable clip',dict(playable=False))]:
 value=r.target_clip_verified(row,inspection|change);check(name+' rejected',not value,dict(target_clip_verified=value))
for name,change in [('rawmean below1700',dict(score=1699.9)),('official UI below1700',dict(ui=1699)),('invalid trial',dict(valid=False)),('failed rawaudit',dict(audit_passed=False)),('duplicate verified URLs',dict(product_urls=urls[:-1]+urls[:1]))]:
 value=r.target_clip_verified(row|change,inspection);check(name+' rejected',not value,dict(target_clip_verified=value))
for duration,expected in [('60',True),('60.001',False),('0',False),('NaN',False),('Infinity',False)]:
 changed=copy.deepcopy(inspection);changed['media']['demo.mp4']['ffprobe']['format']['duration']=duration
 value=r.target_clip_verified(row,changed);check('clip duration '+duration,value is expected,dict(target_clip_verified=value))
early=r.completion_state(1,1,[row['id']],[row],True)
check('verified early target completes goal before eight sends',early['goal_complete'] and early['complete'] and early['passed'] and not early['comparison_complete'] and early['status']=='goal_complete',early)
missing=r.completion_state(1,1,[],[row],False)
check('raw target with missing clip stays attention',not missing['goal_complete'] and not missing['passed'] and missing['status']=='target_needs_attention',missing)
finished_missing=r.completion_state(8,8,[],[row],True)
check('eight sends cannot bypass a missing target clip',finished_missing['comparison_complete'] and not finished_missing['complete'] and not finished_missing['passed'] and finished_missing['status']=='target_needs_attention',finished_missing)
blocked=r.completion_state(1,1,[row['id']],[row],False)
check('verified clip does not erase unrelated audit failure',not blocked['goal_complete'] and not blocked['passed'],blocked)
comparison=r.completion_state(8,8,[],[],True)
check('eight-send below-target study completes comparison only',comparison['comparison_complete'] and comparison['complete'] and comparison['passed'] and not comparison['goal_complete'],comparison)
partial=r.completion_state(3,3,[],[],True)
check('below-target partial study remains incomplete',not partial['complete'] and not partial['passed'],partial)
# The predicates must not rewrite the strict inspector result or the raw row.
check('strict full-run diagnostic remains unchanged',inspection['full_run_verified'] is False and inspection['timing']=='first_frame_during_run',dict(full_run_verified=inspection['full_run_verified'],timing=inspection['timing']))
(OUT/'goalcriterion-results.json').write_text(json.dumps(dict(mode='pure unit predicate inputs; no media/UI evidence and no actual target achievement claimed',pass_=True,checks=checks),indent=2))
