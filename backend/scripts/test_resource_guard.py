import unittest

from resource_guard import MAX_RSS_KIB, violation


class ResourceBudgetTests(unittest.TestCase):
    def test_normal_pressure_and_bounded_usage_pass(self):
        sample = {"rss_kib": 500_000, "pressure_level": 1, "swap_used_mib": 4100}
        self.assertIsNone(violation(sample, 4096, 20, 180))

    def test_each_budget_boundary_stops_the_job(self):
        base = {"rss_kib": 500_000, "pressure_level": 1, "swap_used_mib": 4096}
        checks = [
            ({**base, "rss_kib": MAX_RSS_KIB}, 20, "rss_limit"),
            ({**base, "pressure_level": 2}, 20, "system_memory_pressure"),
            ({**base, "swap_used_mib": 4224}, 20, "swap_growth"),
            (base, 180, "timeout"),
        ]
        for sample, elapsed, expected in checks:
            with self.subTest(expected=expected):
                self.assertEqual(violation(sample, 4096, elapsed, 180), expected)


if __name__ == "__main__":
    unittest.main()
