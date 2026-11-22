from pathlib import Path
from types import SimpleNamespace
from tempfile import TemporaryDirectory
from unittest import TestCase
import hashlib,json,sys
STAGE=Path(__file__).resolve().parent
sys.path[:0]=[str(STAGE),str(STAGE.parent)]
from gap_recovery import GapRecovery

SHA='a'*64
TIME=2_000_000_000
def row(n,ok):
    return {'id':str(n),'valid':ok,'rate_limited':not ok,'commit':'fixture'}

class Four(TestCase):
    def setUp(self):
        d=TemporaryDirectory();self.addCleanup(d.cleanup);self.d=Path(d.name)
        self.rows=[row(0,True),row(1,False)]
        self.orig={'index':1,'mode':'retry-only','requested_seconds':60,'phase':'complete','history_cursor':1,
                   'outcome':{'run_id':'1','valid':False,'rate_limited':True}}
        self.old=SimpleNamespace(config={'anchor_id':'0','history_start':1,'relay_sha256':SHA},
                                 state={'status':'inconclusive_after_failure','failed_run_id':'1','assignments':[self.orig]})
        cfg=dict(version=1,max_total_transmissions=4,registered_at='2026-11-22T00:00:00+00:00',first_id='1',anchor_id='0')
        (self.d/'longgap-recovery-config.json').write_text(json.dumps(cfg))
    def manager(self):
        return GapRecovery(self.d,TIME+100,self.old,lambda r,e,c:{'valid':r['valid'],'rate_limited':r['rate_limited']})
    def select(self,m):
        return m.select(self.rows,set(),TIME,lambda r:r['valid'],SHA)
    def run_slot(self,expected,ok):
        m=self.manager()
        e=self.select(m)
        self.assertEqual(e['requested_seconds'],expected)
        cmd=['x','--once']+([] if expected is None else ['--d5027-post-success-seconds',str(expected)])
        m.dispatch(e,self.rows,set(),cmd,TIME)
        self.rows.append(row(len(self.rows),ok))
        m.reconcile_terminal(self.rows)
        return m
    def test_adopt_successful_slot2_and_one_reverse_pair(self):
        self.rows.append(row(2,True))
        self.run_slot(90,True)
        m=self.run_slot(60,True)
        self.assertEqual([e['requested_seconds'] for e in m.state['assignments']],[60,None,90,60])
        self.assertEqual(m.state['assignments'][1]['origin'],'existing_default_recovery')
        self.assertEqual(m.state['status'],'complete')
        self.assertIsNone(self.select(self.manager()))
    def test_slot2_fail_recovery3_then_lone90(self):
        self.run_slot(None,False)
        self.run_slot(None,True)
        m=self.run_slot(90,True)
        self.assertEqual([e['requested_seconds'] for e in m.state['assignments']],[60,None,None,90])
        self.assertIsNone(self.select(m))
    def test_failed90_never_repeats(self):
        self.rows.append(row(2,True))
        m=self.run_slot(90,False)
        self.assertEqual(m.state['status'],'inconclusive')
        self.assertIsNone(self.select(self.manager()))
        self.assertEqual(len(m.state['assignments']),3)
    def test_two_ineligible_recoveries_stop(self):
        self.rows.append(row(2,False))
        m=self.run_slot(None,False)
        self.assertIsNone(self.select(m))
        self.assertEqual(m.state['status'],'inconclusive')
        self.assertEqual(len(m.state['assignments']),3)
    def test_uncertain_dispatch_no_retry_extra_history_no_adoption(self):
        self.rows.append(row(2,True))
        m=self.manager();e=self.select(m)
        m.dispatch(e,self.rows,set(),['x','--once','--d5027-post-success-seconds','90'],TIME)
        with self.assertRaisesRegex(RuntimeError,'no automatic retry'):
            self.manager().reconcile(self.rows,set())
        m=self.manager();m.reconcile(self.rows,{'presend'})
        self.assertEqual(m.state['assignments'][-1]['phase'],'allocated')
        self.assertEqual(len(m.state['assignments']),3)
    def test_extra_unowned_third_row_halts(self):
        self.rows.extend([row(2,True),row(3,True)])
        with self.assertRaisesRegex(RuntimeError,'unscheduled physical'):
            self.select(self.manager())

    def test_controller_stops_on_result_and_restart_before_fifth_dispatch(self):
        from contextlib import ExitStack
        from unittest.mock import patch,Mock
        import supervisor as s
        root=self.d/'test';cache=root/'mean-2000'
        cache.mkdir(parents=True)
        for name in ('2026-11-22','2026-11-22-exp2000'):
            parent=self.d/name/'mean-2000';parent.mkdir(parents=True);(parent/'loop.lock').touch()
        (cache/'loop.lock').touch()
        (self.d/'stop-after-longgap').touch()
        (self.d/'campaign.json').write_text(json.dumps({'history_start':0,'threshold':1500,
                'initial_head':'fixture','deadline':'2100-01-01T00:07:00+00:00'}))
        self.rows.append(row(2,True))
        def status():
            (cache/'status.json').write_text(json.dumps({'phase':'result','id':self.rows[-1]['id']}))
        status()
        cd=Mock(state=None);cd.select.return_value=None
        ab=Mock(state=None);ab.select.return_value=None
        lg=Mock(state=self.old.state,config=self.old.config);lg.select.return_value=None
        commands=[]
        def child(command,**_):
            if len(commands)>=2:
                raise AssertionError('physical send #5 attempted')
            commands.append(command)
            def wait():
                self.rows.append(row(len(self.rows),True));status();return 0
            return SimpleNamespace(wait=wait)
        with ExitStack() as stack:
            stack.enter_context(patch.multiple(s,CAMPAIGN_DIR=self.d,ROOT=root,CACHE=cache))
            stack.enter_context(patch.object(s,'Cadence',return_value=cd))
            stack.enter_context(patch.object(s,'RequiredAB',return_value=ab))
            stack.enter_context(patch.object(s,'LongGap',return_value=lg))
            stack.enter_context(patch.object(s.os,'dup2'))
            stack.enter_context(patch.object(s.subprocess,'Popen',side_effect=child))
            for k,fn in {'history':lambda:list(self.rows),'reconcile':lambda *a:(list(self.rows),False,set()),
                         'current_source_hash':lambda:SHA,'cadence_eligible':lambda r:r['valid'],
                         'cooldown_until':lambda *a:0,'report':lambda:None,'controls':lambda *a:None,
                         'git':lambda *a:b'test' if a[0]=='branch' else b'',
                         'audit_longgap_outcome':lambda r,e,c:{'valid':r['valid'],'rate_limited':r['rate_limited']}}.items():
                stack.enter_context(patch.object(s,k,side_effect=fn))
            self.assertEqual(s.main(),0)
            self.assertEqual([cmd[-1] for cmd in commands],['90','60'])
            receipt=json.loads((cache/'stop-requested').read_bytes())
            self.assertEqual(receipt['reason'],'requested stop after four-slot comparison')
            self.assertEqual(s.main(),0)
            self.assertEqual(len(commands),2)
