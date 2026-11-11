"""Model selection checks without inference or an embedding backend."""
import json
import threading
import unittest
from unittest.mock import patch
from urllib import error, request

import orq_models as models
import orq_proxy as proxy
from test_orq_proxy import BODY, CONTENT_TYPE, FIXTURE, tool_call, final_answer


class OrqModelsTest(unittest.TestCase):
    def test_allowed_selection_and_actual_model_are_distinct(self):
        catalog = models.ModelCatalog()
        selected = 'openai/gpt-4.1-2025-04-14'
        self.assertEqual(catalog.select(selected), selected)
        self.assertIsNone(models.provider_model({}, selected))
        self.assertEqual(models.provider_model({'model': 'gpt-4.1-2025-04-14'}, selected), 'gpt-4.1-2025-04-14')
        with self.assertRaises(models.UnsupportedModel): catalog.select('unknown')
        with self.assertRaises(models.ModelIdentityError):
            models.provider_model({'model': models.DEFAULT_MODEL}, selected)

    def test_sidecar_routes_model_header_and_rejects_unknown_before_work(self):
        selected = 'openai/gpt-4.1-2025-04-14'
        calls = []
        def provider(body):
            calls.append(body['model'])
            result = tool_call() if len(calls) == 1 else final_answer()
            return {**result, 'model': selected.removeprefix('openai/')}
        server = proxy.ThreadingHTTPServer(('127.0.0.1', 0), proxy.handler_class('http://unused', provider, models.DEFAULT_MODEL))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f'http://127.0.0.1:{server.server_port}'
        headers = {'Origin': 'http://127.0.0.1:5177', 'Content-Type': CONTENT_TYPE, 'X-Orq-Model': 'unknown'}
        try:
            with patch.object(proxy, 'backend_request', return_value=FIXTURE) as retrieve:
                invalid = request.Request(base + '/api/search', data=BODY, headers=headers)
                with self.assertRaises(error.HTTPError) as rejected: request.urlopen(invalid)
                self.assertEqual(rejected.exception.code, 400)
                rejected.exception.close()
                self.assertEqual(calls, [])
                retrieve.assert_not_called()
                headers['X-Orq-Model'] = selected
                with request.urlopen(request.Request(base + '/api/search', data=BODY, headers=headers)) as response:
                    result = json.load(response)
                self.assertEqual(result['explanation_requested_model'], selected)
                self.assertEqual(result['explanation_model'], selected.removeprefix('openai/'))
                self.assertEqual(calls, [selected, selected])
                retrieve.assert_called_once_with('http://unused', '/api/search', BODY, CONTENT_TYPE)
            with request.urlopen(base + '/api/models') as response:
                self.assertEqual(json.load(response)['default_model'], models.DEFAULT_MODEL)
            options = request.Request(base + '/api/search', method='OPTIONS', headers={'Origin': headers['Origin']})
            with request.urlopen(options) as response:
                self.assertIn('X-Orq-Model', response.headers['Access-Control-Allow-Headers'])
                self.assertEqual(response.headers['Access-Control-Allow-Origin'], headers['Origin'])
        finally:
            server.shutdown()
            server.server_close()
            thread.join()


if __name__ == '__main__':
    unittest.main()
