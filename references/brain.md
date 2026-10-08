# Brain mode

A brain is a small set of files in `docs/agents/` that an agent reads **on demand**, routed by `AGENTS.md`. The goal is fewer tokens per task: the agent loads the root file, follows one row of the Context map, and stops.

## Shape

```
AGENTS.md              ← commands + "## Context map" (router: if you touch X, read Y)
docs/agents/
  INDEX.md             ← one row per file: file | read when
  architecture.md      ← entry points and the main flow across modules
  glossary.md          ← domain terms an agent would misread
  domains/<slug>.md    ← one per area of the code (rules, invariants, gotchas)
  decisions/README.md  ← links to decisions/NNNN-title.md and existing ADRs
  runbooks/README.md   ← links to runbooks/<task>.md
  MAINTENANCE.md       ← when and how to update the brain
```

Every file starts with frontmatter. `paths` lists the code it covers (`[]` when none), so the validator can flag a stale file when that code moves:

```markdown
---
read_when: touching src/billing/ or invoice totals
paths: [src/billing/]
---
```

## Choosing domains

Start from `brain_candidates.domains` in the collector output. A domain is an area someone changes on its own: a package, a bounded context, or a service. It is not a technical layer.

- Merge candidates that always change together. Split one only when it has its own rules.
- Aim for 3–8 domains in a typical repo. A domain earns its own file when you can seed its entry point **and** at least one rule, invariant or gotcha. Otherwise, fold it into a broader domain. A tiny repo can have 1.
- `read_when` names the trigger in task words ("touching login, sessions or permissions"), not the folder alone.
- Generated code, vendored code and migrations are Boundaries in `AGENTS.md`, not domains.

## Seeding content

The scaffold only creates headings and `<!-- agentify:pending — <question> -->` lines. In the first session, replace a pending line only with a fact you read. Tag it the same way as in `AGENTS.md` (*from code*, *from config*, *from docs*, *from tests*, *from user*, *verified*) or give it a file reference.

- **Good seeds**: the entry point of each domain, an invariant visible in code or tests, links to existing ADRs and READMEs, and terms defined in code.
- **Leave as pending**: the reasons behind decisions, ownership, anything you would have to guess. Rewrite the generic question as a specific one ("Why does `jobs/retry.py` cap retries at 3?") so the next session can answer it quickly.
- A claim about absence ("no test covers `auth/`") is tagged with where you looked: *from tests*, *from code*.
- New decisions go in the repo's existing ADR folder, if there is one. `decisions/README.md` links to them.
- Link to existing docs instead of copying them. Do not repeat facts across files. Put each fact in the most specific file and link to it from the others.

## Context-saving rules

| Rule | Why |
|---|---|
| `AGENTS.md` keeps commands, the Context map and repo-wide boundaries. Domain detail goes in `docs/agents/` | The root file loads on every task |
| One topic per file, ≤80 lines (enforced) | A file that matches a task can be read whole |
| Every file is reachable from `INDEX.md` (enforced) | An orphan file is never read |
| Links, not copies | One fact, one place to update |
| Pending items are questions, not placeholders | They show the next session what to ask or check |

## Proposal format (chat, before writing)

```
docs/agents/
  domains/billing.md   src/billing/          seeds: entry point (from code), rounding rule (from tests)
  domains/auth.md      src/auth/, src/mw/    seeds: session TTL (from config); pending: why JWT + cookie
  decisions/README.md                         links: docs/adr/ (4 ADRs)
Context map rows: 2 · Planned pending questions: 7 · Files skipped (exist): none
```

List the core files (architecture, glossary, decisions, runbooks) only when you will seed or link something in them. The scaffold creates them either way. Then show the plan JSON for `scaffold_brain.py`; its schema is in `--help`.
