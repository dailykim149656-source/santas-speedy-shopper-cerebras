from pathlib import Path
import copy, hashlib, importlib.util, json, shutil, subprocess, sys
ROOT=Path(__file__).resolve().parents[3]
OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'tools'))
import first5027_film as old
import gift8_film
f=gift8_film.film
checks=[]
def check(name,truth):
 assert truth,name
 checks.append(name)
fixture=OUT/'queue-fixture'
if fixture.exists(): shutil.rmtree(fixture)
fixture.mkdir(exist_ok=True)
f.REPO=fixture/'repo';f.CACHE=fixture/'cache';f.FILMS=f.CACHE/'film-gift8-5051';f.SENTINEL=f.CACHE/'recording-complete-gift8-5051'
f.REPO.mkdir(exist_ok=True);(f.CACHE/'runs').mkdir(parents=True,exist_ok=True)
subprocess.run(['git','init','-q',str(f.REPO)],check=True)
ident='12345678-abcd-1234-abcd-123456789012';label='D5051-gift8-tool'
plan=dict(id=ident,label=label,variant='gift8-tool',capturePolicy='score-first',sessionKey='agent:main:shop-d5051-gift8-tool-12345678',prompt='OFFLINE QA FIXTURE ONLY')
for path in [f.REPO/'runs'/ident/'plan.json',f.CACHE/'capture'/ident/'plan.json']:
 path.parent.mkdir(parents=True,exist_ok=True);f.put(path,plan)
subprocess.run(['git','-C',str(f.REPO),'add','runs'],check=True)
subprocess.run(['git','-C',str(f.REPO),'-c','user.name=Fixture','-c','user.email=fixture@invalid','commit','--allow-empty','-qm','Offline plan fixture'],check=True)
check('gift8 eligible canonical D5051',f.eligible(plan))
for variant in ('gift8-tool','gift8-prefetch'):
 p=plan|dict(label=f'D5052-{variant}',variant=variant,sessionKey=f'agent:main:shop-d5052-{variant}-12345678')
 check('gift8 variant '+variant,f.eligible(p))
check('reject trial before start',not f.eligible(plan|dict(label='D5050-gift8-tool',sessionKey='agent:main:shop-d5050-gift8-tool-12345678')))
check('reject capture gate policy',not f.eligible(plan|dict(capturePolicy='gate')))
check('reject wrong session',not f.eligible(plan|dict(sessionKey='agent:main:other')))
prior=plan|dict(label='D5037-first5027-extract-text',variant='first5027-extract-text',sessionKey='agent:main:shop-d5037-first5027-extract-text-12345678')
check('old campaign unchanged in same interpreter',old.eligible(prior) and old.START==5037 and 'first5027' in old.FILMS.name)
check('old campaign excluded from gift8',not f.eligible(prior))
check('committed private plan accepted',f.committed_plan(ident)==plan)
check('no marker means no queue',f.watch_queue(5051)==[])
marker=f.CACHE/'runs'/(label+'.session.json')
f.put(marker,dict(id=ident,sessionKey=plan['sessionKey']))
check('session marker queues without sender gate',len(f.watch_queue(5051))==1 and not f.send_begun(label))
f.put(marker,dict(id='wrong',sessionKey=plan['sessionKey']))
check('wrong marker excluded',f.watch_queue(5051)==[])
f.put(marker,dict(id=ident,sessionKey=plan['sessionKey']))
f.SENTINEL.touch();check('sentinel excludes unsent session',f.watch_queue(5051)==[])
f.put(f.CACHE/'runs'/(label+'.send-intent.json'),dict(id=ident,sessionKey=plan['sessionKey']))
check('sentinel preserves begun session',len(f.watch_queue(5051))==1)
f.put(f.REPO/'runs'/ident/'preflight.json',dict(aborted=True));check('preflight aborted excluded',f.watch_queue(5051)==[])
(f.REPO/'runs'/ident/'preflight.json').unlink()
f.FILMS.joinpath(ident).mkdir(parents=True,exist_ok=True)
f.put(f.FILMS/ident/'receipt.json',dict(classification='partial_or_post_run'))
check('existing receipt prevents repeated recording',f.watch_queue(5051)==[])
products=[dict(url=f'https://fixture.invalid/{i}',verified=True) for i in range(5)]
validation=dict(run_id=ident,valid=True,score=dict(ui_rounded_tps=1700),products=products)
f.put(f.CACHE/'capture'/ident/'validation.json',validation)
check('canonical 1700 score and five verified products',f.state(label,plan)['qualifying'] and f.state(label,plan)['mean']==1700)
f.put(f.CACHE/'capture'/ident/'validation.json',validation|dict(products=products[:-1]+products[:1]))
check('duplicate URL rejected',not f.state(label,plan)['qualifying'])
help_run=subprocess.run([sys.executable,str(ROOT/'tools/gift8_film.py'),'--help'],capture_output=True,text=True)
(OUT/'cli-help.txt').write_text(help_run.stdout)
check('CLI documents exact sentinel and retry',help_run.returncode==0 and 'recording-complete-gift8-5051' in help_run.stdout and '--retry' in help_run.stdout)
bad=subprocess.run([sys.executable,str(ROOT/'tools/gift8_film.py'),'--start','5050'],capture_output=True,text=True)
(OUT/'cli-invalid-start.txt').write_text(bad.stderr)
check('CLI rejects old start',bad.returncode==2 and '5051 or later' in bad.stderr)
(OUT/'offline-results.json').write_text(json.dumps(dict(fixtureOnly=True,pass_=True,checks=checks),indent=2))
print(json.dumps(dict(pass_=True,checks=checks)))
