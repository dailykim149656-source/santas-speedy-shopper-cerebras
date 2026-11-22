import copy,json,pathlib,sys,unittest
sys.path.insert(0,str(pathlib.Path.cwd()/'speed-bounty-evidence-test/tools'))
import first5027 as f
REPO=pathlib.Path.cwd()/'speed-bounty-evidence-test'
def rows(order=f.ORDER):
 return [dict(id=f'id-{i}',label=f'D{7000+i*2}-x',arm=f.arm_key(f._arm(s)),valid=True,method_valid=True,score=1400+(20 if s!='A' else 0),first_tps=900+(150 if s!='A' else 0),first_ms=400-(20 if s!='A' else 0),first_tokens=400,first_think_chars=10,final_tps=1800,started_wall=1795335856859+i*10000,product_urls=[f'https://aisynthesis.com/product/{n}/' for n in range(5)],terminal_429=False) for i,s in enumerate(order)]
class Schedule(unittest.TestCase):
 def test_all_slots_and_gap_labels(self):
  rs=rows(f.ORDER+'ABBA')
  for i,side in enumerate(f.ORDER+'ABBA'):
   result=f.summary(REPO,7000,rs[:i]);self.assertEqual(result['next_arm'],f._arm(side))
  result=f.summary(REPO,7000,rs);self.assertTrue(result['confirmation']['qualified']);self.assertIsNone(result['next_arm']);self.assertEqual(result['completed'],16)
 def test_invalid_sequences_and_duplicates(self):
  for mutation in ('number','id','arm'):
   rs=rows()[:2]
   if mutation=='number':rs[1]['label']=rs[0]['label']
   elif mutation=='id':rs[1]['id']=rs[0]['id']
   else:rs[1]['arm']=f.arm_key(f._arm('C'))
   self.assertIsNone(f.summary(REPO,7000,rs)['next_arm'])
 def test_pair_rejections_and_boundary(self):
  rs=rows();rs[0]['started_wall']=rs[1]['started_wall']+900000
  self.assertTrue(f.summary(REPO,7000,rs)['pairs'][0]['valid'])
  rs[0]['started_wall']+=1
  self.assertIn('send times more than 15 minutes apart',f.summary(REPO,7000,rs)['pairs'][0]['reasons'])
  rs=rows();rs[0]['product_urls']=list(reversed(rs[0]['product_urls']))
  self.assertIn('ordered products differ (inventory change)',f.summary(REPO,7000,rs)['pairs'][0]['reasons'])
 def test_qualification_failure(self):
  rs=rows()
  for r in rs:r['first_tps']=900
  result=f.summary(REPO,7000,rs);self.assertIsNone(result['promotion']);self.assertIsNone(result['next_arm'])
 def test_selection_tiebreak_and_confirmation_failure(self):
  rs=rows()
  for r in rs:
   if r['arm']==f.arm_key(f._arm('C')):r['first_ms']=350
  self.assertEqual(f.summary(REPO,7000,rs)['promotion'],f.ARMS['C'])
  rs=rows(f.ORDER+'ABBA');rs[-2]['valid']=False
  self.assertFalse(f.summary(REPO,7000,rs)['confirmation']['qualified'])
 def test_raw_target_stops_without_video(self):
  rs=rows()[:1];rs[0]['score']=1700
  self.assertIsNone(f.summary(REPO,7000,rs)['next_arm'])
 def test_failures_count_and_resume_advisory(self):
  rs=rows()[:2]
  for r in rs:r.update(valid=False,method_valid=False,terminal_429=True)
  result=f.summary(REPO,7000,rs);self.assertEqual(result['completed'],2);self.assertTrue(result['pause_required']);self.assertEqual(result['next_arm'],f._arm('C'))
 def test_429_terminal_only(self):
  raw={'id':'abc','ended':{'terminal':'error'},'history':{'messages':[{'role':'assistant','provider':'cerebras','__openclaw':{'runId':'abc'},'stopReason':'error','errorMessage':'429 High traffic'}]}}
  self.assertTrue(f.terminal_429(raw));raw['ended']['terminal']='final';self.assertFalse(f.terminal_429(raw))
  raw['ended']['terminal']='error';raw['history']['messages'].append({'role':'assistant','__openclaw':{'runId':'abc'},'stopReason':'stop'});self.assertFalse(f.terminal_429(raw))
 def test_actual_partial_terminal_preserves_first(self):
  root=pathlib.Path.home()/'Library/Application Support/Cerebras Speed Bounty/2026-11-22/raw-test'
  raw=next(json.loads(p.read_text()) for p in root.glob('*.json') if 'D5032-' in p.read_text()[:300])
  plan=json.loads((REPO/'runs'/raw['id']/'plan.json').read_text())
  calls=[dict(message_index=i,response_id=m['responseId'],**m['serverGeneration']) for i,m in enumerate(raw['history']['messages']) if m.get('role')=='assistant' and m.get('__openclaw',{}).get('runId')==raw['id'] and m.get('serverGeneration')]
  result=f.metrics(plan,raw,{'run_id':raw['id'],'calls':calls,'retail_sources':[]})
  self.assertTrue(result['identity_valid']);self.assertGreater(result['first_tps'],0);self.assertIsNone(result['final_tps'])
 def test_real_d5027_metrics_and_identity_mutation(self):
  ident='cd75e5e0-be7c-471f-a9ab-c9e6f0d1bd77';plan=json.loads((REPO/'runs'/ident/'plan.json').read_text())
  raw=json.loads((pathlib.Path.home()/'Library/Application Support/Cerebras Speed Bounty/2026-11-22/raw-test'/f'{ident}.json').read_text())
  evidence=json.loads((REPO/'runs'/ident/'evidence.json').read_text())
  validation={'run_id':ident,'retail_sources':evidence['retail_sources'],'calls':[dict(message_index=c['message_index'],response_id=c['responseId'],**c['serverGeneration']) for c in evidence['calls']]}
  result=f.metrics(plan,raw,validation);self.assertTrue(result['identity_valid']);self.assertEqual(result['first_tokens'],447);self.assertEqual(result['first_think_chars'],304);self.assertAlmostEqual(result['first_tps'],1035.39,places=2);self.assertEqual(len(result['product_urls']),5)
  validation['calls'][0]['response_id']='wrong';self.assertFalse(f.metrics(plan,raw,validation)['identity_valid'])
if __name__=='__main__':unittest.main(verbosity=2)
