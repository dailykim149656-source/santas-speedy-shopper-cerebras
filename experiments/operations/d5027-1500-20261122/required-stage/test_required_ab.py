"""Local allocating, failover, gate and wire-verification fixtures. No provider or server calls."""
import copy
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
import uuid
from unittest.mock import Mock, patch

STAGE = Path(__file__).resolve().parent
sys.path[:0] = [str(STAGE), str(STAGE.parent)]
import required_ab as ab
import supervisor

NEW, OLD = '1'*64,'0'*64


def put(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))


class Allocation(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.dir = Path(temp.name)
        self.rows = [{'id':str(uuid.uuid4()),'commit':'anchor'}]
        self.cfg = dict(version=1,enabled=True,history_start=1, anchor_id=self.rows[0]['id'],
                        relay_sha256=NEW,previous_relay_sha256=OLD,cutoff='2100-01-01T00:00:00+00:00')
        self.cadence = SimpleNamespace(state={'assignments':[{'phase':'complete','outcome':{'history_index':0}}]*8})
        put(self.dir/'required-ab-config.json',self.cfg)
        self.sealed = set()

    def manager(self):
        def observe(row, assignment, config):
            return dict(valid=row['valid'], mean_tps=row['mean'],first_tps=row['first'],final_tps=900,
                        mode=assignment['mode'], relay_sha256=config['relay_sha256'],terminal='final')
        return ab.RequiredAB(self.dir,4102444800,observe)

    def select(self,m):
        return m.select(self.rows,self.sealed,1,self.cadence,NEW)

    def dispatch(self,m):
        e=self.select(m)
        cmd=['loop.py','--once']+(['--d5027-first-required'] if e['arm']=='B' else [])
        m.dispatch(e,self.rows,self.sealed,cmd,1)
        return e

    def complete(self,m,b_gain=100,permitted=True):
        e=self.dispatch(m)
        self.rows.append({'id':str(uuid.uuid4()),'commit':'fake','valid':permitted,
                          'mean':1000+(b_gain if e['arm']=='B' else 0),
                          'first':1000+(b_gain if e['arm']=='B' else 0)})
        m.reconcile_terminal(self.rows)
        return e

    def test_confirm_and_return_to_baseline(self):
        m=self.manager()
        for i,arm in enumerate(ab.ARMS):
            e=self.complete(m,b_gain=80 if i<16 else 30)
            self.assertEqual((e['pair'],e['arm']), (i//2+1,arm))
            self.assertEqual(e['outcome']['run_id'],self.rows[-1]['id'])
            m=self.manager()
        self.assertEqual(m.state['status'],'baseline_after_confirmation')
        self.assertTrue(m.state['screening']['pass'])
        self.assertTrue(m.state['confirmation']['pass'])
        self.assertIsNone(self.select(m))

    def test_insufficient_and_detrimental_do_not_expand(self):
        m=self.manager()
        for i in range(16):
            self.complete(m,permitted=ab.ARMS[i]=='A' or i < 5)
        self.assertLess(m.state['screening']['valid_pairs'],4)
        self.assertEqual(m.state['screening']['n_sent'],16)
        self.assertFalse(m.state['screening']['pass'])
        self.assertIsNone(self.select(self.manager()))

    def test_losses_count_and_first_gain_majority_is_strict(self):
        def result(i,arm,mean,first,valid=True):
            return {'pair':i,'arm':arm,'outcome':{'valid':valid,'mean_tps':mean,'first_tps':first}}
        es=[]
        for i in range(8):
            es.extend([result(i,'A',100,100),result(i,'B',200 if i<6 else 80,110 if i<4 else 80)])
        self.assertFalse(ab.paired(es)['pass'])
        es[9]['outcome']['first_tps']=101
        self.assertTrue(ab.paired(es)['pass'])
        es[15]['outcome']['valid']=False
        self.assertFalse(ab.paired(es)['pass'])
        confirm=es[:8]
        self.assertTrue(ab.paired(confirm,True)['pass'])

    def test_presend_reuse_ambiguous_dispatch_no_retry_and_cli_guard(self):
        m=self.manager()
        e=self.dispatch(m)
        with self.assertRaisesRegex(RuntimeError,'no automatic retry'):
            self.manager().reconcile(self.rows,set())
        self.sealed={'sealed-presend'}
        m=self.manager(); m.reconcile(self.rows,self.sealed)
        self.assertEqual(self.select(m)['index'],1)
        with self.assertRaisesRegex(RuntimeError,'allocated arm'):
            m.dispatch(self.select(m),self.rows,self.sealed,['loop','--once','--d5027-first-required'],1)
        e=self.complete(m)
        self.assertEqual(e['attempts'][0]['phase'],'proven_presend')
        self.assertEqual(len(e['attempts']),2)

    def test_config_anchor_cadence_hash_cutoff_and_nonoptin(self):
        m=self.manager()
        with self.assertRaisesRegex(RuntimeError,'eight completed'):
            m.select(self.rows,set(),1,SimpleNamespace(state=None),NEW)
        with self.assertRaisesRegex(RuntimeError,'hash'):
            m.select(self.rows,set(),1,self.cadence,OLD)
        with self.assertRaisesRegex(RuntimeError,'cursor'):
            m.select([dict(id='other')],set(),1,self.cadence,NEW)
        self.assertEqual(self.select(m)['phase'],'allocated')
        self.assertIsNone(m.select(self.rows,set(),m.cutoff,self.cadence,NEW))
        self.assertEqual(m.state['assignments'][0]['phase'],'cutoff')
        (self.dir/'required-ab-config.json').unlink()
        with self.assertRaisesRegex(RuntimeError,'without A/B opt-in'):
            self.manager()
        (self.dir/'required-ab-state.json').unlink()
        self.assertIsNone(self.select(self.manager()))

    def test_mixed_source_hash_on_historical_candidate_and_baseline(self):
        m=self.manager()
        self.assertEqual(supervisor.candidate_arm(self.rows[0]['id'],0,m),('retry-only',OLD))
        self.complete(m); e=self.complete(m)
        self.assertEqual(supervisor.candidate_arm(e['outcome']['run_id'],2,m),('first-required',NEW))
        self.assertEqual(supervisor.candidate_arm('fallback',25,m),('retry-only',NEW))
        with self.assertRaisesRegex(RuntimeError,'lacks reconciled'):
            supervisor.candidate_arm('different',2,m)


    def test_actual_supervisor_wires_ab_after_cadence_without_changing_cooldown(self):
        root = self.dir/'2026-test'
        cache = root/'mean-2000'
        campaign = cache/'campaign'
        put(campaign/'campaign.json', {'history_start':0,'threshold':1500,
            'deadline':'2100-01-01T00:07:00+00:00','initial_head':'fixture'})
        put(campaign/'required-ab-config.json',self.cfg)
        put(cache/'status.json', {'phase':'result','id':self.rows[-1]['id']})
        (cache/'loop.lock').touch()
        for n in ('2026-11-22','2026-11-22-exp2000'):
            lock=self.dir/n/'mean-2000/loop.lock'
            lock.parent.mkdir(parents=True);lock.touch()
        cadence=Mock(state=self.cadence.state)
        cadence.select.return_value=None
        commands=[]
        def emit_child(cmd,**kw):
            commands.append(cmd)
            ledger=json.loads((campaign/'required-ab-state.json').read_bytes())
            allocated=ledger['assignments'][-1]
            self.assertEqual(allocated['phase'],'dispatched')
            valid=allocated['arm']=='A'
            def wait():
                ident=str(uuid.uuid4())
                self.rows.append({'id':ident,'valid':valid,'commit':'fake','mean':1000,'first':900})
                put(cache/'status.json', {'phase':'result','id':ident})
                return 0
            return SimpleNamespace(wait=wait)
        def report():
            ledger=json.loads((campaign/'required-ab-state.json').read_bytes())
            self.assertEqual(ledger['assignments'][-1]['outcome']['run_id'], self.rows[-1]['id'])
        def outcome(row,e,c):
            return {'valid':row['valid'],'mean_tps':row['mean'],'first_tps':row['first'],
                    'final_tps':0,'mode':e['mode'],'relay_sha256':c['relay_sha256']}
        with patch.multiple(supervisor, ROOT=root, CACHE=cache, CAMPAIGN_DIR=campaign), \
             patch.object(supervisor, 'Cadence',return_value=cadence), \
             patch.object(supervisor, 'git',side_effect=lambda *a:b'test' if a[0]=='branch' else b''), \
             patch.object(supervisor, 'reconcile',side_effect=lambda *a:(list(self.rows),False,set())), \
             patch.object(supervisor, 'history',side_effect=lambda:list(self.rows)), \
             patch.object(supervisor, 'current_source_hash',return_value=NEW), \
             patch.object(supervisor, 'audit_ab_outcome',side_effect=outcome), \
             patch.object(supervisor, 'cooldown_until',return_value=0) as cool, \
             patch.object(supervisor, 'controls',side_effect=lambda *a:'fixture done' if len(self.rows)==3 else None), \
             patch.object(supervisor, 'owned_stop'), patch.object(supervisor.os,'dup2'), \
             patch.object(supervisor.subprocess, 'Popen',side_effect=emit_child), \
             patch.object(supervisor, 'report',side_effect=report):
            self.assertEqual(supervisor.main(),0)
        self.assertEqual(len(commands),2)
        self.assertEqual(commands[0][-1],'--once')
        self.assertEqual(commands[1][-2:],['--once','--d5027-first-required'])
        self.assertTrue(all(call.args[-1] is None for call in cool.call_args_list))


class Wire(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.d=Path(temp.name); self.ident=str(uuid.uuid4())
        self.logs=self.d/'relay/logs'; self.dir=self.logs/self.ident; self.dir.mkdir(parents=True)
        self.row={'id':self.ident}
        self.calls=[{'stopReason':s,'serverGeneration':{'outputTokens':161,'completionMs':100.0}}
                    for s in ('toolUse','stop')]

    def populate(self,arm='B',extra=False,mutate_final=False):
        reqs=[]
        for i in range(2):
            orig={'messages':[{'role':'user'}]+([{'role':'tool'}] if i else []),
                  'tools':[{'type':'function','function':{'name':'web_fetch'}}],'tool_choice':'auto'}
            new=copy.deepcopy(orig)
            changed=arm=='B' and i==0
            if changed:
                new['tool_choice']='required'
                if extra:new['parallel_tool_calls']=True
            if i and mutate_final:new['parallel_tool_calls']=True
            b1=json.dumps(orig).encode();b2=json.dumps(new).encode();h1=ab.sha(b1);h2=ab.sha(b2)
            if changed:(self.dir/f'{i}-{h1[:12]}.received.json').write_bytes(b1)
            (self.dir/f'{i}-{h2[:12]}.json').write_bytes(b2)
            reqs.append(dict(status=200,run_id=self.ident,nonce=self.ident[:8],relay_sha256=NEW,at_ms=i,
                             method='POST',received_sha256=h1,forwarded_sha256=h2,attempts=[{'status':429}],
                             retry_schedule='first' if i==0 else 'late',phase='first' if changed else 'final' if arm=='B' else 'passthrough',
                             changes=['tool_choice_required'] if changed else [],
                             timing={'completion_time':.1,'completion_tokens':161}))
        (self.logs/'requests.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in reqs))

    def test_valid_b_and_a_and_extra_changes(self):
        for arm,mode in ab.MODES.items():
            self.populate(arm)
            self.assertEqual(len(ab.check_wire(self.d,self.row,NEW,mode,self.calls)),2)
        self.populate(extra=True)
        with self.assertRaisesRegex(RuntimeError,'more than'):
            ab.check_wire(self.d,self.row,NEW,ab.MODES['B'],self.calls)
        self.populate(mutate_final=True)
        with self.assertRaisesRegex(RuntimeError,'passthrough'):
            ab.check_wire(self.d,self.row,NEW,ab.MODES['B'],self.calls)
        self.populate();self.calls[0]['serverGeneration']['outputTokens']=999
        with self.assertRaisesRegex(RuntimeError,'timing'):
            ab.check_wire(self.d,self.row,NEW,ab.MODES['B'],self.calls)


if __name__=='__main__':
    unittest.main(verbosity=2)
