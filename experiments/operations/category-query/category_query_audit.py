"""Offline audit. Reads the preserved campaign and recorded detail checks. Makes no requests."""
import os
import argparse
from collections import Counter
from datetime import datetime
import hashlib
import html
import json
import math
from pathlib import Path
import re
from statistics import mean, median
import sys

REPO = Path(os.environ.get("BOUNTY_TEST_REPO", Path.cwd()))
sys.path.insert(0, str(REPO / 'tools'))
import category_query_report as official
from variants import SYNTH_CATEGORIES, catalogs
from validate import identity, merchant

THROTTLED = re.compile(r'\b429\b|queue_exceeded|too_many_requests_error', re.I)
MERCHANT_LIMIT = re.compile(r'(?:web fetch failed\s*\(429\)|\bHTTP(?:/\d(?:\.\d)?)?\s+429\b|\b429\s+too many requests\b|\bstatus(?: code)?[ :=]+429\b)', re.I)
read = lambda p: json.loads(p.read_bytes())


def receipt_details(campaign, plan, raw, messages):
    folder = campaign / 'receipts' / plan['id']
    lookup_hits, receipts, urls = set(), [], set()
    errors_without_status = []
    times = (raw.get('sentAt'), raw.get('endedAt'))
    for query, want_url in zip(SYNTH_CATEGORIES, catalogs(plan['id'][:8], 1, shops='synth-categories')):
        p = folder / (query + '.json')
        if not p.exists():
            continue
        receipt = read(p)
        if (receipt.get('runId'), receipt.get('sessionKey'), receipt.get('query'), receipt.get('url')) != (plan['id'],plan['sessionKey'],query,want_url):
            continue
        call = receipt.get('callId')
        if not call:
            continue
        if receipt.get('status') == 429 or MERCHANT_LIMIT.search(str(receipt.get('error', ''))):
            lookup_hits.add(call)
        elif receipt.get('error') and not isinstance(receipt.get('status'), int):
            errors_without_status.append(query)
        body = folder / ('body-' + query + '.txt')
        if (not body.exists() or receipt.get('status') != 200 or receipt.get('finalUrl') != want_url
                or not all(official.finite(t) for t in (*times,receipt.get('startedMs'),receipt.get('completedMs')))
                or not times[0] <= receipt['startedMs'] <= receipt['completedMs'] <= times[1]):
            continue
        content = body.read_bytes()
        cards = json.loads(content)
        if not isinstance(cards,list) or len(cards)!=1 or not isinstance(cards[0],dict):
            continue
        product = receipt.get('product') or {}
        url, name = product.get('permalink'), product.get('name')
        if (hashlib.sha256(content).hexdigest() != receipt.get('bodySha256') or not isinstance(name,str) or not name.strip()
                or product != {k: cards[0].get(k) for k in ('name','permalink')} or not merchant(url,product=True)
                or identity(url)[0] != 'aisynthesis.com' or identity(url) in urls):
            continue
        urls.add(identity(url))
        receipts.append({'query':query,'url':url,'catalog_name':name,'source_tool_call_id':call,
                         'receipt':str(p),'body':str(body),'body_sha256':receipt['bodySha256']})
    for m in messages:
        if m.get('role')=='toolResult' and m.get('toolName')=='search_category' and m.get('isError'):
            blocks = m.get('content') if isinstance(m.get('content'),list) else []
            # Error receipt + transcript from one failed tool call count as one occurrence.
            error = '\n'.join(b.get('text','') for b in blocks if isinstance(b,dict))
            if MERCHANT_LIMIT.search(error):
                lookup_hits.add(m['toolCallId'])
    return receipts,sorted(lookup_hits),errors_without_status


def check_saved_page(page):
    proof=page.get('product_evidence') or {}
    url=page.get('url')
    try:
        return (page.get('verified') is True and page.get('http')==200 and merchant(url,product=True)
                and identity(page['canonical'])==identity(page['final_url'])==identity(url)
                and page.get('title_matches_catalog') is True and any(proof.get(flag) is True for flag in
                ['matching_schema_product','woocommerce_product_heading','woocommerce_sticky_product_price_and_cart'])
                and len(page['html_sha256'])==64 and int(page['html_bytes_read'])>0
                and datetime.fromisoformat(page['checked_at']).tzinfo is not None)
    except (KeyError,TypeError,ValueError):
        return False


def audit(campaign, report_path=None):
    campaign=campaign.resolve()
    plans=official.read_plan(campaign)
    source=report_path or campaign/'report.json'
    evidence=read(source).get('trials',[]) if source.is_file() else []
    rows_by_id={r['id']:r for r in evidence}
    if len(rows_by_id)!=len(evidence):
        raise ValueError('report contains duplicate session ID')
    out=[]
    for p in plans:
        raw_file=campaign/(p['label']+'.json')
        if not raw_file.is_file():
            continue
        r=read(raw_file)
        if any(p[k]!=r.get(k) for k in ('id','sessionKey','slot','arm','label','prompt')):
            raise ValueError('terminal or pending session identity mismatch: '+p['label'])
        if not official.finite(r.get('sentAt')):
            continue
        messages=[m for m in (r.get('history') or {}).get('messages',[]) if (m.get('__openclaw') or {}).get('runId')==p['id']]
        calls=official.score_calls(messages)
        current=[m for m in messages if m.get('role')=='assistant' and m.get('provider')=='cerebras' and m.get('stopReason')=='error']
        # The same 429 may appear both in SQLite-derived providerFailures and in the chat transcript.
        errors=[f for f in r.get('providerFailures',[]) if f.get('status')==429]
        assistant_signal=any(THROTTLED.search(' '.join(str(m.get(k,'')) for k in ('errorMessage','errorCode','errorType'))) for m in current)
        diag=bool(r.get('providerDiagnosticsAvailable', 'providerFailures' in r))
        receipts,hits,unknown_merchant=receipt_details(campaign,p,r,messages)
        row=rows_by_id.get(p['id'],{})
        if row and row.get('slot')!=p['slot']:
            raise ValueError('report slot identity mismatch')
        pages=row.get('pages') or []
        if len({x.get('url') for x in pages})!=len(pages):
            raise ValueError('duplicate product page in one session')
        by_url={x['url']:x for x in pages}
        def certified(product):
            doc=by_url.get(product['url'],{})
            return (all(doc.get(k)==product[k] for k in ('url','source_tool_call_id','query'))
                    and doc.get('catalog_name')==html.unescape(product['catalog_name']) and check_saved_page(doc))
        def verify(product):
            if certified(product):
                return by_url[product['url']]
            return dict(product,verified=False,reasons=['no matching archived passing page check'])
        strict=official.assess(campaign,p,verify=verify)
        page_count=sum(certified(product) for product in receipts)
        page_429=sum(x.get('http')==429 or any(MERCHANT_LIMIT.search(str(e)) for e in x.get('reasons',[])) for x in pages)
        out.append(dict(slot=p['slot'],id=p['id'],raw_path=str(raw_file),sent_at=r['sentAt'],
                        observed=bool(messages or receipts or r.get('providerFailures')),pending=bool(r.get('pending')),
                        terminal=(r.get('ended') or {}).get('terminal'),unconfirmed_termination=bool(r.get('unconfirmedTermination')),
                        provider_429=bool(errors or assistant_signal),provider_diagnostics=diag,
                        provider_429_events=len(errors),provider_429_stages=[e.get('stage') for e in errors],
                        lookup_429_ids=hits,unknown_merchant_error_queries=unknown_merchant,detail_429_observed=page_429,
                        receipt_5of5=len(receipts)==5 and len({x['source_tool_call_id'] for x in receipts})==5,
                        detail_5of5=page_count==5,details_observed=len(pages),details_pass=page_count,
                        strict_pass=strict['valid'],reason=strict.get('reason'),calls=calls,
                        mean_tps=strict.get('mean_tps'),receipts=receipts))
    ids=Counter(c['response_id'] for row in out for c in row['calls'] if c['response_id'])
    for row in out:
        if row['strict_pass'] and any(ids[c['response_id']]>1 for c in row['calls']):
            row.update(strict_pass=False, reason='provider response identity reused in another trial')
    valid=[r for r in out if r['strict_pass']]
    scores=[r['mean_tps'] for r in valid]
    best=max(valid,key=lambda r:r['mean_tps'],default=None)
    provider={r['id'] for r in out if r['provider_429']}
    retail={r['id'] for r in out if r['lookup_429_ids'] or r['detail_429_observed']}
    return dict(planned=len(plans),sent_at_records=len(out),confirmed_sent=sum(r['observed'] for r in out),
                rpc_only_unconfirmed=[r['slot'] for r in out if not r['observed']],pending=sum(r['pending'] for r in out),
                terminal=dict(Counter(r['terminal'] or 'unknown' for r in out)),provider_429_sessions=len(provider),
                provider_diagnostics_available=sum(r['provider_diagnostics'] for r in out),
                provider_429_transcript_events=sum(r['provider_429_events'] for r in out),
                merchant_429_sessions=len(retail),merchant_lookup_429_events=sum(len(r['lookup_429_ids']) for r in out),
                merchant_detail_429_events=sum(r['detail_429_observed'] for r in out),both_429_sessions=len(provider&retail),
                any_429_sessions=len(provider|retail),merchant_unknown_error_slots=[r['slot'] for r in out if r['unknown_merchant_error_queries']],
                respective_5_lookup_products=sum(r['receipt_5of5'] for r in out),
                five_detail_pages_observed=sum(r['details_observed']==5 for r in out),
                five_detail_pages_verified=sum(r['detail_5of5'] for r in out),valid=len(valid),
                mean=mean(scores) if scores else None,median=median(scores) if scores else None,
                avg_first=mean(r['calls'][0]['tps'] for r in valid) if valid else None,
                avg_final=mean(r['calls'][-1]['tps'] for r in valid) if valid else None,
                above_d5027=sum(s>official.D5027_MEAN for s in scores),above_1500=sum(s>1500 for s in scores),
                above_1673_exact=sum(s>1673 for s in scores),above_1673_displayed=sum(official.round_rate(s)>1673 for s in scores),
                best=best,best_report=str(source.resolve()) if best else None,
                nonvalid=[{'slot':r['slot'],'reason':r['reason']} for r in out if not r['strict_pass']])


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory',type=Path)
    parser.add_argument('--report',type=Path)
    args=parser.parse_args()
    print(json.dumps(audit(args.directory,args.report),ensure_ascii=False,indent=2,allow_nan=False))
