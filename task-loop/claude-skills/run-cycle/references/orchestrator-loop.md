# Orchestrator loop — the per-tick pass (run-cycle detail)

The orchestrator is the **sole dispatcher, decider, merger, and editor of `proposal.md`**, and it
holds **no durable state of its own**: every tick re-derives everything from the **task DB** (via the
`task-loop` CLI), **GitHub** (via `gh`), and the git-tracked **`docs/task-loop/`** files. Two
orchestrators reading the same DB + GitHub + `directions.md` take the same action. **Recovery is just
the next tick.** It is also **relentless**: short of the time bound it **never gives up on the goal** —
every failed / blocked / stuck attempt is *diagnosed* and *re-attacked* with a materially-different,
AIM-aligned strategy (§3/§5/§7), never surrendered, idled, or redefined into an easier goal.

## Where state lives

- **Task DB (Supabase, via the CLI).** `task-loop status` → each task's `seq`, `status`
  (`open`/`working`/`closed`), `title`, `deps`, `issue`. `task-loop claim` is the atomic dispatch
  primitive (`open → working`, `FOR UPDATE SKIP LOCKED`).
- **GitHub (via `gh`).** One issue **per unit of work** — the *persistent identity*; each **attempt**
  at that unit is one task linked via `tasks.issue`, and the attempt's PR + study log are the durable
  **attempt history** the orchestrator reads to diagnose a failure and avoid repeating it. Branch
  protection is the merge gate.
- **Git-tracked files.** `proposal.md` (the roadmap the orchestrator reconciles), `directions.md`
  (human steering), `docs/task-loop/logs/<seq>_<task>.md` (merged study-logs = the durable evidence set).
- **In-session only (not durable).** Which teammate this orchestrator spawned for which task — the
  basis for *in-session* reset (case (a)). A fresh session has none; it recovers opaque orphans via the
  cold-start reclaim (case (c)) instead.

## Control plane (set up once per invocation)

`/run-cycle` mints a fresh **`run_generation`** (`date -u +%s`), best-effort cancels stale
`task-loop-<project>-*` scheduled jobs, ensures the cycle-worker **team** exists, then creates Loop A
and Loop B. Loop C is created only when the stop transition fires:

- **Loop A** — a fixed-interval loop (default 15 min, `task-loop-<project>-<gen>-A`) running the pass
  below, with `stop_at` + `run_generation` embedded in its prompt. Before `stop_at`, it runs the full
  pass. At/after `stop_at`, it runs drain-only and must not cancel the generation before the Loop B/C
  transition exists.
- **Loop B** — a one-time job at `stop_at` (`...-<gen>-B`) that is the **stop transition**. It validates
  its generation from schedule names: if a newer `task-loop-<project>-<newer-gen>-*` job exists, it
  no-ops/cancels itself. Otherwise it creates or ensures Loop C and may run/wake one drain tick. It
  never dispatches, never materializes re-attacks, and never force-stops live work.
- **Loop C** — a recurring drain monitor (default ~30 min, `...-<gen>-C`) created by Loop B. It runs the
  drain subset until no positively live in-session worker/monitored detached job remains for this
  generation and no PR-present `working` task still needs merge/classification; then it cancels
  `-A`/`-B`/`-C` for the generation and stops.

Because every job is generation-named, a leftover job from an earlier run can only touch its own
generation. Generation checks use schedule names only — no DB cell, stored handle, or local runtime
file.

## The pass

### 0. Read state + phase check
`task-loop status`; list open PRs/issues; read `directions.md`. If `now ≥ stop_at`, enter
**drain-only**: skip **materialize re-attacks (step 5)** and **dispatch (step 6)** — no new starts —
but still run steps 1–4 (steering, liveness, **merge/classify** landed in-flight PRs, reconcile).

Loop B is the normal creator of Loop C. If a Loop A tick happens after `stop_at` before Loop B has
installed Loop C, it must not cancel the generation; it either leaves the generation alive for Loop B or
best-effort ensures Loop C if Loop B is clearly absent/stale. Loop C self-closes only after:

- no positively live in-session worker or monitored detached job remains for this generation; and
- no PR-present `working` task still needs merge/classification.

Opaque `working`-no-PR tasks without positive live ownership follow the Reset rule. They do not block
Loop C forever; they are reset, surfaced, or left as recoverable state according to that rule.

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
tick** and act — the worker has idled after opening the PR, so it will not repair a failing one. A
non-mergeable attempt is **never a dead end and never a reason to idle**: it is diagnosed and
re-attacked (step 5).

Read the study-log **Outcome** *before* deciding — broken work is never merged just because its gate is green.

- **`success` & mergeable** (study-log **Outcome: success** *and* required CI + review green *and*
  GitHub merge-state clean — `mergeable`, no conflict, not behind a required up-to-date base) → merge
  **atomically**: `gh pr merge <N> --squash --match-head-commit <validated head SHA>` (re-checks at the
  bound head; if the head moved or the merge is rejected for a **transient** reason → re-evaluate next
  tick, defeating a green→red flap). Then `gh issue close <issue>`; `task-loop close <seq>` (its
  **Findings** feed step 5); **reap the idle teammate** (`TaskStop` the worker you spawned for that seq).
- **`blocked`** (Outcome: blocked) → `task-loop close <seq>`; on an active tick, step 5 recreates the
  remaining work as a `--dep` task. In drain-only mode, defer recreation to the next active run. The
  issue stays **open**, re-linked there → reap. (Merge the partial PR only if it is independently
  valuable — your call; otherwise `gh pr close <N>` as the record.)
- **`success` but behind base only** (green, no conflict, just behind a required up-to-date base) → run
  **`gh pr update-branch <N>`** — a *mechanical base-sync the orchestrator owns* (not task code) → CI
  re-runs → merge next tick. The cheapest re-attack: no new task.
- **`failed` / gate-failed / stuck / merge-conflict** (Outcome: **failed**; **or** a success-declared PR
  whose required check is red/failed, review failed, has a genuine conflict / deterministic merge
  rejection, or is pending **past the bound** / never posts) → **do not idle, do not surface-and-wait,
  do not merge broken work.** **Diagnose** the failure (study log + CI logs + the diff) and re-attack:
  close this attempt — `gh pr close <N>` (it stays as the record) + `task-loop close <seq>` — and let
  **step 5 materialize the *next* attempt against the same issue** on the next active tick with a
  **materially-different, AIM-aligned** strategy, *escalating the class of approach* if the same
  obstacle has recurred. In drain-only mode, defer materialization to the next active run rather than
  starting a new attempt after `stop_at`.
  (Recreation is safe **because** it is diagnosed escalation, never blind repetition — and `stop_at`
  bounds it; this reverses the prior surface-and-wait rule.)
- **Genuinely pending** (required checks still running within the **CI bound** — a *configurable max
  age of the PR head commit* for required checks to post and finish, default ~30 min; past it, or a
  required context that never posts a check-run, the PR is **stuck**, above) → leave for next tick.
- **No PR** → liveness applies (§Reset); never launder a merge done by someone else (*Merge gate*).

Every task funnels `working → closed` (merged on success, else closed-as-attempt with its **work
re-materialized** in step 5 on an active tick or deferred from drain-only to the next active run) —
nothing is silently dropped, and **no difficulty is ever abandoned short of the goal.**

### 4. Findings → proposal (reconcile sweep, NOT a patch)
If merged findings change the roadmap / plan / milestones, **recompute** the affected `proposal.md`
sections from **(current default-branch `proposal.md`) + (the complete set of merged study-logs not yet
reflected in it)** — never one orchestrator's stale local patch. Edit on a branch, PR it, and merge it
(you are the sole editor). **Merge only if the PR's base is the current default**; if default moved,
**discard and regenerate**. Carry an "incorporated through task `<seq>`" marker in `proposal.md` so
"not yet reflected" is cheap. Skip this step entirely on ticks with no plan-affecting finding (the
common case). This makes the update convergent even under concurrent orchestrators — no lock.

### 5. Materialize tasks (idempotent) — the goal-driver that never gives up
Skip this step entirely in drain-only mode; `stop_at` forbids new starts. Drain-deferred blocked or
failed attempts stay recoverable through the open GitHub issue and the PR attempt history, and the next
active run materializes the next attempt here.

This step keeps the board carrying the **next real work toward the Success criteria**; while the goal
is unmet it is **never** allowed to go empty. From the reconciled `proposal.md` + merged findings +
`directions.md` + the **attempts §3 just closed**, ensure a task exists for each unit that should:
- the proposal's **planned stages not yet turned into tasks** — the initial **seed** (tick 1) and the
  **ongoing decomposition** of the roadmap; seed the **riskiest-hypothesis / critical-path** work too —
  don't avoid the heavy lifting in favour of easy wins (it must be *on the board*, not deferred);
- **discovered blockers** and **blocked re-creation**
  (`task-loop add "<remaining>" --dep <blocker-seq> --issue <issue>`, re-linking the blocked issue);
- **re-attacks** — for every attempt §3 closed non-mergeable, materialize the **next attempt against
  the same issue**. The unit's **attempt history is durably derivable** (not semantic): every PR —
  open *and closed* — that `Refs #<issue>` is one prior attempt (`gh pr list --search "<issue>"
  --state all`), and its study log records what was tried and why it failed. Read that history, then
  **diagnose with `dev-skills:discuss-with-codex`** — *what failed, what is still untried* — codex
  pushing "you have not exhausted this; what else?" Add a task whose strategy is **materially different
  from every prior attempt on that issue**; if the **same obstacle recurs across attempts**, **escalate
  the class of approach** — decompose differently, attack an orthogonal sub-problem, or change technique
  — **never re-file the same wall**. (Because the issue is the stable identity and its PR history is the
  attempt ledger, a re-attack is never mistaken for a fresh unit — the escalation always has the full
  record to act on.)
- **drain-deferred re-attacks** — open task-loop issues whose latest task/PR attempt closed
  non-successfully after `stop_at` and that currently have no open/working task.
- **direction-instructed** and **finding-unlocked** tasks driving the goal.

**AIM-fidelity (the other half of the constraint).** Every task this step creates must serve the
proposal's **Success criteria**. Pressure-test non-obvious decomposition *and* every re-attack with
`discuss-with-codex` on a second axis — *does this still serve the AIM, or is it drift to an easier
adjacent goal?* Keep only AIM-aligned work; the Specific Aims zone is never edited here.

For each: open a new issue or **adopt** an existing one (reuse an issue carrying a task marker — never
duplicate), then `task-loop add "<title>" --issue <n> [--dep <seq>…]`. Only add what's missing
(`task-loop status` shows what exists). **Invariant:** while the Success criteria are unmet this step
**always** produces the next work — there is **no give-up exit**; only goal-met or `stop_at` ends the
run (§7).

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

### 7. Goal check / terminate (close the loop on the GOAL, never on difficulty)
Evaluate the proposal's **Success criteria** against the repo — **run them** (commands/tests/artifacts,
`superpowers:verification-before-completion`); don't infer from "tasks closed".

- **Criteria met** → **done**: dispatch nothing. If observable in-flight workers or PR-present working
  tasks remain, enter the same drain-only behavior and stop when the Loop C self-close condition holds;
  otherwise cancel the generation's jobs and stop. (The natural finish.)
- **Criteria unmet** → **always continue.** §5 guarantees the board carries the next diagnosed,
  AIM-aligned work (re-attacks, decomposition, blockers), so the loop keeps driving. **There is no
  exhaustion terminal and no idle-on-difficulty** — a non-mergeable attempt is diagnosed and
  re-attacked, not surrendered; a recurring obstacle triggers an *escalation* (§5), not a stop. The
  **only** thing that ends an unmet run is **`stop_at`** (the time bound, §0).

**Non-blocking human note (steering, never a wait).** If repeated escalations converge on something
genuinely outside the loop's reach (an external dependency, missing access, an apparent AIM/criteria
contradiction), record a **non-blocking note** — a labeled issue / proposal note the human can act on
via `directions.md` *asynchronously* — and **keep attacking other angles toward the goal**. Never idle
waiting for a reply; never redefine the goal into something easier. Humans steer *direction*; the loop
never stops *trying*.

**Drain / `stop_at`:** at `now ≥ stop_at`, the run stops dispatching and re-attacking. Loop B installs
Loop C, and Loop C keeps the same live session around to process observable in-flight work:

- keep checking positively live workers you spawned this session and any monitored detached jobs they
  reported;
- merge/classify PR-present `working` tasks as they land;
- run proposal reconciliation for merged findings;
- skip materialization and dispatch.

Loop C self-closes when no positively live in-flight worker/monitored job remains and no PR-present
`working` task needs merge/classification. Opaque `working`-no-PR rows without positive live ownership
never become hidden blockers: apply the Reset rule if you have positive no-live-owner knowledge, surface
them under declared multi-orchestrator ambiguity, or leave them as recoverable state for the next run.
If the session dies during Loop C, recovery is unchanged: the next `/run-cycle` re-derives from DB +
GitHub and reclaims/surfaces according to the Reset rule.

This is the closure guarantee, reframed for live-through workers. **`stop_at` bounds new starts, not
post-stop observation of work already launched.** **Goal progress** rests on §5 always materializing the
next diagnosed, AIM-aligned work while active and the goal is unmet. **Drain progress** rests on positive
liveness and PR artifacts: Loop C waits only for work it can observe as live or PR-present, never for
opaque no-PR rows with no live owner evidence. **Non-spin** is not a hard invariant but an
**adversarially-enforced bias**: each re-attack reads the unit's full (derivable) attempt history and is
pushed by `discuss-with-codex` to be materially different and escalate — so the active-run budget is
spent exploring, not blindly repeating. The loop therefore **advances the goal, finishes it, or reaches
`stop_at` having genuinely kept trying, then drains observable in-flight work without starting more.**

## Reset rule (the central invariant)

`claim` protects `open → working` but **not** `working → open`. A PR is a durable artifact (merge is
safe for any orchestrator); a PR-absent `working` task is ambiguous — without an ownership/liveness
marker you cannot distinguish "alive but pre-PR" from "dead". So a `working`-no-PR task is reset **only
with positive knowledge that no live worker owns it** — true in three cases:

- **(a) In-session observed death** — you spawned that teammate this session and saw it die /
  finish-without-PR → `task-loop reset <seq>` (claimable again next tick). On the *same* tick, delete
  the stale remote branch (`git push origin --delete <branch>`) so re-dispatch starts clean.
- **(b) Human direct CLI** — the operator runs `task-loop reset <seq>` out-of-band.
- **(c) Single-orchestrator cold start** — on a fresh session in **single-orchestrator operation**,
  **every** opaque `working`-no-PR task is safely reclaimable: each worker from a prior session died
  **with** that session, so no live worker can own one. Reset and re-attack them (deleting any stale
  remote branch first). This is the autonomous recovery that keeps the loop from **ever waiting on a
  human** after a crash / restart. Single-orchestrator is an **operator deployment declaration** (the
  harness's default mode — the operator controls how many orchestrators run), *not* a runtime
  detection. Accidental concurrency (running two while declaring single) is operator error and degrades
  to **bounded waste** — a reset may clobber a peer's `tl/<seq>` branch, so that unit is simply
  re-attacked — never unrecoverable loss.

**Only under *declared* multi-orchestrator operation** (the operator runs more than one orchestrator —
declared via `directions.md` / the invocation) does a tick refuse to reclaim an opaque `working`-no-PR
task it didn't spawn: a concurrent peer's worker may be live **and** share the `tl/<seq>` branch, so an
erroneous reset would clobber it. It **surfaces** the task instead ("`012` looks orphaned; if no
orchestrator is live, run `task-loop reset 012`") and moves on (still merging PR-present tasks and
dispatching claimable). `directions.md` never *triggers* a reset — a stale `reset 012` line would
re-fire and kill a live worker.

**Consequence (honest):** the default **single-orchestrator** mode — including sequential cross-machine
and crash / restart (teammates die with their session) — **always** reclaims pre-PR orphans
autonomously and never waits on a human. Only **declared concurrent multi-orchestrator** operation
trades that for a human reset *or* a tolerated duplicate attempt (bounded waste — the issue is the unit
identity, and at most one attempt merges).

## Merge gate

Before merging, confirm the required **CI** checks are green, the **independent review check** is
green, **GitHub's merge-state is clean** (no conflict, not behind a required up-to-date base), and the
study-log **Outcome** is present and acceptable. Merge is **head-SHA-atomic**:
`gh pr merge <N> --squash --match-head-commit <the validated head SHA>` — so a PR that flipped red or
gained commits between classification and merge is **rejected**, not merged stale. A **transient**
rejection (head moved / gate race) → re-evaluate next tick; a **deterministic** rejection → re-attack
via §3/§5 (**behind base** → `gh pr update-branch`; **conflict / other** → diagnose + a
materially-different next attempt), **never an endless identical retry and never a human-wait branch**.
The orchestrator is the **sole merger** and makes the task-specific call ("is this outcome mergeable?")
as it reads the PR. **Branch protection** (required
CI + a review check posted by a CI workflow, **never** the worker) is the structural backstop no merge
can bypass; a task-loop-specific merge hook is **not** part of this harness. If a task-loop PR was
somehow merged by someone else, treat it as already-integrated and just apply the outcome — don't
re-merge.

## Issues ↔ tasks

Every task is paired with a GitHub issue at **creation** (create or adopt; stored in `tasks.issue`).
The **issue is the persistent unit-of-work identity; a task is one *attempt* at it.** The worker's PR
uses `Refs #<issue>` — links, never auto-closes. On **success** the orchestrator closes the *issue*. On
**blocked / gate-failed / conflict** it closes only the *task* (the attempt) but **keeps the issue open
and re-links** it to the next attempt §5 materializes — so the unit is pursued across attempts until it
succeeds or `stop_at` halts the run. The issue closes **only on success** (or by human steering).

## Recovery = the next tick

There is no resume path. A fresh orchestrator recreates the team, reads `task-loop status` + GitHub +
`directions.md`, and runs a normal tick: PR-present `working` tasks are integrated; PR-absent orphans
are **reclaimed and re-attacked** in the default single-orchestrator mode (§Reset case (c)) — held and
surfaced only under *declared* multi-orchestrator operation. So a crash / restart **self-heals** without
human intervention.

## Multiple orchestrators

Declared multi-orchestrator operation (one per ecosystem — Claude / Gemini / Codex) runs with **no
coordination beyond `task-loop claim`**: the atomic claim guarantees single-flight *dispatch*, any
orchestrator may merge any ready PR, and the proposal reconcile-sweep (§4) is convergent. The two
surfaces they must respect: a foreign orchestrator never resets an opaque `working` task it doesn't own
(§Reset), and *materialization* is unlocked, so two peers may create a **duplicate attempt** for one
unit — bounded waste (the issue is the unit identity; at most one attempt merges). Both are accepted
costs of lock-free concurrency; the default single-orchestrator mode incurs neither.

## Deliberate with Codex

`dev-skills:discuss-with-codex` is the orchestrator's judgment engine. Its **adversarial stance is the
point** — it is what stops the loop giving up early or wandering off-aim. Use it for:
- **failure diagnosis + re-attack design** (§3/§5) — *what went wrong, what's untried*, codex pushing
  "you have not exhausted this; escalate the approach";
- the **AIM-fidelity check** (§5) — *does this new work still serve the Success criteria, or is it
  drift to an easier goal?*;
- task **decomposition / dependency ordering** (§5), and whether a **finding warrants a roadmap
  change** (§4).

Keep the mechanical steps mechanical; reserve deliberation for these judgments.
