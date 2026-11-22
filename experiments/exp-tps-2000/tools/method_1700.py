"""Offline method checks for the private 1,700 TPS experiment.

These checks supplement validate.py; they never calculate or filter the official
score. Pass its full validation result, including calls and retail_sources.
"""

import json
from urllib.parse import parse_qsl, urlsplit

from validate import answer_links, identity, merchant, text_content, unwrap_json


ARMS = {
    'synth-five-categories-cap': [1, 1, 1, 1, 1],
    'synth-five-categories-cap-4000': [1, 1, 1, 1, 1],
    'synth-six-sorted': [6],
    'synth-six-sorted-pages': [3, 3],
}


def _requests(plan):
    variant = plan['variant']
    sizes = ARMS[variant]
    requests = [json.loads(line) for line in plan['prompt'].splitlines()
                if line.lstrip().startswith('{')]
    if len(requests) != len(sizes):
        raise ValueError('wrong number of planned requests')
    for slot, args in enumerate(requests):
        url = args['url']
        expected = {'url': url}
        if variant == 'synth-five-categories-cap-4000':
            expected.update(extractMode='text', maxChars=4000)
        if args != expected:
            raise ValueError('wrong planned fetch arguments')
        parsed = urlsplit(url)
        query = parse_qsl(parsed.query, keep_blank_values=True)
        expected_query = {
            'search': ('filter', 'mixer', 'oscillator', 'echo', 'cable')[slot]
            if len(sizes) == 5 else 'eurorack',
            'per_page': str(sizes[slot]), 'stock_status': 'instock',
            '_fields': 'name,permalink', '_run': plan['id'][:8],
        }
        if len(sizes) != 5:
            expected_query.update(orderby='id', order='asc')
        if variant == 'synth-six-sorted-pages':
            expected_query['offset'] = str(slot * 3)
        if (parsed.scheme != 'https' or parsed.netloc != 'aisynthesis.com'
                or parsed.path != '/wp-json/wc/store/v1/products' or parsed.fragment
                or len(query) != len(expected_query) or dict(query) != expected_query):
            raise ValueError('wrong planned catalog URL')
    return requests


def ordered_candidates(plan: dict, validation: dict) -> list[str] | None:
    """Return all five/six candidates in request and catalog order, or None.

Use all six candidates when comparing the sorted arms for inventory changes;
the final answer must contain the first five. Tool completion order is ignored.
"""
    try:
        requests = _requests(plan)
        sources = validation['retail_sources']
        if len(sources) != len(requests):
            return None
        by_url = {source['url']: source for source in sources}
        if (len(by_url) != len(sources)
                or len({source['tool_call_id'] for source in sources}) != len(sources)):
            return None
        candidates = []
        for args, size in zip(requests, ARMS[plan['variant']]):
            source = by_url[args['url']]
            products = source['products']
            if (source.get('accepted') is not True or source.get('reasons')
                    or source.get('status') != 200 or source.get('cached')
                    or source.get('truncated') or not isinstance(products, list)
                    or len(products) != size
                    or not all(merchant(url, product=True)
                               and urlsplit(url).hostname == 'aisynthesis.com' for url in products)):
                return None
            candidates.extend(products)
        if len({identity(url) for url in candidates}) != len(candidates):
            return None
        return candidates
    except (KeyError, TypeError, ValueError, AttributeError, IndexError):
        return None


def _arguments(part):
    if part.get('name') == 'web_fetch':
        return part['arguments']
    args = part.get('arguments', {})
    if (part.get('name') == 'tool_call'
            and args.get('id') in ('web_fetch', 'openclaw:core:web_fetch')
            and set(args) == {'id', 'args'}):
        return args['args']
    raise ValueError('unexpected tool call')


def assess(plan: dict, raw: dict, validation: dict) -> bool:
    """Require every planned fetch together in one measured assistant turn.

    Additional non-tool turns are permitted and remain in the unmodified
    validator's official mean; callers must retain that validation result.
    """
    try:
        if (raw['id'] != plan['id'] or validation['run_id'] != plan['id']
                or validation.get('valid') is not True):
            return False
        expected = _requests(plan)
        candidates = ordered_candidates(plan, validation)
        if candidates is None:
            return False
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
        if len(batches) != 1:
            return False
        batch_index, batch = batches[0]
        final_index, final = assistants[-1]
        if batch.get('stopReason') != 'toolUse' or final.get('stopReason') != 'stop':
            return False
        tool_calls = [part for part in batch['content'] if part.get('type') == 'toolCall']
        if len(tool_calls) != len(expected):
            return False
        if any(part.get('type') == 'toolCall' for part in final['content']):
            return False
        actual = [_arguments(part) for part in tool_calls]
        for actual_args, expected_args in zip(actual, expected):
            if plan['variant'].startswith('synth-five-categories'):
                if actual_args != expected_args:
                    return False
            elif (actual_args.get('url') != expected_args['url']
                  or set(actual_args) - {'url', 'extractMode', 'maxChars'}
                  or ('extractMode' in actual_args and actual_args['extractMode'] not in ('text', 'markdown'))
                  or ('maxChars' in actual_args and (type(actual_args['maxChars']) is not int
                                                    or actual_args['maxChars'] < 1))):
                return False
        ids = [part['id'] for part in tool_calls]
        if len(set(ids)) != len(ids) or not all(ids):
            return False
        results = [(i, message) for i, message in messages if message.get('role') == 'toolResult']
        if (len(results) != len(ids)
                or {message['toolCallId'] for _, message in results} != set(ids)):
            return False
        sources = {source['tool_call_id']: source for source in validation['retail_sources']}
        for call, args in zip(tool_calls, expected):
            if sources[call['id']]['url'] != args['url']:
                return False
        for index, message in results:
            if not batch_index < index < final_index or message.get('isError') is not False:
                return False
            payload = message.get('details') or unwrap_json(text_content(message))
            if 'tool' in payload:
                payload = payload['result']
                payload = payload.get('details') or unwrap_json(text_content(payload))
            source = sources[message['toolCallId']]
            if (payload.get('truncated') or payload.get('cached') or payload.get('status') != 200
                    or payload.get('url') != source['url']):
                return False
            products = unwrap_json(payload['text'])
            if (not isinstance(products, list)
                    or [product['permalink'] for product in products] != source['products']
                    or not all(isinstance(product.get('name'), str) and product['name'].strip()
                               for product in products)):
                return False
        final_text = text_content(final)
        links, misleading = answer_links(final_text)
        return (not misleading and links == candidates[:5]
                and validation['final_text'] == final_text)
    except (KeyError, TypeError, ValueError, AttributeError, IndexError):
        return False
