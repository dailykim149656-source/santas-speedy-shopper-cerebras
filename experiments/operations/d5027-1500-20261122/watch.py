"""Print only changed trial rows or a campaign state requiring attention."""
from pathlib import Path
import json,sys,time
from datetime import datetime
D=Path(__file__).resolve().parent
C=D.parent
since=int(sys.argv[1])
until=time.monotonic()+float(sys.argv[2])
while True:
 rows=json.loads((D/'trials.json').read_bytes())
 state=json.loads((C/'status.json').read_bytes())
 stop=(C/'stop-requested')
 if len(rows)>since or stop.exists() or state.get('phase')=='needs_attention' or time.monotonic()>=until:
  fields=('label','first','final','score','valid','clean','rate_limited','attempts','http429','clean_wire','media','products')
  for r in rows[since:]:
   print(json.dumps({k:(round(r[k],2) if isinstance(r[k],float) else r[k]) for k in fields},ensure_ascii=False))
  print(datetime.now().astimezone().strftime('%H:%M:%S'),len(rows),state.get('phase'),state.get('label'),('STOP '+stop.read_text()[:130]) if stop.exists() else '')
  break
 time.sleep(2)
