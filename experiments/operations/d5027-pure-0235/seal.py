"""Privately retain and verify a completed run before the next ledger pruning pass."""
import argparse
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from uuid import UUID

HERE = Path(__file__).resolve().parent
CACHE = HERE.parent
REPO = Path(os.environ.get("BOUNTY_TEST_REPO", Path.cwd()))
RAW = Path.home() / 'Library/Application Support/Cerebras Speed Bounty/2026-11-22/raw-test'
D5009 = 'a9530b69-3aed-4ea9-8fd9-9ee1fcb36b51'
D5027 = 'cd75e5e0-be7c-471f-a9ab-c9e6f0d1bd77'
MEDIA = ('original.mp4', 'demo.mp4', 'final.png', 'viewport-evidence.json')


def read(path):
    return json.loads(path.read_bytes())


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def git(*args):
    return subprocess.check_output(['git', '--no-optional-locks', '-C', str(REPO), *args], text=True).strip()


def check(ok, reason):
    if not ok:
        raise ValueError(reason)


def seal_run(ident):
    check(str(UUID(ident)) == ident, 'run ID must be a canonical UUID')
    seals = HERE / 'sealed'
    seals.mkdir(mode=0o700, exist_ok=True)
    lock = Path(git('rev-parse', '--absolute-git-dir')) / 'benchmark-retention.lock'
    with lock.open('rb') as retention:
        fcntl.flock(retention, fcntl.LOCK_SH)
        run = REPO / 'runs' / ident
        rows = [r for line in (CACHE / 'iterations.jsonl').read_text().splitlines()
                if (r := json.loads(line)).get('id') == ident]
        check(len(rows) == 1, 'missing or duplicate official iteration')
        row = rows[0]
        check(row.get('valid') is True and row.get('method_valid') is True, 'iteration validation failed')
        baseline = read(REPO / 'runs' / D5027 / 'evidence.json')['score']['mean_exact_tps']
        fallback = read(REPO / 'runs' / D5009 / 'evidence.json')['score']['mean_exact_tps']
        evidence = read(run / 'evidence.json')
        score = evidence['score']['mean_exact_tps']
        check(math.isfinite(score) and score == row['score'], 'iteration disagrees with evidence')
        complete = evidence['evidence_status'] == 'complete'
        check(ident in (D5009, D5027) or score > baseline or (complete and score > fallback),
              'score meets neither record nor full-video improvement criteria')
        # Distinct versions preserve a later genuine video recovery of a provisional record.
        dest = seals / ident / sha(run / 'evidence.json')
        dest.parent.mkdir(mode=0o700, exist_ok=True)
        if dest.exists():
            manifest = read(dest / 'manifest.json')
            for rel, item in manifest['files'].items():
                p = dest / rel
                check(p.stat().st_size == item['bytes'] and sha(p) == item['sha256'], 'sealed file changed')
            return dest
        raw = RAW / (ident + '.json')
        process = subprocess.run([sys.executable, '-B', str(REPO / 'tools/verify_run.py'),
                                  ident, '--raw', str(raw)], check=True, capture_output=True)
        verified = json.loads(process.stdout)
        check(verified['raw_digest_checked'] and verified['verified_products'] == 5 and verified['mean'] == score,
              'private raw or five products failed verification')
        check(not complete or set(verified['checked_media']) == set(MEDIA), 'full capture missing verified media')
        spool = CACHE / 'capture' / ident
        with tempfile.TemporaryDirectory(prefix='.writing-', dir=dest.parent) as temp:
            package = Path(temp) / 'record'
            package.mkdir(mode=0o700)
            files = {}
            def save(source, rel):
                if not source.is_file():
                    return
                check(not source.is_symlink(), 'refusing linked file')
                target = package / rel
                target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                shutil.copyfile(source, target)
                target.chmod(0o600)
                digest = sha(target)
                check(digest == sha(source), 'copy failed digest verification')
                files[rel] = {'bytes':target.stat().st_size, 'sha256':digest}
            for name in ('plan.json', 'evidence.json', *MEDIA):
                save(run / name, name)
            for name in ('recording.json', 'ready.json', 'finish.json', 'capture-timeline.json', 'viewport-observations.json'):
                save(spool / name, 'capture/' + name)
            if not complete and ident != D5027:
                for name in MEDIA:
                    save(spool / name, 'capture/' + name)
                for frames in spool.glob('.frames-*'):
                    if frames.is_dir() and not frames.is_symlink():
                        for frame in frames.iterdir():
                            if frame.suffix in ('.png','.jpg','.jpeg') or frame.name == 'concat.txt':
                                save(frame, 'capture/' + frames.name + '/' + frame.name)
            for name in verified['checked_media']:
                check(files[name] == {k:evidence['media'][name][k] for k in ('bytes','sha256')},
                      'sealed media differs from committed digest')
            manifest = {'id':ident, 'label':row['label'], 'mean_exact_tps':score, 'method_valid':True,
                        'beats_D5027':score > baseline, 'complete_full_run':complete,
                        'official_iteration_commit':row['commit'], 'verification':verified,
                        'audited_HEAD':git('rev-parse','HEAD'), 'private_raw_path':str(raw),
                        'private_raw_sha256':evidence['private_raw_sha256'], 'files':files}
            manifest_path = package / 'manifest.json'
            manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+'\n')
            manifest_path.chmod(0o600)
            try:
                package.rename(dest)
            except OSError:
                if not dest.is_dir() or read(dest / 'manifest.json')['files'] != files:
                    raise
            return dest


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    print(seal_run(args.run_id) / 'manifest.json')
