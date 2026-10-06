"""Regression checks for the validator CLI; no external dependencies."""

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "check_agents_md.py"
sys.path.insert(0, str(SCRIPT.parent))
from check_agents_md import check

VALID_DOC = """<!-- agentify:start -->
## Commands
| Task | Command | Status |
|---|---|---|
| Test | `python -m unittest` | not verified (example) |
<!-- agentify:end -->
"""


class ValidatorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.doc = self.root / "AGENTS.md"
        self.doc.write_text(VALID_DOC, encoding="utf-8")

    def run_validator(self, *args):
        return subprocess.run(
            [sys.executable, str(SCRIPT), str(self.root), *args],
            capture_output=True, text=True, encoding="utf-8", timeout=10,
        )

    def test_document_check_accepts_valid_block(self):
        report = check(self.root, self.doc)
        self.assertEqual(report.errors, [])
        self.assertEqual(report.warnings, [])

    def test_document_check_rejects_reversed_markers(self):
        self.doc.write_text(
            "<!-- agentify:end -->\n## Commands\n<!-- agentify:start -->\n",
            encoding="utf-8",
        )
        self.assertTrue(any("markers" in error for error in check(self.root, self.doc).errors))

    def test_default_and_explicit_claude_keep_missing_file_warning(self):
        for args in ((), ("--agent", "claude")):
            with self.subTest(args=args):
                result = self.run_validator(*args)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("no sibling CLAUDE.md", result.stdout)

    def test_codex_omits_claude_warnings_without_writing_files(self):
        claude = self.root / "CLAUDE.md"
        for content in (None, "Human instructions\n", "@AGENTS.md\n"):
            with self.subTest(content=content):
                if content is not None:
                    claude.write_text(content, encoding="utf-8")
                before = {p.name: p.read_bytes() for p in self.root.iterdir()}
                result = self.run_validator("--agent", "codex")
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("0 error(s), 0 warning(s)", result.stdout)
                after = {p.name: p.read_bytes() for p in self.root.iterdir()}
                self.assertEqual(before, after)

    def test_claude_still_checks_existing_import(self):
        claude = self.root / "CLAUDE.md"
        claude.write_text("Human instructions\n", encoding="utf-8")
        self.assertIn("does not import", self.run_validator().stdout)
        claude.write_text("@AGENTS.md\n", encoding="utf-8")
        self.assertIn("0 warning(s)", self.run_validator().stdout)

    def test_codex_keeps_document_and_secret_errors(self):
        (self.root / ".env").write_text("API_TOKEN=fixture-secret-value\n", encoding="utf-8")
        cases = {
            "markers": VALID_DOC.replace("<!-- agentify:end -->", ""),
            "command row": VALID_DOC.replace("not verified (example)", "unknown"),
            "secret leak": VALID_DOC + "fixture-secret-value\n",
        }
        for error, text in cases.items():
            with self.subTest(error=error):
                self.doc.write_text(text, encoding="utf-8")
                result = self.run_validator("--agent", "codex")
                self.assertEqual(result.returncode, 1, result.stderr)
                self.assertIn(error, result.stdout)
                self.assertNotIn("fixture-secret-value", result.stdout)

    def test_codex_supports_explicit_doc_path(self):
        result = self.run_validator(str(self.doc), "--agent", "codex")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("[PASS] AGENTS.md", result.stdout)

    def test_invalid_agent_is_rejected(self):
        result = self.run_validator("--agent", "unknown")
        self.assertEqual(result.returncode, 2)
        self.assertIn("invalid choice", result.stderr)

    def test_codex_reports_missing_agents_doc(self):
        self.doc.unlink()
        result = self.run_validator("--agent", "codex")
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("no AGENTS.md found", result.stderr)


if __name__ == "__main__":
    unittest.main()
