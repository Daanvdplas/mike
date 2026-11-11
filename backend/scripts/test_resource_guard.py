import unittest
from contextlib import redirect_stderr
from io import StringIO

from resource_guard import MAX_RSS_KIB, command_timeout_limit, parse_arguments, violation


class ResourceBudgetTests(unittest.TestCase):
    def test_parser_accepts_preview_deadline_only_with_the_explicit_flag(self):
        options = ["--label", "policy", "--report", "/tmp/policy-report.json", "--log", "/tmp/policy.log"]
        preview = ["--serve-preview", "--timeout-seconds", "7200", "--", "./backend/target/debug/texas-case-finder", "serve"]
        with redirect_stderr(StringIO()):
            try:
                args, command = parse_arguments(options + preview)
            except SystemExit:
                self.fail("The explicit direct-server preview should accept 7200 seconds")
        self.assertTrue(args.serve_preview)
        self.assertEqual(args.timeout_seconds, 7200)
        self.assertEqual(command[-1], "serve")
        for rejected in [
            ["--timeout-seconds", "7200", "--", "./backend/target/debug/texas-case-finder", "serve"],
            ["--serve-preview", "--timeout-seconds", "7201", "--", "./backend/target/debug/texas-case-finder", "serve"],
            ["--serve-preview", "--timeout-seconds", "7200", "--", "./backend/target/debug/texas-case-finder", "import", "corpus"],
            ["--timeout-seconds", "601", "--", "python3", "-m", "unittest"],
        ]:
            with self.subTest(argv=rejected), redirect_stderr(StringIO()), self.assertRaises(SystemExit):
                parse_arguments(options + rejected)

    def test_only_explicit_direct_serve_preview_gets_two_hour_limit(self):
        for binary in ["/tmp/backend/texas-case-finder", "./backend/target/debug/texas-case-finder"]:
            with self.subTest(binary=binary):
                self.assertEqual(command_timeout_limit([binary, "serve"], True), 7200)
                self.assertEqual(command_timeout_limit([binary, "serve"]), 600)
        self.assertEqual(command_timeout_limit(["python3", "-m", "unittest"]), 600)
        self.assertEqual(command_timeout_limit(["/tmp/backend/texas-case-finder", "import", "corpus"]), 600)

    def test_preview_rejects_aliases_wrappers_and_other_commands(self):
        commands = [
            [], ["texas-case-finder", "serve"], ["/tmp/other-server", "serve"],
            ["/tmp/texas-case-finder", "import", "corpus"],
            ["/tmp/texas-case-finder", "serve", "extra"],
            ["cargo", "run", "--", "serve"], ["sh", "-c", "/tmp/texas-case-finder serve"],
        ]
        for command in commands:
            with self.subTest(command=command), self.assertRaises(ValueError):
                command_timeout_limit(command, True)

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
