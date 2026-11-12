"""One lightweight web-route check; no native model or external API calls."""
import json
from contextlib import closing
from pathlib import Path
import hashlib
import math
import sqlite3
import tempfile
import threading
import unittest
from urllib import error, request
from unittest.mock import patch

import evals_web


class EvalsWebTest(unittest.TestCase):
    def test_e06_ai_grades_keep_private_raw_responses_and_method_lineage(self):
        with tempfile.TemporaryDirectory() as temporary:
            config = {'repo': evals_web.REPO, 'outputs': Path(temporary), 'backend': 'http://unused', 'retrieval_methods': ['opinion_chunks', 'head_matter'], 'judge_enabled': True, 'model': 'mock/model', 'key': 'synthetic-private-key', 'orq_base': 'http://unused'}
            manifest = {'corpus_version': 'synthetic-corpus', 'embedding': {'model': 'same-local-model'}}
            def search(_url, query, document, method, excluded):
                rows = [{'case_id': str(i), 'title': f'Case {i}', 'score': .8, 'passage': {'text': f'Literal evidence for case {i}.', 'source_section': 'head_matter' if method == 'head_matter' else 'majority'}} for i in range(3)]
                return {'response': {'mode': 'query', 'retrieval_method': method, 'corpus_version': 'synthetic-corpus', 'ranking_version': 'cosine-max-v1', 'results': rows}, 'excluded_case_ids': ['156133'], 'eligible_case_count': 134, 'index_manifest': manifest}
            provider_responses = []
            def provider(req):
                supplied = json.loads(json.loads(req.data)['messages'][1]['content'])['cases']
                judgments = {row['case_id']: {'grade': i, 'reasoning': 'Synthetic relevance reason.', 'quote_id': next(iter(row['source_options']))} for i, row in enumerate(supplied)}
                response = {'id': f'synthetic-{len(provider_responses)}', 'model': 'mock/model', 'choices': [{'finish_reason': 'stop', 'message': {'content': json.dumps({'judgments': judgments})}}], 'usage': {'total_tokens': 150}}
                provider_responses.append(response); return response
            with patch.object(evals_web, 'indexed_source', return_value=(manifest, {'case_id': '156133', 'file': 'source.json'}, 'Not sent as query context')), patch.object(evals_web.relevance, 'search', side_effect=search), patch.object(evals_web.relevance, 'fetch_json', side_effect=provider):
                result = evals_web.run_eval(config, 'E06')
            self.assertEqual(len(provider_responses), 2)
            self.assertEqual(result['runs'][0]['input_sha256'], result['runs'][1]['input_sha256'])
            for run, provider_response in zip(result['runs'], provider_responses):
                self.assertEqual(run['judge_status'], 'completed')
                self.assertEqual([row['grade'] for row in run['judgments']], [0, 1, 2])
                self.assertEqual((run['requested_model'], run['model']), ('mock/model', 'mock/model'))
                trace = Path(temporary) / run['judge_response_artifact']
                self.assertEqual(json.loads(trace.read_text()), provider_response)
                self.assertEqual(trace.stat().st_mode & 0o777, 0o600)
                self.assertEqual(hashlib.sha256(trace.read_bytes()).hexdigest(), run['judge_response_sha256'])
                self.assertNotIn('synthetic-private-key', trace.read_text())
            trace = Path(temporary) / result['runs'][0]['judge_response_artifact']
            before = trace.read_bytes()
            with self.assertRaises(FileExistsError): evals_web.private_json(trace, {'overwrite': True})
            self.assertEqual(trace.read_bytes(), before)

    def test_primary_b1_accepts_each_method_and_both_without_a_judge(self):
        calls = []
        def run(config, eval_id):
            calls.append((eval_id, config['retrieval_methods'], config['judge_enabled']))
            return {'eval_id': eval_id, 'status': 'completed'}
        server = evals_web.ThreadingHTTPServer(('127.0.0.1', 0), evals_web.handler_class({'repo': evals_web.REPO, 'key': ''}, run))
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        base = f'http://127.0.0.1:{server.server_port}'
        try:
            for methods in [['opinion_chunks'], ['head_matter'], ['opinion_chunks', 'head_matter']]:
                req = request.Request(base + '/api/evals/B1/run', data=json.dumps({'retrieval_methods': methods}).encode(), headers={'Origin': base, 'Content-Type': 'application/json'})
                try:
                    with request.urlopen(req) as response: self.assertEqual(json.load(response)['status'], 'completed')
                except error.HTTPError as failure:
                    failure.close(); self.fail('The normal B1 action must accept local method selection.')
            self.assertEqual(calls, [('B1', methods, False) for methods in [['opinion_chunks'], ['head_matter'], ['opinion_chunks', 'head_matter']]])
        finally:
            server.shutdown(); server.server_close(); thread.join()

    def test_judge_model_choices_are_validated_without_blocking_local_retrieval(self):
        alternate = 'openai/gpt-4.1-2025-04-14'
        config = {'repo': evals_web.REPO, 'key': 'synthetic'}
        calls = []
        def run(actual, eval_id):
            calls.append((eval_id, actual['retrieval_methods'], actual['judge_enabled'], actual.get('model')))
            return {'eval_id': eval_id, 'status': 'completed'}
        server = evals_web.ThreadingHTTPServer(('127.0.0.1', 0), evals_web.handler_class(config, run))
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        base = f'http://127.0.0.1:{server.server_port}'
        def req(eval_id, payload):
            return request.Request(base + f'/api/evals/{eval_id}/run', data=json.dumps(payload).encode(), headers={'Origin': base, 'Content-Type': 'application/json'})
        try:
            with request.urlopen(base + '/api/models') as response:
                self.assertIn(alternate, [model['id'] for model in json.load(response)['models']])
            with request.urlopen(req('E06', {'retrieval_methods': ['head_matter'], 'judge': True, 'model': alternate})) as response:
                self.assertEqual(json.load(response)['status'], 'completed')
            self.assertEqual(calls[-1], ('E06', ['head_matter'], True, alternate))
            with request.urlopen(req('E06', {'model': alternate})) as response:
                self.assertEqual(json.load(response)['status'], 'completed')
            self.assertEqual(calls[-1][-1], alternate)
            for eval_id, payload in [('E06', {'judge': True, 'model': 'unknown'}), ('E06', {'model': None}), ('B1', {'model': alternate}), ('B1', {'judge': False})]:
                with self.subTest(eval_id=eval_id, payload=payload), self.assertRaises(error.HTTPError) as rejected:
                    request.urlopen(req(eval_id, payload))
                self.assertEqual(rejected.exception.code, 400); rejected.exception.close()
            config['key'] = ''
            with request.urlopen(req('E06', {'retrieval_methods': ['opinion_chunks', 'head_matter'], 'judge': False})) as response:
                self.assertEqual(json.load(response)['status'], 'completed')
            self.assertFalse(calls[-1][2])
            with self.assertRaises(error.HTTPError) as rejected:
                request.urlopen(req('E06', {'judge': True, 'model': alternate}))
            self.assertEqual(rejected.exception.code, 503); rejected.exception.close()
        finally:
            server.shutdown(); server.server_close(); thread.join()

    def test_primary_b1_scores_real_targets_per_method_on_the_bound_index(self):
        fixture, fixture_hash = evals_web.b1.load_fixture(evals_web.REPO)
        ids = ['156040', '156042', '156000', '156001']
        cases = {key: {'metadata': {'case_id': key, 'title': key, 'text_version': 'test-version'}, 'text': key, 'head_matter': key, 'head_matter_text_version': 'test-version'} for key in ids}
        manifest = {'format_version': 3, 'corpus_version': fixture['context']['corpus_version'], 'pipeline': fixture['context']['index_pipeline'], 'embedding': fixture['context']['embedding']}
        with tempfile.TemporaryDirectory() as temporary:
            config = {'repo': evals_web.REPO, 'outputs': Path(temporary), 'backend': 'http://unused', 'database': Path('/unused'), 'corpus': Path('/unused'), 'retrieval_methods': ['opinion_chunks', 'head_matter'], 'judge_enabled': False}
            calls = []
            def search(_url, query, document, method, excluded):
                calls.append((query, document, method, excluded))
                order = ids[:3] if method == 'opinion_chunks' else [ids[0], ids[2], ids[3]]
                rows = [{**cases[key]['metadata'], 'score': .8, 'passage': {'source_section': 'majority' if method == 'opinion_chunks' else 'head_matter', 'text_version': 'test-version', 'text': key, 'start_utf16': 0, 'end_utf16': len(key)}} for key in order]
                return {'response': {'mode': 'query', 'retrieval_method': method, 'corpus_version': manifest['corpus_version'], 'ranking_version': 'cosine-max-v1', 'results': rows}, 'index_manifest': manifest, 'excluded_case_ids': [], 'eligible_case_count': 135}
            with patch.object(evals_web.b1, 'verified_index', return_value=(manifest, cases)), patch.object(evals_web.relevance, 'search', side_effect=search), patch.object(evals_web.relevance, 'judge') as judge:
                result = evals_web.run_eval(config, 'B1')
            self.assertEqual(calls, [(fixture['query'], None, method, []) for method in config['retrieval_methods']])
            self.assertEqual([run['hit_count'] for run in result['runs']], [2, 1])
            self.assertEqual([run['passed'] for run in result['runs']], [True, False])
            self.assertTrue(all(run['fixture_sha256'] == fixture_hash for run in result['runs']))
            self.assertEqual(result['runs'][0]['input_sha256'], result['runs'][1]['input_sha256'])
            self.assertEqual(result['fixture_version'], 'appeal-bond-b1-v2'); judge.assert_not_called()

    def test_b1_context_mismatch_stops_before_search_without_rebinding_fixture(self):
        with tempfile.TemporaryDirectory() as temporary:
            config = {'repo': evals_web.REPO, 'outputs': Path(temporary), 'database': Path('/unused.sqlite'), 'corpus': Path('/unused'), 'backend': 'http://unused'}
            with patch.object(evals_web.b1, 'verified_index', side_effect=evals_web.b1.IndexContextError('De index wijkt af van de vooraf vastgelegde corpusversie.')), \
                    patch.object(evals_web.relevance, 'search') as search:
                with self.assertRaisesRegex(evals_web.RunError, 'vooraf vastgelegde corpusversie'):
                    evals_web.run_eval(config, 'B1')
                search.assert_not_called()

    def test_baseline_search_keeps_the_original_query_only_multipart_contract(self):
        with patch.object(evals_web.relevance, 'fetch_json', return_value={}) as fetch:
            evals_web.relevance.search('http://unused', 'Fixed baseline question', None)
        body = fetch.call_args.args[0].data.decode()
        self.assertIn('name="query"', body)
        self.assertNotIn('name="retrieval_method"', body)
        self.assertNotIn('name="excluded_case_ids"', body)

    def test_all_catalog_scenarios_accept_local_method_selection(self):
        config = {"repo": evals_web.REPO, "demo_document": Path('demo.txt'), "key": ''}
        expected = [f'E{i:02}' for i in range(1, 26)]
        catalog = evals_web.catalog(config)
        self.assertEqual([row['id'] for row in catalog['evals']], ['B1', 'E06'])
        self.assertEqual([row['id'] for row in catalog['diagnostic_evals']], expected)
        calls = []
        def run(actual_config, eval_id):
            calls.append(eval_id)
            return {'eval_id': eval_id, 'status': 'completed'}
        server = evals_web.ThreadingHTTPServer(('127.0.0.1', 0), evals_web.handler_class(config, run))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f'http://127.0.0.1:{server.server_port}'
        try:
            for eval_id in expected:
                with self.subTest(eval_id=eval_id):
                    req = request.Request(base + f'/api/evals/{eval_id}/run', data=b'{}', headers={'Origin': base, 'Content-Type': 'application/json'})
                    with request.urlopen(req) as response:
                        self.assertEqual(json.load(response)['eval_id'], eval_id)
            self.assertEqual(calls, expected)
        finally:
            server.shutdown(); server.server_close(); thread.join()

    def test_scenario_input_modes_preserve_full_majority_hashes_and_source_exclusion(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'docs/evals').mkdir(parents=True)
            (root / 'corpus/json').mkdir(parents=True)
            database = root / 'cases.sqlite'
            manifest = {'corpus_version': 'synthetic-corpus', 'embedding': {'model': 'synthetic-model'}}
            rows, expected = [], {}
            with closing(sqlite3.connect(database)) as db:
                db.execute('CREATE TABLE metadata (id INTEGER, manifest TEXT)')
                db.execute('INSERT INTO metadata VALUES (1, ?)', (json.dumps(manifest),))
                db.execute('CREATE TABLE cases (case_id TEXT, record TEXT)')
                for eval_id, mode in [('E01', 'document'), ('E06', 'query'), ('E11', 'combined')]:
                    case_id = f'source-{eval_id}'
                    text = f'Complete synthetic majority text for {eval_id}. No editorial text.'
                    digest = hashlib.sha256(text.encode()).hexdigest()
                    source = {'id': case_id, 'decision_date': '1892-04-20', 'analysis': {'pagerank': {'raw': 7.317852702137001e-08}}, 'casebody': {'opinions': [{'type': 'majority', 'text': text}], 'head_matter': 'Never use this as document input.'}}
                    (root / f'corpus/json/{eval_id}.json').write_text(json.dumps(source))
                    db.execute('INSERT INTO cases VALUES (?, ?)', (case_id, json.dumps({'text': text, 'metadata': {'text_version': 'sha256:' + digest}, 'source_json': json.dumps(source)})))
                    row = {'id': eval_id, 'title': eval_id, 'input_mode': mode, 'query_case_id': case_id,
                           'source_case': {'id': case_id, 'name': eval_id, 'file': f'json/{eval_id}.json', 'decision_date': source['decision_date']},
                           'document': {'field': 'casebody.opinions[0].text', 'opinion_type': 'majority', 'sha256': digest} if mode != 'query' else None,
                           'query': {'en': f'Exact question for {eval_id}', 'nl': 'Leesvertaling'} if mode != 'document' else None,
                           'expected_behavior': 'Synthetic expectation', 'why': 'Synthetic reason'}
                    rows.append(row)
                    expected[eval_id] = (row['query']['en'] if row['query'] else None, text if row['document'] else None, mode, case_id)
                db.commit()
            catalog_path = root / 'docs/evals/scenarios.json'
            catalog_path.write_text(json.dumps({'schema_version': 1, 'status': 'ontwerp', 'scenarios': rows}))
            config = {'repo': root, 'corpus': root / 'corpus', 'database': database, 'outputs': root / 'runs', 'backend': 'http://local',
                      'model': 'not-requested', 'key': '', 'retrieval_methods': ['opinion_chunks', 'head_matter'], 'judge_enabled': False}
            for eval_id, (query, document, mode, case_id) in expected.items():
                with self.subTest(eval_id=eval_id):
                    calls = []
                    def search(_url, actual_query, actual_document, method, excluded):
                        calls.append((actual_query, actual_document, method, excluded))
                        return {'response': {'mode': mode, 'retrieval_method': method, 'corpus_version': 'synthetic-corpus', 'ranking_version': 'cosine-max-v1',
                                             'results': [{'case_id': str(i), 'title': f'Case {i}', 'score': .9 - i / 10, 'case_url': f'/api/cases/{i}',
                                                          'passage': {'text': f'Exact synthetic source passage {i}.', 'source_section': 'head_matter' if method == 'head_matter' else 'majority'}} for i in range(3)]},
                                'index_manifest': manifest, 'excluded_case_ids': excluded, 'eligible_case_count': 134}
                    with patch.object(evals_web.relevance, 'search', side_effect=search):
                        result = evals_web.run_eval(config, eval_id)
                    self.assertEqual(calls, [(query, document, method, [case_id]) for method in ['opinion_chunks', 'head_matter']])
                    self.assertTrue(all(run['source']['case_id'] == case_id and run['eligible_case_count'] == 134 for run in result['runs']))
                    self.assertEqual(result['input']['mode'], mode)
            with closing(sqlite3.connect(database)) as db:
                stored = json.loads(db.execute('SELECT record FROM cases WHERE case_id=?', ('source-E01',)).fetchone()[0])
                altered = json.loads(stored['source_json'])
                altered['analysis']['pagerank']['raw'] = math.nextafter(altered['analysis']['pagerank']['raw'], math.inf)
                stored['source_json'] = json.dumps(altered)
                db.execute('UPDATE cases SET record=? WHERE case_id=?', (json.dumps(stored), 'source-E01'))
                db.commit()
            with self.assertRaises(evals_web.RunError):
                evals_web.run_eval(config, 'E01')
            rows[0]['document']['sha256'] = '0' * 64
            catalog_path.write_text(json.dumps({'schema_version': 1, 'status': 'ontwerp', 'scenarios': rows}))
            with self.assertRaises(evals_web.RunError):
                evals_web.run_eval(config, 'E01')

    def test_compares_both_methods_without_a_model_call_and_preserves_run_inputs(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config = {"repo": evals_web.REPO, "outputs": root / 'runs',
                      "backend": 'http://127.0.0.1:18081', "model": 'not-requested', "key": '',
                      "orq_base": 'http://unused', "retrieval_methods": ['opinion_chunks', 'head_matter'],
                      "judge_enabled": False}
            requests = []
            def fetch(req):
                body = req.data.decode()
                method = 'head_matter' if '\r\n\r\nhead_matter\r\n' in body else 'opinion_chunks'
                requests.append((req.full_url, body, method))
                response = {"mode": 'query', "corpus_version": 'same-corpus', "ranking_version": 'cosine-max-v1',
                            "retrieval_method": method, "results": [
                    {"case_id": str(i), "title": f'Case {i}', "score": .8 - i / 10, "case_url": f'/api/cases/{i}',
                     "passage": {"text": f'Verbatim source passage for case {i}.', "source_section": 'head_matter' if method == 'head_matter' else 'majority'}}
                    for i in range(3)
                ]}
                return {"response": response, "excluded_case_ids": ['156133'], "eligible_case_count": 134,
                        "index_manifest": {"corpus_version": 'same-corpus', "model": {"model": 'same-model'}}} if req.full_url.endswith('/api/evals/search') else response
            with patch.object(evals_web.relevance, 'fetch_json', side_effect=fetch), \
                    patch.object(evals_web.relevance, 'judge', side_effect=AssertionError('Paid judge must stay off.')), \
                    patch.object(evals_web, 'indexed_source', return_value=({'corpus_version': 'same-corpus', 'model': {'model': 'same-model'}}, {'case_id': '156133', 'file': 'source.json'}, 'Not sent for query-only')):
                result = evals_web.run_eval(config, 'E06')
            self.assertEqual([run['retrieval_method'] for run in result['runs']], ['opinion_chunks', 'head_matter'])
            self.assertEqual(len(requests), 2)
            self.assertTrue(all(url.endswith('/api/evals/search') for url, _, _ in requests))
            self.assertEqual(result['comparison']['shared_case_ids'], ['0', '1', '2'])
            self.assertTrue(all(run['judge_status'] == 'not_requested' for run in result['runs']))
            self.assertEqual(result['runs'][0]['input_sha256'], result['runs'][1]['input_sha256'])
            self.assertTrue((root / 'runs' / result['run_id'] / 'result.json').is_file())

    def test_method_choice_is_validated_and_local_runs_do_not_require_credentials(self):
        calls = []
        config = {"repo": evals_web.REPO, "demo_document": Path('demo.txt'), "key": ''}
        def run(actual_config, eval_id):
            calls.append((eval_id, actual_config['retrieval_methods'], actual_config['judge_enabled']))
            return {'eval_id': eval_id, 'status': 'completed'}
        server = evals_web.ThreadingHTTPServer(('127.0.0.1', 0), evals_web.handler_class(config, run))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f'http://127.0.0.1:{server.server_port}'
        try:
            body = json.dumps({'retrieval_methods': ['opinion_chunks', 'head_matter'], 'judge': False}).encode()
            req = request.Request(base + '/api/evals/E06/run', data=body, headers={'Origin': base, 'Content-Type': 'application/json'})
            with request.urlopen(req) as response:
                self.assertEqual(json.load(response)['status'], 'completed')
            self.assertEqual(calls, [('E06', ['opinion_chunks', 'head_matter'], False)])
            b1body = json.dumps({'retrieval_methods': ['opinion_chunks', 'head_matter']}).encode()
            primary = request.Request(base + '/api/evals/B1/run', data=b1body, headers={'Origin': base, 'Content-Type': 'application/json'})
            with request.urlopen(primary) as response: self.assertEqual(json.load(response)['status'], 'completed')
            self.assertEqual(calls[-1], ('B1', ['opinion_chunks', 'head_matter'], False))
            req = request.Request(base + '/api/evals/E06/run', data=b'{"retrieval_methods":["unknown"]}', headers={'Origin': base, 'Content-Type': 'application/json'})
            with self.assertRaises(error.HTTPError) as rejected:
                request.urlopen(req)
            self.assertEqual(rejected.exception.code, 400)
            rejected.exception.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join()

    def test_catalog_and_one_run_share_the_local_page_without_exposing_files(self):
        calls = []
        config = {"repo": evals_web.REPO, "demo_document": Path("demo.txt"), "key": "synthetic"}
        def run(_config, eval_id):
            calls.append(eval_id)
            return {"eval_id": eval_id, "status": "completed"}
        server = evals_web.ThreadingHTTPServer(('127.0.0.1', 0), evals_web.handler_class(config, run))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_port}"
        try:
            with request.urlopen(base + "/api/evals") as response:
                data = json.load(response)
            self.assertEqual([row['id'] for row in data['evals']], ['B1', 'E06'])
            self.assertEqual(len(data['diagnostic_evals']), 25)
            e06 = next(row for row in data['evals'] if row['id'] == 'E06')
            self.assertEqual(e06['input_mode'], 'query')
            self.assertIsNone(e06['document_label'])
            req = request.Request(base + "/api/evals/E06/run", data=b"{}",
                                  headers={"Origin": base, "Content-Type": "application/json"})
            with request.urlopen(req) as response:
                self.assertEqual(json.load(response)["status"], "completed")
            self.assertEqual(calls, ["E06"])
            for options in ({'model': 'anything'}, {'judge': False}):
                fixed = request.Request(base + '/api/evals/B1/run', data=json.dumps(options).encode(), headers={'Origin': base, 'Content-Type': 'application/json'})
                with self.assertRaises(error.HTTPError) as rejected:
                    request.urlopen(fixed)
                self.assertEqual(rejected.exception.code, 400)
                rejected.exception.close()
            fixed = request.Request(base + '/api/evals/B1/run', data=b'{}', headers={'Origin': base, 'Content-Type': 'application/json'})
            with request.urlopen(fixed) as response:
                self.assertEqual(json.load(response)['status'], 'completed')
            removed = request.Request(base + '/api/evals/relevance/run', data=b'{}', headers={'Origin': base, 'Content-Type': 'application/json'})
            with self.assertRaises(error.HTTPError) as rejected:
                request.urlopen(removed)
            self.assertEqual(rejected.exception.code, 404)
            rejected.exception.close()
            with self.assertRaises(error.HTTPError) as rejected:
                request.urlopen(base + "/.git/config")
            self.assertEqual(rejected.exception.code, 404)
            rejected.exception.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join()


if __name__ == "__main__":
    unittest.main()
