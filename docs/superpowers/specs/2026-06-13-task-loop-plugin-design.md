# Design — `task-loop` plugin (autonomous, orchestrated cycle-driven development)

**Status:** design (brainstorming output)
**Branch:** `feat-cycle-driven-dev`
**Companion deliberations:**
- `2026-06-13-cycle-loop-mechanism-conclusion.md` (loop driver + termination)
- `2026-06-13-living-proposal-ownership-conclusion.md` (proposal ownership + split-brain)

## 1. Overview

`task-loop` generalizes the METBG "study loop" — a proven autonomous, resumable
development loop (issue → branch → binary rubric → spec → plan → TDD → verify → PR →
squash-merge, one self-contained increment per cycle, recoverable from a cold context)
— into a **reusable, project-agnostic** Claude Code plugin.

It changes the execution model from METBG's single coordinator to an
**orchestrator + worker-team** model:

- The **main agent is an orchestrator** (Agent-Teams team lead). It does **all
  high-level planning and dispatching**, owns the proposal, and is the **sole
  integrator** (only agent that merges).
- **Worker teammates** each execute **exactly one task's cycle** in their own git
  worktree, then hand off the PR. One teammate per task.

The suite is three skills run in order plus one worker agent:

```
a. /specify-aims  → docs/task-loop/proposal.md     (goal + rough stages; living research spine)
b. /create-cycle  → docs/task-loop/task-loop.md     (per-task playbook referencing all docs)
c. /run-cycle     → orchestrator: /loop self-paced + Agent Team + drain-on-signal
                    cycle-worker (agent): executes one task's cycle
```

### Goals
- Reuse METBG's durability/resumability discipline on **any** project.
- Make the orchestrator a pure planner/dispatcher/integrator; keep workers single-task.
- Drive decisions by `discuss-with-codex` deliberation, not by pausing for the user.
- Survive cold resume from durable state alone (git + GitHub + numbered records).

### Non-goals
- Not a replacement for `problem-solving-cycle` (kept as the lightweight manual flow).
- No external watchdog process in v1 (deferred; see §12).
- Not a general project-management tool — it drives *implementation* against a proposal.

## 2. Plugin structure

```
task-loop/
├── .claude-plugin/plugin.json          # name: task-loop, version, description
├── README.md                           # what it is + the a→b→c workflow + enablement
├── skills/
│   ├── specify-aims/SKILL.md
│   ├── create-cycle/SKILL.md
│   │   └── references/cycle-skeleton.md # generic playbook the generator fills in
│   └── run-cycle/SKILL.md
│   │   └── references/orchestrator-loop.md  # state machine + coordination protocol
└── agents/
    └── cycle-worker.md
```

Plus a root `.claude-plugin/marketplace.json` entry pointing at `./task-loop`.

### Dependency contract (required prerequisites — not assumptions)
This repo's `marketplace.json` registers `dev-skills`, `core-hooks`, `creator-skills`,
`doc-skills`, `productivity-skills`, `pymol-skills`, `cc-customize` — it does **not**
package `superpowers`. The suite invokes skills from two **required prerequisite
plugins** that the user must have installed:
- **`dev-skills`** — `discuss-with-codex`, `goal-rubric`, `doc-update`, `step-workflow`.
- **`superpowers`** — `brainstorming`, `writing-plans`, `test-driven-development`,
  `verification-before-completion`, `using-git-worktrees`, `finishing-a-development-branch`.

`README.md` declares these prerequisites explicitly. `run-cycle` and `create-cycle`
**fail fast** with install guidance if a required skill is unavailable (rather than
half-running and erroring at the first missing `Skill` call).

## 3. Project artifacts and authority

Created in the **target project** (not the plugin):

| Path | Lifetime | Writer | Role |
|---|---|---|---|
| `docs/task-loop/proposal.md` | durable (git) | `specify-aims` (initial); **orchestrator only** thereafter | charter (aims/success/non-goals, human-gated) + roadmap (stages + hypothesis ledger, orchestrator-authored PRs). **Not** the live coordination primitive. |
| `docs/task-loop/task-loop.md` | durable (git) | create-cycle | the per-task playbook each worker reads |
| `docs/task-loop/directions.md` | durable (git) | human | steering channel, read first each planning round |
| `docs/task-loop/logs/NNN_<task>_rubric.md` | durable (git) | worker | binary acceptance criteria (orchestrator↔worker "done" interface) |
| `docs/task-loop/logs/NNN_<task>_log.md` | durable (git) | worker | decision record: task, steering, codex dispositions, rubric evidence, follow-ups |
| GitHub issues — **append-only control events** | durable (remote) | worker + orchestrator | **authoritative cross-agent coordination log** (see §8) |
| `.claude/task-loop/orchestrator-state.json` | runtime (gitignored) | **orchestrator only** | private fast cache (lease, `plan_revision`, ready/active/blocked); rebuilt from GitHub on resume |
| `.claude/task-loop/stop-request.json` | runtime (gitignored) | scheduled stop job only | atomic stop signal (temp-file + rename) |

> Note: the playbook lives at `docs/task-loop/task-loop.md` (grouped layout). The slight
> name echo is intentional — the dir is the namespace, the file is the playbook.

## 4. `specify-aims` skill (step a)

**Purpose.** Initialize the living research spine: a combined proposal+implementation
doc. "It does not need to be perfect, but must be clear about the goal and roughly the
stages/phases."

**Process.**
1. Explore the project (repo state, existing docs, the user's stated direction).
2. **Brainstorm with the user** to extract: the north-star goal, what *done* looks like
   (success criteria), constraints, non-goals, and the rough stages/phases.
3. Use `discuss-with-codex` **proactively** to pressure-test the aims and the stage
   decomposition (is the goal falsifiable? are stages ordered by real dependency? what's
   the riskiest hypothesis?).
4. Write `docs/task-loop/proposal.md` with two zones:
   - **Charter** — aims, success criteria, constraints, non-goals (stable; human-gated).
   - **Roadmap** — stages/phases, each with its purpose, rough acceptance, and a
     **hypothesis ledger** (`open` / `validated` / `rejected`).
   - Frontmatter carries `plan_revision: 1`.
5. Commit on its own branch + PR (the proposal is durable git state).

**Output.** A clear, intentionally-imperfect proposal that the loop will refine.

## 5. `create-cycle` skill (step b)

**Purpose.** Generate the **project-specific** `docs/task-loop/task-loop.md` playbook from
a generic skeleton + project specifics, and scaffold the rest.

**Process.**
1. Read `proposal.md`. Auto-detect what it can: test command, lint, git hooks (branch
   prefixes, attribution rules, protected master), whether a code skeleton exists.
2. **Interview** the user for the project-specific fills, finalizing fuzzy ones with
   `discuss-with-codex`:
   - the source-of-truth docs `task-loop.md` must reference (proposal + **any others**),
   - domain correctness contracts / invariants (not optional polish),
   - what "tested" means beyond smoke tests (analytic limits, golden values, …),
   - a bootstrap note if the repo has no code yet.
3. Render `task-loop.md` = the **generic cycle skeleton** (§6) + a project-specifics
   section (north-star, referenced docs, contracts, test conventions, branch/hook rules).
4. Scaffold `docs/task-loop/directions.md`, `docs/task-loop/logs/`, ensure `.gitignore`
   covers `.claude/task-loop/` runtime state + `/goal` scratch, and create the
   `loop:in-progress` GitHub label.
5. Commit via branch + PR.

## 6. The generic cycle skeleton (what every `task-loop.md` inherits)

The worker's per-task playbook (generalized from METBG's 11 steps; project specifics
stripped to the create-cycle fills). A worker runs this **once** for its assigned task:

1. **Recover & anchor** — read the issue's `RECOVERY` control events (resume or
   abandon); read `directions.md`; re-read the referenced docs at the current
   `plan_revision`.
2. **Confirm task** — the orchestrator already chose/scoped it; validate scope and the
   `spawned_plan_revision`.
3. **Issue & branch** — confirm issue; branch from fresh master into the worker's **own
   git worktree**; open the `RECOVERY` control-event thread + `NNN_<task>_log.md`.
4. **Rubric** — `goal-rubric` → binary rubric → finalize via a `discuss-with-codex`
   pass → write `NNN_<task>_rubric.md` and post to the issue.
5. **Spec → plan → implement** — `brainstorming` (autonomous: decline user gates → route
   open questions to `discuss-with-codex`) → spec → `writing-plans` → **TDD**. Long
   compute → background; intra-task parallelism → `Workflow`/inline subagents (never a
   sub-team).
6. **Verify** — run every rubric item, capture real output
   (`verification-before-completion`).
7. **Reconcile** — compare results to the plan/proposal. If a fact invalidates a
   hypothesis, post a `PLAN_FINDING` *inbox* event (the orchestrator records the
   corresponding `PLAN_FINDING_RECORDED` control event) + file an issue. **Never edit
   `proposal.md`.**
8. **Doc-update** — `doc-update` affected docs to current truth.
9. **Open PR & review** — commit (clean text, `-F`, explicit paths); open PR with
   `Plan-Revision: N` + task ID; **`discuss-with-codex` adversarial PR review until no
   blocking issues**.
10. **Request merge & hand off** — re-check `plan_revision` validity; post a
    `MERGE_REQUEST` control event (PR head SHA, revision) and **go idle. The worker does
    NOT merge.** If its revision was invalidated at any phase boundary, it marks itself
    `stale_revision_blocked` and shuts down without merging.
11. *(Finalization — set `RECOVERY: complete`, evidence into the log — happens after the
    orchestrator merges; the worker records what it can before handoff.)*

**Generic operating principles** (constant across projects): deliberate-with-codex
instead of asking the user; never let long jobs block (background + `Monitor`/
`ScheduleWakeup`); small increments / one PR; evidence before done; tests first; durable
resumable state; `step-workflow` numbered file naming.

## 7. `run-cycle` skill + orchestrator (step c)

Human entry point. Starts the orchestrator under **built-in `/loop` self-paced** (per the
loop-mechanism conclusion — **not** ralph, **not** a blocking Stop hook), creates the
Agent Team, and runs the state machine. A small `schedule`/`CronCreate` helper
(documented here) sets the stop time by writing `stop-request.json` atomically.

### State machine (each `/loop` turn)
- **acquire/heartbeat lease** in `orchestrator-state.json`; on resume detect a stale lease
  and rebuild fast state from the GitHub append-only log.
- **check `stop-request.json` first** → if set, go to `draining`.
- `dispatching` — read `directions.md` + repo + GitHub; run the **replan barrier** (§8);
  `TaskCreate` ready tasks with dependency edges; spawn **one `cycle-worker` per ready
  task** (capped to frontier width).
- `waiting` — wait on automatic teammate idle notifications.
- `idle` — frontier empty, nothing active, **no** stop signal → long `ScheduleWakeup`/
  `Monitor`; **does not exit** (continuous service).
- `draining` — stop signal observed → no new dispatch; let active workers finish, bounded
  by `drain_deadline_at`; past the deadline, mark overdue workers `orphaned_acknowledged`
  (non-destructive — record worktree/issue/PR pointers; **no abrupt kill**).
- `exiting_pending` → record the pre-exit audit, `ScheduleWakeup` a 60–120 s cooldown.
- `exiting` → re-run the audit from scratch; if still clean, stop rescheduling; else revert
  to `dispatching`/`waiting`.

**Pre-exit audit** (agent-run, recorded with real command outputs): `ready == 0`,
`active == 0`, `blocked == acknowledged`, `unmerged == 0`.

### Merge (orchestrator-only)
On a `MERGE_REQUEST`, the orchestrator performs **one atomic validate-then-act**:
run the **pre-merge event-drain barrier** (§8), re-read `current_plan_revision` + the
task's compatibility + CI/review state, then `gh pr merge --squash --delete-branch
--match-head-commit <validated SHA>`. If invalid → `MERGE_DENIED` + mark task stale + tell
the worker to shut down / rescope. If the orchestrator is dead/draining, nothing merges
(stalled merge ≫ stale merge); the PR + `RECOVERY` persist for resume.

## 8. Coordination & correctness model

(Full rationale in the proposal-ownership conclusion. Invariants:)

### Control protocol (single-sequencer — the correctness core, built first)
There is **one canonical ordered log per project: a single pinned GitHub "control
issue."** The orchestrator is the **only writer** of the ordered log; workers never
assign sequence numbers (GitHub gives comment IDs, not a project-wide ordered stream).

- **Worker inbox events** are *unsequenced* comments on the worker's **own task issue**,
  each a fenced JSON block tagged with a client-generated `uuid`, `task_id`,
  `spawned_plan_revision`, event type (`PLAN_FINDING`, `MERGE_REQUEST`), and (for
  `MERGE_REQUEST`) `pr_head_sha`.
- The orchestrator **ingests** inbox events across task issues and **emits normalized
  `CONTROL_EVENT` comments on the control issue** with a monotonic integer `seq` it alone
  assigns. Control event types are two families:
  - *orchestrator-originated* (no source provenance): `TASK_CREATED` (carries the task's
    `issue_number`), `TASK_DISPATCHED`, `PLAN_REVISION_BUMP` (carries `proposal_sha`),
    `TASK_STALE`, `TASK_REVISION_COMPATIBLE`, `INBOX_SCAN_CHECKPOINT` (carries
    `issue_number` + `through_ts`);
  - *inbox-derived* (carry `source_issue` / `source_comment_id` / `source_comment_ts` /
    `source_uuid`): `MERGE_GRANTED`, `MERGE_DENIED` (answer a `MERGE_REQUEST`),
    `PLAN_FINDING_RECORDED` (records an ingested `PLAN_FINDING`).
- **Idempotency invariant (exactly one):** every ingested inbox `uuid` maps to **exactly
  one source-tagged** control event. *At least one:* answering a `MERGE_REQUEST` with a
  *bare, untagged* `TASK_STALE`/`TASK_REVISION_COMPATIBLE` would drop the `uuid` and cause
  re-ingestion — so a `MERGE_REQUEST` is always answered with `MERGE_GRANTED`/`MERGE_DENIED`
  (`control_log.unacknowledged_uuids` checks this). *At most one:* `replay` raises on a
  duplicate `source_uuid`.
- **Total order = `seq` on the control issue.** A single sequencer means no tie-breaks.
- **Dedupe vs. scan floor are decoupled.** The authoritative idempotency mechanism is
  `seen_source_uuids`, rebuilt from source-tagged events in any order. The per-issue
  **scan floor** (`scan_floor_ts_by_issue`) is a *separate* optimization advanced **only**
  by explicit `INBOX_SCAN_CHECKPOINT{issue_number, through_ts}` events — never by an acked
  comment timestamp. (Acks can arrive out of timestamp order — the pre-merge barrier acks
  findings before merge requests — so `max(acked_ts)` is *not* a valid floor; a crash
  between an out-of-order ack and its earlier-timestamp sibling would skip the sibling.)
  The orchestrator emits a checkpoint through `T` for an issue **only after** every comment
  with `createdAt <= T` on that issue has exactly one source-tagged event; a crash before
  the checkpoint leaves the old floor, so an **inclusive** rescan
  (`comments_at_or_after_watermark`, `createdAt >= floor`) + UUID dedupe recovers safely.
  Timestamps are GitHub canonical UTC `YYYY-MM-DDTHH:MM:SSZ` (no fractional seconds, so
  lexical `>=` is chronological).
- **Replay:** rebuild fast state (dedupe set + per-issue scan floor + task/issue map) by
  reading control-issue events `seq 0..N`. (Snapshot compaction is a later optimization —
  see §15.)
- **Labels are a derived human index only.** The **Agent-Teams mailbox is
  notification-only** (never independent truth), so cold resume reconstructs from GitHub.
- *Schema, idempotency, ordering, watermark, replay, and recovery have unit/integration
  tests — this protocol is implementation Phase 1 (§16), built and tested before any skill
  workflow.*
- **Revision lease**: every task carries `spawned_plan_revision`. Invalidation is scoped
  to the affected subgraph via explicitly declared `depends_on_tasks` /
  `depends_on_hypotheses`; if blast radius is unclear → **broad freeze**.
  (`proposal.md`'s frontmatter records the last roadmap revision *committed to git* — the
  durable narrative, which may lag; the **authoritative live `current_plan_revision`** is
  the GitHub control-event log, cached in `orchestrator-state.json`.)
- **Replan barrier** (before dispatch): ingest findings, bump `plan_revision` on
  invalidation, recompute frontier, halt stale dependent dispatch.
- **Revision materialization** (no revision without a materialized plan): a
  `plan_revision` bump to N is **final only once the orchestrator has merged the
  proposal-update PR for N to `master`** (it is the sole integrator, so this is its own
  fast PR). The replan barrier writes+merges `proposal.md`@N **before dispatching any task
  at N**; the `PLAN_REVISION_BUMP` event carries the proposal commit SHA at N. A worker
  spawned at N therefore anchors to `proposal.md`@`master`, which is guaranteed to read N.
  In-flight workers at N−1 are handled by the revision lease + merge gate.
- **Pre-merge event-drain barrier**: fetch all issue events since the **sync watermark**,
  drain mailbox, **ingest findings before merge requests** in the batch, recompute
  invalidations, advance watermark; deny/hold on sync failure / ambiguity / any
  unclassified plan-affecting finding.
- **Head-SHA-bound merge**: merge only the exact validated SHA.

## 9. `cycle-worker` agent

Subagent definition referenced by `agentType` when the orchestrator spawns a teammate.
- **System prompt:** "Execute exactly one task's cycle by following
  `docs/task-loop/task-loop.md`. Deliberate with `discuss-with-codex` at rubric / open
  design questions / PR review. Never edit `proposal.md`. Never merge — open the PR,
  re-check your `plan_revision`, post `MERGE_REQUEST`, and go idle. Record durable state
  as control events + your `NNN_*` records."
- **Tools:** full dev set (Bash, Read, Edit, Write, git/gh via Bash, Skill, Workflow).
- Note: a teammate ignores the agent def's `skills:`/`mcpServers:` frontmatter but loads
  skills from project/user settings, so it can invoke `discuss-with-codex` etc.

## 10. `discuss-with-codex` usage policy (your item 7)
- **Worker:** rubric finalization (step 4), every open design question (replacing user
  prompts, step 5), adversarial PR review (step 9, every PR).
- **Orchestrator:** task selection / "are these two tasks truly independent?" /
  dependency ordering; resolving conflicting worker outcomes; proposal roadmap changes.

## 11. Durable state & recovery
A fresh agent on clean `master` recovers from: git `master`, the GitHub append-only
control-event log + per-task `RECOVERY`, open PRs, and `docs/task-loop/logs/`. The
orchestrator rebuilds `orchestrator-state.json` (incl. `current_plan_revision` and the
ready/active/blocked sets) from the GitHub log. Ephemeral Agent-Teams state (teammates,
`~/.claude/tasks/`) is **not** relied upon — the orchestrator respawns workers for
still-open tasks. The planning step is idempotent.

## 12. Agent Teams enablement & constraints
- Requires `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` (settings.json) and Claude Code
  ≥ v2.1.32. `run-cycle` checks/documents this and fails fast with guidance if unset.
- Teammates are ephemeral (no `/resume` survival; task list wiped on session end) →
  handled by §11.
- No nested teams → intra-task parallelism via `Workflow`/inline subagents only.
- Higher token cost; one team at a time.

## 13. Marketplace / packaging
- New `task-loop/.claude-plugin/plugin.json` (name `task-loop`, version `0.1.0`).
- Add a `task-loop` entry to root `.claude-plugin/marketplace.json`.
- New `task-loop/README.md` documenting the a→b→c workflow + enablement.
- `problem-solving-cycle` is left unchanged.

## 14. Coverage of the original 8 requirements
1 → `create-cycle` generates `task-loop.md`. 2 → `cycle-worker` agent runs the cycle.
3 → orchestrator does all planning/dispatch via the Agent-Teams dependency DAG.
4 → `run-cycle` = `/loop` self-paced + scheduled drain-on-signal (reinterpreted from
"ralph + max-iterations" per the loop-mechanism conclusion). 5 → `docs/task-loop/logs/`
two files per task. 6 → cycle step 5 uses `brainstorming` + `writing-plans`. 7 → §10.
8 → one teammate per task via Agent Teams.

## 15. Open / deferred (for later, not v1 blockers)
- Merge-queue throughput when many PRs land together.
- Worktree cleanup after orchestrator-merge.
- Control-log **snapshot compaction** (bound replay cost as the log grows).
- **Comment pagination** in `gh_store.read_comments`: a long-running control issue can
  exceed a single `gh issue view --json comments` page; pagination must be handled before
  any real multi-day run, or a long log could be silently truncated (a *correctness* risk,
  separate from snapshot compaction). Phase 2 prerequisite.
- External watchdog (YAGNI v1).

## 16. Implementation phasing (de-risk unproven primitives first)
The riskiest parts are the **experimental Agent-Teams primitives** and the **control
protocol**, not the skill prose. Build bottom-up so a later phase never rests on an
unproven lower one:

- **Phase 0 — primitive spike (throwaway, runnable).** Prove the Claude Code primitive
  contract before building on it. Checks:
  - `run-cycle` can require/enter `/loop` in the intended way.
  - a plugin-packaged `agents/cycle-worker.md` resolves as the teammate `agentType`.
  - the lead can spawn exactly one worker, pass task/revision/issue metadata, and receive
    an idle/completion notification.
  - `ScheduleWakeup` works from the lead inside `/loop`.
  - the stop-signal writer has an actual primitive; if `CronCreate`/`schedule` is
    unavailable/unsuitable, document the fallback (background scheduled shell job).
  - required worker skill dependencies (§2) can be detected, or fail clearly when missing.
  Phase 0 output is a short findings note; if a primitive can't be made to work, the
  design adapts here before any real build.
- **Phase 1 — control protocol** (§8): control issue, UUID inbox events, orchestrator
  sequencer, JSON schema, watermark, replay, idempotency — with tests. Buildable and
  testable **without** Agent Teams (simulate workers by posting inbox comments).
- **Phase 2+ — skills & agent** on top: `specify-aims`, `create-cycle` (+ generated
  `task-loop.md` skeleton), `cycle-worker`, then `run-cycle`'s orchestrator state machine,
  then packaging (plugin.json, marketplace entry, README).
