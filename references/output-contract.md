# Output contract

## Sections, in this order

Omit a section that would be empty. `check_agents_md.py` enforces the order. **Commands** is the only required section.

1. **Project** — 1–2 sentences: what it is and its main stack.
2. **Commands** — table: `Task | Command | Status`. Statuses come from `verification.md`. Include the table even when nothing could be run; it is still the best map. If tests need services, put the service setup here.
3. **Layout** — only non-obvious locations ("API routes are in `server/handlers`, not `routes/`"). Not a tree.
4. **Conventions** — rules that linters and formatters **don't** enforce. Give each one a source tag or a file reference.
5. **Boundaries** — what not to touch, or to ask about first: generated code, migrations, raw SQL, vendored code, public APIs, scripts that hit real systems.
6. **Gotchas & known issues** — failing commands, `empty_or_stub_files`, required env vars (names only), version constraints, ordering traps, side-effecting scripts.
7. **Decisions** — "we do X because Y", each with its source, linking to ADRs or docs if they exist.
8. **Done means** — the checks to run before declaring a task complete. Mirror CI. If CI skips part of the repo or is broken, say so. Without CI, list the local commands you verified.

Budget: ≤150 lines per file. When over budget, cut first whatever is visible in the code.

## Lines that earn their place vs. noise

| Noise (delete) | Useful (keep) |
|---|---|
| "The project uses React and Jest." | "`npm test` starts watch mode and never exits; use `CI=true npm test -- --watchAll=false` (verified)." |
| "`src/` contains the source code." | "Shared site constants live in `src/site.js`; don't hardcode the URL or email in components (from code)." |
| "Follow best practices and write tests." | "Every i18n key must exist in both `en` and `es` (enforced by `src/i18n/dictionary.test.js`)." |
| "Configure your environment variables." | "Tests read `DB_URL`; CI seeds the DB with `db/schema.sql` before `mvn verify` (from config: `.github/workflows/ci.yml`)." |
| "ESLint enforces code style." | "Lint lives in `package.json` `eslintConfig`; there is no `lint` script, so run `npx eslint src`." |

## Monorepos (`monorepo_signals` is non-empty)

- The root AGENTS.md holds repo-wide rules.
- Create `<package>/AGENTS.md` (plus a sibling `CLAUDE.md` containing `@AGENTS.md`) when the package has its own toolchain or commands that the root commands don't run. Otherwise keep everything in the root file.
- A package file follows the same contract and holds that package's commands and failures. The root file links to it.

## Other agent files

- Treat `CLAUDE.md`, `.cursorrules`, `.cursor/rules/`, `.github/copilot-instructions.md`, and `GEMINI.md` that contain human content as input. Don't overwrite them. Report contradictions with AGENTS.md in the final report.
- A missing `CLAUDE.md` is created as `@AGENTS.md` only (`write_block.py --import`).

## Skeleton

```markdown
## Project
<what + stack, 1–2 sentences>

## Commands
| Task | Command | Status |
|---|---|---|
| Setup | `…` | ✅ verified |
| Test | `…` | ✅ verified (N passed) |
| Single test | `…` | ✅ verified |

## Gotchas & known issues
- …

## Done means
1. `…`
```
