"""Offline fixtures for four fixed interval transmissions and unchanged fallback."""
from contextlib import ExitStack
from datetime import datetime, timezone
import json
import hashlib
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
import uuid
from unittest.mock import Mock, patch

STAGE = Path(__file__).resolve().parent
sys.path[:0] = [str(STAGE), str(STAGE.parent)]
from longgap import LongGap, activate_pending
import supervisor

SHA = 'a' * 64
ORDER = [60, 90, 90, 60]
CAP = 4102444800
NOW = 2000000000


def put(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj))


def row(ok=True):
    return {'id': str(uuid.uuid4()), 'valid':ok, 'method_valid':ok,
            'rate_limited':not ok, 'commit':'fixture'}


def observe(r, e, config):
    return {'valid': r['valid'], 'rate_limited': r['rate_limited'], 'mode':e['mode'], 'terminal':'final' if r['valid'] else 'error'}


class Allocation(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)
        self.rows = [row()]
        self.ab = SimpleNamespace(config={'relay_sha256':SHA},state={
            'status':'baseline_after_screening', 'screening':{'pass':False},
            'assignments':[{'phase':'complete','outcome':{'history_index':0}} for _ in range(16)]})
        self.config = {'version':1,'enabled':True,'registered_at':'2026-01-01T00:00:00+00:00',
                       'cutoff':'2100-01-01T00:00:00+00:00','history_start':1,
                       'anchor_id':self.rows[0]['id'],'relay_sha256':SHA,'order_seconds':ORDER}
        self.prereg={'version':1,'order_seconds':ORDER,'created':self.config['registered_at'],
                     'pairs':[[60,90],[90,60]],'max_assignments':4}
        put(self.dir/'longgap-config.json', self.config)
        put(self.dir/'longgap-prereg.json', self.prereg)
        self.sealed = set()

    def manager(self):
        return LongGap(self.dir, CAP, observe)

    def choose(self,m,now=NOW,sha=SHA):
        return m.select(self.rows,self.sealed,now,self.ab,sha,lambda r:r['valid'])

    def dispatch(self,m):
        e=self.choose(m)
        args=['loop','--once','--d5027-post-success-seconds',str(e['requested_seconds'])]
        m.dispatch(e,self.rows,self.sealed,args,NOW)
        return e

    def finish(self,m,ok=True):
        e=self.dispatch(m)
        self.rows.append(row(ok))
        m.reconcile_terminal(self.rows)
        return e

    def test_four_and_no_more_across_restarts(self):
        for i,seconds in enumerate(ORDER):
            m=self.manager()
            e=self.finish(m)
            self.assertEqual((e['index'],e['pair'],e['slot'],e['requested_seconds']), (i+1,i//2+1,i%2+1,seconds))
            self.assertEqual(e['mode'],'retry-only')
            self.assertEqual(e['outcome']['run_id'],self.rows[-1]['id'])
            self.assertEqual(e['outcome']['evidence'],f"runs/{self.rows[-1]['id']}/evidence.json")
        m=self.manager()
        self.assertEqual(m.state['status'],'complete')
        self.assertIsNone(self.choose(m))
        self.rows.append(row())
        self.assertIsNone(self.choose(m))

    def test_429_hard_early_stop_in_all_slots(self):
        for idx in range(4):
            with self.subTest(idx=idx):
                self.rows=self.rows[:1]
                (self.dir/'longgap-state.json').unlink(missing_ok=True)
                for _ in range(idx):
                    self.finish(self.manager())
                e=self.finish(self.manager(),False)
                m=self.manager()
                self.assertEqual(m.state['status'],'inconclusive_after_failure')
                self.assertEqual(m.state['failed_run_id'],e['outcome']['run_id'])
                self.assertEqual(len(m.state['assignments']),idx+1)
                self.assertFalse(e['outcome']['valid'])
                self.rows.append(row())
                self.assertIsNone(self.choose(m))
                self.assertEqual(len(m.state['assignments']),idx+1)

    def test_failure_counts_when_product_invalid_without_429(self):
        m=self.manager()
        self.dispatch(m)
        r=row(False);r['rate_limited']=False
        self.rows.append(r)
        m.reconcile_terminal(self.rows)
        self.assertEqual(m.state['status'],'inconclusive_after_failure')
        self.assertIsNone(self.choose(m))

    def test_proven_presend_only_preserves_slot_and_ambiguous_halts(self):
        m=self.manager()
        e=self.dispatch(m)
        with self.assertRaisesRegex(RuntimeError,'no automatic retry'):
            self.manager().reconcile(self.rows,set())
        self.sealed={'proven-presend'}
        m=self.manager();m.reconcile(self.rows,self.sealed)
        self.assertEqual(self.choose(m)['attempts'][0]['phase'],'proven_presend')
        with self.assertRaisesRegex(RuntimeError,'dispatch'):
            m.dispatch(self.choose(m),self.rows,self.sealed,['loop','--once','--d5027-first-required'],NOW)
        self.finish(m)
        self.assertEqual(len(m.state['assignments']),1)
        self.assertEqual(len(m.state['assignments'][0]['attempts']),2)
        self.assertEqual(e['previous_uuid'],m.state['assignments'][0]['previous_uuid'])

    def test_only_after_ab_all_stages_and_eligible_anchor(self):
        m=self.manager(); self.ab.state['status']='confirmation'
        self.assertIsNone(self.choose(m))
        self.ab.state['status']='baseline_after_confirmation'
        self.ab.state['screening']['pass']=True
        with self.assertRaisesRegex(RuntimeError,'terminal decision'):
            self.choose(m)
        self.ab.state['assignments'] += self.ab.state['assignments'][:8]
        self.ab.state['confirmation']={'pass':False}
        self.rows[-1]['valid']=False
        with self.assertRaisesRegex(RuntimeError,'eligible A'):
            self.choose(m)
        self.rows[-1]['valid']=True
        self.assertEqual(self.choose(m)['index'],1)

    def setup_short_ab(self, n):
        self.rows[:] = [row() for _ in range(n + 1)]
        self.config.update(history_start=len(self.rows), anchor_id=self.rows[-1]['id'])
        put(self.dir/'longgap-config.json', self.config)
        put(self.dir/'required-ab-cap.json', dict(version=1, max_transmissions=4,
            allow_confirmation=False, registered_at='2026-11-22T14:46:10+00:00', reason='user_requested_minimum'))
        self.ab.state.update(reduced_cap=4, confirmation=None, screening={'n_sent':n,'pass':False, 'confirmation_allowed':False,
                      'end_reason':'no_valid_B_after_three' if n==3 else 'four_transmissions_reached'},
            assignments=[{'arm':arm,'phase':'complete','history_cursor':i,
                         'outcome':{'valid':arm=='A','run_id':self.rows[i]['id'],'history_index':i,'sent':True}}
                        for i,arm in enumerate('ABBA'[:n])])

    def test_reduced_ab_three_invalid_b_and_four_complete(self):
        for n in (3,4):
            with self.subTest(n=n):
                (self.dir/'longgap-state.json').unlink(missing_ok=True)
                self.setup_short_ab(n)
                self.assertEqual(self.choose(self.manager())['requested_seconds'],60)
        (self.dir/'longgap-state.json').unlink()
        self.setup_short_ab(3)
        self.ab.state['assignments'].append(dict(arm='A',phase='cutoff',cutoff_reason='user_requested_minimum',attempts=[],history_cursor=3))
        self.assertEqual(self.choose(self.manager())['index'],1)
        self.ab.config.update(history_start=0,previous_relay_sha256='b'*64)
        self.assertEqual(supervisor.candidate_arm(self.rows[3]['id'],3,self.ab), ('retry-only',SHA))
        self.ab.state['assignments'][-1]['attempts'] = [{'phase':'dispatched'}]
        with self.assertRaisesRegex(RuntimeError,'lacks reconciled'):
            supervisor.candidate_arm(self.rows[3]['id'],3,self.ab)

    def test_reduced_ab_refuses_missing_or_inconsistent_terminal_proof(self):
        self.setup_short_ab(3)
        self.ab.state['assignments'][1]['outcome']['valid']=True
        with self.assertRaisesRegex(RuntimeError,'two invalid B'):
            self.choose(self.manager())
        self.setup_short_ab(4)
        self.ab.state['assignments'][-1]['outcome']['run_id']='different'
        with self.assertRaisesRegex(RuntimeError,'committed run history'):
            self.choose(self.manager())
        self.setup_short_ab(3)
        (self.dir/'required-ab-cap.json').unlink()
        with self.assertRaisesRegex(RuntimeError,'lacks cap'):
            self.choose(self.manager())

    def test_pending_only_after_amended_outcomes_and_valid_a_and_duplicate_safe(self):
        for n in (3,4):
            with self.subTest(n=n):
                self.setup_short_ab(n)
                config = self.dir/'longgap-config.json'
                config.unlink()
                approval = self.dir/'longgap-approved-pending.json'
                approval.unlink(missing_ok=True)
                eligible=lambda r:r.get('mode')=='retry-only' and r['valid']
                def attempt(now=NOW,sha=SHA):
                    return activate_pending(self.dir,CAP,self.rows,self.ab,sha,eligible,now)
                self.rows[-1].update(mode='retry-only')
                self.assertFalse(attempt())
                put(approval,{'version':1,'wait_for_eligible_baseline':True,
                    'prereg_sha256':hashlib.sha256((self.dir/'longgap-prereg.json').read_bytes()).hexdigest()})
                self.ab.state['status']='screening'
                self.assertFalse(attempt())
                self.ab.state['status']='baseline_after_screening'
                for mode, valid in [('first-required',True),('first-required',False),('retry-only',False)]:
                    self.rows[-1].update(mode=mode,valid=valid)
                    self.assertFalse(attempt())
                    self.assertFalse(config.exists())
                self.rows[-1].update(mode='retry-only',valid=True)
                self.assertFalse(attempt(CAP))
                self.assertFalse(config.exists())
                self.assertTrue(attempt())
                original=config.read_bytes()
                self.assertEqual(json.loads(original)['anchor_id'],self.rows[-1]['id'])
                self.assertEqual(json.loads(original)['history_start'],len(self.rows))
                ino=config.stat().st_ino
                self.rows.append(row())
                self.assertTrue(attempt())
                self.assertEqual(config.read_bytes(),original)
                self.assertEqual(config.stat().st_ino,ino)
                self.assertEqual(self.manager().config['order_seconds'],ORDER)

    def test_pending_mismatched_digest_or_sha_never_written(self):
        self.setup_short_ab(3)
        config=self.dir/'longgap-config.json'
        config.unlink()
        approval=self.dir/'longgap-approved-pending.json'
        values={'version':1, 'prereg_sha256':'f'*64, 'wait_for_eligible_baseline':True}
        put(approval,values)
        with self.assertRaisesRegex(RuntimeError,'differs from preregistration'):
            activate_pending(self.dir,CAP,self.rows,self.ab,SHA,lambda r:True,NOW)
        values['prereg_sha256']=hashlib.sha256((self.dir/'longgap-prereg.json').read_bytes()).hexdigest()
        put(approval,values)
        with self.assertRaisesRegex(RuntimeError,'relay changed'):
            activate_pending(self.dir,CAP,self.rows,self.ab,'0'*64,lambda r:True,NOW)
        self.assertFalse(config.exists())

    def test_hash_cutoff_predeclared_four_and_immutable_order(self):
        m=self.manager()
        with self.assertRaisesRegex(RuntimeError,'history or deployed relay'):
            self.choose(m,sha='b'*64)
        self.assertEqual(self.choose(m)['phase'],'allocated')
        self.assertIsNone(self.choose(m,now=CAP))
        self.assertEqual(m.state['status'],'cutoff')
        self.assertEqual(m.state['assignments'][0]['phase'],'cutoff')
        self.config['order_seconds']=ORDER*3
        put(self.dir/'longgap-config.json',self.config)
        with self.assertRaisesRegex(RuntimeError,'preregistered'):
            self.manager()
        self.config['order_seconds']=ORDER; put(self.dir/'longgap-config.json',self.config)
        self.prereg['created']='2026-01-01T00:01:00+00:00'; put(self.dir/'longgap-prereg.json',self.prereg)
        with self.assertRaisesRegex(RuntimeError,'preregistered'):
            self.manager()

    def test_outcome_timing_and_existing_backoff(self):
        current=self.rows[0]
        prior={'ended':{'time':1100},'startedWall':500}
        rec={'ended':{'time':130100},'startedWall':92100}
        with patch.object(supervisor,'audit_ab_outcome',return_value={'valid':True}), \
             patch.object(supervisor,'committed_record',side_effect=(prior,rec)):
            out=supervisor.audit_longgap_outcome(current,{'previous_uuid':'prior'},{})
        self.assertEqual(out['actual_wait_seconds'],91)
        self.assertEqual(out['start_to_start_seconds'],91.6)
        self.assertEqual(out['cycle_seconds'],129)
        with patch.object(supervisor,'read',return_value=prior),patch.object(supervisor,'cadence_eligible',return_value=True):
            self.assertEqual(supervisor.cooldown_until([row()],{},90),91.1)
            self.assertEqual(supervisor.cooldown_until([row()],{},None),61.1)
            self.assertEqual(supervisor.cooldown_until([row(False)]*3,{},None),121.1)

    def test_real_supervisor_command_and_fallback_mocked(self):
        root=self.dir/'2026-test';cache=root/'mean-2000';campaign=cache/'campaign'
        put(campaign/'campaign.json',{'history_start':0,'threshold':1500,
            'deadline':'2100-01-01T00:07:00+00:00','initial_head':'fixture'})
        put(campaign/'longgap-config.json',self.config)
        put(campaign/'longgap-prereg.json',self.prereg)
        put(cache/'status.json',{'phase':'result','id':self.rows[-1]['id']})
        (cache/'loop.lock').touch()
        for n in ('2026-11-22','2026-11-22-exp2000'):
            lock=self.dir/n/'mean-2000/loop.lock';lock.parent.mkdir(parents=True);lock.touch()
        ab=Mock(state=self.ab.state, config=self.ab.config);ab.select.return_value=None
        cadence=Mock(state=None);cadence.select.return_value=None
        commands=[]
        def child(cmd,**_):
            commands.append(cmd)
            if len(commands) <=4:
                e=json.loads((campaign/'longgap-state.json').read_bytes())['assignments'][-1]
                self.assertEqual(e['phase'],'dispatched')
            def wait():
                self.rows.append(row());put(cache/'status.json',{'phase':'result','id':self.rows[-1]['id']})
                return 0
            return SimpleNamespace(wait=wait)
        with ExitStack() as st:
            st.enter_context(patch.multiple(supervisor,ROOT=root,CACHE=cache,CAMPAIGN_DIR=campaign))
            for name, func in {'git':lambda *a:b'test' if a[0]=='branch' else b'',
                               'history':lambda:list(self.rows),'reconcile':lambda *a:(list(self.rows),False,set()),
                               'controls':lambda *a:'done' if len(commands)>=5 and len(self.rows)>=6 else None,
                               'current_source_hash':lambda:SHA,'cadence_eligible':lambda _:True,
                               'audit_longgap_outcome':observe,'owned_stop':lambda *a:False,
                               'report':lambda:None}.items():
                st.enter_context(patch.object(supervisor,name,side_effect=func))
            st.enter_context(patch.object(supervisor,'Cadence',return_value=cadence))
            st.enter_context(patch.object(supervisor,'RequiredAB',return_value=ab))
            st.enter_context(patch.object(supervisor.os,'dup2'))
            st.enter_context(patch.object(supervisor.subprocess,'Popen',side_effect=child))
            cooldown=st.enter_context(patch.object(supervisor,'cooldown_until',return_value=0))
            self.assertEqual(supervisor.main(),0)
        self.assertEqual([c[-1] for c in commands],['60','90','90','60','--once'])
        self.assertEqual([x.args[-1] for x in cooldown.call_args_list],ORDER+[None])

if __name__=='__main__':
    unittest.main()
