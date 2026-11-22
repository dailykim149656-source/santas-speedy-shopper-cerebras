"""Atomically refresh a self-contained, portable Git bundle on the evidence volume."""
from pathlib import Path
import subprocess
import tempfile

def publish(repo):
    with tempfile.TemporaryDirectory(prefix='.bundle-',dir=repo) as tmp:
        bundle=Path(tmp)/'latest.bundle'
        subprocess.run(['git','-C',str(repo),'bundle','create',str(bundle),'--branches','--tags'],check=True)
        subprocess.run(['git','-C',str(repo),'bundle','verify',str(bundle)],check=True,capture_output=True)
        head=subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD'],text=True).strip()
        refs=subprocess.check_output(['git','bundle','list-heads',str(bundle)],text=True)
        if not any(line.startswith(head+' ') for line in refs.splitlines()):
            raise RuntimeError('Portable bundle did not include the current commit')
        bundle.replace(repo/'evidence.bundle')
    return head

if __name__=='__main__':
    print(publish(Path(__file__).resolve().parents[1]))
