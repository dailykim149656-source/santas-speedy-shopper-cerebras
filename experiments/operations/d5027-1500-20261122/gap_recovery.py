"""Four physical slots including the originally failed 60s and normal recovery."""
from datetime import datetime
import hashlib
import json
from pathlib import Path

from cadence import Cadence, stamp
from required_ab import RequiredAB


class GapRecovery(RequiredAB):
    def __init__(self, directory, cutoff, previous, audit):
        self.directory = Path(directory)
        self.path = self.directory / 'longgap-recovery-state.json'
        self.cutoff = cutoff
        self.audit_outcome = audit
        self.config = None
        self.state = None
        approval = self.directory / 'longgap-recovery-config.json'
        if not approval.is_file():
            if self.path.exists():
                raise RuntimeError('four-slot continuation state lost its approval')
            return
        cfg = json.loads(approval.read_bytes())
        old = previous.state
        if (not old or old['status'] != 'inconclusive_after_failure' or len(old['assignments']) != 1
                or cfg.get('version') != 1 or cfg.get('max_total_transmissions') != 4
                or datetime.fromisoformat(cfg['registered_at']).tzinfo is None
                or cfg['anchor_id'] != previous.config['anchor_id'] or cfg['first_id'] != old['failed_run_id']):
            raise RuntimeError('unexpected four-slot continuation approval or prior state')
        original = old['assignments'][0]
        if (original['outcome']['run_id'] != cfg['first_id'] or original['requested_seconds'] != 60
                or original['outcome']['valid'] or not original['outcome']['rate_limited']):
            raise RuntimeError('original first 60s was not a verified 429 termination')
        self.config = {**cfg, 'history_start':previous.config['history_start'],
                       'relay_sha256':previous.config['relay_sha256']}
        digest = hashlib.sha256(json.dumps(self.config, sort_keys=True).encode()).hexdigest()
        if self.path.is_file():
            self.state = json.loads(self.path.read_bytes())
            if self.state.get('config_sha256') != digest:
                raise RuntimeError('four-slot continuation config changed')
        else:
            self.state = {'version':1, 'config_sha256':digest, 'config':self.config, 'status':'active',
                          'assignments':[{**original, 'kind':'interval', 'origin':'original_ledger'}]}
            self.save()
        entries = self.state['assignments']
        if len(entries) not in range(1,5) or self.state['status'] not in ('active','complete','inconclusive','cutoff'):
            raise RuntimeError('invalid four-slot continuation state')
        for i,e in enumerate(entries):
            if (e['index'] != i+1 or e['history_cursor'] != self.config['history_start']+i
                    or e['mode'] != 'retry-only' or e['phase'] not in ('complete','allocated','dispatched','cutoff')
                    or i < len(entries)-1 and e['phase'] != 'complete'):
                raise RuntimeError('invalid four-slot continuation ledger')
        if sum(e['requested_seconds']==90 for e in entries)>1:
            raise RuntimeError('duplicate 90-second comparison allocation')

    def update_decision(self):
        last = self.state['assignments'][-1]
        out = last['outcome']
        if last['requested_seconds'] == 90 and (not out['valid'] or out['rate_limited'] is True):
            self.state.update(status='inconclusive',reason='sole 90-second attempt failed')
        elif last['index'] == 3 and last['kind'] == 'recovery' and (not out['valid'] or out['rate_limited'] is True):
            self.state.update(status='inconclusive',reason='slot 4 has no eligible previous A')
        elif last['index'] == 4:
            self.state.update(status='complete',reason='four physical transmissions reached')

    def entry(self, rows, seconds, origin='prospective'):
        count = len(self.state['assignments'])
        return {'index':count+1,'kind':'recovery' if seconds is None else 'interval',
                'origin':origin,'requested_seconds':seconds,'history_cursor':len(rows),
                'previous_uuid':rows[-1]['id'],'mode':'retry-only','relay_sha256':self.config['relay_sha256'],
                'phase':'allocated','allocated_at':stamp(),'attempts':[]}

    def adopt_second(self, rows):
        # The existing 60-second fallback may already have sent physical slot 2
        # before handoff. It counts only as recovery, never as a tested interval.
        pos=self.config['history_start']+1
        e=self.entry(rows[:pos],None,'existing_default_recovery')
        r=rows[pos]
        out=self.audit_outcome(r,e,self.config)
        out.update(run_id=r['id'],sent=True,history_index=pos,commit=r['commit'],
                   evidence=f"runs/{r['id']}/evidence.json",recorded_at=stamp())
        e.update(phase='complete',outcome=out)
        self.state['assignments'].append(e)
        self.save()

    def select(self, rows, sealed, now, eligible, source_hash):
        if not self.state:
            return None
        anchor = self.config['history_start']
        if (len(rows)<anchor+1 or rows[anchor-1]['id']!=self.config['anchor_id']
                or rows[anchor]['id']!=self.config['first_id'] or source_hash!=self.config['relay_sha256']):
            raise RuntimeError('continuation anchor or source changed')
        if self.state['status'] != 'active':
            return None
        entries=self.state['assignments']
        if len(entries)==1 and len(rows)==anchor+2:
            self.adopt_second(rows)
        self.reconcile(rows,sealed)
        if self.state['status'] != 'active':
            return None
        active=self.active()
        if now>=self.cutoff:
            if active:
                active.update(phase='cutoff',cutoff_at=stamp())
            self.state.update(status='cutoff',reason='preparation cutoff')
            self.save()
            return None
        completed=sum(e['phase']=='complete' for e in entries)
        if len(rows)!=anchor+completed:
            raise RuntimeError('additional unscheduled physical send during four-slot comparison')
        if active:
            if active['requested_seconds'] is not None and not eligible(rows[-1]):
                raise RuntimeError('previous success no longer eligible')
            return active
        if len(entries)==1:
            seconds=None
        elif len(entries)==2:
            seconds=90 if eligible(rows[-1]) else None
        elif len(entries)==3:
            if not eligible(rows[-1]):
                self.state.update(status='inconclusive',reason='slot 4 has no eligible previous A')
                self.save()
                return None
            seconds=60 if entries[-1]['requested_seconds']==90 else 90
        else:
            raise RuntimeError('unexpected fourth slot at allocation')
        result=self.entry(rows,seconds)
        entries.append(result)
        self.save()
        return result

    def dispatch(self, assignment, rows, sealed, command, now):
        sec=assignment['requested_seconds']
        expected=['--once'] if sec is None else ['--once','--d5027-post-success-seconds',str(sec)]
        if '--once' not in command or list(command[command.index('--once'):])!=expected:
            raise RuntimeError('unexpected continuation command')
        Cadence.dispatch(self,assignment,rows,sealed,command,now)
