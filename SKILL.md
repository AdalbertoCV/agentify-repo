---
name: agentify-repo
description: Use when asked to prepare, onboard, or "agentify" a repository for AI coding agents; to create, update, regenerate, or audit AGENTS.md, CLAUDE.md, GEMINI.md, .cursorrules, or copilot-instructions; or when agent instruction files are missing, stale, bloated, or contradict each other or the code.
---

# Agentify Repo

## Overview

An AGENTS.md is worth only what an agent **cannot cheaply discover by itself**: commands that verifiably work, traps, boundaries, and decisions that are invisible in the code. Folder listings, dependency lists and lint rules are noise: the agent can read those itself.

**Core rule:** every statement in the file has a known source. Commands carry a status from verification. Any other claim is tagged in its text: *verified*, *from config*, *from code*, *from docs*, *from tests*, or *from user*. `check_agents_md.py` warns about untagged bullets. Leave out anything that has none of these sources.

Scripts live in `<skill-dir>/scripts/`. Run them with `python`, or with `py` on Windows when `python` is a Store alias. All of them are stdlib-only and accept `--help`.

## Procedure

1. **Collect facts.** Run `collect_facts.py <repo> --audit > facts.json`. It reads the repo but never writes to it. Read the JSON first.
   - The fields to act on are `risk_signals`, `sql_files`, `schema_management`, `external_hosts_in_config`, `containers.conflicts_on_this_machine`, `script_warnings`, `env_vars`, `toolchain_on_this_machine`, `empty_or_stub_files`, and `audit`.
   - `suggested_commands_UNVERIFIED` holds candidates, not facts.
2. **Read the sources of truth.** Read them in this order and stop once you have enough:
   1. existing agent docs
   2. CI (CI commands are the most reliable answer to "how do I verify a change")
   3. README and CONTRIBUTING
   4. lint and test configs
   5. app config (`app_configs`)
   6. 2–3 representative modules plus one test
3. **Verify the commands.** **REQUIRED:** follow `references/verification.md`. It covers the status vocabulary, missing toolchains, services, risky scripts, and hung processes.
4. **Ask** the user at most 3 questions about what can't be inferred: off-limits areas, decisions an agent would likely undo, and review expectations. With no user available, leave out those parts. Don't invent them.
5. **Write the doc.** Follow `references/output-contract.md` for sections, tagging, monorepos and examples. Draft the block in a scratch file, then run:
   ```bash
   write_block.py <repo>/AGENTS.md <draft.md>      # inserts/replaces only the marked block
   write_block.py <repo>/CLAUDE.md --import AGENTS.md
   ```
   Don't hand-edit the markers. `write_block.py` refuses malformed ones and never alters human text.
6. **Validate.** Run `check_agents_md.py <repo>`. Fix every ERROR. Fix or consciously accept each warning: a path the text says is missing is fine, filler is not.
7. **Final report** to the user, in chat. Include:
   - the files you changed
   - the command status table
   - human lines marked stale
   - contradictions between agent docs
   - stale human docs you noticed (README numbers, missing referenced files). Report them; don't edit them.
   - anything you skipped, and why
   - repo files the verification touched, and whether you reverted them

## Hard rules

| Never | Instead |
|---|---|
| Document a command you didn't run as if it works | Give it a status: `not verified (<reason>)` |
| Run SQL, migrations or `risk_signals` scripts against anything but a throwaway local container | Read them, then mark them `not verified (touches <db/network>)` |
| Install global tools, or use `npx`/`uvx`/`corepack`/`docker run` to fetch toolchains, without the user's OK | Ask first, and say it will also download dependencies from public registries. If there is no user, record `not verified (<tool> not installed)` |
| Start the app with config defaults that point at real external hosts (`external_hosts_in_config`) | Override them to `localhost` or a dummy value for the run |
| Reuse, stop, or collide with containers, volumes, or ports that already exist | Use resources prefixed `agentify-<id>` and free ports; check `containers.conflicts_on_this_machine` |
| Copy env values, even from a tracked `.env` | Use variable names only |
| Delete or rewrite human-written lines | Mark them with `<!-- agentify: stale — <reason> -->` |
| Fix the repo while documenting it | Record the problem under Gotchas |
| Leave files that verification modified (lockfiles, builds) | `git checkout -- <file>`, delete the build output, and report it |

## Audit mode

Use audit mode only when the user asks to **check, audit, or review** docs rather than to create or update them. Report:

- `audit.missing_paths`, after confirming each one (the check is heuristic)
- commands that now fail
- CI commands that are absent from the doc
- `empty_or_stub_files`
- the output of `check_agents_md.py`

Stop after the report. Edit only when the user says so.
