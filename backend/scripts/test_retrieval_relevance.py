"""One targeted mocked judge workflow; no model or network calls."""
import json
import unittest
from unittest.mock import patch

import retrieval_relevance as evaluation


class RelevanceTest(unittest.TestCase):
    def test_one_call_preserves_ids_grades_and_verbatim_quotes(self):
        response = {"mode": "query", "results": [
            {"case_id": str(i), "score": 0.9 - i / 10,
             "passage": {"text": f"Exact source passage for case {i}."}}
            for i in range(3)
        ]}
        passages = evaluation.passages_from_response(response, "query")
        rows = [{"case_id": key, "grade": i, "reasoning": "Synthetic reason.", "quote": text}
                for i, (key, text) in enumerate(passages.items())]
        completion = {"model": "mock/model", "choices": [{"finish_reason": "stop", "message": {"content": json.dumps({"judgments": rows})}}]}
        with patch.object(evaluation, "fetch_json", return_value=completion) as call:
            actual, model, _ = evaluation.judge("Synthetic question", None, passages, "mock/model", "synthetic-key", evaluation.ORQ_BASE_URL)
            self.assertEqual(actual, rows)
            self.assertEqual(model, "mock/model")
            self.assertEqual(call.call_count, 1)
        rows[0]["quote"] = "A fabricated source quote."
        with self.assertRaises(evaluation.EvaluationError):
            evaluation.validate_judgments({"judgments": rows}, passages)


if __name__ == "__main__":
    unittest.main()
