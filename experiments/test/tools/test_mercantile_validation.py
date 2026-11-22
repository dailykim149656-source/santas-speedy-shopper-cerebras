"""Exercise the shopping validator with local catalog receipts and product-page HTML."""
import json
import unittest
from unittest.mock import patch
from urllib.parse import urlsplit

import research_report
import validate
from variants import FOCUS_D5027, MERCANTILE_ARM, prompt


RUN_ID = '12345678-1234-4678-8234-0123456789ab'


def assistant(response_id, stop_reason, content):
    return {
        'role': 'assistant', 'provider': 'cerebras', 'model': validate.MODEL,
        '__openclaw': {'runId': RUN_ID}, 'responseId': response_id, 'stopReason': stop_reason,
        'serverGeneration': {'outputTokens': 10, 'completionMs': 100}, 'content': content,
    }


def shopping_fixture(arm):
    plan = {'id': RUN_ID, 'variant': arm[0], 'prompt': prompt(arm, RUN_ID[:8])}
    calls, receipts, products = [], [], []
    for index, line in enumerate(plan['prompt'].splitlines()[1:], 1):
        arguments = json.loads(line)
        url = arguments['url']
        call_id = f'fetch-{index}'
        product = {'name': f'Test Gift {index}',
                   'permalink': f'https://{urlsplit(url).hostname}/product/gift-{index}/'}
        products.append(product)
        calls.append({'type': 'toolCall', 'name': 'web_fetch', 'id': call_id, 'arguments': arguments})
        receipts.append({
            'role': 'toolResult', 'toolName': 'web_fetch', 'toolCallId': call_id, 'isError': False,
            '__openclaw': {'runId': RUN_ID, 'resultContentSource': 'network'},
            'details': {'url': url, 'finalUrl': url, 'status': 200, 'cached': False, 'truncated': False,
                        'fetchedAt': '2026-01-01T00:00:01Z', 'text': json.dumps([product])},
        })
    answer = '\n'.join(f"{i}. [{p['name']}]({p['permalink']})" for i, p in enumerate(products, 1))
    messages = [assistant('fetch', 'toolUse', calls), *receipts,
                assistant('answer', 'stop', [{'type': 'text', 'text': answer}])]
    run = dict(plan, history={'messages': messages}, startedWall=1767225600000,
               ended={'time': 1767225602000, 'terminal': 'final'})
    return run, messages, products


def validate_locally(run, products, wrong_canonical=''):
    names = {p['permalink']: p['name'] for p in products}

    def read_page(request):
        url = request.full_url
        canonical = url + 'different-product/' if url == wrong_canonical else url
        html = f'<link rel="canonical" href="{canonical}"><h1 class="product_title">{names[url]}</h1>'
        return html.encode(), 200, url, 'utf-8'

    with patch.object(validate, 'read_product_page', side_effect=read_page):
        return validate.validate(run)


class MerchantCategoryValidationTests(unittest.TestCase):
    def test_five_live_sources_match_five_verified_product_pages_in_both_arms(self):
        for arm in (FOCUS_D5027, MERCANTILE_ARM):
            with self.subTest(arm=arm[0]):
                run, _, products = shopping_fixture(arm)
                record = validate_locally(run, products)
                self.assertTrue(record['valid'], record['reject_reasons'])
                self.assertEqual([p['source_tool_call_id'] for p in record['products']],
                                 [f'fetch-{i}' for i in range(1, 6)])
                self.assertTrue(all(p['verified'] for p in record['products']))
                self.assertTrue(research_report.category_links_for_plan(record, run))

    def test_unplanned_query_with_five_valid_products_fails_the_method(self):
        run, messages, products = shopping_fixture(MERCANTILE_ARM)
        calls = messages[0]['content']
        wrong = calls[0]['arguments']['url'].replace('search=shirt&', 'search=socks&')
        calls[0]['arguments']['url'] = wrong
        messages[1]['details'].update(url=wrong, finalUrl=wrong)
        record = validate_locally(run, products)
        self.assertTrue(record['valid'], record['reject_reasons'])
        self.assertFalse(research_report.category_links_for_plan(record, run))

    def test_two_products_in_one_receipt_cannot_cover_a_missing_category(self):
        run, messages, products = shopping_fixture(MERCANTILE_ARM)
        del messages[0]['content'][-1]
        del messages[-2]
        messages[-2]['details']['text'] = json.dumps(products[-2:])
        record = validate_locally(run, products)
        self.assertTrue(record['valid'], record['reject_reasons'])
        self.assertFalse(research_report.category_links_for_plan(record, run))

    def test_separate_model_turns_do_not_count_as_five_parallel_requests(self):
        run, messages, products = shopping_fixture(MERCANTILE_ARM)
        last_call = messages[0]['content'].pop()
        messages.insert(-2, assistant('late-fetch', 'toolUse', [last_call]))
        record = validate_locally(run, products)
        self.assertTrue(record['valid'], record['reject_reasons'])
        self.assertFalse(research_report.category_links_for_plan(record, run))

    def test_duplicate_product_from_two_categories_fails(self):
        run, messages, products = shopping_fixture(MERCANTILE_ARM)
        messages[2]['details']['text'] = messages[1]['details']['text']
        record = validate_locally(run, products)
        self.assertFalse(record['valid'])
        self.assertFalse(research_report.category_links_for_plan(record, run))

    def test_detail_page_with_wrong_canonical_fails_independent_validation(self):
        run, _, products = shopping_fixture(MERCANTILE_ARM)
        record = validate_locally(run, products, wrong_canonical=products[0]['permalink'])
        self.assertFalse(record['valid'])
        self.assertIn('canonical does not identify submitted merchant product', record['products'][0]['reasons'])

    def test_retry_after_failed_lookup_keeps_all_measured_calls(self):
        run, messages, products = shopping_fixture(MERCANTILE_ARM)
        first_call = messages[0]['content'][0]
        successful_retry = dict(first_call, id='retry-1')
        messages[1]['toolCallId'] = successful_retry['id']
        error = {'role': 'toolResult', 'toolName': 'web_fetch', 'toolCallId': first_call['id'],
                 '__openclaw': {'runId': RUN_ID}, 'isError': True,
                 'content': [{'type': 'text', 'text': 'Web fetch failed (429) Too Many Requests'}]}
        first, success, *rest, final = messages
        messages[:] = [first, error, *rest, assistant('retry', 'toolUse', [successful_retry]), success, final]
        record = validate_locally(run, products)
        self.assertTrue(record['valid'], record['reject_reasons'])
        self.assertEqual(len(record['retail_sources']), 6)
        self.assertEqual(record['score']['call_count'], 3)
        self.assertTrue(research_report.category_links_for_plan(record, run))


if __name__ == '__main__':
    unittest.main()
