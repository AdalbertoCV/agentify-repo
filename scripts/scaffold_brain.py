#!/usr/bin/env python3
"""Create the docs/agents brain skeleton from an approved plan, never overwriting existing files.

Usage:
    python scaffold_brain.py REPO_ROOT PLAN_JSON [--dry-run]

PLAN_JSON:
    {"domains": [{"slug": "billing", "title": "Billing", "paths": ["src/billing/"],
                  "read_when": "touching src/billing/ or invoice totals"}]}

Behavior:
    - the whole plan is validated first; any invalid entry -> exit 1, nothing is written
    - missing files are created with frontmatter and <!-- agentify:pending --> questions
    - existing files are skipped and listed; they are never modified
    - prints JSON: created, skipped, and a Context map table for the AGENTS.md block
"""

import argparse
import json
import re
import sys
from pathlib import Path

BRAIN_DIR = "docs/agents"
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")

CORE = [
    ("architecture.md", "Architecture", "you need the flow across modules (entry points, request or data path)", [], """\
## Entry points
<!-- agentify:pending — Which files start the app, jobs or CLIs? -->

## Main flow
<!-- agentify:pending — How does a typical request or job travel through the modules? -->
"""),
    ("glossary.md", "Glossary", "a domain term in code, tickets or docs is unclear", [], """\
<!-- agentify:pending — Which domain terms would a new agent misread? One bullet each, with its source. -->
"""),
    ("decisions/README.md", "Decisions", "you are about to change an established pattern, or just made a decision worth keeping", [], """\
One file per decision: `decisions/NNNN-short-title.md` with Context, Decision, Consequences and a source.
If the repo already has an ADR folder, new decisions go there instead. Link them here; don't copy them.

<!-- agentify:pending — Which decisions would an agent likely undo by accident? -->
"""),
    ("runbooks/README.md", "Runbooks", "doing a repeated multi-step task (release, migration, new endpoint)", [], """\
One file per task: `runbooks/<task>.md` with numbered steps and the command status for each step.

<!-- agentify:pending — Which multi-step tasks are repeated often enough to write down? -->
"""),
]

MAINTENANCE = """\
Keep the brain small and true. It is read on demand, through the Context map in `AGENTS.md`.

- Changed code in a domain: update that domain file in the same change.
- Moved or deleted a path listed in a file's `paths`: fix the frontmatter.
- Made a decision an agent might undo: add `decisions/NNNN-title.md` and link it from `decisions/README.md`.
- Repeated a multi-step task twice: write `runbooks/<task>.md`.
- New file: give it `read_when` and `paths` frontmatter and add it to `INDEX.md` and, if code maps to it, the Context map.
- Every claim carries a source: verified, from config, from code, from docs, from tests, or from user.
- Answer an `agentify:pending` question by replacing it with a sourced line. Delete it if it no longer applies.
- Budget: 80 lines per file. Split by topic before you exceed it. Link instead of copying.
- Validate with `scripts/check_agents_md.py <repo> --brain` from the agentify-repo skill, when it is installed.
"""


def frontmatter(read_when: str, paths: list) -> str:
    return f"---\nread_when: {read_when}\npaths: [{', '.join(paths)}]\n---\n"


def domain_body(paths: list) -> str:
    where = ", ".join(f"`{p}`" for p in paths)
    return f"""\
Code: {where}

## Entry points
<!-- agentify:pending — Which file should an agent open first here, and why? -->

## Rules & invariants
<!-- agentify:pending — What must stay true that no linter or test enforces? -->

## Gotchas
<!-- agentify:pending — What breaks in non-obvious ways when changing this area? -->
"""


def validate(root: Path, plan) -> list:
    if not isinstance(plan, dict) or not isinstance(plan.get("domains", []), list):
        raise ValueError("plan must be an object with a 'domains' list")
    seen = set()
    for d in plan.get("domains", []):
        if not isinstance(d, dict) or set(d) != {"slug", "title", "paths", "read_when"}:
            raise ValueError("each domain needs exactly: slug, title, paths, read_when")
        slug, title, paths, read_when = d["slug"], d["title"], d["paths"], d["read_when"]
        if not isinstance(slug, str) or not SLUG_RE.match(slug) or slug in seen:
            raise ValueError(f"domain slug {slug!r} must be unique kebab-case")
        seen.add(slug)
        for field, value in (("title", title), ("read_when", read_when)):
            if not isinstance(value, str) or not value.strip() or "\n" in value or "|" in value:
                raise ValueError(f"domain {slug}: {field} must be one non-empty line without '|'")
        if not isinstance(paths, list) or not paths:
            raise ValueError(f"domain {slug}: paths must be a non-empty list")
        for p in paths:
            target = (root / str(p)).resolve()
            if (not isinstance(p, str) or not p.strip() or Path(p).is_absolute() or any(c in p for c in ",[]|`")
                    or not target.is_relative_to(root) or target == root or not target.exists()):
                raise ValueError(f"domain {slug}: path {p!r} must exist inside the repository and not contain , [ ] | or backticks")
    return plan.get("domains", [])


def render(domains: list) -> dict:
    files = {}
    rows = []
    for name, title, read_when, paths, body in CORE:
        files[name] = f"{frontmatter(read_when, paths)}# {title}\n\n{body}"
        rows.append((name, read_when))
    for d in domains:
        name = f"domains/{d['slug']}.md"
        files[name] = f"{frontmatter(d['read_when'].strip(), d['paths'])}# {d['title'].strip()}\n\n{domain_body(d['paths'])}"
        rows.append((name, d["read_when"].strip()))
    files["MAINTENANCE.md"] = (f"{frontmatter('adding, moving or answering anything in this folder', [])}"
                               f"# Maintaining the brain\n\n{MAINTENANCE}")
    rows.append(("MAINTENANCE.md", "adding, moving or answering anything in this folder"))
    table = "\n".join(f"| [{n}]({n}) | {w} |" for n, w in rows)
    files["INDEX.md"] = (f"{frontmatter('starting any task that needs more than AGENTS.md', [])}"
                         "# Agent brain index\n\n"
                         "Open only the file whose row matches your task. Do not load the whole folder.\n\n"
                         f"| File | Read when |\n|---|---|\n{table}\n")
    cmap = ["| If you touch | Read first |", "|---|---|"]
    for d in domains:
        cmap.append(f"| {', '.join(f'`{p}`' for p in d['paths'])} | [{BRAIN_DIR}/domains/{d['slug']}.md]"
                    f"({BRAIN_DIR}/domains/{d['slug']}.md) |")
    cmap.append(f"| Anything else | [{BRAIN_DIR}/INDEX.md]({BRAIN_DIR}/INDEX.md) |")
    return {"files": files, "context_map": "\n".join(cmap)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("root")
    parser.add_argument("plan")
    parser.add_argument("--dry-run", action="store_true", help="report what would be created; write nothing")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    try:
        domains = validate(root, json.loads(Path(args.plan).read_text(encoding="utf-8-sig")))
    except (OSError, ValueError, TypeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    out = render(domains)
    created, skipped = [], []
    for name, text in out["files"].items():
        target = root / BRAIN_DIR / name
        rel = f"{BRAIN_DIR}/{name}"
        if target.exists():
            skipped.append(rel)
            continue
        created.append(rel)
        if not args.dry_run:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-8", newline="\n")
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        pass
    json.dump({"dry_run": args.dry_run, "created": created, "skipped": skipped,
               "context_map": out["context_map"]}, sys.stdout, indent=2, ensure_ascii=False)
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
