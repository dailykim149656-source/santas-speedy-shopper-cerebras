import json
from pathlib import Path
import tempfile
import unittest

from report_longgap import section


class ReportFixture(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.base = Path(tmp.name)
        self.repo = self.base / 'repo'
        self.results = []
        self.assignments = []
        self.order = [60,90,90,60]

    def add(self, ident, start, end, first, final, valid=True, limited=False, retries=0):
        run = dict(id=ident, label=ident, end=end*1000, valid=valid, rate_limited=limited, relay_mode='retry-only',
                   first=first, final=final, score=(first + final)/2 if valid else first,
                   first_ms=210 if first else None, final_ms=115 if final else None,
                   first_reasoning=4 if first else None, final_reasoning=3 if final else None,
                   final_output_tokens=161 if final else None, http429=retries)
        path = self.repo/'runs'/ident/'evidence.json'
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps(dict(startedWall=start*1000, ended={'time':end*1000})))
        self.results.append(run)
        return run

    def assignment(self, prior, run, arm):
        i = len(self.assignments)
        self.assignments.append(dict(index=i+1,pair=i//2+1,slot=i%2+1,requested_seconds=arm,
                                     previous_uuid=prior['id'],phase='complete',
                                     outcome={'run_id':run['id'],'valid':run['valid']}))

    def render(self, status="active", failed_run=None):
        (self.base/'longgap-state.json').write_text(json.dumps(
            {'config':{'order_seconds':self.order},'assignments':self.assignments,'status':status,'failed_run_id':failed_run}))
        return '\n'.join(section(self.base,self.repo,self.results))

    def test_absent_and_empty(self):
        self.assertIn('2쌍', '\n'.join(section(self.base,self.repo,[])))
        self.assertIn('0/4회', self.render())

    def test_early_terminal_failure_counts_and_inconclusive(self):
        prev = self.add('seed',0,10,900,900)
        a = self.add('a',75,90,800,1000)
        b = self.add('b',185,195,1000,1200)
        c = self.add('c',288,310,None,None,False,True,10)
        for prior, run, arm in ((prev,a,60),(a,b,90),(b,c,90)):
            self.assignment(prior,run,arm)
        output = self.render('inconclusive_after_failure','c')
        self.assertIn('3/4회 종료, 1/2쌍 종료, 양쪽 모두 유효한 쌍 1개', output)
        self.assertIn('c 429 종료로 전송 3/4회', output)
        self.assertIn('**+200.00 TPS**',output)
        self.assertIn('판정 보류.',output)
        self.assertIn('| 2 | 90 → 60 | — | — | — | 조기 종료로 미완료 |',output)
        self.assertIn('65.0 / 75.0',output)
        self.assertIn('| 90초 | 2/2 | 1 | 1 | 10 | 220.0 | 16.36 | b |', output)
        self.assertIn('a/evidence.json',output)

    def test_directional_only_with_two_same_sign_pairs(self):
        prev = self.add('seed',0,10,900,900)
        for i,arm in enumerate(self.order):
            score = 1000 if arm == 60 else 1040
            new = self.add('n'+str(i),100+i*200,130+i*200,score,score)
            self.assignment(prev,new,arm)
            prev = new
        self.assertIn('두 유효 쌍에서 모두 90초 조건',self.render())
        self.results[-1]['score'] = 1060
        self.assertIn('판정 보류.',self.render())
        self.results[-1]['score'] = 1040
        self.assertIn('동률 1쌍',self.render())
        self.assertIn('판정 보류.',self.render())

    def test_pending_and_wrong_order(self):
        self.add('seed',0,10,900,900)
        self.assignments.append(dict(index=1,pair=1,slot=1,requested_seconds=60,
                                     previous_uuid='seed',phase='dispatched'))
        self.assertIn('실행 중',self.render())
        self.order = [60,90] * 6
        self.assertIn('집계를 보류',self.render())

    def prepare_amendment(self, recovery_valid=True):
        seed = self.add('seed',0,5,880,880)
        first = self.add('r1',70,100,None,None,False,True,10)
        second = self.add('r2',168,250,800,900,recovery_valid,not recovery_valid,4)
        self.assignment(seed,first,60)
        self.render('inconclusive_after_failure','r1')
        (self.base/'longgap-recovery-config.json').write_text(json.dumps(
            {'first_id':'r1','anchor_id':'seed','max_total_transmissions':4}))
        self.modified = [dict(self.assignments[0], kind='interval'),
                         dict(index=2,kind='recovery',requested_seconds=None,phase='complete',
                              previous_uuid=first['id'],outcome={'run_id':second['id'],'valid':recovery_valid})]

    def amended(self,status):
        (self.base/'longgap-recovery-state.json').write_text(json.dumps(
            {'status':status,'assignments':self.modified}))
        return '\n'.join(section(self.base,self.repo,self.results))

    def test_amended_before_allocator_and_while_waiting(self):
        self.prepare_amendment()
        report = '\n'.join(section(self.base,self.repo,self.results))
        self.assertIn('종료 결과 **2/4회**, 유효 1회',report)
        self.assertIn('| 2 | 실패 후 기본 대기 | r1 → [r2]',report)
        self.assertNotIn('두 유효 쌍',report)
        self.modified.append(dict(index=3,kind='interval',requested_seconds=90,phase='dispatched',
                                  previous_uuid='r2'))
        self.assertIn('| 3 | 90초 | r2 → … | 진행 중',self.amended('active'))

    def test_amended_valid_90_60_pair_and_no_duplicate_total(self):
        self.prepare_amendment()
        self.add('r3',345,365,1200,1300)
        self.add('r4',431,450,900,1100)
        self.modified.extend([dict(index=3,kind='interval',requested_seconds=90,phase='complete',
                                   previous_uuid='r2',outcome={'run_id':'r3','valid':True}),
                              dict(index=4,kind='interval',requested_seconds=60,phase='complete',
                                   previous_uuid='r3',outcome={'run_id':'r4','valid':True})])
        report=self.amended('complete')
        self.assertIn('종료 결과 **4/4회**, 유효 3회',report)
        self.assertIn('**+250.00 TPS**',report)
        self.assertIn('| 60초 | 2 | 1 | 1 | 10 | 180.0 | 20.00 |',report)
        self.assertEqual(report.count('[r1]'),1)
        self.assertIn('유효 1쌍',report)

    def test_amended_unpaired_90_and_terminal_failure(self):
        self.prepare_amendment(recovery_valid=False)
        self.add('r3',380,400,880,900)
        self.add('r4',499,510,1100,1200)
        self.modified.extend([dict(index=3,kind='recovery',requested_seconds=None,phase='complete',
                                   previous_uuid='r2',outcome={'run_id':'r3','valid':True}),
                              dict(index=4,kind='interval',requested_seconds=90,phase='complete',
                                   previous_uuid='r3',outcome={'run_id':'r4','valid':True})])
        self.assertIn('판정 보류.',self.amended('complete'))
        self.assertIn('| 실패 후 기본 대기 | 2 | 1 | 1',self.amended('complete'))
        self.modified.pop()
        self.assertIn('종료 결과 **3/4회**',self.amended('inconclusive'))
        self.assertIn('판정 보류.',self.amended('inconclusive'))

    def test_impossible_timestamps(self):
        p = self.add('seed',0,100,900,900)
        a = self.add('a',95,110,1100,1000)
        self.assignment(p,a,60)
        with self.assertRaisesRegex(ValueError,'Invalid timing'):
            self.render()


if __name__ == '__main__':
    unittest.main()
