import unittest
from contextlib import redirect_stderr
from io import StringIO
from unittest.mock import patch

import resource_guard as guard

from resource_guard import MAX_RSS_KIB, command_timeout_limit, parse_arguments, violation


class ResourceBudgetTests(unittest.TestCase):
    MEMINFO = 'MemTotal: 10000 kB\nMemAvailable: 1000 kB\nSwapTotal: 1048576 kB\nSwapFree: 524288 kB\nHugePages_Total: 0\n'

    def test_linux_reads_meminfo_instead_of_macos_commands(self):
        with (patch.object(guard.sys, 'platform', 'linux'),
              patch.object(guard.Path, 'read_text', return_value=self.MEMINFO) as read,
              patch.object(guard.subprocess, 'check_output', side_effect=['1', 'used = 4M']) as command):
            self.assertEqual(guard.system_metrics(), {'pressure_level': 1, 'swap_used_mib': 512})
        read.assert_called_once_with(encoding='utf-8')
        command.assert_not_called()

    def test_linux_pressure_boundary_and_swap_units(self):
        for available, expected in [(1001, 1), (1000, 1), (999, 2), (0, 2)]:
            with self.subTest(available=available):
                sample = guard.parse_linux_meminfo(self.MEMINFO.replace('MemAvailable: 1000', f'MemAvailable: {available}'))
                self.assertEqual(sample, {'pressure_level': expected, 'swap_used_mib': 512})
        no_swap = self.MEMINFO.replace('1048576 kB', '0 kB').replace('524288 kB', '0 kB')
        self.assertEqual(guard.parse_linux_meminfo(no_swap)['swap_used_mib'], 0)

    def test_linux_rejects_untrustworthy_metrics(self):
        bad = [self.MEMINFO.replace('MemTotal: 10000 kB\n', ''), self.MEMINFO + 'MemTotal: 10000 kB\n',
               self.MEMINFO.replace('10000 kB', '0 kB'), self.MEMINFO.replace('1000 kB', '-1 kB'),
               self.MEMINFO.replace('1000 kB', '10001 kB'), self.MEMINFO.replace('1000 kB', '1.5 kB'),
               self.MEMINFO.replace('1000 kB', '1000 MB'), self.MEMINFO.replace('524288 kB', '1048577 kB')]
        for text in bad:
            with self.subTest(text=text), self.assertRaises(ValueError):
                guard.parse_linux_meminfo(text)
        for line in self.MEMINFO.splitlines(keepends=True)[:4]:
            for text in (self.MEMINFO.replace(line, ''), self.MEMINFO + line):
                with self.subTest(text=text), self.assertRaises(ValueError):
                    guard.parse_linux_meminfo(text)

    def test_unreadable_linux_metrics_and_unknown_platform_fail_closed(self):
        with (patch.object(guard.sys, 'platform', 'linux'),
              patch.object(guard.Path, 'read_text', side_effect=OSError('unavailable')),
              self.assertRaises(OSError)):
            guard.system_metrics()
        with patch.object(guard.sys, 'platform', 'win32'), self.assertRaises(ValueError):
            guard.system_metrics()

    def test_macos_metrics_and_platform_peak_units_are_preserved(self):
        with (patch.object(guard.sys, 'platform', 'darwin'),
              patch.object(guard.subprocess, 'check_output', side_effect=['1', 'used = 1.5G'])):
            self.assertEqual(guard.system_metrics(), {'pressure_level': 1, 'swap_used_mib': 1536})
            self.assertEqual(guard.peak_rss_mib(512 * 1024 * 1024), 512)
        with patch.object(guard.sys, 'platform', 'linux'):
            self.assertEqual(guard.peak_rss_mib(512 * 1024), 512)

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
