"""Regression checks for brain mode: collector candidates, scaffolder, and validator."""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
COLLECT, SCAFFOLD, CHECK = (SCRIPTS / n for n in ("collect_facts.py", "scaffold_brain.py", "check_agents_md.py"))

PLAN = {
    "domains": [
        {"slug": "billing", "title": "Billing", "paths": ["src/billing/"],
         "read_when": "touching src/billing/ or invoice totals"},
        {"slug": "auth", "title": "Auth", "paths": ["src/auth/"],
         "read_when": "touching login, sessions or permissions"},
    ],
}


def run(script, *args):
    return subprocess.run([sys.executable, str(script), *map(str, args)],
                          capture_output=True, text=True, encoding="utf-8", timeout=30)


class BrainTestCase(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        for path in ("src/billing/invoice.py", "src/auth/login.py", "src/auth/session.py", "tests/test_x.py"):
            (self.root / path).parent.mkdir(parents=True, exist_ok=True)
            (self.root / path).write_text("x = 1\n", encoding="utf-8")
        self.brain = self.root / "docs" / "agents"

    def scaffold(self, plan=PLAN, *extra):
        plan_file = self.root.parent / f"{self.root.name}-plan.json"
        plan_file.write_text(json.dumps(plan), encoding="utf-8")
        self.addCleanup(plan_file.unlink, missing_ok=True)
        return run(SCAFFOLD, self.root, plan_file, *extra)

    def write_agents_md(self, context_map=True):
        result = self.scaffold()
        summary = json.loads(result.stdout)
        cmap = f"## Context map\n{summary['context_map']}\n\n" if context_map else ""
        (self.root / "AGENTS.md").write_text(
            "<!-- agentify:start -->\n## Commands\n| Task | Command | Status |\n|---|---|---|\n"
            "| Test | `python -m unittest` | not verified (brain mode: mini scan) |\n\n"
            f"{cmap}<!-- agentify:end -->\n", encoding="utf-8")


class CollectorTests(BrainTestCase):
    def test_brain_flag_lists_domain_candidates(self):
        result = run(COLLECT, self.root, "--brain")
        self.assertEqual(result.returncode, 0, result.stderr)
        brain = json.loads(result.stdout)["brain_candidates"]
        self.assertEqual(brain["brain_dir"], "docs/agents")
        self.assertFalse(brain["brain_dir_exists"])
        domains = {d["path"]: d["source_files"] for d in brain["domains"]}
        self.assertEqual(domains, {"src/auth": 2, "src/billing": 1})

    def test_brain_candidates_absent_without_flag(self):
        result = run(COLLECT, self.root)
        self.assertNotIn("brain_candidates", json.loads(result.stdout))


class ScaffoldTests(BrainTestCase):
    def test_creates_skeleton_with_frontmatter_and_context_map(self):
        result = self.scaffold()
        self.assertEqual(result.returncode, 0, result.stderr)
        summary = json.loads(result.stdout)
        expected = {"INDEX.md", "architecture.md", "glossary.md", "MAINTENANCE.md",
                    "decisions/README.md", "runbooks/README.md", "domains/billing.md", "domains/auth.md"}
        self.assertEqual({Path(p).relative_to("docs/agents").as_posix() for p in summary["created"]}, expected)
        billing = (self.brain / "domains" / "billing.md").read_text(encoding="utf-8")
        self.assertTrue(billing.startswith("---\nread_when: touching src/billing/ or invoice totals\n"))
        self.assertIn("paths: [src/billing/]", billing)
        self.assertIn("<!-- agentify:pending", billing)
        self.assertIn("domains/billing.md", (self.brain / "INDEX.md").read_text(encoding="utf-8"))
        self.assertIn("docs/agents/domains/auth.md", summary["context_map"])

    def test_never_overwrites_existing_files(self):
        self.scaffold()
        human = self.brain / "domains" / "billing.md"
        human.write_text("hand written\n", encoding="utf-8")
        summary = json.loads(self.scaffold().stdout)
        self.assertEqual(human.read_text(encoding="utf-8"), "hand written\n")
        self.assertIn("docs/agents/domains/billing.md", summary["skipped"])
        self.assertEqual(summary["created"], [])

    def test_invalid_plan_writes_nothing(self):
        bad_plans = (
            {"domains": [{"slug": "x", "title": "X", "paths": ["../outside/"], "read_when": "always"}]},
            {"domains": [{"slug": "Bad Slug", "title": "X", "paths": ["src/"], "read_when": "always"}]},
            {"domains": [{"slug": "x", "title": "X", "paths": ["src/missing/"], "read_when": "always"}]},
            {"domains": [{"slug": "x", "title": "X", "paths": ["src/"], "read_when": " "}]},
            {"domains": [{"slug": "x", "title": "X", "paths": ["src/"], "read_when": "a"}] * 2},
            {"domains": [{"slug": "x", "title": "X", "paths": ["src/"], "read_when": "invoices | refunds"}]},
            {"domains": [{"slug": "x", "title": "X", "paths": ["."], "read_when": "always"}]},
            {"domains": [{"slug": "x", "title": "X", "paths": ["src/a,b"], "read_when": "always"}]},
        )
        for plan in bad_plans:
            with self.subTest(plan=plan):
                result = self.scaffold(plan)
                self.assertEqual(result.returncode, 1)
                self.assertFalse(self.brain.exists())

    def test_help_documents_plan_schema(self):
        self.assertIn('"read_when"', run(SCAFFOLD, "--help").stdout)

    def test_dry_run_writes_nothing(self):
        result = self.scaffold(PLAN, "--dry-run")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(json.loads(result.stdout)["created"])
        self.assertFalse(self.brain.exists())


class ValidatorTests(BrainTestCase):
    def check(self):
        return run(CHECK, self.root, "--agent", "codex", "--brain")

    def test_fresh_scaffold_passes_with_pending_warnings(self):
        self.write_agents_md()
        result = self.check()
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("pending item(s)", result.stdout)

    def test_without_brain_flag_brain_is_not_checked(self):
        self.write_agents_md()
        (self.brain / "orphan.md").write_text("no frontmatter\n", encoding="utf-8")
        result = run(CHECK, self.root, "--agent", "codex")
        self.assertEqual(result.returncode, 0, result.stdout)

    def test_errors(self):
        cases = {
            "missing context map": (lambda: self.write_agents_md(context_map=False), "Context map"),
            "missing index": (lambda: (self.brain / "INDEX.md").unlink(), "INDEX.md"),
            "broken link": (lambda: self._append("INDEX.md", "\n[gone](domains/gone.md)\n"), "broken link"),
            "orphan": (lambda: self._write("domains/orphan.md", "---\nread_when: never\npaths: []\n---\n# O\n"), "not reachable"),
            "no frontmatter": (lambda: self._write("glossary.md", "# Glossary\n"), "frontmatter"),
            "over budget": (lambda: self._append("glossary.md", "\n" * 90), "lines"),
        }
        for name, (mutate, needle) in cases.items():
            with self.subTest(name):
                self.write_agents_md()
                mutate()
                result = self.check()
                self.assertEqual(result.returncode, 1, result.stdout)
                self.assertIn(needle, result.stdout)
                for p in sorted(self.brain.rglob("*"), reverse=True):
                    p.unlink() if p.is_file() else p.rmdir()

    def test_bom_before_frontmatter_is_accepted(self):
        self.write_agents_md()
        glossary = self.brain / "glossary.md"
        glossary.write_text("﻿" + glossary.read_text(encoding="utf-8"), encoding="utf-8")
        result = self.check()
        self.assertEqual(result.returncode, 0, result.stdout)

    def test_stale_frontmatter_path_warns(self):
        self.write_agents_md()
        (self.root / "src" / "billing" / "invoice.py").unlink()
        (self.root / "src" / "billing").rmdir()
        result = self.check()
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("stale", result.stdout)

    def test_untagged_bullet_in_domain_file_warns(self):
        self.write_agents_md()
        self._append("domains/auth.md", "\n- Sessions expire after an hour.\n")
        self.assertIn("no source tag", self.check().stdout)

    def test_secret_in_brain_file_is_an_error(self):
        self.write_agents_md()
        self._append("glossary.md", "\n- token: ghp_" + "a" * 36 + " (from config)\n")
        result = self.check()
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("GitHub token", result.stdout)

    def _write(self, rel, text):
        (self.brain / rel).write_text(text, encoding="utf-8")

    def _append(self, rel, text):
        path = self.brain / rel
        path.write_text(path.read_text(encoding="utf-8") + text, encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
