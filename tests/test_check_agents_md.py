"""Regression checks for the validator CLI; no external dependencies."""

import json
import re
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

    def write_review(self, key, source="manifest.txt", reason="Public name confirmed independently"):
        result = self.run_validator("--agent", "codex")
        match_line = next(line for line in result.stdout.splitlines() if f"env match {key} " in line)
        match_id = re.search(r"review ([0-9a-f]{64})", match_line).group(1)
        path = self.root / "reviews.json"
        path.write_text(json.dumps({match_id: {"source": source, "reason": reason}}), encoding="utf-8")
        return path

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

    def test_no_env_key_is_automatically_exempt(self):
        for key in ("APP_NAME", "SERVICE_NAME", "NODE_ENV", "CUSTOM_SETTING"):
            with self.subTest(key=key):
                (self.root / ".env").write_text(f"{key}=ExampleService\n", encoding="utf-8")
                text = VALID_DOC.replace("## Commands", "## Project\nExampleService (from docs).\n\n## Commands")
                self.doc.write_text(text, encoding="utf-8")
                result = self.run_validator("--agent", "codex")
                self.assertEqual(result.returncode, 1, result.stderr)
                self.assertIn(f"env match {key}", result.stdout)
                self.assertEqual(self.doc.read_text(encoding="utf-8"), text)
                self.assertNotIn("ExampleService", result.stdout)

    def test_framework_facts_are_preserved_across_ecosystems(self):
        cases = (
            ("APP_NAME", "Laravel", "Laravel 11 / PHP >=8.2"),
            ("PROJECT_NAME", "Django", "Django 5 / Python >=3.10"),
            ("SERVICE_NAME", "Express", "Express 5 / Node >=18"),
            ("APPLICATION_NAME", "Ruby on Rails", "Ruby on Rails 7 / Ruby >=3.1"),
            ("SERVICE_NAME", "SpringBoot", "SpringBoot 3 / Java >=17"),
            ("APPLICATION_NAME", "AspNetCore", "AspNetCore 8 / .NET 8"),
        )
        for key, value, stack in cases:
            with self.subTest(stack=stack):
                (self.root / ".env").write_text(f"{key}={value}\n", encoding="utf-8")
                text = VALID_DOC.replace("## Commands", f"## Project\n{stack} (from config).\n\n## Commands")
                self.doc.write_text(text, encoding="utf-8")
                (self.root / "manifest.txt").write_text(stack, encoding="utf-8")
                review = self.write_review(key)
                result = self.run_validator("--agent", "codex", "--env-reviews", str(review))
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn(f"reviewed env match {key}", result.stdout)
                self.assertEqual(self.doc.read_text(encoding="utf-8"), text)
                self.assertNotIn(value, result.stdout)

    def test_unknown_env_keys_remain_blocking_without_printing_values(self):
        (self.root / ".env").write_text("CUSTOM_SETTING=fixture-private-value\n", encoding="utf-8")
        self.doc.write_text(VALID_DOC + "fixture-private-value\n", encoding="utf-8")
        result = self.run_validator("--agent", "codex")
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("CUSTOM_SETTING", result.stdout)
        self.assertNotIn("fixture-private-value", result.stdout)

    def test_secret_key_still_blocks_a_value_also_used_in_app_name(self):
        (self.root / ".env").write_text("APP_NAME=fixture-secret-value\nAPI_TOKEN=fixture-secret-value\n", encoding="utf-8")
        self.doc.write_text(VALID_DOC + "fixture-secret-value\n", encoding="utf-8")
        (self.root / "manifest.txt").write_text("fixture-secret-value", encoding="utf-8")
        review = self.write_review("APP_NAME")
        result = self.run_validator("--agent", "codex", "--env-reviews", str(review))
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("API_TOKEN", result.stdout)
        self.assertNotIn("fixture-secret-value", result.stdout)

    def test_credential_patterns_cannot_be_exempted(self):
        token = "ghp_" + "x" * 36
        (self.root / ".env").write_text(f"APP_NAME={token}\n", encoding="utf-8")
        self.doc.write_text(VALID_DOC + token + "\n", encoding="utf-8")
        (self.root / "manifest.txt").write_text(token, encoding="utf-8")
        review = self.write_review("APP_NAME")
        result = self.run_validator("--agent", "codex", "--env-reviews", str(review))
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("possible GitHub token", result.stdout)
        self.assertNotIn(token, result.stdout)

    def test_sensitive_env_keys_cannot_be_exempted(self):
        (self.root / ".env").write_text("API_TOKEN=fixture-secret-value\n", encoding="utf-8")
        self.doc.write_text(VALID_DOC + "fixture-secret-value\n", encoding="utf-8")
        (self.root / "manifest.txt").write_text("fixture-secret-value", encoding="utf-8")
        review = self.write_review("API_TOKEN")
        result = self.run_validator("--agent", "codex", "--env-reviews", str(review))
        self.assertEqual(result.returncode, 1)
        self.assertIn("cannot be exempted", result.stdout)
        self.assertNotIn("fixture-secret-value", result.stdout)

    def test_review_is_limited_to_one_occurrence(self):
        (self.root / ".env").write_text("APP_NAME=ExampleService\n", encoding="utf-8")
        self.doc.write_text(VALID_DOC + "ExampleService\nExampleService\n", encoding="utf-8")
        (self.root / "manifest.txt").write_text("ExampleService", encoding="utf-8")
        review = self.write_review("APP_NAME")
        result = self.run_validator("--agent", "codex", "--env-reviews", str(review))
        self.assertEqual(result.returncode, 1)
        self.assertIn("reviewed env match APP_NAME", result.stdout)
        self.assertIn("possible secret leak", result.stdout)

    def test_changed_document_invalidates_review(self):
        (self.root / ".env").write_text("APP_NAME=ExampleService\n", encoding="utf-8")
        self.doc.write_text(VALID_DOC + "ExampleService\n", encoding="utf-8")
        (self.root / "manifest.txt").write_text("ExampleService", encoding="utf-8")
        review = self.write_review("APP_NAME")
        self.doc.write_text(VALID_DOC + "ExampleService changed\n", encoding="utf-8")
        result = self.run_validator("--agent", "codex", "--env-reviews", str(review))
        self.assertEqual(result.returncode, 1)
        self.assertIn("stale env reviews", result.stderr)

    def test_changed_env_key_value_or_file_invalidates_review(self):
        for filename, key, value in ((".env", "OTHER_NAME", "ExampleService"),
                                     (".env", "APP_NAME", "Service"),
                                     (".env.local", "APP_NAME", "ExampleService")):
            with self.subTest(filename=filename, key=key, value=value):
                for env_file in self.root.glob(".env*"):
                    env_file.unlink()
                (self.root / ".env").write_text("APP_NAME=ExampleService\n", encoding="utf-8")
                self.doc.write_text(VALID_DOC + "ExampleService\n", encoding="utf-8")
                (self.root / "manifest.txt").write_text("ExampleService", encoding="utf-8")
                review = self.write_review("APP_NAME")
                (self.root / ".env").unlink()
                (self.root / filename).write_text(f"{key}={value}\n", encoding="utf-8")
                result = self.run_validator("--agent", "codex", "--env-reviews", str(review))
                self.assertEqual(result.returncode, 1)
                self.assertIn("stale env reviews", result.stderr)

    def test_diagnostics_do_not_echo_env_values_from_document_paths(self):
        (self.root / ".env").write_text("CUSTOM_SETTING=fixture-private-value\n", encoding="utf-8")
        self.doc.write_text(VALID_DOC + "`missing/fixture-private-value`\n", encoding="utf-8")
        result = self.run_validator("--agent", "codex")
        self.assertEqual(result.returncode, 1)
        self.assertNotIn("fixture-private-value", result.stdout + result.stderr)

    def test_evidence_outside_repository_is_rejected(self):
        with tempfile.TemporaryDirectory() as outside:
            source = Path(outside) / "manifest.txt"
            source.write_text("ExampleService", encoding="utf-8")
            (self.root / ".env").write_text("APP_NAME=ExampleService\n", encoding="utf-8")
            self.doc.write_text(VALID_DOC + "ExampleService\n", encoding="utf-8")
            review = self.write_review("APP_NAME", str(source))
            result = self.run_validator("--agent", "codex", "--env-reviews", str(review))
            self.assertEqual(result.returncode, 1)
            self.assertIn("invalid env review file", result.stderr)

    def test_independent_evidence_and_nonempty_reason_are_required(self):
        (self.root / ".env").write_text("APP_NAME=ExampleService\n", encoding="utf-8")
        self.doc.write_text(VALID_DOC + "ExampleService\n", encoding="utf-8")
        (self.root / "manifest.txt").write_text("DifferentName", encoding="utf-8")
        for source, reason in (("manifest.txt", "Checked"), (".env", "Checked"),
                               ("missing.txt", "Checked"), ("AGENTS.md", "Checked"),
                               ("manifest.txt", "")):
            with self.subTest(source=source, reason=reason):
                review = self.write_review("APP_NAME", source, reason)
                result = self.run_validator("--agent", "codex", "--env-reviews", str(review))
                self.assertEqual(result.returncode, 1)
                self.assertNotIn("ExampleService", result.stdout + result.stderr)

    def test_duplicate_keys_in_env_files_are_all_checked(self):
        (self.root / ".env").write_text("CUSTOM_SETTING=first-private-value\n", encoding="utf-8")
        (self.root / ".env.local").write_text("CUSTOM_SETTING=second-private-value\n", encoding="utf-8")
        self.doc.write_text(VALID_DOC + "first-private-value\nsecond-private-value\n", encoding="utf-8")
        result = self.run_validator("--agent", "codex")
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout.count("possible secret leak"), 2)
        self.assertNotIn("first-private-value", result.stdout)
        self.assertNotIn("second-private-value", result.stdout)

    def test_malformed_review_files_are_rejected_without_echoing_contents(self):
        review = self.root / "reviews.json"
        for content in ("not-json-sensitive", "[]", '{"bad-id": {}}'):
            with self.subTest(content=content):
                review.write_text(content, encoding="utf-8")
                result = self.run_validator("--env-reviews", str(review))
                self.assertEqual(result.returncode, 1)
                self.assertIn("invalid env review file", result.stderr)
                self.assertNotIn(content, result.stdout + result.stderr)

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
