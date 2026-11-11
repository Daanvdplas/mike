import copy
import importlib.util
import json
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('orq_proxy', Path(__file__).with_name('orq_proxy.py'))
proxy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(proxy)
FIXTURE = json.loads((Path(__file__).parents[2] / 'docs/examples/search-response.json').read_text())
BODY = b'--bound\r\nContent-Disposition: form-data; name="query"\r\n\r\nWitness evidence?\r\n--bound--\r\n'
CONTENT_TYPE = 'multipart/form-data; boundary=bound'

def tool_call(arguments='{}'):
    return {'status': 'completed', 'output': [{'type': 'function_call', 'name': 'search_cases', 'call_id': 'call-1', 'arguments': arguments}]}

def final_answer(bad_quote=False):
    rows = []
    for result in FIXTURE['results']:
        rows.append({'case_id': result['case_id'], 'text': 'De bronpassage bespreekt bewijs.', 'citations': [{'passage_id': result['passage']['passage_id'], **({'quote': 'verzonnen bewijs'} if bad_quote else {})}], 'limitations': ['Een tekstovereenkomst bewijst geen juridische relevantie.']})
    return {'status': 'completed', 'output': [{'type': 'message', 'role': 'assistant', 'content': [{'type': 'output_text', 'text': json.dumps({'explanations': rows})}]}]}

class OrqProxyTests(unittest.TestCase):
    def run_search(self, responses):
        requests, retrievals = [], []
        def provider(body):
            requests.append(body)
            response = responses.pop(0)
            if isinstance(response, Exception): raise response
            return response
        def retrieve(body, content_type):
            retrievals.append((body, content_type))
            return copy.deepcopy(FIXTURE)
        actual = proxy.explain_search(BODY, CONTENT_TYPE, provider, retrieve, 'test-model')
        return actual, requests, retrievals

    def test_model_calls_original_fixed_search_once_and_preserves_three_results(self):
        actual, requests, retrievals = self.run_search([tool_call(), final_answer()])
        self.assertEqual(actual.get('explanation_status'), 'available')
        self.assertEqual(len(requests), 2)
        self.assertEqual(retrievals, [(BODY, CONTENT_TYPE)])
        self.assertEqual(requests[0]['tool_choice']['name'], 'search_cases')
        self.assertEqual(requests[1]['tool_choice'], 'none')
        for original, result in zip(FIXTURE['results'], actual['results']):
            self.assertEqual({k: v for k, v in result.items() if k != 'explanation'}, original)
            self.assertEqual(result['explanation']['citations'][0]['quote'], original['passage']['text'])

    def test_invented_quote_fails_closed_without_losing_real_search_results(self):
        actual, requests, retrievals = self.run_search([tool_call(), final_answer(bad_quote=True)])
        self.assertEqual(actual.get('explanation_status'), 'unavailable')
        self.assertEqual(actual['results'], FIXTURE['results'])
        self.assertEqual(len(retrievals), 1)
        self.assertEqual(len(requests), 2)

    def test_provider_failure_does_not_disclose_details_or_return_fake_results(self):
        actual, requests, retrievals = self.run_search([RuntimeError('sensitive-provider-detail')])
        self.assertEqual(actual.get('explanation_status'), 'unavailable')
        self.assertEqual(actual['results'], FIXTURE['results'])
        self.assertNotIn('sensitive-provider-detail', json.dumps(actual))
        self.assertEqual(len(requests), 1)
        self.assertEqual(len(retrievals), 1)

    def test_model_cannot_rewrite_the_original_query_or_select_new_cases(self):
        actual, requests, retrievals = self.run_search([tool_call('{"query":"other"}')])
        self.assertEqual(actual.get('explanation_status'), 'unavailable')
        self.assertEqual(actual['results'], FIXTURE['results'])
        self.assertEqual(len(requests), 1)
        self.assertEqual(retrievals, [(BODY, CONTENT_TYPE)])

    def test_query_context_never_includes_uploaded_content(self):
        body = BODY.replace(b'--bound--', b'--bound\r\nContent-Disposition: form-data; name="document"; filename="test.txt"\r\nContent-Type: text/plain\r\n\r\nPRIVATE-UPLOAD-TEXT\r\n--bound--')
        context = proxy.input_context(body, CONTENT_TYPE)
        self.assertTrue(context.get('has_document'))
        self.assertNotIn('PRIVATE-UPLOAD-TEXT', json.dumps(context))
        self.assertEqual(context['query'], 'Witness evidence?')

    def test_document_limits_keep_existing_http_error_contract(self):
        large = b'--bound\r\nContent-Disposition: form-data; name="document"; filename="large.txt"\r\n\r\n' + b'x' * (10 * 1024 * 1024 + 1) + b'\r\n--bound--\r\n'
        with self.assertRaises(proxy.UpstreamError) as caught:
            proxy.input_context(large, CONTENT_TYPE)
        self.assertEqual(caught.exception.status, 413)
        self.assertEqual(caught.exception.payload['error']['code'], 'document_too_large')
        unnamed = b'--bound\r\nContent-Disposition: form-data; name="document"\r\n\r\nx\r\n--bound--\r\n'
        with self.assertRaises(proxy.UpstreamError) as caught:
            proxy.input_context(unnamed, CONTENT_TYPE)
        self.assertEqual(caught.exception.status, 415)

    def test_sidecar_openapi_advertises_optional_explanation_fields(self):
        contract = {'components': {'schemas': {'SearchResult': {'allOf': [{}, {'properties': {}}]}, 'SearchResponse': {'properties': {}}}}}
        actual = proxy.extended_contract(contract)
        self.assertIn('explanation_status', actual['components']['schemas']['SearchResponse']['properties'])
        self.assertIn('explanation', actual['components']['schemas']['SearchResult']['allOf'][1]['properties'])
        self.assertNotIn('explanation_status', contract['components']['schemas']['SearchResponse']['properties'])

if __name__ == '__main__': unittest.main()
