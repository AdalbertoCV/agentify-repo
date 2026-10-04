#!/usr/bin/env python3
"""Insert or replace the agentify block in an agent doc without touching human-written content.

Usage:
    python write_block.py TARGET BLOCK_FILE        # BLOCK_FILE holds the generated markdown (no markers)
    python write_block.py TARGET --import AGENTS.md  # create TARGET containing only "@AGENTS.md" if missing

Behavior:
    - TARGET missing             -> created with the block (wrapped in markers)
    - TARGET has markers         -> only the text between them is replaced
    - TARGET has no markers      -> block appended after the existing human content
    - malformed markers          -> refuses (exit 1); nothing is written
"""

import argparse
import re
import sys
from pathlib import Path

START, END = "<!-- agentify:start -->", "<!-- agentify:end -->"


def upsert(existing: str, block: str) -> str:
    block = block.strip("\n")
    wrapped = f"{START}\n{block}\n{END}"
    starts, ends = existing.count(START), existing.count(END)
    if starts == 0 and ends == 0:
        human = existing.rstrip()
        return f"{human}\n\n{wrapped}\n" if human else f"{wrapped}\n"
    if starts != 1 or ends != 1 or existing.index(START) > existing.index(END):
        raise ValueError(f"malformed markers: {starts} start / {ends} end; fix by hand first")
    pattern = re.compile(re.escape(START) + r".*?" + re.escape(END), re.S)
    return pattern.sub(lambda _: wrapped, existing, count=1)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("target")
    parser.add_argument("block_file", nargs="?")
    parser.add_argument("--import", dest="import_of", help="create TARGET as '@<file>' if it does not exist")
    args = parser.parse_args()
    target = Path(args.target)

    if args.import_of:
        if target.exists():
            text = target.read_text(encoding="utf-8")
            has = f"@{args.import_of}" in text
            print(f"{target}: exists, {'already imports' if has else 'does NOT import'} {args.import_of}; left unchanged")
            return 0
        target.write_text(f"@{args.import_of}\n", encoding="utf-8", newline="\n")
        print(f"{target}: created with @{args.import_of}")
        return 0

    if not args.block_file:
        parser.error("BLOCK_FILE is required unless --import is used")
    block = Path(args.block_file).read_text(encoding="utf-8")
    if START in block or END in block:
        print("error: BLOCK_FILE must not contain the markers; they are added for you", file=sys.stderr)
        return 1
    existing = target.read_text(encoding="utf-8") if target.exists() else ""
    try:
        new = upsert(existing, block)
    except ValueError as exc:
        print(f"error: {target}: {exc}", file=sys.stderr)
        return 1
    if new == existing:
        print(f"{target}: unchanged")
        return 0
    human_before = existing.split(START)[0].rstrip() if START in existing else existing.rstrip()
    assert new.startswith(human_before), "human content would be altered"  # invariant, never expected
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(new, encoding="utf-8", newline="\n")
    mode = "created" if not existing else ("block replaced" if START in existing else "block appended")
    print(f"{target}: {mode} ({new.count(chr(10))} lines)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
