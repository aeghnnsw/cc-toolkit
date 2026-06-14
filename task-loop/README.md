# task-loop

Autonomous, orchestrated **cycle-driven development**. `task-loop` generalizes a proven
study/dev loop (issue → branch → binary rubric → spec → plan → TDD → verify → PR →
squash-merge, one increment per cycle, fully resumable) into an **orchestrator + worker-team**
workflow:

- The **orchestrator** (main agent) does all high-level planning and dispatching, owns the
  proposal, and is the **sole integrator** (the only agent that merges).
- **Worker teammates** each run **one task's** full cycle in their own git worktree, post a
  `MERGE_REQUEST`, and hand off — they never merge and never edit the proposal.

State is durable and resumable from git + a single GitHub **control issue** (an append-only,
single-sequencer event log) + numbered decision records, so a cold agent can continue.

## Workflow

Three skills, run in order, plus one agent:

```
a. /specify-aims   → docs/task-loop/proposal.md   (Charter + Roadmap; collaborative + codex)
b. /create-cycle   → docs/task-loop/task-loop.md   (per-task playbook + scaffolding)
c. /run-cycle      → orchestrator: /loop self-paced + Agent Team + drain-on-signal
                     cycle-worker (agent): executes one task's cycle
```

1. **`specify-aims`** — brainstorm the project goal *with you* and pressure-test it with
   `discuss-with-codex`, then write `docs/task-loop/proposal.md`: a **Charter** (stable
   aims/success/constraints/non-goals — human-gated) and a **Roadmap** (living stages +
   hypothesis ledger — orchestrator-authored).
2. **`create-cycle`** — render the project-specific `docs/task-loop/task-loop.md` from a
   generic cycle skeleton plus auto-detected/interviewed project specifics, and scaffold
   `directions.md` (steering), the logs directory, `.gitignore`, and the `loop:in-progress`
   label.
3. **`run-cycle`** — the orchestrator: each turn it computes the dependency-ordered task frontier,
   spawns one `cycle-worker` teammate per ready task, and validates + merges their PRs. It runs as
   a **live `/loop` lead plus two scheduler guard jobs (no local files)** — a watchdog that detects
   the lead's death and alerts (unattended auto-relaunch needs a tested local supervisor) and a
   one-time stop — coordinating purely through the GitHub control issue, and it **prompts for a run
   duration (default 24h)**, self-bounding on that stop time (a graceful drain, not an iteration cap).

## Prerequisites

`task-loop` invokes skills from two **required** plugins — install them first:

- **`superpowers`** — `brainstorming`, `writing-plans`, `test-driven-development`,
  `verification-before-completion`, `finishing-a-development-branch`. (Each `cycle-worker` creates its
  own git worktree at invocation — in-process Teams do not honor an `isolation: worktree` declaration,
  so the worker self-provisions one keyed on its `attempt_id`.)
- **`dev-skills`** — `discuss-with-codex`, `goal-rubric`, `doc-update`, `step-workflow`.

**Run the `preflight` skill** to check two scopes: that these skills are loadable in your
**session** (re-run it per task-loop session — it reports installed / owner-unverified /
missing) and that **Agent Teams is enabled on your machine** (a one-time `settings.json` write,
below). It's a standalone check, not a step in the a→b→c workflow.

## Enablement (orchestrator)

`run-cycle` uses **experimental Agent Teams**, which are off by default. Enable them and use
Claude Code ≥ v2.1.32:

```json
// settings.json
{ "env": { "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "1" } }
```

The **`preflight`** skill sets this for you (and reminds you to restart). The `specify-aims` and
`create-cycle` skills do **not** require Agent Teams.

## Files this creates in your project

| Path | Owner | Purpose |
|---|---|---|
| `docs/task-loop/proposal.md` | `specify-aims`, then orchestrator | Charter + Roadmap (living research spine) |
| `docs/task-loop/task-loop.md` | `create-cycle` | the per-task playbook each worker follows |
| `docs/task-loop/directions.md` | you | human steering channel (read first each round) |
| `docs/task-loop/logs/NNN_<task>.md` | worker | one git-tracked per-cycle record (**Rubric** + **Decision log** sections); `NNN` = zero-padded iteration index from `001` (orchestrator-assigned, tracks cycles chronologically) |
| GitHub control issue (comments) + per-task issues | orchestrator + workers | append-only control-event log |
| GitHub control issue (body runtime header) | orchestrator (sole writer) | lease/heartbeat, `stop_at`, schedule handles — **no local files** |

## Components

```
task-loop/
├── skills/
│   ├── preflight/        # standalone: verify required skills + enable Agent Teams (run once)
│   ├── specify-aims/     # step a: author the proposal (Charter + Roadmap)
│   ├── create-cycle/     # step b: render task-loop.md + scaffolding
│   └── run-cycle/        # step c: the orchestrator (state machine in references/)
├── agents/
│   └── cycle-worker.md   # the per-task executor (Agent-Teams teammate)
├── scripts/
│   ├── control_log.py    # pure single-sequencer control protocol (dedupe, replay, checkpoints)
│   └── gh_store.py        # thin gh adapter (read/post issue comments)
└── tests/                # stdlib unittest for the protocol (no external deps)
```

## Status

- ✅ **Control protocol** (`control_log.py`, `gh_store.py`) — single-sequencer log, UUID
  dedupe, checkpoint-based scan floor, per-attempt ownership + iteration fields, recovery-comment
  parser, schema validation; 58 unit tests.
- ✅ **`specify-aims`**, **`create-cycle`**, **`run-cycle`** skills + **`cycle-worker`** agent.
- ⚠️ **Phase 0 spike (operator-run)** — `run-cycle` is built against the documented
  Agent-Teams / `/loop` / stop-signal contract; the operator validates those primitives with
  `docs/superpowers/plans/2026-06-13-task-loop-phase0-spike.md` before the first unattended run.

Design and rationale: `docs/superpowers/specs/2026-06-13-task-loop-plugin-design.md` and the
`discuss-with-codex` conclusions alongside it.
