<p align="center">
  <img src="assets/banner.svg" alt="agentify-repo — make any repository agent-ready" width="100%">
</p>

<p align="center">
  <a href="LICENSE"><img alt="License: MIT" src="https://img.shields.io/badge/license-MIT-34D399?style=flat-square"></a>
  <img alt="Status: beta" src="https://img.shields.io/badge/status-beta-FBBF24?style=flat-square">
  <img alt="Python 3.11+" src="https://img.shields.io/badge/python-3.11%2B-22D3EE?style=flat-square&logo=python&logoColor=white">
  <img alt="Dependencies: none" src="https://img.shields.io/badge/dependencies-stdlib%20only-A78BFA?style=flat-square">
  <img alt="Agent Skill" src="https://img.shields.io/badge/Agent%20Skill-AGENTS.md-818CF8?style=flat-square">
</p>

<p align="center">
  <b>An agent skill that turns any repository into one an AI coding agent can work in on day one.</b><br>
  It collects facts, <i>runs</i> the real commands, and writes a short, verified <code>AGENTS.md</code>. Nothing in it is guessed.
</p>

---

## Why

Most `AGENTS.md` / `CLAUDE.md` files are either missing or full of things an agent could have found by itself: folder trees, dependency lists, "follow best practices". The useful parts are usually missing:

- the **commands that actually work**, and the ones that silently hang (`npm test` in watch mode, anyone?)
- the **traps**: tests that need a seeded database, scripts that write outside the repo, config defaults pointing at real servers
- the **boundaries and decisions** you can't see in the code

`agentify-repo` documents only that. **Every line has a source**: either the agent ran it and it passed, or the text says where the claim comes from (`from config`, `from code`, `from docs`, `from tests`, `from user`).

## What you get

An `AGENTS.md` like this one, excerpted from a real run on a Spring Boot + PostgreSQL service:

```markdown
## Commands
| Task                     | Command                                      | Status                                   |
|--------------------------|----------------------------------------------|------------------------------------------|
| Load test schema         | `psql … -f db/schema.sql`                     | ✅ verified (in postgres:16-alpine)      |
| Build + all tests (= CI) | `mvn -B verify`                               | ✅ verified (1196 passed, 0 skipped)     |
| Single test              | `mvn -B test -Dtest=AuthControllerTest#…`     | ✅ verified                              |
| E2E sync script          | `bash scripts/verify-sync.sh`                 | ❌ fails (38 OK, 3 failed)               |

## Gotchas & known issues
- Every test TRUNCATEs non-catalog tables; a seeded table your tests need must be
  listed in `DatabaseCleaner.java` or it is wiped before each test (from code).
- `/actuator/health` returns 503 when the SMTP host is unreachable, even with the DB up (verified).
```

Codex reads `AGENTS.md` directly. For Claude compatibility, the skill also creates a `CLAUDE.md` that just imports it (`@AGENTS.md`). Codex-only runs create no Claude file.

## How it works

```mermaid
flowchart LR
    A[1 · Collect facts<br><sub>collect_facts.py</sub>] --> B[2 · Read sources<br><sub>CI → docs → config → code</sub>]
    B --> C[3 · Verify commands<br><sub>run them, record status</sub>]
    C --> D[4 · Ask ≤3 questions<br><sub>what can't be inferred</sub>]
    D --> E[5 · Write block<br><sub>write_block.py</sub>]
    E --> F[6 · Validate<br><sub>check_agents_md.py</sub>]
    F --> G[7 · Report]
```

| Piece | What it does |
|---|---|
| [`SKILL.md`](SKILL.md) | The workflow and hard rules the agent follows |
| [`references/verification.md`](references/verification.md) | How to verify: status vocabulary, missing toolchains, Docker, services, E2E scripts |
| [`references/output-contract.md`](references/output-contract.md) | Section order, useful-vs-noise examples, monorepos |
| [`scripts/collect_facts.py`](scripts/collect_facts.py) | Read-only scan, output as JSON: stacks, CI commands, containers, env var **names**, risky scripts, raw SQL, external hosts in config, installed toolchain, candidate commands |
| [`scripts/write_block.py`](scripts/write_block.py) | Inserts or replaces only the `<!-- agentify:start/end -->` block. Never touches human-written text |
| [`scripts/check_agents_md.py`](scripts/check_agents_md.py) | Validates the result: markers, section order, every command has a status, paths exist, **no leaked secrets**, no filler |

All scripts are standard-library Python with no dependencies.

## Safety by design

The skill is built to run on repos you care about:

- 🔒 **Never copies secret values.** Only env var names go in the doc, even when `.env` is committed. The validator fails the run if a value from a real `.env` shows up in the doc.
- 🧪 **Never runs SQL, migrations, or network-touching scripts against anything but a throwaway local container.**
- 🐳 **Asks before installing toolchains** or pulling Docker images. Every container, volume and network it creates is named `agentify-*` and removed afterwards. It checks for name and port collisions with what's already running.
- ✍️ **Never deletes human lines.** Lines that are now wrong get a `<!-- agentify: stale -->` note and are listed in the report.
- 🧹 **Leaves the tree clean.** It reverts lockfile drift and build output, and reports what verification touched.
- 🙅 **Doesn't fix your repo.** Broken things are documented, not silently patched.

## Install

Clone the repo into your agent's skills directory:

```bash
# Claude Code (personal skills)
git clone https://github.com/AdalbertoCV/agentify-repo ~/.claude/skills/agentify-repo

# Cross-agent location used by several tools
git clone https://github.com/AdalbertoCV/agentify-repo ~/.agents/skills/agentify-repo
```

Then, inside any repository, ask your agent:

> *"agentify this repo"* · *"create an AGENTS.md for this project"* · *"audit our AGENTS.md"*

You can also run the collector on its own to see what the agent sees:

```bash
python scripts/collect_facts.py path/to/repo --audit
```

### Codex (Windows / PowerShell)

Requires Git and Python 3.11+. Check `git --version` and `python --version` first.
No Python packages, application dependencies, MCP server, or API key are needed
to install this skill. `py` may be used only if it resolves to a working interpreter.

**Personal installation (all projects):**

```powershell
$skillPath = Join-Path $HOME '.agents/skills/agentify-repo'
if (Test-Path -LiteralPath $skillPath) { throw 'Skill already exists; inspect it before updating.' }
New-Item -ItemType Directory -Force -Path (Split-Path $skillPath) | Out-Null
git clone https://github.com/AdalbertoCV/agentify-repo $skillPath
```

**Project installation (this project only):** run the following from the target
project root instead of performing the personal installation:

```powershell
New-Item -ItemType Directory -Force -Path .agents/skills | Out-Null
git clone https://github.com/AdalbertoCV/agentify-repo .agents/skills/agentify-repo
```

Keep one installation per scope to avoid duplicate skill names. A project-local
clone contains its own Git repository; share its files deliberately if the team
needs them. Installing personally is simpler for individual use.

Codex discovers skills in these locations. If it does not appear, restart Codex.
Open the target project, then invoke:

```text
$agentify-repo Prepare this project for Codex only. Show the verification
results and files changed. Do not create CLAUDE.md.
```

In Codex CLI/IDE, `/skills` also opens the skill selector. This repository does
not register a `/agentify repo` slash command. See the official
[Codex skill documentation](https://learn.chatgpt.com/docs/build-skills).

The skill asks Codex to collect facts, read sources, verify commands, and draft
the Markdown. `write_block.py` writes that draft; it does not infer or generate
the content on its own. `check_agents_md.py` validates the result; it does not
execute the documented commands.

Codex-only validation uses:

```powershell
python "$skillPath/scripts/check_agents_md.py" 'C:/path/to/project' --agent codex
```

`--agent codex` skips only the sibling CLAUDE.md checks. All AGENTS.md structure,
command status, path, and secret checks still run. The default remains
`--agent claude` for compatibility with existing invocations. Existing human
Claude instructions remain input for contradiction review, even in Codex mode.

**Preview an unpublished local branch:** the clone commands above download the
published version, which may not contain these changes yet. To test a local
checkout, copy its skill files to a separate project instead of overwriting an
existing personal installation:

```powershell
$source = 'C:/path/to/agentify-repo' # checkout on the local codex-support branch
$preview = 'C:/path/to/preview-project'
$destination = Join-Path $preview '.agents/skills/agentify-repo'
if (Test-Path -LiteralPath $destination) { throw 'Preview skill already exists.' }
New-Item -ItemType Directory -Force -Path $destination | Out-Null
Copy-Item -LiteralPath "$source/SKILL.md" -Destination $destination
foreach ($folder in 'scripts', 'references') {
    Copy-Item -LiteralPath (Join-Path $source $folder) -Destination $destination -Recurse
}
```

Open that preview project in Codex. If the personal skill of the same name is
already installed, explicitly select the project-local skill by its path. This
preview does not change the personal installation or the original application.

### Local QA

From this repository root:

```powershell
python -m unittest discover -s tests -v
git diff --check
```

The dependency-free tests exercise the validator CLI with temporary repos:
Codex warning suppression, unchanged files, legacy Claude behavior, explicit doc
paths, invalid agent values, missing docs, and preserved structure/secret errors.
They do not require Docker, services, or a live coding-agent session.

## Current scope

> [!NOTE]
> **This is an early release.** It is already useful, and we'll keep updating it with broader stack support and more robustness. Here is exactly where it stands, so you know what to expect.

**Tested end to end on real projects** (Windows 11, Claude Code):

| Stack | Project type | Result |
|---|---|---|
| Python | CLI with PyTorch/audio deps, no lockfile, no CI | ✅ install, tests and single test verified; found an interpreter-version trap and an env-gated test file |
| Node / React | Create React App SPA, no CI | ✅ build, tests and dev server verified; found a failing lint, a watch-mode hang and a script that writes outside the repo |
| Java / Maven | Spring Boot + PostgreSQL, CI, two compose files, raw SQL schema | ✅ CI-equivalent `mvn verify` (1196 tests) run in Docker; found a failing E2E script |
| Monorepo | pnpm + Turborepo with a Python package (synthetic) | ✅ per-package `AGENTS.md`, stale human line annotated |

**Detected by the collector, not yet validated on a real project:** Go, Rust, Gradle/Kotlin, PHP, Ruby, Poetry/uv/pnpm/yarn/bun lockfiles, Makefile/justfile/Taskfile.

**Known gaps:**
- .NET (`.csproj` / `.sln`) is not supported yet.
- Large real-world monorepos (Nx, Turborepo with dozens of packages) are untested.
- Merging into an existing, human-written `AGENTS.md`/`CLAUDE.md` has only been tested on a synthetic repo.
- Only tested on Windows with Claude Code. Linux, macOS and other agents should work but are unverified.
- The validator has focused CLI regression tests; the collector and writer still lack a dedicated test suite. The docker-compose reader is a lightweight parser, not a full YAML parser.
- Repos that need private registries or real secrets to build will produce `not verified` rows. That is by design, but untested.

## Roadmap

- [ ] .NET support (`dotnet build/test`, solution layout)
- [ ] Test suite + CI for the scripts, with fixture repos per stack
- [ ] Real-world validation on Go, Rust, Gradle and a large Nx/Turborepo monorepo
- [ ] End-to-end runs on Linux and macOS, and with other agents (Codex, Cursor, opencode)
- [ ] Hardened merge for existing human-written agent docs
- [ ] `--refresh` mode: re-verify an existing `AGENTS.md` and report drift (e.g. on a schedule)

Have a repo where it gets something wrong? [Open an issue](https://github.com/AdalbertoCV/agentify-repo/issues). A short description of the stack and the bad line is the most useful bug report there is.

## Contributing

PRs are welcome, especially:
- **New stack support** in `collect_facts.py`, plus a note in `references/verification.md` on how to verify that stack
- **Failure reports** from real repos, which are what most of the current rules came from
- **Fixture repos** for the upcoming test suite

Please keep the scripts dependency-free (standard library only).

## License

[MIT](LICENSE) © Adal Cerrillo
