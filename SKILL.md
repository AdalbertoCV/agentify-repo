---
name: agentify-repo
description: Use when asked to prepare, onboard, or "agentify" a repository for AI coding agents; to create, update, regenerate, or audit AGENTS.md, CLAUDE.md, GEMINI.md, .cursorrules, or copilot-instructions; when agent instruction files are missing, stale, bloated, or contradict each other or the code; or when asked (or passed `--brain`) to set up a context brain, a docs/agents documentation structure, or routers that save agent context.
---

# Agentify Repo

## Overview

An AGENTS.md is worth only what an agent **cannot cheaply discover by itself**: commands that verifiably work, traps, boundaries, and decisions that are invisible in the code. Folder listings, dependency lists and lint rules are noise: the agent can read those itself.

**Core rule:** every statement in the file has a known source. Commands carry a status from verification. Any other claim is tagged in its text: *verified*, *from config*, *from code*, *from docs*, *from tests*, or *from user*. `check_agents_md.py` warns about untagged bullets. Leave out anything that has none of these sources.

Scripts live in `<skill-dir>/scripts/`. Run them with `python`, or with `py` on Windows when `python` is a Store alias. All of them are stdlib-only and accept `--help`.

In Codex, invoke this skill with `$agentify-repo` or select it with `/skills`. Use the Codex workflow below when running in Codex or when the user requests Codex-only output; otherwise preserve the existing Claude-compatible workflow. If the target is unclear, ask which agent the docs should support.

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
   Treat collector stack labels as an inventory, not the final project description. For every language, distinguish the language/runtime, framework, and tools; attach each version to its component and source. Manifests declare requirements, lockfiles record resolved dependencies, and the available runtime or package metadata can establish installed versions. Do not infer one category from another or use env values as evidence for stack identification.
3. **Verify the commands.** **REQUIRED:** follow `references/verification.md`. It covers the status vocabulary, missing toolchains, services, risky scripts, and hung processes.
4. **Ask** the user at most 3 questions about what can't be inferred: off-limits areas, decisions an agent would likely undo, and review expectations. With no user available, leave out those parts. Don't invent them.
5. **Write the doc.** Follow `references/output-contract.md` for sections, tagging, monorepos and examples. Draft the block in a scratch file, then run:
   ```bash
   write_block.py <repo>/AGENTS.md <draft.md>      # inserts/replaces only the marked block
   ```
   In Codex, create only `AGENTS.md`. For Claude Code or explicitly requested Claude compatibility, also run `write_block.py <repo>/CLAUDE.md --import AGENTS.md`.
   Don't hand-edit the markers. `write_block.py` refuses malformed ones and never alters human text.
6. **Validate.** In Codex, run `check_agents_md.py <repo> --agent codex`. For Claude compatibility, run `check_agents_md.py <repo>` (the default preserves CLAUDE.md checks). Fix every ERROR. Fix or consciously accept each warning: a path the text says is missing is fine, filler is not.
   Never rename a framework, change a version, or remove a sourced fact just to pass validation. The validator reads env values internally for comparison; a match is a leak candidate, not evidence that a sourced fact is incorrect. No env key is automatically safe. For a confirmed non-sensitive false positive, record its printed review ID in a scratch JSON file with an independent repository `source` and a meaningful `reason`, then rerun with `--env-reviews <file>` (see README). Do not use env files or generated agent docs as evidence. Reviews apply only to the exact document location, line content, env file, key, and value; changes require renewed review. Credential patterns and sensitive key names cannot be exempted. Report accepted reviews without printing env values, and preserve the review file for reproducibility. For an unresolved error, report the block instead of distorting the fact. Before delivery, check that every version names its component and source.
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

## Brain mode (`--brain`)

Use brain mode when the user passes `--brain`, or asks for a context brain, a documentation structure, or routers that save agent context. This is a **mini scan**: it does not verify commands unless the user also asks for the full workflow. **REQUIRED:** follow `references/brain.md`.

1. Run `collect_facts.py <repo> --audit --brain > facts.json`. Read `brain_candidates`, `ci`, `docs` and `adr_dirs`.
2. Read CI, the README, existing agent docs and ADRs, and one entry module per candidate domain. Stop there.
3. **Propose** the structure in chat, using the format in `references/brain.md`: files, the paths each one covers, sourced seeds, pending questions, and existing files that will be skipped. Wait for approval or edits. Approval the user gave in advance for this run counts. With no user and no advance approval, stop after the proposal and write nothing.
4. Write the approved plan to a scratch JSON and run `scaffold_brain.py <repo> <plan.json>`. It creates only missing files and prints a `context_map` table. Any file it skips is human-owned: report it and do not edit it. The one exception is an existing `INDEX.md`: list in the proposal the rows you will append for new files, and append only those rows after approval.
5. Seed the created files with sourced facts only. Turn generic pending questions into specific ones.
6. Write the `AGENTS.md` block with `write_block.py`. It needs `## Commands` (status `not verified (brain mode: mini scan)` for anything you did not run) and `## Context map` (the printed table). Other contract sections hold repo-wide facts only. A fact about one domain lives in that domain's file and nowhere else. For Claude compatibility, also create `CLAUDE.md` with `--import AGENTS.md`.
7. Run `check_agents_md.py <repo> --brain` (add `--agent codex` for Codex). Fix every ERROR. Pending-item warnings are expected.
8. Final report. Include:
   - the files created and skipped
   - the Context map
   - the command status table
   - contradictions with existing agent docs
   - the pending questions, grouped by file
   - the next step: run the full workflow to verify commands

## Audit mode

Use audit mode only when the user asks to **check, audit, or review** docs rather than to create or update them. Report:

- `audit.missing_paths`, after confirming each one (the check is heuristic)
- commands that now fail
- CI commands that are absent from the doc
- `empty_or_stub_files`
- the output of `check_agents_md.py` (with `--agent codex` for Codex)

Stop after the report. Edit only when the user says so.
