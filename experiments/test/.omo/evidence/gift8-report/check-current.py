import hashlib,json,subprocess
from pathlib import Path
out=Path(__file__).resolve().parent
commands=[['python3','-m','py_compile','tools/gift8_report.py'],['git','diff','--check','--','tools/gift8_report.py'],['python3','tools/gift8_report.py','--output',str(out/'current.md'),'--copy-demos',str(out/'demos')]]
results=[]
for command in commands:
 p=subprocess.run(command,capture_output=True,text=True)
 results.append(dict(invocation=command,exit_code=p.returncode,stdout=p.stdout,stderr=p.stderr))
(out/'validation-commands.json').write_text(json.dumps(results,indent=2))
assert all(x['exit_code']==0 for x in results[:2])
audit=json.loads((out/'current.audit.json').read_text())
assert results[2]['exit_code']==(0 if audit['passed'] else 2)
assert all(x['audit_passed'] for x in audit['rows']),[(r['label'],r['audit_errors']) for r in audit['rows']]
assert all(e=='send intents and completed iteration rows differ' for e in audit['errors']),audit['errors']
if audit['sent_count']<8 and not audit.get('goal_complete'):assert not audit['complete'] and not audit['passed']
for movie in audit['copied_demos']:
 assert hashlib.sha256(Path(movie['source']).read_bytes()).hexdigest()==movie['sha256']==hashlib.sha256(Path(movie['path']).read_bytes()).hexdigest()
manifest=json.loads((out/'current.sha256.json').read_text())
for name,metadata in manifest['artifacts'].items():
 body=Path(name).read_bytes();assert metadata['sha256']==hashlib.sha256(body).hexdigest() and metadata['bytes']==len(body)
checks=dict(completed=audit['completed_count'],sent=audit['sent_count'],expected_in_progress_issues=audit['errors'],completed_row_integrity_passed=True,no_overlap=audit['no_overlap']['passed'],incomplete_sends=audit['no_overlap']['incomplete_sends'],reservation_closed=audit['reservation']['passed'],copied_demos=len(audit['copied_demos']),all_demo_source_and_copy_hashes_match=True,checksum_manifest_readback_matches=True,complete=audit['complete'],status=audit['status'],partial_snapshot_qa_passed=True)
(out/'current-results.json').write_text(json.dumps(checks,indent=2));print(json.dumps(checks))
