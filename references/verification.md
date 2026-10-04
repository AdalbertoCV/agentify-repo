# Verifying commands

Goal: for each task (install, dev, build, lint, format, typecheck, test, single test), find the command that really works in this repo and record its status.

## Before running anything

- **Pick the package manager.** Use the lockfile (`lockfiles`). With no lockfile, use what README or CONTRIBUTING say.
- **Check versions.** Compare `requires-python`, `engines`, `java_version` and toolchain files with `toolchain_on_this_machine`. If they don't match, use a version manager that is already installed (`uv venv -p 3.12`, `fnm`, `sdkman`). Document the constraint as a gotcha.
- **Prefer installs that respect the lockfile:** `npm ci`, `pnpm install --frozen-lockfile`, `uv sync --frozen`, `mvn -B`. If an install modifies a tracked file anyway, revert it (`git checkout -- <file>`) and record the drift.
- **Read custom scripts before running them.** That covers `scripts/*`, Makefile targets, and anything in `risk_signals.scripts_touching_network_or_db`. If a script writes outside the repo, deletes data, or calls a non-local host, run it pointed at a temp directory or a local container, or skip it.
- **Force non-interactive mode:** `CI=true`, `--watchAll=false`, `vitest run`, `-B` for Maven. Check `script_warnings`.
- **Run long installs and builds** (torch, first Maven or Gradle run) in the background and poll them. Don't let them hit a command timeout.

## Missing toolchain (e.g. no `mvn`/`java`, no `pnpm`)

1. Look for a wrapper in the repo: `./mvnw`, `./gradlew`, `packageManager` together with an enabled corepack. Wrappers are part of the repo, so you may use them.
2. If there is no wrapper, the repo's `Dockerfile` or `containers.compose` often names the exact build image (for example `maven:3.9-eclipse-temurin-21`). **Ask the user** before pulling it. Say in the question that the build will also download dependencies from public registries (Maven Central, npm, PyPI). If they approve, run the build in that image with the repo mounted:
   ```bash
   docker run --rm -v "$PWD":/w -w /w -v agentify-m2-<id>:/root/.m2 <image> <command>
   # Git Bash on Windows: prefix with MSYS_NO_PATHCONV=1 and use "$(pwd -W)"
   ```
   The cache volume name must be unique to this run, prefixed `agentify-`. A generic name like `m2` could reuse a volume the user already has.
3. If there is no user or no Docker, record `not verified (<tool> not installed)`. This is a machine problem, not a repo problem.

## Services the tests need (DB, cache, queue)

- Find them in CI (`services:`, setup steps such as `psql -f schema.sql`), in `containers.compose`, and in test config (`application-test.*`, `testcontainers`).
- Start them **only** as throwaway local containers. Seed them exactly the way CI does. Never point anything at a host from `.env` or from config that isn't `localhost`.
- Check `containers.conflicts_on_this_machine` first. If the repo's compose uses fixed `container_name`s or ports that are already taken, don't run that compose file. Run the same images with `docker run` instead, using `agentify-<id>-*` names, a private network, and no host port or a free one.
- Clean up everything you started. Use `--rm` or `docker rm -fv`; plain `-f` leaks the anonymous volumes that images like `postgres` declare. Use `docker compose down -v` for compose. Then count `docker volume ls` before and after. Report what you created and confirm it is gone.
- Document the service setup in Commands, since it is usually the #1 trap.

## Running the app, dev servers and E2E/smoke scripts

- Before starting the app, override every default in `external_hosts_in_config` (SMTP, APIs) to `localhost` or a dummy value, so nothing reaches a real system.
- Start the app on a free port with a timeout, make one meaningful request, then stop it.
  - Health endpoints can be `DOWN` by design when an optional dependency is unreachable. A login or auth check (for example 200 for a valid login, 401/403 without credentials) is better proof.
  - A 200 from a port that something else was already using doesn't count.
- E2E or smoke scripts in the repo (`scripts/verify-*`, `e2e/`) are often the most valuable verification. Read them first. Run them only against your throwaway app and DB, by overriding their host, port and container variables. Run them from a scratch directory if they write files to the current directory.
- When a run is slow, put the duration under Gotchas with "(verified)". Timing depends on the machine, so state where it ran.

## Status vocabulary (Commands table)

| Situation | Status |
|---|---|
| Passed | `✅ verified` |
| Passed, but some tests were skipped | `✅ verified (N passed, M skipped: <condition>)`. Also add the condition, such as an env var, under Gotchas. |
| Failed once, passed on an identical retry | `✅ verified`. Mention the flake in the final report only. Retry once at most. |
| Failed because of a problem in the repo | `❌ fails`. Put the first meaningful error line under Gotchas. Don't fix it. |
| Tool not installed and not approved | `not verified (<tool> not installed)` |
| Ran inside a container | `✅ verified (in <image>)` |
| Blocked because an earlier step failed | `not verified (blocked by <step>)` |
| Deploy, publish, release, remote migrations, or anything needing real secrets | `not verified (not run: <reason>)`. Never run these. |
| No tool configured for the task | `—` |
