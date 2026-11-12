"""One targeted mocked judge workflow; no model or network calls."""
import json
import unittest
from unittest.mock import patch

from evals import retrieval_relevance as evaluation


class RelevanceTest(unittest.TestCase):
    def test_successful_response_trace_and_editorial_source_labels_are_preserved(self):
        passages = {str(i): f'Exact source passage for case {i}.' for i in range(3)}
        rows = {key: {'grade': i, 'reasoning': 'Synthetic reason.', 'quote_id': f'{key}:q1'} for i, key in enumerate(passages)}
        completion = {'id': 'synthetic-response', 'model': 'mock/model', 'choices': [{'finish_reason': 'stop', 'message': {'content': json.dumps({'judgments': rows})}}], 'usage': {'prompt_tokens': 100}}
        traces = []
        with patch.object(evaluation, 'fetch_json', return_value=completion) as call:
            try:
                checked, model, _ = evaluation.judge('Fixed question', None, passages, 'mock/model', 'synthetic-private-key', evaluation.ORQ_BASE_URL, source_sections={'0': 'head_matter'}, response_sink=traces.append)
            except TypeError:
                self.fail('Successful provider responses must be available for private run evidence.')
            self.assertEqual(traces, [completion])
            self.assertNotIn('synthetic-private-key', json.dumps(traces))
            payload = json.loads(call.call_args.args[0].data)
            supplied = json.loads(payload['messages'][1]['content'])['cases']
            self.assertEqual(supplied[0]['source_section'], 'head_matter')
            self.assertIn('editorial context', payload['messages'][0]['content'])
            self.assertTrue(all(row['quote'] in passages[row['case_id']] for row in checked))
            self.assertEqual(model, 'mock/model')

    def test_one_call_preserves_ids_grades_and_verbatim_quotes(self):
        response = {"mode": "query", "results": [
            {"case_id": str(i), "score": 0.9 - i / 10,
             "passage": {"text": f"Exact source passage for case {i}."}}
            for i in range(3)
        ]}
        passages = evaluation.passages_from_response(response, "query")
        options = evaluation.source_options(passages)
        rows = {key: {"grade": i, "reasoning": "Synthetic reason.", "quote_id": next(iter(options[key]))}
                for i, key in enumerate(passages)}
        completion = {"model": "mock/model", "choices": [{"finish_reason": "stop", "message": {"content": json.dumps({"judgments": rows})}}]}
        with patch.object(evaluation, "fetch_json", return_value=completion) as call:
            actual, model, _ = evaluation.judge("Synthetic question", None, passages, "mock/model", "synthetic-key", evaluation.ORQ_BASE_URL)
            self.assertEqual([row["grade"] for row in actual], [0, 1, 2])
            self.assertTrue(all(row["quote"] in passages[row["case_id"]] for row in actual))
            self.assertEqual(model, "mock/model")
            self.assertEqual(call.call_count, 1)
            schema = json.loads(call.call_args.args[0].data)["response_format"]["json_schema"]
            self.assertTrue(schema["strict"])
            self.assertEqual(schema["schema"]["properties"]["judgments"]["required"], list(passages))
        rows["0"]["quote_id"] = rows["1"]["quote_id"]
        with self.assertRaises(evaluation.EvaluationError):
            evaluation.validate_judgments({"judgments": rows}, passages)


if __name__ == "__main__":
    unittest.main()
