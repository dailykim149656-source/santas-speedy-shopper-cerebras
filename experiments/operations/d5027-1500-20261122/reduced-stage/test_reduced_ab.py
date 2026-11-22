"""Offline amendment and restart fixtures using the installed ledger format."""
import copy
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
import uuid

STAGE = Path(__file__).resolve().parent
D = STAGE.parent
sys.path[:0] = [str(STAGE),str(D)]
import required_ab as updated
spec = importlib.util.spec_from_file_location('original_required_ab', D / 'required_ab.py')
original = importlib.util.module_from_spec(spec)
spec.loader.exec_module(original)

class Reduce(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        self.d=Path(tmp.name)
        self.rows=[{'id':str(uuid.uuid4()),'commit':'fixture'}]
        self.cap={'version':1,'max_transmissions':4,'allow_confirmation':False,'registered_at':'2026-11-22T14:48:00+00:00','reason':'user_requested_minimum'}
        self.cfg={'version':1,'enabled':True,'history_start':1,'anchor_id':self.rows[0]['id'],'relay_sha256':'a'*64,'previous_relay_sha256':'b'*64,'cutoff':'2100-01-01T00:00:00+00:00'}
        self.cadence=SimpleNamespace(state={'assignments':[{'phase':'complete','outcome':{'history_index':0}}]*8})
        self.write('required-ab-config.json',self.cfg)

    def write(self,name,x):
        (self.d/name).write_text(json.dumps(x))

    def manager(self,module):
        def audit(row,entry,cfg):
            return {'valid':row['valid'],'first_tps':100,'final_tps':120,'mean_tps':110}
        return module.RequiredAB(self.d,4102444800,audit)

    def select(self,m):
        return m.select(self.rows,set(),1,self.cadence,'a'*64)

    def dispatch(self,m):
        e=self.select(m)
        m.dispatch(e,self.rows,set(),['loop.py','--once']+(['--d5027-first-required'] if e['arm']=='B' else []),1)
        return e

    def terminal(self,m,valid):
        self.rows.append({'id':str(uuid.uuid4()),'commit':'fixture','valid':valid})
        m.reconcile_terminal(self.rows)

    def complete(self,m,valid):
        self.dispatch(m);self.terminal(m,valid)

    def seed(self,b3,extra=False):
        m=self.manager(original)
        for ok in (True,False,b3):
            self.complete(m,ok)
        if extra:self.select(m)
        return m

    def enable(self):
        self.write('required-ab-cap.json',self.cap)
        return self.manager(updated)

    def check_end(self,m,count,reason):
        self.assertEqual(m.state['status'],'baseline_after_screening')
        self.assertEqual(m.state['reduced_cap'],4)
        self.assertEqual(m.state['screening']['n_sent'],count)
        self.assertFalse(m.state['screening']['pass'])
        self.assertEqual(m.state['screening']['end_reason'],reason)
        self.assertIsNone(m.state['confirmation'])
        self.assertIsNone(self.select(m))
        self.assertIsNone(self.select(self.manager(updated)))

    def test_three_invalid_b_never_assign_four(self):
        before=copy.deepcopy(self.seed(False).state['assignments'])
        m=self.enable()
        self.check_end(m,3,'no_valid_B_after_three')
        self.assertEqual(m.state['assignments'],before)
        self.assertEqual(m.state['screening']['valid_counts'],{'A':1,'B':0})

    def test_cancel_unsent_a4_and_a5_keep_exposures(self):
        self.seed(False,extra=True)
        m=self.enable()
        self.check_end(m,3,'no_valid_B_after_three')
        self.assertEqual(m.state['assignments'][3]['cutoff_reason'],'user_requested_minimum')
        self.assertEqual(m.state['assignments'][3]['attempts'],[])

    def test_valid_b3_produces_only_a4_and_no_confirmation(self):
        self.seed(True,extra=True)
        m=self.enable()
        self.assertEqual(self.select(m)['arm'],'A')
        self.complete(m,False)
        self.check_end(m,4,'four_transmissions_reached')
        self.assertEqual(m.state['screening']['valid_counts'],{'A':1,'B':1})

    def test_preallocated_fifth_is_not_transmitted(self):
        m=self.seed(True); self.complete(m,True); self.select(m)
        m=self.enable()
        self.check_end(m,4,'four_transmissions_reached')
        self.assertEqual(m.state['assignments'][-1]['phase'],'cutoff')
        self.assertEqual(m.state['screening']['valid_pairs'],1)

    def test_b3_dispatched_before_old_controller_exit_is_reconciled(self):
        m=self.manager(original)
        self.complete(m,True);self.complete(m,False);self.dispatch(m)
        m=self.enable()
        self.assertEqual(m.state['status'],'screening')
        self.terminal(m,False)
        self.check_end(m,3,'no_valid_B_after_three')

    def test_missing_modified_and_bad_cap_refuse(self):
        self.seed(False)
        self.enable()
        self.cap['registered_at']='2026-11-22T14:49:00+00:00'
        self.write('required-ab-cap.json',self.cap)
        with self.assertRaisesRegex(RuntimeError,'changed after registration'):
            self.manager(updated)
        (self.d/'required-ab-cap.json').unlink()
        with self.assertRaisesRegex(RuntimeError,'missing its amendment'):
            self.manager(updated)

    def test_actual_ab_snapshot_on_copy_only(self):
        import shutil
        for n in ('required-ab-config.json','required-ab-state.json'):
            shutil.copyfile(D/n,self.d/n)
        original_state=json.loads((self.d/'required-ab-state.json').read_bytes())
        if 'cap_amendment' in original_state:
            self.cap = json.loads((D/'required-ab-cap.json').read_bytes())
            self.assertEqual(self.cap, original_state['cap_amendment'])
        m=self.enable()
        for old,new in zip(original_state['assignments'],m.state['assignments']):
            if old['phase']=='complete':
                self.assertEqual(old,new)
        self.assertEqual(m.config['history_start'],79)

if __name__=='__main__':
    unittest.main(verbosity=2)
