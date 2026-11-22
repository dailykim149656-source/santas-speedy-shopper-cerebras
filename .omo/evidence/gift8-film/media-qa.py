from pathlib import Path
import hashlib, json, shutil, sys
ROOT=Path(__file__).resolve().parents[3];OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'tools'))
import gift8_film
f=gift8_film.film
ident='1236be0d-9fd2-4d3b-ab83-067ad950aeea'
src=f.CACHE/'film-first5027-5037'/ident/'attempt-01'
plan=f.read(f.CACHE/'capture'/ident/'plan.json')
dst=OUT/'existing-real-clip'
dst.mkdir(exist_ok=True)
for name in ('original.mp4','demo.mp4','ready.json','recording.json','capture-timeline.json','viewport-evidence.json'):
 shutil.copyfile(src/name,dst/name)
result=f.inspect(plan['label'],plan,dst)
f.put(OUT/'real-media-inspection.json',result)
assert result['playable'] and result['real_time_verified'] and result['viewportVerified'],result
assert result['timing']=='first_frame_during_run' and result['classification']=='partial_or_post_run' and not result['full_run_verified'] and not result['target_1700_verified'],result
for name in ('original.mp4','demo.mp4'):
 assert result['media'][name]['sha256']==hashlib.sha256((src/name).read_bytes()).hexdigest()
checks=['actual old clip ffprobe playable','media SHA matches source bytes','actual official score and five product URL proof match canonical validation','real duration agrees with capture timeline','actual during-run first frame remains partial; no full-run claim','actual score below1700 never qualifies target']
original=(dst/'demo.mp4').read_bytes()
try:
 (dst/'demo.mp4').write_bytes(b'CORRUPT QA INPUT')
 corrupt=f.inspect(plan['label'],plan,dst)
 f.put(OUT/'corrupt-media-inspection.json',corrupt)
 assert not corrupt['playable'] and not corrupt['target_1700_verified']
 checks.append('corrupt demo rejected by actual ffprobe')
finally:(dst/'demo.mp4').write_bytes(original)
f.inspect(plan['label'],plan,dst)
f.put(OUT/'media-results.json',dict(pass_=True,source=str(src),note='Regression inspection of prior genuine recording, not a new gift8 campaign recording',checks=checks))
print(json.dumps(dict(pass_=True,checks=checks)))
