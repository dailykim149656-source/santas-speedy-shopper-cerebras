"""Offline method checks and call diagnostics for the isolated TPS-2000 campaign.

These checks supplement validate.py; they never alter official scoring.
"""

import json
from urllib.parse import parse_qsl, urlsplit

from validate import answer_links, identity, merchant, text_content, unwrap_json
from variants import SYNTH_DISCOVERY_FIELDS, SYNTH_RICH_CATEGORIES, SYNTH_RICH_FIELDS


TWO_CALL_ARMS = {
    'synth-five-categories-cap-4000': ('aisynthesis.com', ('filter', 'mixer', 'oscillator', 'echo', 'cable'), 'name,permalink', 4000),
    'exp2k-call0-zero-think': ('aisynthesis.com', SYNTH_RICH_CATEGORIES, 'name,permalink', 4000),
    'exp2k-verbatim-cards': ('aisynthesis.com', SYNTH_RICH_CATEGORIES, SYNTH_RICH_FIELDS, 4000),
    'exp2k-verbatim-cards-topp03': ('aisynthesis.com', SYNTH_RICH_CATEGORIES, SYNTH_RICH_FIELDS, 4000),
}
VERBATIM_ARMS = {'exp2k-verbatim-cards', 'exp2k-verbatim-cards-topp03', 'exp2k-three-call-verify'}
SUPPORTED_ARMS = set(TWO_CALL_ARMS) | {'exp2k-three-call-verify'}


def _parse_category_requests(plan):
    variant = plan['variant']
    if variant not in SUPPORTED_ARMS:
        raise ValueError('unsupported variant for method_2000')
    nonce = plan['id'][:8]
    json_lines = [json.loads(line) for line in plan['prompt'].splitlines()
                  if line.lstrip().startswith('{')]
    if variant == 'exp2k-three-call-verify':
        # Prompt includes one Step-2 template line (with <ID>) followed by 5 Step-1 discovery objects.
        expected_template = {
            'url': (f'https://aisynthesis.com/wp-json/wc/store/v1/products?include=<ID>'
                    f'&_fields={SYNTH_RICH_FIELDS}&_run={nonce}'),
            'extractMode': 'text',
            'maxChars': 4000,
        }
        templates = [item for item in json_lines if '<ID>' in str(item.get('url', ''))]
        requests = [item for item in json_lines if '<ID>' not in str(item.get('url', ''))]
        if templates != [expected_template]:
            raise ValueError('missing or mismatched Step-2 include template')
        categories, fields, max_chars = SYNTH_RICH_CATEGORIES, SYNTH_DISCOVERY_FIELDS, 2000
    else:
        _, categories, fields, max_chars = TWO_CALL_ARMS[variant]
        requests = json_lines
    if len(requests) != len(categories):
        raise ValueError('wrong number of planned requests')
    for slot, args in enumerate(requests):
        url = args.get('url', '')
        expected = {'url': url, 'extractMode': 'text', 'maxChars': max_chars}
        if args != expected:
            raise ValueError('wrong planned fetch arguments')
        parsed = urlsplit(url)
        query = parse_qsl(parsed.query, keep_blank_values=True)
        expected_query = {
            'search': categories[slot],
            'per_page': '1',
            'stock_status': 'instock',
            '_fields': fields,
            '_run': nonce,
        }
        if (parsed.scheme != 'https' or parsed.netloc != 'aisynthesis.com'
                or parsed.path != '/wp-json/wc/store/v1/products' or parsed.fragment
                or len(query) != len(expected_query) or dict(query) != expected_query):
            raise ValueError('wrong planned catalog URL')
    return requests


def _arguments(part):
    if part.get('name') == 'web_fetch':
        return part.get('arguments')
    args = part.get('arguments', {})
    if (part.get('name') == 'tool_call'
            and args.get('id') in ('web_fetch', 'openclaw:core:web_fetch')
            and set(args) == {'id', 'args'}):
        return args['args']
    raise ValueError('unexpected tool call')


def _unwrap_tool_result(message, expected_url):
    if message.get('isError') is not False:
        raise ValueError('tool result error')
    if message.get('__openclaw', {}).get('resultContentSource') not in (None, 'network'):
        raise ValueError('tool result not from network')
    payload = message.get('details') or unwrap_json(text_content(message))
    if 'tool' in payload:
        if payload['tool'].get('id') != 'openclaw:core:web_fetch':
            raise ValueError('unexpected wrapped tool')
        wrapped = payload['result']
        if wrapped.get('isError'):
            raise ValueError('wrapped tool failed')
        payload = wrapped.get('details') or unwrap_json(text_content(wrapped))
    if (payload.get('truncated') or payload.get('cached')
            or payload.get('status') != 200 or payload.get('url') != expected_url):
        raise ValueError('tool payload failed checks')
    products = unwrap_json(payload['text'])
    if not isinstance(products, list) or len(products) != 1 or not isinstance(products[0], dict):
        raise ValueError('expected single-product JSON array')
    product = products[0]
    link = product.get('permalink')
    if not merchant(link, product=True) or urlsplit(link).hostname != 'aisynthesis.com':
        raise ValueError('invalid product permalink')
    return product


def _verify_verbatim_cards(final_text, products):
    for product in products:
        pid = product.get('id')
        slug = product.get('slug')
        if type(pid) is not int or not isinstance(slug, str) or not slug:
            return False
        if str(pid) not in final_text or slug not in final_text:
            return False
        variations = product.get('variations')
        if not isinstance(variations, list):
            return False
        var_ids = [str(v['id']) for v in variations if isinstance(v, dict) and v.get('id') is not None]
        var_vals = [str(a['value']) for v in variations if isinstance(v, dict)
                    for a in (v.get('attributes') or [])
                    if isinstance(a, dict) and a.get('value')]
        min_ids = min(5, len(var_ids))
        min_vals = min(5, len(var_vals))
        if sum(vid in final_text for vid in var_ids) < min_ids:
            return False
        if sum(val in final_text for val in var_vals) < min_vals:
            return False
    return True


def assess(plan: dict, raw: dict, validation: dict) -> bool:
    """Validate strict workflow structure and verbatim coverage for TPS-2000 arms."""
    try:
        if (raw['id'] != plan['id'] or validation['run_id'] != plan['id']
                or validation.get('valid') is not True):
            return False
        expected_step1 = _parse_category_requests(plan)
        messages = [(i, message) for i, message in enumerate(raw['history']['messages'])
                    if message.get('__openclaw', {}).get('runId') == plan['id']]
        assistants = [(i, message) for i, message in messages if message.get('role') == 'assistant']
        if len(assistants) < 2 or len(validation['calls']) != len(assistants):
            return False
        for (index, message), measured in zip(assistants, validation['calls']):
            if (measured['message_index'] != index or measured['response_id'] != message['responseId']
                    or measured['completionMs'] != message['serverGeneration']['completionMs']
                    or measured['outputTokens'] != message['serverGeneration']['outputTokens']):
                return False
        batches = [(i, message) for i, message in assistants
                   if any(part.get('type') == 'toolCall' for part in message['content'])]
        final_index, final = assistants[-1]
        if final.get('stopReason') != 'stop' or any(part.get('type') == 'toolCall' for part in final['content']):
            return False

        variant = plan['variant']
        all_results = [(i, message) for i, message in messages if message.get('role') == 'toolResult']
        by_id = {message['toolCallId']: (index, message) for index, message in all_results}
        if len(by_id) != len(all_results):
            return False

        if variant == 'exp2k-three-call-verify':
            if len(batches) != 2:
                return False
            (b1_idx, b1), (b2_idx, b2) = batches
            if not b1_idx < b2_idx < final_index:
                return False
            if b1.get('stopReason') != 'toolUse' or b2.get('stopReason') != 'toolUse':
                return False
            calls1 = [part for part in b1['content'] if part.get('type') == 'toolCall']
            calls2 = [part for part in b2['content'] if part.get('type') == 'toolCall']
            if len(calls1) != 5 or len(calls2) != 5:
                return False
            if [_arguments(part) for part in calls1] != expected_step1:
                return False
            step1_products = []
            for part, req in zip(calls1, expected_step1):
                entry = by_id.get(part.get('id'))
                if not entry or not b1_idx < entry[0] < b2_idx:
                    return False
                step1_products.append(_unwrap_tool_result(entry[1], req['url']))
            pids = [p['id'] for p in step1_products]
            if any(type(pid) is not int or pid <= 0 for pid in pids) or len(set(pids)) != 5:
                return False
            nonce = plan['id'][:8]
            expected_step2 = [
                {
                    'url': (f'https://aisynthesis.com/wp-json/wc/store/v1/products?include={pid}'
                            f'&_fields={SYNTH_RICH_FIELDS}&_run={nonce}'),
                    'extractMode': 'text',
                    'maxChars': 4000,
                }
                for pid in pids
            ]
            if [_arguments(part) for part in calls2] != expected_step2:
                return False
            products = []
            for part, req, s1 in zip(calls2, expected_step2, step1_products):
                entry = by_id.get(part.get('id'))
                if not entry or not b2_idx < entry[0] < final_index:
                    return False
                prod = _unwrap_tool_result(entry[1], req['url'])
                if prod.get('id') != s1['id'] or prod.get('permalink') != s1['permalink']:
                    return False
                products.append(prod)
            if len(all_results) != 10:
                return False
        else:
            if len(batches) != 1:
                return False
            b1_idx, b1 = batches[0]
            if not b1_idx < final_index or b1.get('stopReason') != 'toolUse':
                return False
            calls1 = [part for part in b1['content'] if part.get('type') == 'toolCall']
            if len(calls1) != 5 or [_arguments(part) for part in calls1] != expected_step1:
                return False
            if len(all_results) != 5:
                return False
            products = []
            for part, req in zip(calls1, expected_step1):
                entry = by_id.get(part.get('id'))
                if not entry or not b1_idx < entry[0] < final_index:
                    return False
                products.append(_unwrap_tool_result(entry[1], req['url']))

        candidates = [p['permalink'] for p in products]
        if len({identity(u) for u in candidates}) != 5:
            return False
        final_text = text_content(final)
        links, misleading = answer_links(final_text)
        if misleading or links != candidates or validation['final_text'] != final_text:
            return False
        if variant in VERBATIM_ARMS and not _verify_verbatim_cards(final_text, products):
            return False
        return True
    except (KeyError, TypeError, ValueError, AttributeError, IndexError):
        return False


def call_diagnostics(raw: dict) -> list[dict]:
    """Return per-call timing and reasoning/text character diagnostics from a raw run dict."""
    run_id = raw.get('id')
    out = []
    for idx, msg in enumerate((raw.get('history') or {}).get('messages') or []):
        if msg.get('role') != 'assistant' or (msg.get('__openclaw') or {}).get('runId') != run_id:
            continue
        sg = msg.get('serverGeneration') or {}
        tok = sg.get('outputTokens')
        ms = sg.get('completionMs')
        tps = tok / (ms / 1000) if tok and ms else None
        parts = msg.get('content') or []
        think_c = sum(len(p.get('thinking') or '') for p in parts if isinstance(p, dict) and p.get('type') == 'thinking')
        text_c = sum(len(p.get('text') or '') for p in parts if isinstance(p, dict) and p.get('type') == 'text')
        tool_n = sum(1 for p in parts if isinstance(p, dict) and p.get('type') == 'toolCall')
        usage = msg.get('usage') or {}
        out.append({
            'message_index': idx,
            'stopReason': msg.get('stopReason'),
            'outputTokens': tok,
            'completionMs': ms,
            'tps': tps,
            'think_chars': think_c,
            'text_chars': text_c,
            'tool_count': tool_n,
            'input_tokens': usage.get('input'),
            'cache_read': usage.get('cacheRead'),
        })
    return out
