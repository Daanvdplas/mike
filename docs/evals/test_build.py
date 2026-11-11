"""Protect the documentation source and freshness contract, not retrieval quality."""

from pathlib import Path
import json
import shutil
import subprocess
import sys
import tempfile
import unittest


HERE = Path(__file__).resolve().parent


class DocumentationBuildTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        shutil.copytree(HERE, self.root / "evals", ignore=shutil.ignore_patterns("__pycache__"))
        shutil.copy(HERE.parent / "EVALUATIEOPDRACHT.md", self.root)
        self.source = self.root / "EVALUATIEOPDRACHT.md"
        self.output = self.root / "evals" / "index.html"

    def run_build(self, *args):
        return subprocess.run(
            [sys.executable, str(self.root / "evals" / "build.py"), *args],
            capture_output=True,
            text=True,
            check=False,
        )

    def test_source_change_is_visible_and_stale_check_does_not_write(self):
        result = self.run_build()
        self.assertEqual(result.returncode, 0, result.stderr)
        original = self.output.read_bytes()
        self.source.write_text(self.source.read_text() + "\n## Nieuwe bronafspraak\n\nUnieke afspraak voor deze test.\n")
        result = self.run_build("--check")
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertEqual(self.output.read_bytes(), original, "--check must never rewrite the artifact")
        result = self.run_build()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Unieke afspraak voor deze test.", self.output.read_text())
        self.assertNotEqual(self.output.read_bytes(), original)
        self.assertEqual(self.run_build("--check").returncode, 0)

    def test_catalog_title_change_is_visible_escaped_and_detected_as_stale(self):
        self.assertEqual(self.run_build().returncode, 0)
        original = self.output.read_bytes()
        catalog_path = self.root / "evals" / "scenarios.json"
        catalog = json.loads(catalog_path.read_text())
        catalog["scenarios"][0]["title"] = '<script>untrusted catalog title</script>'
        catalog_path.write_text(json.dumps(catalog))
        self.assertEqual(self.run_build("--check").returncode, 1)
        self.assertEqual(self.output.read_bytes(), original)
        self.assertEqual(self.run_build().returncode, 0)
        rendered = self.output.read_text()
        self.assertIn('&lt;script&gt;untrusted catalog title&lt;/script&gt;', rendered)
        self.assertNotIn('<script>untrusted catalog title</script>', rendered)
        self.assertEqual(self.run_build("--check").returncode, 0)

    def test_raw_source_html_is_text_not_executable_markup(self):
        self.source.write_text(self.source.read_text() + '\n<script>window.untrusted = true;</script>\n')
        result = self.run_build()
        self.assertEqual(result.returncode, 0, result.stderr)
        rendered = self.output.read_text()
        self.assertNotIn("<script>window.untrusted", rendered)
        self.assertIn("&lt;script&gt;window.untrusted", rendered)

    def test_missing_source_section_fails_without_overwriting_output(self):
        result = self.run_build()
        self.assertEqual(result.returncode, 0, result.stderr)
        original = self.output.read_bytes()
        self.source.write_text(self.source.read_text().replace("## Scenarioselectie en relevantie", "## Onverwacht hernoemd"))
        result = self.run_build()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.output.read_bytes(), original)
        self.assertIn("Scenarioselectie en relevantie", result.stderr)


if __name__ == "__main__":
    unittest.main()
