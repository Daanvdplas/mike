import copy
import hashlib
import contextlib
import io
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

def final_answer(bad_quote=False, input_ids=None):
    rows = []
    for result in FIXTURE['results']:
        rows.append({'case_id': result['case_id'], 'text': 'De bronpassage bespreekt bewijs.', 'citations': [{'passage_id': result['passage']['passage_id'], **({'quote': 'verzonnen bewijs'} if bad_quote else {})}], 'limitations': ['Een tekstovereenkomst bewijst geen juridische relevantie.'], 'input_passage_ids': input_ids or []})
    return {'status': 'completed', 'output': [{'type': 'message', 'role': 'assistant', 'content': [{'type': 'output_text', 'text': json.dumps({'explanations': rows})}]}]}

class OrqProxyTests(unittest.TestCase):
    def test_head_matter_method_is_validated_and_forwarded_without_losing_source_identity(self):
        body = BODY.replace(b'--bound--', b'--bound\r\nContent-Disposition: form-data; name="retrieval_method"\r\n\r\nhead_matter\r\n--bound--')
        search = copy.deepcopy(FIXTURE)
        search['retrieval_method'] = 'head_matter'
        for result in search['results']:
            result['passage']['source_section'] = 'head_matter'
            result['passage']['text_version'] = 'sha256:' + 'b' * 64
        retrieved = []
        responses = [tool_call(), final_answer()]
        def retrieve(raw, kind):
            retrieved.append((raw, kind))
            return copy.deepcopy(search)
        actual = proxy.explain_search(body, CONTENT_TYPE, lambda _: responses.pop(0), retrieve, 'test-model')
        self.assertEqual(retrieved, [(body, CONTENT_TYPE)])
        self.assertEqual(actual['retrieval_method'], 'head_matter')
        self.assertTrue(all('redactionele' in ' '.join(row['explanation']['limitations']).lower() for row in actual['results']))

    def test_head_matter_selection_preserves_upload_context_and_verified_input_evidence(self):
        body = BODY.replace(b'--bound--', b'--bound\r\nContent-Disposition: form-data; name="retrieval_method"\r\n\r\nhead_matter\r\n--bound\r\nContent-Disposition: form-data; name="document"; filename="input.txt"\r\n\r\nWitness input.\r\n--bound--')
        search = copy.deepcopy(FIXTURE)
        search['retrieval_method'] = 'head_matter'
        for row in search['results']:
            row['passage']['source_section'] = 'head_matter'
            row['passage']['text_version'] = 'sha256:' + 'b' * 64
        responses = [tool_call(), final_answer(input_ids=['input-0001'])]
        received = []
        def retrieve(raw, kind):
            received.append((raw, kind))
            return copy.deepcopy(search)
        actual = proxy.explain_search(body, CONTENT_TYPE, lambda _: responses.pop(0), retrieve, 'test-model', extractor=lambda *_: 'Witness input.')
        self.assertEqual(actual['explanation_status'], 'available')
        self.assertEqual(actual['retrieval_method'], 'head_matter')
        self.assertEqual(received, [(body, CONTENT_TYPE)])
        self.assertIn('input_context', actual)
        for row in actual['results']:
            self.assertEqual(row['explanation']['input_citations'][0]['quote'], 'Witness input.')
            self.assertTrue(any('redactionele' in text for text in row['explanation']['limitations']))
            self.assertFalse(any('niet aan het taalmodel' in text for text in row['explanation']['limitations']))

    def run_search(self, responses, body=BODY, extractor=None):
        requests, retrievals = [], []
        def provider(body):
            requests.append(body)
            response = responses.pop(0)
            if isinstance(response, Exception): raise response
            return response
        def retrieve(body, content_type):
            retrievals.append((body, content_type))
            return copy.deepcopy(FIXTURE)
        actual = proxy.explain_search(body, CONTENT_TYPE, provider, retrieve, 'test-model', extractor=extractor)
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

    def test_failures_log_only_fixed_stage_and_validation_codes(self):
        captured = io.StringIO()
        with contextlib.redirect_stderr(captured):
            self.run_search([RuntimeError('PRIVATE-UPLOAD-AND-CREDENTIAL')])
            self.run_search([tool_call(), final_answer(bad_quote=True)])
        log = captured.getvalue()
        self.assertIn('phase=provider_tool reason=RuntimeError', log)
        self.assertIn('phase=validate_explanation reason=invalid_citation_schema', log)
        self.assertNotIn('PRIVATE-UPLOAD-AND-CREDENTIAL', log)
        self.assertNotIn('verzonnen bewijs', log)

    def test_model_cannot_rewrite_the_original_query_or_select_new_cases(self):
        actual, requests, retrievals = self.run_search([tool_call('{"query":"other"}')])
        self.assertEqual(actual.get('explanation_status'), 'unavailable')
        self.assertEqual(actual['results'], FIXTURE['results'])
        self.assertEqual(len(requests), 1)
        self.assertEqual(retrievals, [(BODY, CONTENT_TYPE)])

    def test_query_context_includes_the_full_canonical_upload(self):
        body = BODY.replace(b'--bound--', b'--bound\r\nContent-Disposition: form-data; name="document"; filename="test.txt"\r\nContent-Type: text/plain\r\n\r\nPRIVATE-UPLOAD-TEXT\r\n--bound--')
        context = proxy.input_context(body, CONTENT_TYPE, extractor=lambda name, data: data.decode('utf-8'))
        self.assertTrue(context.get('has_document'))
        self.assertEqual(''.join(part['text'] for part in context.get('upload_passages', [])), 'PRIVATE-UPLOAD-TEXT')
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

    def test_upload_identity_and_utf16_positions_cover_the_entire_original_text(self):
        text = '🧪' + 'a' * 1000 + '\r\nComplete original upload.\n'
        body = b'--bound\r\nContent-Disposition: form-data; name="document"; filename="test.txt"\r\n\r\n' + text.encode() + b'\r\n--bound--\r\n'
        context = proxy.input_context(body, CONTENT_TYPE, extractor=lambda name, data: data.decode())
        self.assertEqual(''.join(part['text'] for part in context.get('upload_passages', [])), text)
        self.assertEqual(context['input_context']['text_version'], 'sha256:' + hashlib.sha256(text.encode()).hexdigest())
        self.assertEqual(context['upload_passages'][1]['start_utf16'], 1001)
        self.assertEqual(context['input_context']['utf16_length'], len(text.encode('utf-16-le')) // 2)

    def test_upload_comparison_returns_verified_input_citations_without_full_document_response(self):
        text = 'The officer claimed friendship and promised help. 🧪'
        body = b'--bound\r\nContent-Disposition: form-data; name="document"; filename="test.txt"\r\n\r\n' + text.encode() + b'\r\n--bound--\r\n'
        actual, requests, _ = self.run_search([tool_call(), final_answer(input_ids=['input-0001'])], body, lambda name, data: data.decode())
        self.assertEqual(actual.get('explanation_status'), 'available')
        evidence_schema = requests[1]['text']['format']['schema']['properties']['explanations']['items']['properties']['input_passage_ids']
        self.assertEqual(evidence_schema.get('minItems'), 1)
        self.assertEqual(evidence_schema['items'].get('enum'), ['input-0001'])
        sent = json.loads(requests[0]['input'][0]['content'])
        self.assertEqual(''.join(part['text'] for part in sent['upload_passages']), text)
        self.assertEqual(set(actual['input_context']), {'text_version', 'utf16_length'})
        for result in actual['results']:
            citation = result['explanation']['input_citations'][0]
            self.assertEqual(citation['quote'], text)
            self.assertEqual(text.encode('utf-16-le')[citation['start_utf16']*2:citation['end_utf16']*2].decode('utf-16-le'), citation['quote'])
            self.assertNotIn('niet aan het taalmodel', ' '.join(result['explanation']['limitations']))

    def test_unknown_upload_evidence_fails_closed_and_overlong_context_is_rejected(self):
        body = b'--bound\r\nContent-Disposition: form-data; name="document"; filename="test.txt"\r\n\r\nOriginal content\r\n--bound--\r\n'
        actual, _, _ = self.run_search([tool_call(), final_answer(input_ids=['unknown'])], body, lambda name, data: data.decode())
        self.assertEqual(actual.get('explanation_status'), 'unavailable')
        self.assertEqual(actual['results'], FIXTURE['results'])
        with self.assertRaises(proxy.UpstreamError) as caught:
            proxy.input_context(body, CONTENT_TYPE, extractor=lambda name, data: 'x' * (48 * 1024 + 1))
        self.assertEqual(caught.exception.status, 413)

    def test_serialized_provider_context_limit_is_an_explicit_413(self):
        provider = proxy.OrqProvider('unit-test-key', budget=1)
        with self.assertRaises((proxy.UpstreamError, ValueError)) as caught:
            provider({'input': 'x' * (129 * 1024)})
        self.assertIsInstance(caught.exception, proxy.UpstreamError)
        self.assertEqual(caught.exception.status, 413)

if __name__ == '__main__': unittest.main()
