"""Close queued raw sessions after 02:35 KST with serial, independently checked pages."""
import argparse
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import sys
import time
from urllib.request import HTTPSHandler, build_opener
from zoneinfo import ZoneInfo

WORK = Path(__file__).resolve().parent
CACHE = WORK.parent
REPO = Path(os.environ.get("BOUNTY_TEST_REPO", Path.cwd()))
RAW = Path.home() / 'Library/Application Support/Cerebras Speed Bounty/2026-11-22/raw-test'
sys.path.insert(0, str(REPO / 'tools'))
os.environ.update(BOUNTY_SCHEDULE='test', BOUNTY_ROOT=str(CACHE.parent), BOUNTY_LABEL_BASE='5000',
                  BOUNTY_RAW_ARCHIVE=str(RAW))
import loop
from ledger import atomic, encode
import validate
from receipt import assess
from research_report import category_links_for_plan

KST = ZoneInfo('Asia/Seoul')
AFTER = datetime(2026, 11, 23, 2, 35, tzinfo=KST).timestamp()
SUBMISSION_END = datetime(2026, 11, 23, 3, tzinfo=KST).timestamp()


def need_open():
    if time.time() < AFTER:
        raise RuntimeError('postvalidation starts at 02:35 KST')


def write(path, value):
    atomic(path, encode(value))


def utc():
    return datetime.now(timezone.utc).isoformat(timespec='milliseconds')


class PacedHTTPS(HTTPSHandler):
    """Gate every HTTPS send, including redirects and transient upstream retries."""
    def __init__(self, folder, budget):
        super().__init__()
        self.folder = folder
        self.budget = budget
        self.audit = folder / 'detail-http.jsonl'
        self.ready = 0
        self.last_status = None
        self.local_error = None
        self.check_id = None
        self.item_key = None
        self.previous = None
        if self.audit.exists():
            with self.audit.open() as stream:
                for line in stream:
                    if line.strip():
                        self.previous = json.loads(line)['wall']
        if self.previous is not None:
            self.ready = time.monotonic() + max(0, self.previous + 2.02 - time.time())

    def log(self, event, **extra):
        with self.audit.open('a') as stream:
            json.dump(dict(event=event, run_id=self.check_id, url_sha256=self.item_key,
                           wall=time.time(), utc=utc(), **extra), stream)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())

    def https_open(self, request):
        try:
            need_open()
            time.sleep(max(0, self.ready - time.monotonic()))
            self.budget()
            self.log('send')
        except Exception as exc:
            self.local_error = exc
            raise
        self.last_status = None
        try:
            response = super().https_open(request)
            self.last_status = response.status
            return response
        finally:
            try:
                self.log('headers_or_error', http=self.last_status)
            except OSError as exc:
                self.local_error = exc
                raise
            self.ready = time.monotonic() + 2.02


def verification(raw, row, handler):
    ident = row['id']
    records = WORK / 'details' / ident
    opener = build_opener(validate.RetailRedirect(), handler)
    handler.check_id = ident

    def verify_many(candidates):
        for item in candidates:
            key = hashlib.sha256(item['url'].encode()).hexdigest()
            path = records / (key + '.json')
            if path.exists():
                proof = loop.get(path)
                if proof['raw_sha256'] != row['raw_sha256'] or proof['candidate'] != item:
                    raise RuntimeError('existing detail receipt belongs to another input')
                yield proof['product']
                continue
            handler.item_key = key
            handler.last_status = None
            checked = validate.verify_product(item, opener=opener)
            if handler.local_error is not None:
                raise RuntimeError('local traffic or receipt failure, keep item pending') from handler.local_error
            if not checked['verified'] and checked.get('http') is None and handler.last_status is not None:
                checked.update(http=handler.last_status, checked_at=utc())
            write(path, {'raw_sha256': row['raw_sha256'], 'candidate': item, 'product': checked,
                         'finished_at': utc()})
            yield checked
    return validate.validate(raw, verify_many=verify_many)


def finalize(queue_file, handler):
    pending = loop.get(queue_file)
    ident = pending['id']
    archived = RAW / (ident + '.json')
    body = archived.read_bytes()
    raw_sha = hashlib.sha256(body).hexdigest()
    if raw_sha != pending['raw_sha256'] or queue_file.stem != ident or pending['result'] != 'pending_validation':
        raise ValueError('pending receipt does not match archived private raw')
    raw = json.loads(body)
    if raw['id'] != ident or raw['label'] != pending['label'] or pending['score'] >= 1300:
        raise ValueError('pending queue item not eligible')
    dest = WORK / 'finalized' / (ident + '.json')
    if dest.is_file():
        return loop.get(dest)
    scratch = CACHE / 'capture' / ident
    plan = loop.get(REPO / 'runs' / ident / 'plan.json')
    if plan['label'] != raw['label'] or plan['variant'] not in ('synth-five-categories-cap', 'mercantile-five-categories-cap'):
        raise ValueError('pending plan is outside the campaign')
    vp = WORK / 'validations' / (ident + '.json')
    if vp.is_file():
        validation = loop.get(vp)
        if validation['input_sha256'] != raw_sha:
            raise ValueError('saved validation content mismatch')
    else:
        validation = verification(raw, pending, handler)
        validation.update(input_path=str(archived), input_sha256=raw_sha)
        write(vp, validation)
    score = validation['score']
    if score['mean_exact_tps'] != pending['score'] or score['ui_rounded_tps'] != pending['ui']:
        raise ValueError('independent validator score differs from terminal receipt')
    rows = [r for r in loop.past() if r['id'] == ident]
    if len(rows) > 1:
        raise RuntimeError('duplicate ledger iteration')
    if not rows:
        # Test schedule writes only the local repository. finish verifies genuine media and the raw-byte SHA.
        entry = loop.ledger('finish', '--repo', REPO, '--raw', archived, '--validation', vp, '--media-dir', scratch)
        row = dict(id=ident, label=plan['label'], arm=plan['experiment'], score=pending['score'], ui=pending['ui'],
                   valid=validation['valid'], method_valid=bool(validation['valid'] and category_links_for_plan(validation, raw)),
                   call_count=score['call_count'], p90=score['p90_tps'], goal=validation['target_met'],
                   recorded_video=entry['evidence_status'] == 'complete', evidence_status=entry['evidence_status'],
                   commit=entry['commit'], relay_phases=loop.relay_phases(ident),
                   validation_mode='deferred_detail', **loop.context_metrics(raw, raw['variant']))
        if plan['variant'] == 'mercantile-five-categories-cap':
            row['request_relay'] = plan['request_relay']
        loop.append(row)
    else:
        row = rows[0]
        if row.get('score') != pending['score'] or row.get('valid') != validation['valid']:
            raise RuntimeError('existing iteration conflicts with live product validation')
    actual = time.time()
    result = dict(row, result='terminal', ended=pending['ended'], raw_sha256=raw_sha, receipt=assess(row),
                  finalized_at=datetime.fromtimestamp(actual, KST).isoformat(timespec='milliseconds'),
                  finalized_before_submission_deadline=actual < SUBMISSION_END,
                  verified_products=sum(p.get('verified') is True for p in validation['products']),
                  detail_checked_at=[p.get('checked_at') for p in validation['products']])
    write(dest, result)
    return result


def pending_files(work):
    return sorted((work / 'pending').glob('*.json'), key=lambda p: loop.get(p)['ended'])


def closed_run_ids(work):
    journals = [work / 'campaign.json']
    second = work.parent / 'd5027-fast2-0235' / 'campaign.json'
    if second.exists():
        journals.append(second)
    registered = set()
    for journal in journals:
        state = loop.get(journal)
        if state.get('phase') not in ('completed', 'external_stop', 'interrupted') or not state.get('stopped'):
            raise RuntimeError('dispatch loop has not stopped: ' + journal.parent.name)
        for slot in state['slots']:
            ident = slot.get('id')
            if not ident:
                continue
            if ident in registered:
                raise ValueError('duplicate run id in campaign journals')
            registered.add(ident)
    return registered


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--run', action='store_true', help='perform live detail checks after cutoff')
    args = ap.parse_args()
    if not args.run:
        print(json.dumps({'pending': len(pending_files(WORK)), 'finalized': len(list((WORK / 'finalized').glob('*.json')))}))
        return
    need_open()
    from traffic import wait_for_detail_budget
    with (CACHE / 'loop.lock').open('rb') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        registered = closed_run_ids(WORK)
        files = pending_files(WORK)
        if any(file.stem not in registered for file in files):
            raise ValueError('pending receipt not in sealed campaign journals')
        handler = PacedHTTPS(WORK, wait_for_detail_budget)
        for file in files:
            row = finalize(file, handler)
            print(json.dumps({'id': row['id'], 'valid': row['valid'], 'method': row['method_valid'],
                              'finalized_at': row['finalized_at'], 'verified_products': row['verified_products']}), flush=True)


if __name__ == '__main__':
    os.umask(0o077)
    main()
