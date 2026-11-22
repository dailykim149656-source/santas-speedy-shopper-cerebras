"""Recognize an independent benchmark sender. A listening local gateway is expected."""
from pathlib import Path
import os
import shlex
import subprocess

CACHE = Path(__file__).resolve().parents[1]
PROJECT = Path(os.environ.get("BOUNTY_PROJECT_ROOT", Path.cwd().parent))
def competing_senders():
    result=[]
    listing=subprocess.check_output(['ps','-axo','pid=,command='],text=True)
    for line in listing.splitlines():
        head=line.strip().split(None,1)
        if len(head)!=2 or int(head[0])==os.getpid(): continue
        pid=int(head[0]); cmd=head[1]
        # macOS ps renders paths with spaces verbatim. Inspect the executable prefix
        # and match only the argument actually selecting a sender program.
        opt=cmd.split(None,1)
        if len(opt)!=2: continue
        exe=Path(opt[0]).name.lower()
        if not (exe.startswith('python') or exe=='node'): continue
        args=opt[1].lstrip()
        while args.split(None,1)[0] in ('-B','-u','-Bu','-uB'):
            parts=args.split(None,1)
            if len(parts)<2:break
            args=parts[1]
        for name in ('run_catalog_trials.mjs','probe_cli.mjs','loop.py','controller.py','supervisor.py'):
            script=args.split(' '+ '--',1)[0].split(' -',1)[0].strip()
            if not (script.endswith('/'+name) or script==name):
                continue
            if name=='probe_cli.mjs' and '--send' not in args: continue
            scoped=(str(PROJECT) in script or 'cerebras-speed-bounty' in script)
            if not scoped:
                # Use the process' actual working directory only for ambiguous relative paths.
                if Path(script).is_absolute():continue
                proc=subprocess.run(['lsof','-a','-p',str(pid),'-d','cwd','-Fn'],capture_output=True,text=True)
                scoped=any('cerebras-speed-bounty' in row or str(PROJECT) in row for row in proc.stdout.splitlines() if row.startswith('n'))
            if scoped: result.append({'pid':pid,'script':name})
    return result
