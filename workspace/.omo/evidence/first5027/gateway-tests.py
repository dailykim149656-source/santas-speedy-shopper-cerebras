import json,pathlib,sys,tempfile,unittest
sys.path.insert(0,str(pathlib.Path.cwd()/'speed-bounty-evidence-test/tools'))
import first5027 as f
EVIDENCE=pathlib.Path('.omo/evidence/first5027')
class Gateway(unittest.TestCase):
 def test_real_terminal_429_runs(self):
  log=pathlib.Path.home()/'Library/Caches/cerebras-speed-bounty/2026-11-22-test/gateway.log'
  rawroot=pathlib.Path.home()/'Library/Application Support/Cerebras Speed Bounty/2026-11-22/raw-test'
  observed={};fixtures=[]
  for p in rawroot.glob('*.json'):
   raw=json.loads(p.read_text())
   if any(raw.get('label','').startswith(label+'-') for label in ['D5029','D5032','D5035']):
    observed[raw['label']]=f.terminal_429(raw,log)
    fixtures.append({'id':raw['id'],'label':raw['label'],'ended':raw['ended'],'provider_events':[line for line in log.read_text().splitlines() if raw['id'] in line and 'embedded run agent end:' in line][-1:]})
  self.assertEqual(len(observed),3);self.assertTrue(all(observed.values()),observed)
  (EVIDENCE/'gateway-fixtures.json').write_text(json.dumps({'observed':observed,'fixtures':fixtures},indent=2)+'\n')
 def test_last_provider_end_and_abort(self):
  raw={'id':'fixture-run','ended':{'terminal':'error'},'history':{'messages':[]}}
  prefix='[agent/embedded] embedded run agent end: runId=fixture-run '
  rate=prefix+'isError=true provider=cerebras rawError=429 high traffic\n'
  cases={'later_generic_error':(rate+'lane task error: runId=fixture-run error=generic\n',True),
         'recovered_provider':(rate+prefix+'isError=false provider=cerebras\n',False),
         'different_final_failure':(rate+prefix+'isError=true provider=cerebras rawError=401 invalid key\n',False),
         'actual_abort':(rate+'embedded run done: runId=fixture-run aborted=true\n',False),
         'not_aborted':(rate+'embedded run done: runId=fixture-run aborted=false\n',True),
         'wrong_run_suffix':(rate.replace('runId=fixture-run ','runId=fixture-run-other '),False),
         'wrong_provider':(rate.replace('provider=cerebras','provider=other'),False)}
  with tempfile.TemporaryDirectory() as directory:
   path=pathlib.Path(directory)/'gateway.log'
   for name,(content,expected) in cases.items():
    with self.subTest(name=name):path.write_text(content);self.assertEqual(f.terminal_429(raw,path),expected)
   path.write_text(rate);raw['ended']['terminal']='final';self.assertFalse(f.terminal_429(raw,path))
  (EVIDENCE/'gateway-synthetic-fixtures.json').write_text(json.dumps(cases,indent=2)+'\n')
if __name__=='__main__':unittest.main(verbosity=2)
