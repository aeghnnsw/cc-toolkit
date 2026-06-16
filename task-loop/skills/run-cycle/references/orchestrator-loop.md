# Orchestrator loop — the per-tick pass (run-cycle detail)

The orchestrator is the **sole dispatcher, decider, merger, and editor of `proposal.md`**, and it
holds **no durable state of its own**: every tick re-derives everything from the **task DB** (via the
`task-loop` CLI), **GitHub** (via `gh`), and the git-tracked **`docs/task-loop/`** files. Two
orchestrators reading the same DB + GitHub + `directions.md` take the same action. **Recovery is just
the next tick.** This design was pressure-tested with Codex —
`docs/superpowers/specs/2026-06-15-task-loop-orchestrator-pass-conclusion.md`.

## Where state lives

- **Task DB (Supabase, via the CLI).** `task-loop status` → each task's `seq`, `status`
  (`open`/`working`/`closed`), `title`, `deps`, `issue`. `task-loop claim` is the atomic dispatch
  primitive (`open → working`, `FOR UPDATE SKIP LOCKED`).
- **GitHub (via `gh`).** One issue per task; PRs (the work + the study-log record); branch protection
  (the merge gate).
- **Git-tracked files.** `proposal.md` (the roadmap the orchestrator reconciles), `directions.md`
  (human steering), `docs/task-loop/logs/<seq>_<task>.md` (merged study-logs = the durable evidence set).
- **In-session only (not durable).** Which teammate this orchestrator spawned for which task — the
  *only* basis for auto-reset (case (a) below). A fresh session has none, which is correct.

## Control plane (set up once per invocation)

`/run-cycle` mints a fresh **`run_generation`** (`date -u +%s`), best-effort cancels stale
`task-loop-<project>-*` scheduled jobs, ensures the cycle-worker **team** exists, then creates:

- **Loop A** — a fixed-interval loop (default 15 min, `task-loop-<project>-<gen>-A`) running the pass
  below, with `stop_at` + `run_generation` embedded in its prompt.
- **Loop B** — a one-time job at `stop_at` (`…-<gen>-B`) that **wakes Loop A to run a tick promptly**;
  **non-destructive** (a stale fire just makes Loop A run a tick that re-checks the current `stop_at`).

Loop A is the **sole stop authority**: a tick stops the run (cancels its own `-A`/`-B` jobs) once the
board is drained and **either** the proposal's **Success criteria are met** (goal achieved — the
natural finish, step 7) **or** `now ≥ stop_at` (the time bound). Because every job is generation-named,
a leftover job from an earlier run can only touch its own generation — never a newer run's Loop A.

## The pass

### 0. Read state + stop check
`task-loop status`; list open PRs/issues; read `directions.md`. If `now ≥ stop_at`, enter **draining**:
skip dispatch (step 6), but still run steps 2–5 to finish in-flight work; when no `working` task
remains, cancel the `-A`/`-B` jobs and stop.

### 1. Honor steering (first, before any irreversible action)
`directions.md` is highest-priority and free-form; interpret it and apply its constraints **this tick,
before merging**: pause/serialize dispatch, freeze merges, "do not merge PR #X", task priorities,
explicit blockers, explicit `task-loop reset <seq>` *surfacing* (the human still runs reset; see
§Reset). Steering is also an **exogenous trigger** — a tick does real work whenever directions OR
findings introduce change, not only when a worker finished.

### 2. Liveness / progress
For each teammate **you spawned this session**, confirm it is alive and ask it for one progress line
(skip if none dispatched). This is advisory — it decides *wait vs. reset* for a worker you own (see
§Reset); it is never the authority for touching a task you did not spawn.

### 3. Merge / classify every working task's PR (only PRs step 1 allows)
For each `working` task, find its PR (worker handoff this session, else
`gh pr list --search "<issue>" --state all`; the PR's `Refs #<issue>` links it). **Classify it this
tick** and act — the worker has idled after opening the PR, so it will not repair a failing one:

- **Mergeable** (required CI green + independent review check green **and** GitHub's merge-state is
  clean — `mergeable`, no conflict, not behind a required up-to-date base) → merge **atomically**:
  `gh pr merge <N> --squash --match-head-commit <validated head SHA>` (re-checks at the bound head; if
  the head moved or the merge is rejected for a **transient** reason it's no longer mergeable →
  re-evaluate next tick — this defeats a green→red flap between classify and merge; a **deterministic**
  rejection is merge-blocked, below). Then read the study log
  (`docs/task-loop/logs/<seq>_<task>.md` + the body **Outcome**) and apply it:
  - **success** → `gh issue close <issue>`; `task-loop close <seq>` (its **Findings** feed step 5).
  - **failed** → `task-loop close <seq>` (the merged PR + record stay as the account).
  - **blocked** → `task-loop close <seq>` (the remaining work becomes a new task in step 5; the issue
    stays **open**, re-linked there).
  Then **reap the idle teammate** (`TaskStop` the worker you spawned for that seq).
- **Gate-failed / merge-blocked** (a required check red/failed; review failed; **or** GitHub reports a
  merge conflict / behind-base / blocked, **or** an atomic merge deterministically rejects for any
  reason other than a head change / transient gate race) → **do not close-and-recreate** (that spins —
  see §Reset/closure). Idempotently label the issue `needs-human: <reason>` (`merge-blocked` for the
  merge-state cases), **surface it once**, and **leave the task `working`** — the task + its issue are
  the durable escalation record, and step 5's "never duplicate an issue that has a task" prevents
  re-creation. Retry is human-only (fix CI / rebase / clear the label / `task-loop reset <seq>`).
- **Stuck** — required checks pending **past the bound** (computed from the PR head-SHA + the
  required-check-context timestamps; a required context that never posts a check-run counts as stuck) →
  same handling (label `needs-human`, surface once, leave the task).
- **Genuinely pending** (required checks still running within the bound) → leave for next tick (CI
  completing *is* real progress).
- **No PR** → liveness applies (§Reset); never launder a merge done by someone else (*Merge gate*).

Every task funnels `working → closed`, or is held as a surfaced `needs-human` — nothing is silently
dropped, and **nothing failed is auto-recreated**.

### 4. Findings → proposal (reconcile sweep, NOT a patch)
If merged findings change the roadmap / plan / milestones, **recompute** the affected `proposal.md`
sections from **(current default-branch `proposal.md`) + (the complete set of merged study-logs not yet
reflected in it)** — never one orchestrator's stale local patch. Edit on a branch, PR it, and merge it
(you are the sole editor). **Merge only if the PR's base is the current default**; if default moved,
**discard and regenerate**. Carry an "incorporated through task `<seq>`" marker in `proposal.md` so
"not yet reflected" is cheap. Skip this step entirely on ticks with no plan-affecting finding (the
common case). This makes the update convergent even under concurrent orchestrators — no lock.

### 5. Materialize tasks (idempotent) — the goal-driver
This step is **what drives the run toward the Success criteria**: while the goal is unmet, it must keep
the board non-empty. From the freshly-reconciled `proposal.md` + merged findings + `directions.md`,
ensure a task exists for each unit of work that should:
- the proposal's **planned stages not yet turned into tasks** — this is both the initial **seed** on an
  empty board (tick 1) and the **ongoing decomposition** of the roadmap toward the goal;
- discovered **blockers** and **blocked re-creation**
  (`task-loop add "<remaining>" --dep <blocker-seq> --issue <issue>`, re-linking the blocked issue);
- **direction-instructed** and **finding-unlocked** tasks driving the goal.

For each: open a new issue or **adopt** an existing one (reuse an issue carrying a task marker — never
duplicate), then `task-loop add "<title>" --issue <n> [--dep <seq>…]`. Only add what's missing
(`task-loop status` shows what exists). Use `dev-skills:discuss-with-codex` for non-obvious
decomposition or dependency ordering. **Invariant:** if the Success criteria are unmet, this step
either adds the next task(s) or determines the remaining gap needs a human/external input (→ step 7
escalates). It never leaves the board empty while the goal is reachable.

### 6. Dispatch (skip if draining)
While within your **soft capacity** (you decide; not prescribed):
- `task-loop claim` → atomically flips the next ready task (`open` + every dep `closed`) to `working`
  and returns it, or `none`. This is the **only** dispatch lock — concurrent orchestrators can never
  double-claim.
- The claimed task already has an `issue` (paired in step 5); pick a branch (e.g. `tl/<seq>`, honoring
  any repo branch-prefix hook).
- **Spawn one `cycle-worker` teammate** (ask for it by agent type) with: `seq`, `title`, `issue`, and
  the branch. **Record the teammate id against the seq** — it is the basis for liveness (§2) and reap
  (§3).
Stop when `claim` returns `none` or you reach capacity (the rest win a seat on a later tick).

### 7. Goal check / terminate (close the loop on the GOAL)
Evaluate the proposal's **Success criteria** against the repo — run them (commands/tests/artifacts,
`superpowers:verification-before-completion`); don't infer from "tasks closed".

**Real-progress predicate.** A `working` task counts as *progress* only if (its owned worker is alive
and advancing pre-PR) **or** (its PR is mergeable now) **or** (its PR is genuinely pending within the
bound). A gate-failed / stuck / `needs-human` task is **not** progress.

- **Criteria met** → **done**: dispatch nothing, let real-progress work drain, cancel the `-A`/`-B`
  jobs, stop. (The natural finish; `stop_at` is only the time bound.)
- **Unmet, and ≥1 real-progress task or a claimable task exists** → continue; a future tick drives it.
- **Unmet, and no real-progress task and nothing claimable** (every remaining unit is
  `needs-human`/stuck, or the board is empty, or a dep-deadlock) → the loop **cannot progress on its
  own**. Before idling, **guarantee a durable, surfaced blocker exists**:
  - a per-unit gap is already a `needs-human`-labeled issue (step 3); but
  - a **planning gap** — board empty / dep-deadlock / criteria stricter than any planned task — has
    **no** task, so create/update a **proposal-level** issue `needs-human: proposal-unmet-no-planned-work`
    (idempotent, linked to the proposal) **first**.
  Only then idle in this explicit "asked for help" state. **Never idle on an unmet goal without a
  durable surfaced artifact** — otherwise a planning failure is a silent stall.

**Drain / `stop_at`:** draining waits only for **real-progress** working tasks; gate-failed / stuck /
`needs-human` tasks never block it, so `stop_at` always fires.

This is the closure guarantee: nothing failed is auto-recreated (no spin), the real-progress predicate
stops a stuck PR from masking as progress, and every "can't-progress + unmet" state leaves a durable
surfaced blocker (per-unit *or* proposal-level) — so the loop always advances the goal, finishes it, or
has *visibly* asked for help, and it always terminates.

## Reset rule (the central invariant)

`claim` protects `open → working` but **not** `working → open`. A PR is a durable artifact (merge is
safe for any orchestrator); a PR-absent `working` task is ambiguous — without an ownership/liveness
marker you cannot distinguish "alive but pre-PR" from "dead". So a `working`-no-PR task is reset **only
with positive knowledge that no live worker owns it**, true in exactly two cases:

- **(a) In-session observed death** — you spawned that teammate this session and saw it die /
  finish-without-PR → `task-loop reset <seq>` (then it becomes claimable again next tick). On the
  *same* tick, delete the stale remote branch (`git push origin --delete <branch>`) so re-dispatch
  starts clean.
- **(b) Human direct CLI** — the operator runs `task-loop reset <seq>` out-of-band; only the human
  knows whether another orchestrator is live.

A **cold / fresh / foreign** tick **never** auto-resets an opaque `working`-no-PR task. It **surfaces**
it instead ("`012` looks orphaned; if no orchestrator is live, run `task-loop reset 012`"), and moves
on (it still merges PR-present tasks and dispatches claimable). `directions.md` does **not** trigger
reset — a stale `reset 012` line would re-fire and kill a new live worker.

**Consequence (honest):** concurrent multi-orchestrator operation loses *automatic* recovery of pre-PR
orphans (a human `reset` handles the rare stuck one). Single-orchestrator — including sequential
cross-machine (stop here, start there; teammates die with their session) — keeps full auto-recovery,
because the spawning session is the only one that ever has a live teammate to observe.

## Merge gate

Before merging, confirm the required **CI** checks are green, the **independent review check** is
green, **GitHub's merge-state is clean** (no conflict, not behind a required up-to-date base), and the
study-log **Outcome** is present and acceptable. Merge is **head-SHA-atomic**:
`gh pr merge <N> --squash --match-head-commit <the validated head SHA>` — so a PR that flipped red or
gained commits between classification and merge is **rejected**, not merged stale. A **transient**
rejection (head moved / gate race) → re-evaluate next tick; a **deterministic** rejection (conflict /
behind-base / blocked) → classify `needs-human: merge-blocked` (§3), not an endless retry. The orchestrator is the **sole merger** and makes the
task-specific call ("is this outcome mergeable?") as it reads the PR. **Branch protection** (required
CI + a review check posted by a CI workflow, **never** the worker) is the structural backstop no merge
can bypass; a task-loop-specific merge hook is **not** part of this harness. If a task-loop PR was
somehow merged by someone else, treat it as already-integrated and just apply the outcome — don't
re-merge.

## Issues ↔ tasks

Every task is paired with a GitHub issue at **creation** (create or adopt; stored in `tasks.issue`).
The worker's PR uses `Refs #<issue>` — links, never auto-closes. On **success** the orchestrator closes
the issue; on **blocked** it re-links the issue to the new task and leaves it open; on **failed** it
decides. Close-vs-keep is always the orchestrator's judgment.

## Recovery = the next tick

There is no resume path. A fresh orchestrator recreates the team, reads `task-loop status` + GitHub +
`directions.md`, and runs a normal tick: PR-present `working` tasks are integrated; PR-absent ones are
**held and surfaced** (per §Reset), not blindly reset. The only thing a cold start won't auto-do is
reset opaque pre-PR orphans — which requires the human's operational knowledge anyway.

## Multiple orchestrators

One per ecosystem (Claude / Gemini / Codex) may run with **no coordination beyond `task-loop claim`** —
the atomic claim guarantees single-flight dispatch, any orchestrator may merge any ready PR, and the
proposal reconcile-sweep (§4) is convergent. The single shared mutable surface they must respect is the
reset rule: a foreign orchestrator never resets an opaque `working` task it doesn't own.

## Deliberate with Codex

Use `dev-skills:discuss-with-codex` for the genuinely ambiguous calls: task decomposition / dependency
ordering during materialization (§5), whether a finding warrants a roadmap change (§4), and conflicting
or surprising outcomes. Keep the loop mechanical; reserve deliberation for judgment.
