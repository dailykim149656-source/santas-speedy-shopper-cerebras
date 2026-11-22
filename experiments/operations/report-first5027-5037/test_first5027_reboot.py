from pathlib import Path
import json, tempfile, argparse, sys
sys.path.insert(0,'/tmp')
import report_first5027 as r
with tempfile.TemporaryDirectory() as tmp:
 b=Path(tmp); a=argparse.Namespace(cache=b/'test',main_cache=b/'main',exp_cache=b/'exp',project=b,start=5037)
 for cache in (a.cache,a.exp_cache,a.main_cache): (cache/'runs').mkdir(parents=True)
 p=a.cache/'first5027-5037-reservation.jsonl'
 locks=[str(d/'loop.lock') for d in (a.cache,a.main_cache,a.exp_cache)]
 def event(event,ms,pid):
  v={'event':event,'at_ms':ms,'pid':pid}
  if event=='reserved':v['locks']=locks
  return json.dumps(v)+'\n'
 def send(s,e):
  n='D5039-first5027-extract-text'
  x=dict(id='test',label=n,startedWall=s,ended={'time':e,'terminal':'final'},history={'messages':[]})
  (a.cache/'runs'/(n+'.json')).write_text(json.dumps(x))
 p.write_text(event('reserved',1,11)+event('reserved',100,12)+event('releasing',200,12))
 send(120,180)
 v=r.overlap_audit(a);assert v['verified'] and v['reservations'][0]['superseded_at_ms']==100
 send(10,30);assert not r.overlap_audit(a)['verified']
 send(99,150);assert not r.overlap_audit(a)['verified']
 p.write_text(event('reserved',1,11));send(120,180);assert not r.overlap_audit(a)['verified']
 p.write_text(event('reserved',1,11)+event('releasing',300,99));assert not r.overlap_audit(a)['verified']
print('5/5 interrupted/resumed lock scenarios passed')
