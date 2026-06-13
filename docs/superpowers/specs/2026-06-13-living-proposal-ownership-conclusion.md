# Conclusion — living proposal doc: structure, ownership & coordination

**Goal.** In the `cycle-dev` suite, a `specify-aims` skill writes a combined
proposal+implementation doc; `create-cycle` writes `docs/task-loop.md` referencing it;
`run-cycle` is an Agent-Teams orchestrator that dispatches one worker teammate per ready
task. The proposal is *living* — workers validate/reject hypotheses and the plan must
adjust. How should the proposal be structured and **owned** so the north-star stays
stable, the plan evolves, and parallel workers don't conflict-edit or cause
**planning split-brain**?

## Settled model (layered)

**1. `docs/proposal.md` — one durable, human-readable doc. NOT the live coordination
primitive.**
- **Charter zone**: aims, success criteria, constraints, non-goals. Change bar =
  **human-gated** (a goal change is a stop-condition-class escalation).
- **Roadmap zone**: stages/phases + a hypothesis ledger (open / validated / rejected).
  Updated via **orchestrator-authored, codex-reviewed, dedicated PRs**.
- **Only the orchestrator edits `proposal.md`** (per user direction). Workers never do.

**2. GitHub = the authoritative, append-only control-event log** (cross-worktree,
survives cold resume):
- **Worker reports** (append-only comments): `PLAN_FINDING`, `MERGE_REQUEST`, … with
  task ID, `spawned_plan_revision`, PR head SHA.
- **Orchestrator decisions** (append-only comments): `PLAN_REVISION_BUMP`, `TASK_STALE`,
  `TASK_REVISION_COMPATIBLE`, `MERGE_GRANTED`, `MERGE_DENIED`, with task ID, revision,
  affected hypotheses, PR head SHA, and a **sequence number**.
- **Labels are a derived human-facing index only — never sufficient for authority**
  (labels are mutable and don't record who/when/under-which-revision).
- The **Agent-Teams mailbox is notification-only**, never independent truth, so cold
  resume reconstructs full ordering from GitHub alone.

**3. `orchestrator-state.json`** (fixed main-repo path, **single writer = orchestrator**)
— private fast cache of `current_plan_revision`, `invalidated_revisions`, invalidated
subgraph, ready/active/blocked sets, lease/heartbeat. Rebuilt from the GitHub
append-only log on resume.

**4. Per-task `NNN_task_rubric.md` / `NNN_task_log.md`** — durable decision + evidence
trail.

## The orchestrator is the single point of authority
It does **all high-level planning and dispatching** (per user direction) and is also:
- the **single writer** of fast state,
- the **single bumper** of `plan_revision` (only at explicit replan barriers),
- the **sole integrator** — the only agent that merges.

Workers execute exactly one task's cycle through *open PR + request merge*, then report
and go idle. **Workers never merge and never edit the proposal.**

## Causal-ordering protections (how split-brain is dissolved)
1. **Revision lease, not tag.** Every task carries `spawned_plan_revision`. Invalidation
   is scoped to the affected subgraph via **explicitly declared** `depends_on_tasks` /
   `depends_on_hypotheses`; if blast radius can't be confidently mapped, the orchestrator
   **defaults to a broader freeze**.
2. **Replan barrier.** Between `waiting` and the next `dispatching`, the orchestrator
   ingests findings, bumps `plan_revision` if a hypothesis was invalidated, recomputes the
   frontier, and **halts dispatch of now-stale dependent tasks** before spawning anything.
3. **Orchestrator-only merge** collapses the authorize-then-merge **TOCTOU** into one
   serialized action. If the orchestrator is dead/draining, nothing merges — *stalled
   merge ≫ stale merge*.
4. **Pre-merge event-drain barrier.** Before any merge: fetch all task
   issues/comments since the last **sync watermark**, drain pending mailbox messages,
   **ingest findings before merge requests** within the batch, recompute invalidated
   subgraphs, advance the watermark. Deny/hold on sync failure, ambiguous ordering, or any
   unclassified plan-affecting finding.
5. **Head-SHA-bound merge.** Merge only the exact validated PR head SHA
   (`gh pr merge --match-head-commit <SHA>` or equivalent); any branch update since
   validation fails the guard and forces re-validation.

## Strongest objections raised and how each resolved
1. Serialized PRs protect the file, not the system (planning split-brain) → split durable
   narrative from live coordination.
2. `plan_revision` tag gates dispatch but not merge; fast-state file invisible across
   worktrees → revocable lease + hard merge gate + shared channel.
3. Authorize-then-merge is TOCTOU → orchestrator-only merge; explicit deps + broad-freeze.
4. Two-channel stale reads → pre-merge event-drain barrier; single authoritative log;
   head-SHA-bound merge.
5. Mutable labels can't be authority → append-only control-event log; labels derived only.

## Unresolved / deferred (ordinary implementation details, for the plan)
- Merge-queue throughput when many PRs land at once.
- Worktree cleanup after orchestrator-merge.
- Sync-watermark storage (last-processed event seq# per issue).

**How it ended:** converged after 5 rounds.
