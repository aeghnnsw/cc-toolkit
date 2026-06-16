# Task-loop harness redesign — Claude × Codex deliberation conclusion

**Date:** 2026-06-15
**Outcome:** Converged after 9 rounds (the final 3 re-tested a major simplification: **two agent types + multiple orchestrators**). Codex's closing position: "no remaining substantive objection — tasks, findings, attempts, and merges all have a DB-backed claim/reconcile path, and no LLM agent holds the irreversible merge credential."
**Topic:** Replace the GitHub-issue-comment single-sequencer event log with a hosted-Postgres (Supabase) coordination store and a pull/claim model, designed so that following the mechanism guarantees correct runs and illegal operations are *structurally impossible*, not merely improbable.

---

## Goal
Design the task-loop control harness so it is (a) a **complete, self-consistent** development loop, (b) **elegant and minimal**, (c) **simple enough that following the mechanism guarantees** the run proceeds as planned, and (d) **structurally incapable of illegal operations**.

---

## The unifying principle (what every round converged on)
**Authority lives in deterministic, non-agent surfaces — the DB procedures, the CLI, GitHub branch protection, and PreToolUse hooks that gate the orchestrator's irreversible calls.** LLM agents supply *judgment and compute*; their irreversible actions (notably `gh pr merge`) are gated by deterministic hooks. Every unit of work (task, finding, attempt, merge) has a **DB-backed claim / lease / reconcile path**, so a disappearing agent never strands the loop.

> **Operator decision (supersedes Codex's merge recommendation).** The orchestrator **merges its own tasks directly** with `gh pr merge` (option **A**), and a **PreToolUse hook** is the deterministic gate: it runs the live DB check (current attempt, no open finding, status, head) and blocks a non-compliant merge, alongside branch-protection required checks (CI + review). Chosen for simplicity over Codex's recommended single-merge-surface (option B). Trade accepted: enforcement is the hook + branch protection rather than a credential boundary; the finding-after-check window is closed by the hook's live check + idempotent reconcile. The "merge surface" descriptions below are therefore superseded by **"orchestrator merges, hook-gated."**

---

## Settled design

### Exactly two agent types
- **Orchestrator** — the **main / general-purpose agent** (a Claude *or* Gemini *or* Codex session) turned into an orchestrator by the **`run-cycle` skill**. **Not** a custom agent. **One per ecosystem** (heterogeneous agents can't share one). Per loop turn, for the tasks **it** dispatched: it dispatches its own cycle-workers; on a worker's `merge_requested` report it **merges the PR** (hook-gated), updates Supabase status, updates the proposal/roadmap, adds follow-up tasks to the DB, and **creates follow-up GitHub issues**; and it claims + resolves findings. One orchestrator bootstraps the proposal/roadmap once.
- **cycle-worker** — the **single** custom agent (`agents/cycle-worker.md`), dispatched by an orchestrator. It: atomically claims the next ready task, self-provisions a worktree + per-attempt branch, runs the project's `task-loop.md`, opens a PR, requests review, marks `merge_requested`, then idles/exits.

The trusted roles raised during the debate (merge-executor, reviewer, materializer) are **NOT agents** — they are deterministic non-agent surfaces.

### Three deterministic non-agent surfaces
1. **Supabase (Postgres)** — the single source of truth for **tasks, findings, attempts, runtime**. Holds: status-transition CHECK/trigger state machines; RLS (a worker may write only its own current attempt + post events); atomic RPCs `claim_task()`, `claim_finding()`, and the global `apply_replan()`.
2. **The `task-loop` CLI** — performs owner-partitioned task reads/writes and the claim operations, and provides the **live pre-merge check** the hook invokes.
3. **A PreToolUse hook on `gh pr merge`** — the deterministic gate for the orchestrator's merge. The orchestrator holds the merge credential, but every merge call is intercepted by the hook, which runs the live DB check in one transaction (current attempt, no open finding, status, head) and blocks the call unless it passes; branch protection independently requires CI + the review check.

Plus **GitHub**: PRs + per-attempt branches, **branch protection with required checks** (CI + an independent review check), and human-mirror issues. Nothing machine-parsed for coordination.

### Coordination model
- **Workers pull/claim** ready tasks atomically (`claim_task`): one task → exactly one owning orchestrator (the one whose worker won the claim). Heterogeneous, cross-machine agents share one queue safely.
- **Readiness is a global SQL predicate** (deps merged + not blocked + …) — no orchestrator "marks ready."
- **Two write classes:**
  - **Execution writes** — *owner-partitioned*: an orchestrator writes only its own dispatched tasks' execution state (status/branch/attempt/docs). No two orchestrators touch the same task's state → no plan divergence, **without** a single-planner lease.
  - **Plan-repair writes** — *global, atomic*: `apply_replan(finding_id, resolution)` is the only path that mutates across owners. In one transaction it marks the finding resolved (idempotent `resolution_id`), stales/supersedes affected tasks **regardless of owner**, creates replacements/follow-ups, and rewrites dependency edges **with a cycle check**.
- **Cross-orchestrator coordination is via DB state + attempt fencing, never agent-to-agent messaging.** When `apply_replan` supersedes a task's attempt, the other orchestrator's in-flight worker is automatically fenced by the attempt-currency guard and simply observes the new state on its next read. An offline/unaware orchestrator cannot stall the others.

### Attempt fencing (cross-system, retained)
A stale heartbeat ≠ a dead worker, and Postgres fences DB rows but not Git refs / GitHub side effects. So: `claim_task` mints a new **attempt_id (lease epoch)** and sets `tasks.current_attempt_id`; reclaiming mints a **newer** attempt and supersedes the prior one (never reusing its branch); workers push **only** to `<branch>-attempt-<attempt_id>`; worker DB writes are gated on `attempt_id == current_attempt_id`. A superseded/zombie worker can touch only its own dead branch.

### Merge path (option A — orchestrator merges, hook-gated)
- The worker opens the PR, marks `merge_requested`, and **reports to its orchestrator**.
- The **orchestrator merges its own task** with `gh pr merge --squash --match-head-commit <head>`. A **PreToolUse hook** intercepts the call and, in one transaction immediately before merge, performs a **live** check (not a stale snapshot): `current_attempt_id` matches, `status='merge_requested'`, **no open `PLAN_FINDING` affecting the task**, head == recorded SHA → allow; else block. **Idempotent head-keyed reconcile** on crash.
- **Branch protection** independently requires CI + the **independent review check** (posted by a CI workflow / Action, **never** by the worker).
- **Result:** the irreversible merge is gated by deterministic code (the hook) + branch protection, not LLM goodwill. The residual (a buggy orchestrator bypassing its own hook, or a finding landing between the hook check and `gh` completing) is closed by the hook's live check + idempotent reconcile — "disciplined-by-hook + reconciled," the operator's chosen trade vs option B's pure credential boundary.

### Findings are claimable work items (liveness)
- `findings.status`: `open → resolving → resolved | escalated`. `claim_finding()` atomically leases the oldest open finding to **any** orchestrator (not just the producer). Stale `resolving` findings become reclaimable. The resolver supplies judgment, then calls `apply_replan`, which enforces **conservation**: every staled/superseded task carries a structured resolution edge — `replaced_by_task_id`, `superseded_by_resolution_id`, or `human_waived`.

### Plan of record & completeness
- **The DB is the source of truth for tasks.** `proposal.md`/roadmap is a **once-initialized human seed**, not bound by a `graph_hash` and not materialized by a separate agent. (This drops the earlier graph_hash/materializer machinery — there is now only one task store, so the "two plans of record" divergence cannot occur.)
- **DAG:** dependency edges are cycle-checked at creation and inside `apply_replan`.
- **Quiescence (two-phase audit) requires:** zero `ready`/`active`/`merge_requested` tasks, zero unmerged PRs, **zero `open` or `resolving` findings**, and every non-merged task carries a structured resolution edge. The loop cannot exit with open findings or stranded work.

### Substrate & setup
- **One shared Supabase project across repos**; each repo self-registers via idempotent `task-loop init` (rows scoped by an auto-derived `project` id). Connection via an **env var** — never a filesystem path.
- Per-repo human setup (accepted, one-time-ish): register the repo, set the env var, and configure branch protection + the merge surface (GitHub App / Edge Function) + the review-check CI workflow.

### Run lifetime
- Each orchestrator runs the `run-cycle` loop; stop via a `runtime` row `stop_at`; graceful drain. Multiple orchestrators run independently and idle/stop on their own.

---

## Key decisions
1. **Two agent types only** (orchestrator via `run-cycle`; cycle-worker). All trusted roles are deterministic non-agent surfaces.
2. **Multiple orchestrators, one per ecosystem**, made safe by **partitioned execution ownership + atomic claim**, not by a single-planner lease.
3. **The orchestrator merges its own tasks directly** (operator decision A), gated by a **PreToolUse hook** (live DB check) + branch protection — not a separate merge surface.
4. **Two write classes:** owner-partitioned execution vs global-atomic `apply_replan`.
5. **Findings are claimable work items** with their own lease/reconcile path and conservation enforcement.
6. **DB is the source of truth for tasks**; proposal is a once-initialized seed; quiescence is finding-aware.
7. **Attempt fencing retained** (per-attempt branches + lease epoch + currency guard) as cross-system safety.

---

## Strongest objections and how each resolved
1. **Heartbeat-only recovery reintroduces illegal ops** → kept attempt lease-epoch + per-attempt branches + DB currency guard.
2. **Same-identity orchestrator merge race** → no agent holds merge creds; single deterministic merge surface + live check + idempotent reconcile.
3. **`merge_intent` as remote control** → the merge surface owns the full gate; a request authorizes nothing.
4. **Review check forgeable by the worker** → independent reviewer (CI workflow / Action) owns the review-check credential; worker only requests review.
5. **Two plans of record (proposal vs DB)** → made the DB the sole task source of truth; proposal is a human seed (dropped graph_hash/materializer).
6. **`blocked-with-reason` silent drop** → structured resolution edges required; quiescence enforces them.
7. **Raw merge creds make the preflight non-authoritative** → moved the merge credential into a non-agent surface doing a live check (no raw-`gh` bypass).
8. **Owner-partitioning breaks global plan repair** → global atomic `apply_replan` RPC (cross-owner, cycle-checked, conservation-enforced).
9. **Findings lacked a claim/recovery path** → findings are claimable, leased, reclaimable; quiescence requires zero open/resolving findings.

---

## Residual considerations (accepted costs / implementation caveats)
- **The PreToolUse merge hook** is the deterministic gate for the orchestrator's `gh pr merge` and must be installed wherever an orchestrator runs. This is the operator's chosen enforcement (A) in place of Codex's separate merge surface (B); it trades a hard credential boundary for a hook + branch-protection gate.
- **GitHub-Actions credential isolation** must be correct: PR-controlled head code must never obtain the review-check-writing credential (no `pull_request_target` secret leakage).
- **Hosted-service dependency:** the loop stalls safely if Supabase/network is unavailable and resumes on recovery. Accepted given the cross-machine, multi-agent requirement.
- **Per-repo human setup** (register, env var, branch protection + merge surface + review workflow) is front-loaded; `init` automates the schema.

---

## How it ended
Converged after 9 rounds. Every objection was a genuine hit and was adopted; the resulting model is internally consistent. The two-agent simplification *survived* adversarial re-testing because the safety/coherence guarantees were pushed out of the agents and into deterministic surfaces — and because every kind of work (tasks, findings, attempts, merges) was given a uniform DB-backed claim/reconcile path.

---

## Addendum (2026-06-15): FINAL lifecycle — operator-finalized (monotone task, findings in the PR)

This is the **operator-finalized** model and **supersedes all earlier addenda.** Two deliberate simplifications override the Codex-converged version, trading machine-enforcement for orchestrator-judgment + hooks (the operator's stated philosophy: "the orchestrator decides all operations; hooks regulate it").

**TASK — monotone, three states, NO back-edge:**
- `open → working → closed`. **`working` always leads to `closed`** — the orchestrator reads the worker's PR and closes the task.
- **"interrupted / stuck" is handled at the ATTEMPT level, not as a task back-edge:** a dead `live` attempt is abandoned and a new `live` attempt is minted; the task stays `working`.
- `claimable` = `open ∧ all deps satisfied`; `blocked` is **purely derived** (`open ∧ unmet dependency`).
- The orchestrator is the **sole dispatcher / decider / merger** and the only writer of `closed`.

**Closing a task (orchestrator reads the PR):**
- `success` → merge the PR, close the task, unblock dependents, discover/add new tasks + open issues.
- `failed/invalid` → close the task (PR not merged / kept as the log), adjust list + issues.
- `blocked` → **close the original task AND create a NEW task** with the blocking dependency (create the blocker first if needed), redirecting dependents to the new task. The original **always closes** — everything is unified under `working → closed`.

**FINDINGS — written in the PR, NOT a database entity:** the worker writes its findings (with the rubric + results) **in the PR / study log** and just reports "done." There is **no finding table and nothing structured returned**; the orchestrator **reads the PR** to decide the follow-up. *(This overrides the earlier first-class-finding requirement.)*

**ATTEMPTS** remain the flat ledger (`live | merged | abandoned` + `superseded_by_attempt_id` + `artifacts_cleaned_at`, marker-reconciled vs GitHub) — fencing + artifact accounting + the interrupted/stuck recovery path. **Quiescence** = no open/working tasks ∧ no `live` attempts ∧ every `abandoned` attempt's artifacts cleaned ∧ a GitHub marker scan finds no orphan task-loop PR/branch.

**The accepted trade:** with findings as PR prose (not durable rows), cross-task invalidation (task A's PR reveals task B is invalid) is handled by **orchestrator judgment when it reads the PR + the PreToolUse merge hook** — *not* a machine-enforced DB guard. Codex argued for first-class findings to make that *structurally impossible*; the operator chose the simpler model, accepting orchestrator-judgment + hooks as the enforcement. **Net: one monotone task lifecycle (`open → working → closed`) + findings-in-PR + a flat attempt ledger.**
