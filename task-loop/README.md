# task-loop

Autonomous, orchestrated **cycle-driven development**: an **orchestrator + worker-team** workflow over
a hosted **Supabase** task board.

- The **orchestrator** (main agent, `run-cycle`) does all planning and dispatching, owns `proposal.md`,
  and is the **sole merger**. Each fixed-interval tick it runs a **6-step pass**: read state + steering
  → check worker liveness → merge ready PRs → reconcile the roadmap → materialize tasks → dispatch
  claimable tasks.
- **cycle-worker teammates** each run **one task** in their own git worktree, open a PR carrying a
  study log, report the outcome, and idle — they never merge, never touch the DB, never manage tasks
  or the plan.

State is re-derived every tick from the **Supabase task DB** (reached only via the `task-loop` CLI) +
**GitHub** (issues, PRs) + the git-tracked `docs/task-loop/` files. There is **no control issue, no
lease, and no local runtime files** — the loop is idempotent, so it runs from anywhere, anytime, and
recovery is just the next tick.

## Workflow

One-time **`setup`**, then three skills in order, plus one agent:

```
setup           → Supabase project + schema, creds, repo init, Agent Teams, required skills
a. specify-aims → docs/task-loop/proposal.md   (aims + plan + roadmap; collaborative + codex)
b. create-cycle → docs/task-loop/task-loop.md  (the worker's per-project cycle + parameters)
c. run-cycle    → orchestrator: fixed-interval Loop A + a non-destructive Loop B stop nudge
                  cycle-worker (agent): executes one task's cycle in its own worktree
```

1. **`setup`** — onboard the account/machine/repo: create the Supabase project + apply `db/schema.sql`,
   save creds (`task-loop login`), register the repo (`task-loop init`), enable Agent Teams, install
   the required plugin skills.
2. **`specify-aims`** — brainstorm the goal *with you* + pressure-test with `discuss-with-codex`, then
   write `proposal.md`: Specific Aims & Goal (human-gated) + Implementation Plan + Living Roadmap.
3. **`create-cycle`** — render `docs/task-loop/task-loop.md` (the worker's tailored cycle + general
   rules + parameters) and scaffold `directions.md` + `logs/`.
4. **`run-cycle`** — the orchestrator (above); the `cycle-worker` agent does each task.

## The task DB + CLI

All task state lives in the user's own hosted **Supabase** project (one shared across their repos;
repos are rows). The only thing that talks to it is the **`task-loop` CLI** — a single `uv run` script,
REST-only:

```
task-loop status | add "<title>" [--dep N…] [--issue N] | claim | close SEQ | reset SEQ | init | login
```

The orchestrator uses it; workers never do. `claim` is atomic (`FOR UPDATE SKIP LOCKED`) — the only
dispatch lock, so multiple orchestrators (one per ecosystem) need no further coordination.

## Prerequisites

Run **`setup`**, which covers:

- **`uv`** (runs the CLI) and **`gh`** (authenticated; PRs/merges).
- **Agent Teams** — `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` + Claude Code ≥ v2.1.32 (workers are
  teammates; `run-cycle` only — `specify-aims`/`create-cycle` don't need it).
- **Required plugin skills (8):** `superpowers:{brainstorming, writing-plans,
  test-driven-development, verification-before-completion, receiving-code-review}` and
  `dev-skills:{discuss-with-codex, goal-rubric, doc-update}`. `run-cycle` re-checks these each session.

## Files this creates in your project

| Path | Owner | Purpose |
|---|---|---|
| `docs/task-loop/proposal.md` | `specify-aims`, then orchestrator | aims + plan + roadmap (the living spine; the orchestrator reconciles it each loop) |
| `docs/task-loop/task-loop.md` | `create-cycle` | the worker's per-project cycle + general rules + parameters (followed strictly) |
| `docs/task-loop/directions.md` | you | human steering channel (read first each tick) |
| `docs/task-loop/logs/<NNN>_<task>.md` | worker | one git-tracked study-log per task (`NNN` = the task `seq`): Outcome + rubric + evidence + findings, committed in the PR |

(No control issue, no runtime header, no local runtime files — task state lives in Supabase.)

## Components

```
task-loop/
├── db/schema.sql          # the Supabase schema (projects + tasks, claimable view, task_add/task_claim)
├── cli/task-loop          # the uv/REST CLI (the only thing that talks to the DB)
├── references/
│   └── pr-findings.md     # the worker → orchestrator study-log + PR contract
├── claude-skills/
│   ├── setup/             # onboard account/machine/repo (Supabase, creds, Agent Teams, skills)
│   ├── specify-aims/      # step a: author the proposal
│   ├── create-cycle/      # step b: render task-loop.md + scaffolding
│   └── run-cycle/         # step c: the orchestrator (per-tick algorithm in references/)
├── codex-skills/
│   └── setup/             # Codex setup and preflight support
└── agents/
    └── cycle-worker.md    # the per-task executor (Agent-Teams teammate)
```

## Design

`docs/superpowers/specs/2026-06-15-task-loop-supabase-harness-design.md` — the authoritative design
(rationale, data model, the loop), which links its companion deliberations.
