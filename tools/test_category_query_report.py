"""Offline consecutive trial audits with separate per-call merchant response files."""
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from uuid import uuid4

import category_query_report as report
from variants import SYNTH_CATEGORIES, catalogs


def save(path, value):
    path.write_text(json.dumps(value))


def trial(directory, slot=1):
    run_id = str(uuid4())
    arm = 'B'
    plan = dict(slot=slot, arm=arm, id=run_id,
                sessionKey=f'agent:main:category-ab-{arm.lower()}-{run_id}',
                label=f'slot-{slot:03d}-{arm}', prompt='shop live')
    tool = 'search_category'
    calls, results, links = [], [], []
    stamp = {'__openclaw': {'runId':run_id}}
    for cat,url in zip(SYNTH_CATEGORIES, catalogs(run_id[:8],1,shops='synth-categories')):
        card = dict(name='Gift '+cat,permalink='https://aisynthesis.com/product/'+cat+'/')
        body = json.dumps([card]).encode()
        calls.append(dict(type='toolCall',id=cat,name=tool,
                          arguments={'query':cat}))
        result = dict(url=url,finalUrl=url,status=200,truncated=False,cached=False,
                      fetchedAt='2026-01-01T00:00:01Z',text=body.decode())
        results.append(dict(**stamp,role='toolResult',toolName=tool,toolCallId=cat,
                            isError=False,content=[dict(type='text',text=json.dumps(result))]))
        links.append(f"{len(links)+1}. [{card['name']}]({card['permalink']})")
        folder = directory/'receipts'/run_id
        folder.mkdir(parents=True,exist_ok=True)
        (folder/f'body-{cat}.txt').write_bytes(body)
        save(folder/f'{cat}.json',dict(runId=run_id,sessionKey=plan['sessionKey'],callId=cat,
             query=cat,url=url,finalUrl=url,status=200,product=card,startedMs=1767225600020,
             completedMs=1767225601020,bodySha256=hashlib.sha256(body).hexdigest()))
    def message(suffix, stop, content, ms):
        return dict(**stamp,role='assistant',provider='cerebras',model=report.MODEL,
                    responseId=run_id+suffix,stopReason=stop,content=content,
                    serverGeneration=dict(outputTokens=100,completionMs=ms))
    messages = [dict(role='user',content=plan['prompt']), message('i','toolUse',calls,100),
                *reversed(results), message('o','stop',[dict(type='text',text='\n'.join(links))],200)]
    raw = dict(**plan,sentAt=1767225600000,endedAt=1767225602000,ended={'terminal':'final'},
               official=dict(meanTokensPerSecond=750,p90TokensPerSecond=1000,calls=2,
                             outputTokens=200,generationMs=300),history={'messages':messages})
    return plan, raw


class AuditTests(unittest.TestCase):
    def setUp(self):
        td = TemporaryDirectory()
        self.directory = Path(td.name)
        self.addCleanup(td.cleanup)

    def assess(self, plan, raw, verify=lambda p:dict(**p,verified=True)):
        save(self.directory/(plan['label']+'.json'),raw)
        return report.assess(self.directory,plan,verify=verify)

    def test_runs_bind_unordered_results_to_ordered_final_and_official_timings(self):
        for slot in (1,2):
            plan,raw=trial(self.directory,slot)
            rec=self.assess(plan,raw)
            self.assertTrue(rec['valid'],rec)
            self.assertEqual(rec['mean_tps'],750)
            self.assertEqual(len(rec['pages']),5)

    def test_swapped_link_titles_do_not_pass(self):
        plan,raw=trial(self.directory,1)
        block=raw['history']['messages'][-1]['content'][0]
        block['text']=block['text'].replace('[Gift echo]','[Gift cable]')
        self.assertIn('names and URLs',self.assess(plan,raw)['reason'])

    def test_receipt_mismatch_or_missing_body_does_not_pass(self):
        plan,raw=trial(self.directory,2)
        body=self.directory/'receipts'/plan['id']/'body-filter.txt'
        body.write_bytes(b'[]')
        self.assertIn('body does not match',self.assess(plan,raw)['reason'])
        body.unlink()
        self.assertFalse(self.assess(plan,raw)['valid'])

    def test_wrong_score_extra_call_or_page_failure_do_not_pass(self):
        plan,raw=trial(self.directory,1)
        raw['official']['meanTokensPerSecond']=1000
        self.assertIn('official score',self.assess(plan,raw)['reason'])
        raw['official']['meanTokensPerSecond']=750
        self.assertFalse(self.assess(plan,raw,lambda p:{'verified':False})['valid'])
        raw['history']['messages'].insert(2,raw['history']['messages'][1])
        rec=self.assess(plan,raw)
        self.assertFalse(rec['valid'])
        self.assertEqual(len(rec['calls']),3)

    def test_429_incomplete_and_duplicate_sessions_stay_in_denominators(self):
        plans,rows=[],[]
        for slot in (1,2,3,4):
            plan,raw=trial(self.directory,slot)
            plans.append(plan)
            if slot==3:
                raw['error']='provider unavailable'
                raw['providerFailures']=[{'status':429,'stage':'first'}]
            if slot==4:
                rows.append(report.assess(self.directory,plan))
            else:
                rows.append(self.assess(plan,raw))
        save(self.directory/'plan.json',{'count':len(plans),'trials':plans})
        self.assertEqual(report.read_plan(self.directory),plans)
        summary=report.summarize(rows)
        self.assertEqual(summary['valid'],2)
        self.assertEqual(summary['average_valid_session_tps'],750)
        self.assertEqual(summary['best_slot'],1)
        self.assertAlmostEqual(summary['historical_D5027_mean'],1354.6626,places=4)
        self.assertEqual(summary['above_historical'],0)
        self.assertEqual(summary['sent'],3)
        self.assertEqual(summary['observed_provider_429_sessions'],1)
        self.assertEqual(summary['transcript_429_by_stage'],{'first':1})
        self.assertEqual(summary['provider_diagnostics_available_sessions'],1)
        self.assertEqual(summary['status_counts']['missing_record'],1)
        rows[1]['calls'][0]['response_id']=rows[0]['calls'][0]['response_id']
        self.assertEqual(report.summarize(rows)['valid'],0)


if __name__=='__main__':
    unittest.main()
