"""Pure fixed-target checks, without search or external inference."""
import copy
import unittest
from pathlib import Path

import deterministic_b1 as b1


class DeterministicB1Test(unittest.TestCase):
    def test_unordered_expected_ids_and_missing_invalid_results(self):
        fixture, _ = b1.load_fixture(Path(__file__).resolve().parents[2])
        ids = ['156040', '156042', '156000', '156001']
        cases = {case_id: {'metadata': {'case_id': case_id, 'title': case_id, 'text_version': 'synthetic'}} for case_id in ids}
        def response(order):
            return {'mode': 'query', 'corpus_version': fixture['context']['corpus_version'],
                    'ranking_version': fixture['context']['ranking_version'],
                    'results': [{**cases[case_id]['metadata'], 'score': 0.9 - rank / 10} for rank, case_id in enumerate(order)]}
        good = response(['156042', '156040', '156000'])
        self.assertTrue(b1.score(fixture, good, cases)['passed'])
        failed = b1.score(fixture, response(['156040', '156000', '156001']), cases)
        self.assertFalse(failed['passed'])
        self.assertEqual(failed['hit_count'], 1)
        for changed in ['duplicate', 'unknown', 'corpus']:
            invalid = copy.deepcopy(good)
            if changed == 'duplicate': invalid['results'][2] = invalid['results'][0]
            if changed == 'unknown': invalid['results'][2]['case_id'] = 'unknown'
            if changed == 'corpus': invalid['corpus_version'] = 'different'
            with self.assertRaises(ValueError):
                b1.score(fixture, invalid, cases)


if __name__ == '__main__':
    unittest.main()
