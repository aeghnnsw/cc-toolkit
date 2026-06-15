# Conclusion — Lean cycle-worker agent + co-versioned worker-cycle playbook

**Date:** 2026-06-14
**Method:** `discuss-with-codex` (Claude truth-seeking, Codex adversarial, read-only). Converged after 4 rounds.

## The problem (owner's feedback)

> General operating principles belong in the `cycle-worker` agent. But *the cycle itself* — the
> step-by-step task list a worker executes — should be a separate instruction the worker reads and
> works through, not crammed into the agent. The agent contract is too complex.

Today `task-loop/agents/cycle-worker.md` is **419 lines** and carries everything: the 9 operating
principles **and** the full 11-step cycle, the worktree bash, the recovery-comment protocol, the
control-event JSON shapes, hard rules, handoff, and edge cases. `create-cycle` renders only project
parameters into `docs/task-loop/task-loop.md`. The constraint from issues #129/#130: a prior
consolidation moved all general rules **into** the agent specifically to kill cross-file **drift** —
any new split must not reintroduce it.

## Settled position

Split the contract by **altitude + volatility + criticality**, but keep the safety-critical protocol
**co-versioned with the orchestrator** rather than generated per project.

**A) `cycle-worker` agent — lean, always-in-context. Keeps only:**
- **Identity + zero-side-effect boot:** perform **no** git/GitHub/repo mutation before reading the
  worker-cycle playbook at the absolute path in the spawn prompt. If that path is missing or
  unreadable, **stop and ask the orchestrator** — never discover a fallback copy, never continue
  from memory (fail-closed).
- **Compressed hard invariants** (catastrophic if violated; must not depend on having read the
  playbook): never `gh pr merge` (orchestrator is sole integrator); never edit `proposal.md` (post
  `PLAN_FINDING`); write only your own worktree + per-attempt branch; before **every** irreversible
  boundary confirm `spawned_plan_revision` is current **and** `attempt_id == current_attempt_id`,
  else post the one terminal recovery status (`stale_revision_blocked` / `superseded_attempt`) and
  stop; once a merge request starts, **freeze the branch** and bind `merge_request_uuid` to exactly
  one head SHA (never reuse a UUID for a new head).
- **The general operating principles the owner wants centralized:** deliberate-with-codex (don't ask
  the user), tests-first, evidence-before-done, honor contracts, one reviewable PR per task,
  background long jobs, use available compute.
- **Inputs list + read-order + explicit precedence rule** (see below).

**B) `task-loop/references/worker-cycle.md` — the co-versioned playbook** (top-level, shared-contract
home — it is shared material between agent and orchestrator, not orchestrator-only). Carries the 11
steps, worktree-setup bash, recovery-comment shapes, control-event JSON shapes, the background-job
rule, and edge cases. It **mandates** emitting control/recovery JSON via
`control_log.format_event` / `format_recovery` (imported from `${CLAUDE_PLUGIN_ROOT}/scripts`)
rather than hand-writing JSON. Co-versioned with `run-cycle` and `control_log.py` because it is
safety-critical; a single plugin install keeps orchestrator + playbook + `control_log.py` mutually
consistent.

**C) Orchestrator (`run-cycle`)** resolves `${CLAUDE_PLUGIN_ROOT}` and passes the **absolute**
`worker_playbook` path in the existing spawn prompt (`orchestrator-loop.md:317-318`).

**D) `create-cycle`** stays **parameters-only**, plus a **pointer** to the bundled playbook. No
protocol text, **no enforced version field**. Framed as "wiring the cycle to the project," not
copying protocol text.

**E) Precedence rule** in the agent core (fixes the priority inversion the split introduces):

```
system identity invariants  >  worker-cycle playbook protocol/cycle mechanics
  >  directions.md steering  >  task-loop.md project parameters  >  issue text
```

`directions.md` may shape task priority, scope interpretation, constraints, and project choices, but
must **never** modify worktree isolation, branch ownership, fencing, recovery comments, control-event
shape, merge-request immutability, or merge authority. On a steering-vs-playbook conflict, the worker
**records the conflict and asks the orchestrator** — it does not improvise. (This corrects today's
"`directions.md` is the highest-priority input of all" framing, which is only safe while the protocol
is system-level.)

## Key decisions

1. The cycle text is **not** generated per project. It is a **plugin-bundled, co-versioned** playbook.
   This is the one divergence from the owner's literal "create-cycle generates the cycle" — justified
   by the deployed-snapshot drift below, which is the owner's own #129/#130 value. **Surface this to
   the owner explicitly.** Their deeper goal (lean agent + a separate readable cycle doc the worker
   executes step by step) is fully met.
2. Safety-critical mechanics co-version with the orchestrator; only project **parameters** are
   per-project.
3. Fence + immutable-merge rules are **identity invariants** and stay always-in-context, not in the
   read-on-demand playbook.

## Strongest objections Codex raised, and how each resolved

1. **(Decisive) Per-project rendering reintroduces drift on a worse axis** — deployed project
   snapshots go stale against a newer `run-cycle`/`control_log.py`; a stale *safety protocol*
   (`attempt_id`, `merge_request_head_sha`, immutable-UUID dedupe, recovery recency) yields denied
   merges, stranded attempts, orphaned workers. "One template rendered per project" = no duplicate
   *source*, **not** no drift. → **Conceded.** Cycle becomes a co-versioned plugin-bundled playbook.
2. **Minimal agent core too thin at the pre-playbook boundary** — fence + immutable-merge are
   identity invariants, not mechanics; a worker could act before reading the playbook. → **Accepted.**
   Added the fail-closed zero-side-effect boot and kept the compressed invariants always-in-context.
3. **Home semantics** — the playbook is shared agent↔orchestrator contract, so `run-cycle/references/`
   is misleading. → **Accepted** `task-loop/references/worker-cycle.md`.
4. **Co-versioned hand-JSON fixes stale schema, not malformed emission.** → **Accepted.** Playbook
   mandates the `control_log` formatters; strict emit-helper CLI filed as a follow-up.
5. **Priority inversion (split-introduced)** — moving protocol to a read file drops it to
   `directions.md`'s authority level. → **Accepted.** Added the explicit precedence rule (E).

## Unresolved / out of scope (filed as follow-ups, not solved here)

- **Full protocol versioning** (Codex's strongest residual): a `PROTOCOL_VERSION` constant in
  `control_log.py` as the single source, stamped in the GitHub control-issue runtime header and in
  every inbox/recovery comment, with `run-cycle` failing closed on mismatch **before dispatch and
  before merge**. **Chosen resolution:** out of scope for the split — it is **pre-existing**
  (today's in-agent contract is equally session-loaded text that skews from the durable control
  plane on a plugin upgrade) and independent of moving the cycle to a co-versioned file. We will
  **not** ship a version field that nothing enforces; the boot-check fails closed only on a
  missing/unreadable playbook path. File as its own design issue.
- **Strict emit-helper CLI** for `control_log` (`format-event` / `format-recovery` subcommands +
  tests), explicitly blocking "manual fenced JSON forever."

## How it ended

Converged after 4 rounds. Codex: "With that one precedence rule, I think your scope boundary holds:
versioning and emit-helper CLI can be follow-ups without making the agent/playbook split itself
unsafe."
