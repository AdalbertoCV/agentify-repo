#!/usr/bin/env python3
"""Validate a generated AGENTS.md against the agentify output contract.

Usage:
    python check_agents_md.py REPO_ROOT [DOC ...]   # default DOC: every AGENTS.md under REPO_ROOT

Exit 0 = no errors (warnings may remain), 1 = errors. Secret values are never printed, only key names.
"""

import argparse
import re
import sys
from pathlib import Path

START, END = "<!-- agentify:start -->", "<!-- agentify:end -->"
MAX_LINES = 150
SECTION_ORDER = ["project", "commands", "layout", "conventions", "boundaries",
                 "gotchas & known issues", "decisions", "done means"]
STATUS_RE = re.compile(r"(✅ verified|❌ fails|not verified|^—$|^-$|^n/?a$)", re.I)
SOURCE_TAGS = ("from config", "from code", "from docs", "from tests", "from user", "verified")  # keep in sync with SKILL.md
FILLER = ["clean code", "best practices", "write good", "be careful", "make sure to test",
          "follow the existing", "high quality", "well-documented", "as needed"]
SECRET_PATTERNS = {
    "AWS key": r"AKIA[0-9A-Z]{16}",
    "private key": r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
    "GitHub token": r"gh[pousr]_[A-Za-z0-9]{30,}",
    "OpenAI/Anthropic key": r"sk-(?:ant-)?[A-Za-z0-9_-]{20,}",
    "Slack token": r"xox[abpr]-[A-Za-z0-9-]{10,}",
    "inline password": r"(?i)(password|passwd|pwd|secret|token)\s*[=:]\s*['\"]?[^\s'\"`<>{}$]{6,}",
    "credentials in URL": r"[a-z]+://[^\s/:@]+:[^\s/@]{3,}@",
}
BUILD_OUTPUT = {"target", "build", "dist", "out", ".next", "coverage", "node_modules", "bin", "obj"}
IGNORED = {".git", "node_modules", ".venv", "venv", "target", "dist", "build"}


class Report:
    def __init__(self, doc):
        self.doc, self.errors, self.warnings = doc, [], []

    def err(self, msg):
        self.errors.append(msg)

    def warn(self, msg):
        self.warnings.append(msg)


_PATHS = {}


def repo_paths(root: Path) -> list:
    if root not in _PATHS:
        out = []
        for p in root.rglob("*"):
            parts = p.relative_to(root).parts
            if not set(parts) & IGNORED:
                out.append("/" + "/".join(parts))
        _PATHS[root] = out
    return _PATHS[root]


def env_secret_values(root: Path) -> dict:
    """Values from real env files, used only to detect leaks. Never printed."""
    values = {}
    for f in root.glob(".env*"):
        if f.is_file() and not re.search(r"(example|sample|template|dist)$", f.name):
            for line in f.read_text(encoding="utf-8", errors="replace").splitlines():
                m = re.match(r"^\s*(?:export\s+)?([A-Za-z_]\w*)\s*=\s*['\"]?(.*?)['\"]?\s*$", line)
                if m and len(m.group(2)) >= 6 and m.group(2).lower() not in {"true", "false", "localhost"}:
                    values[m.group(1)] = m.group(2)
    return values


def check(root: Path, doc: Path) -> Report:
    r = Report(doc.relative_to(root).as_posix() if doc.is_relative_to(root) else str(doc))
    text = doc.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()

    # Markers
    if text.count(START) != 1 or text.count(END) != 1 or text.find(START) > text.find(END):
        r.err(f"markers: need exactly one {START} before one {END}")
        block = text
    else:
        block = text.split(START, 1)[1].split(END, 1)[0]

    # Budget
    if len(lines) > MAX_LINES:
        r.err(f"length: {len(lines)} lines > {MAX_LINES}; cut what is visible in the code first")

    # Section order
    heads = [h.strip().lower() for h in re.findall(r"^##\s+(.+)$", block, re.M)]
    known = [h for h in heads if h in SECTION_ORDER]
    for h in heads:
        if h not in SECTION_ORDER:
            r.warn(f"section '## {h}' is not in the output contract")
    if known != sorted(known, key=SECTION_ORDER.index):
        r.err(f"section order {known} does not follow the contract order")
    if "commands" not in known:
        r.err("missing '## Commands' section")

    # Commands table: every row needs a status
    cmd_section = re.search(r"^##\s+Commands\s*$(.*?)(?=^##\s|\Z)", block, re.M | re.S | re.I)
    if cmd_section:
        rows = [l for l in cmd_section.group(1).splitlines() if l.strip().startswith("|")]
        body = [l for l in rows[2:]] if len(rows) >= 2 else []
        if not body:
            r.err("Commands section has no table rows")
        for row in body:
            cells = [c.strip() for c in row.strip().strip("|").split("|")]
            status = cells[-1] if cells else ""
            if not STATUS_RE.search(status):
                r.err(f"command row without a valid status: {row.strip()[:90]}")

    # Paths referenced must exist (relative to the doc's dir, repo root, or as a suffix of a repo path)
    for ref in sorted(set(re.findall(r"`([\w.-]+(?:/[\w.@-]+)+/?)`", block))):
        if ref.startswith(("http", "~", "/")) or "*" in ref or "<" in ref:
            continue
        if ref.split("/")[0] in BUILD_OUTPUT or re.match(r"^[A-Z][a-z]+/[A-Z]", ref):  # build output, tz names
            continue
        suffix = "/" + ref.rstrip("/")
        if (not (doc.parent / ref).exists() and not (root / ref).exists()
                and not any(p.endswith(suffix) for p in repo_paths(root))):
            r.warn(f"path `{ref}` does not exist (fine only if the text says it is missing)")

    # Secrets
    for key, value in env_secret_values(root).items():
        if value in text:
            r.err(f"value of env var {key} appears in the doc (secret leak) — remove it")
    for label, pattern in SECRET_PATTERNS.items():
        for m in re.finditer(pattern, text):
            snippet = m.group(0)
            if label == "inline password" and re.search(r"\$\{|<|\*{3}|example|changeme|redacted", snippet, re.I):
                continue
            r.err(f"possible {label} in doc (line {text[:m.start()].count(chr(10)) + 1})")

    # Filler and untagged claims
    low = block.lower()
    for phrase in FILLER:
        if phrase in low:
            r.warn(f"generic filler '{phrase}': delete it unless it states a concrete, repo-specific rule")
    for section in ["conventions", "decisions", "boundaries", "gotchas & known issues"]:
        m = re.search(rf"^##\s+{section}\s*$(.*?)(?=^##\s|\Z)", block, re.M | re.S | re.I)
        if m:
            for bullet in re.findall(r"^\s*[-*]\s+(.+)$", m.group(1), re.M):
                if not any(t in bullet.lower() for t in SOURCE_TAGS) and not re.search(r"`[^`]+\.(md|java|py|ts|js|tsx|jsx|go|rs|sql|ya?ml|properties)`", bullet):
                    r.warn(f"{section}: bullet has no source tag or file reference: {bullet[:70]}")
    return r


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("root")
    parser.add_argument("docs", nargs="*")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    docs = [Path(d).resolve() for d in args.docs] or sorted(
        p for p in root.rglob("AGENTS.md") if not (set(p.relative_to(root).parts) & IGNORED))
    if not docs:
        print("error: no AGENTS.md found", file=sys.stderr)
        return 1
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        pass

    failed = False
    for doc in docs:
        rep = check(root, doc)
        claude = doc.parent / "CLAUDE.md"
        if not claude.exists():
            rep.warn("no sibling CLAUDE.md (create one containing @AGENTS.md)")
        elif "@AGENTS.md" not in claude.read_text(encoding="utf-8", errors="replace"):
            rep.warn("sibling CLAUDE.md does not import @AGENTS.md; check for contradictions")
        status = "FAIL" if rep.errors else "PASS"
        failed |= bool(rep.errors)
        print(f"[{status}] {rep.doc}: {len(rep.errors)} error(s), {len(rep.warnings)} warning(s)")
        for e in rep.errors:
            print(f"  ERROR  {e}")
        for w in rep.warnings:
            print(f"  warn   {w}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
