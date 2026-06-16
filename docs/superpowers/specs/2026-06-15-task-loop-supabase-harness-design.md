# Task-loop v2 — Supabase harness design (authoritative spec)

**Date:** 2026-06-15
**Status:** design agreed; **fully built**. Components: `db/schema.sql`, `cli/task-loop`, `skills/setup` (live-verified), `references/pr-findings.md`, `agents/cycle-worker`, `skills/create-cycle` + `task-loop-skeleton.md`, `skills/run-cycle`. Old harness retired: old `scripts/` + tests removed, `preflight` folded into `setup`, `specify-aims` slimmed, README + `plugin.json` updated.
**Supersedes:** the GitHub-issue-comment control-log harness (`scripts/control_log.py`, `scripts/gh_store.py`, old `run-cycle`).
**Companion docs:** orchestrator-pass deliberation `2026-06-15-task-loop-orchestrator-pass-conclusion.md` (refines §7–§9 below); **persistence-model closure `2026-06-16-task-loop-persistence-loop-conclusion.md` (this revision — supersedes the human-wait branches in §8/§9)**; earlier redesign record `2026-06-15-task-loop-supabase-harness-redesign-conclusion.md`; diagrams `2026-06-15-task-loop-harness-diagram.md`.

This is the single source of truth for the redesigned harness. It records *what* we are building and *why* the non-obvious cuts were made (several reverse earlier drafts).

---

## 1. Goals & philosophy

- **Simple and elegant over flexible.** Flexibility makes a harness fragile. Fewer states, fewer rules, one obvious path.
- **Idempotent, stateless orchestrator.** All durable state lives in the world (Supabase DB + GitHub), never in the orchestrator. Running the loop *from anywhere, anytime* always does the same thing — there is **no** start/resume/recover mode.
- **Relentless toward the goal; never gives up.** Short of the time bound the orchestrator never abandons the goal — every failed attempt is *diagnosed* and *re-attacked* with a materially-different, AIM-aligned strategy, escalating the approach when the same obstacle recurs. It never idles on difficulty, picks the easy task over the hard one, or drifts to an easier goal. Terminal states: **goal-met** or **`stop_at`** (§8).
- **The orchestrator decides; the worker works.** The orchestrator never writes task code; the cycle-worker never touches the DB or merges.
- **Two agent types only.** Everything else is deterministic, non-agent infrastructure (DB, CLI, GitHub, a hook).

---

## 2. Architecture at a glance

**Two agent types:**
- **Orchestrator** — the main / general-purpose agent (Claude *or* Gemini *or* Codex) running the `run-cycle` skill. **Multiple may run, one per ecosystem; no affinity** (any orchestrator handles any task — subject to the reset rule, §8). Sole **dispatcher / decider / merger / editor of `proposal.md`**. Talks to the DB via the CLI and to GitHub via `gh`.
- **cycle-worker** — the one custom agent. Does one task: work → open a PR (findings in the PR) → report done. **Never** touches the DB, **never** merges.

**Three deterministic (non-agent) surfaces:**
- **Supabase (Postgres)** — the task DB. One shared project across all the user's repos; repos are rows.
- **The `task-loop` CLI** — the only thing that talks to the DB (Supabase REST). Used by orchestrators + humans; never by workers.
- **GitHub** — PRs (the work + findings), issues (human mirror), branch protection (the merge gate). Reached by the orchestrator via `gh`.

See the diagram doc for the actor/flow, task-lifecycle, and (historical) state diagrams.

---

## 3. Data model (`db/schema.sql`)

One shared database; **repos are rows, tasks are rows scoped by `project_id`** (multi-tenant by column, not table-per-repo).

```
projects
  id             text primary key          -- "owner/repo" (from git remote)
  default_branch text default 'main'
  next_seq       int  default 1            -- per-project task counter
  created_at     timestamptz default now()

tasks
  id          uuid primary key default gen_random_uuid()  -- internal surrogate key; never shown
  project_id  text references projects(id)
  seq         int                          -- per-project natural key; the only id the CLI shows ("001")
  title       text
  status      text check (status in ('open','working','closed')) default 'open'
  deps        int[] default '{}'           -- per-project seqs this task waits on
  issue       int                          -- GitHub issue # (human mirror + PR↔task link)
  created_at  timestamptz default now()
  unique (project_id, seq)
```

- **`claimable` view** (`security_invoker = on`): `open` tasks whose every dep is `closed`. Inspection only — the CLI doesn't depend on it.
- **`task_add(project, title, deps, issue) → seq`**: bumps `projects.next_seq` and inserts, atomically (per-project sequential id; `unique(project_id,seq)` backstops races).
- **`task_claim(project) → row|null`**: picks the next ready task (`open` + deps closed) `ORDER BY seq FOR UPDATE SKIP LOCKED LIMIT 1` and flips it to `working`. This is the **single-flight dispatch primitive** — concurrent orchestrators can never grab the same task.
- `close` / `reset` are plain one-line `UPDATE`s the CLI runs.

**The two-id pattern (natural + surrogate keys):** humans/CLI use the per-repo `seq` (`001`, `002`, …); the DB uses the global `uuid`. Exactly like GitHub showing `#42` over an opaque node-id.

**Deliberately absent (and why):**
- **No `attempts` table / `attempt_id` / per-attempt branch ledger.** Recovery is "PR or no PR" (below); a worker's in-progress work before a PR is disposable local WIP. Nothing to track.
- **No `findings` table.** Findings are written *in the PR* (study log); the orchestrator reads the PR. (Rationale §8.)
- **No `worker` / `owner` column.** No orchestrator affinity; "is the worker alive" is the orchestrator's in-session knowledge, not DB state.
- **No lease / heartbeat / `runtime` table.** The orchestrator owns its workers (observes death in-session); a fresh pass treats orphaned work as resettable. No timers.
- **No `closed_as` / `priority` / `replaced_by` / `updated_at`.** Outcome lives in the PR; ordering is `created_at`/`seq`; "blocked" recreates a fresh task; the loop reads current state, not timestamps.

---

## 4. Security

- **RLS enabled on both tables, with no policies.** The **secret / `service_role` key bypasses RLS** (full access — what the CLI uses); the **public anon / publishable key is denied** (no policies = deny). So task data is private with zero policy code.
- **`claimable` view is `security_invoker = on`** so it respects the querier's RLS (otherwise a definer view would leak `tasks` past RLS to the anon key).
- The secret key is a **machine-local 0600 secret** (`~/.config/task-loop/config`); never committed, never in `settings.json`. Rotate if exposed.

---

## 5. The CLI (`cli/task-loop`)

- **Single self-contained `uv` script** with PEP 723 inline deps (`httpx`); run via `uv run` (no install beyond `uv`).
- **DB-only**, over the **Supabase REST API (PostgREST)** — no Postgres wire driver, so any machine with `uv` (or stock Python/Node/`curl`) can drive it. This is what keeps the heterogeneous-agent promise.
- **Project auto-detected** from `git remote get-url origin` (`owner/repo`); `--project` overrides.
- **Credentials**: env-first (`TASK_LOOP_URL` / `TASK_LOOP_KEY`), then `~/.config/task-loop/config`.
- **Commands**: `init`, `add "<title>" [--dep N]… [--issue N]`, `claim`, `close SEQ`, `reset SEQ`, `status`, `login [--url --key]`. Workers never call it.
- **No `delete`** — tasks are `closed`, not deleted (closed is terminal and invisible to the loop). Ad-hoc cleanup is a one-off REST call.

---

## 6. Setup (`skills/setup`)

Three independent granularities, each done once:

| Layer | Once per… | Action |
|---|---|---|
| Supabase project + schema | **account** | create a hosted project; apply `db/schema.sql` via the SQL editor (REST can't run DDL) |
| credentials | **machine** | `task-loop login` → `~/.config/task-loop/config` (0600) |
| repo registration | **repo** | `task-loop init` |

- **The Supabase MCP is *not* required.** It's only a setup-time convenience for a Claude agent (it can run DDL); the running harness uses REST only. When in doubt, apply the schema via the SQL editor.

---

## 7. Agents

### Orchestrator (the `run-cycle` skill on the main agent)
- One per ecosystem; multiple may run concurrently with no coordination beyond the atomic `claim` (and the reset rule, §8).
- Each fixed-interval tick runs the **6-step pass** (§8): read state + steering → liveness → merge → reconcile `proposal.md` → materialize tasks → dispatch. Sole writer of `closed`; sole merger; sole editor of `proposal.md`.
- Uses the CLI (DB) + `gh` (GitHub). Never writes task code.

### cycle-worker (the one custom agent)
- Inputs: a task `seq`, title, its GitHub `issue`, and a branch to work on.
- Does: the work → opens a PR (with the **study log: rubric + results + any findings**) → reports done. Then idle/exit.
- **Never** touches the DB, **never** merges, **never** edits the plan, **never** manages tasks/issues. It just does its one task and faithfully reports findings; its only durable output is the PR. All task/issue/plan management is the orchestrator's.

---

## 8. The loop (`run-cycle`) — a fixed-interval 6-step pass

The orchestrator runs under a **fixed-interval Loop A** (default 15 min). Each tick is one idempotent
pass over (DB + GitHub + `directions.md`) — no start/resume/recover distinction. **Loop B** is a
one-time job at `stop_at` that *non-destructively* wakes Loop A; **Loop A is the sole stop authority**
(a tick with `now ≥ stop_at` + a drained board cancels its own generation-named schedules and stops).
Both jobs carry a `run_generation` so a stale job never touches a newer run. Full algorithm +
rationale: `skills/run-cycle` and the deliberation `…-orchestrator-pass-conclusion.md`.

Each tick, **in order** (steering first — it gates everything irreversible):

0. **Read state + stop check.** `task-loop status` + open PRs/issues + `directions.md`. `now ≥ stop_at`
   → drain (skip dispatch; finish in-flight; stop when no `working` remains).
1. **Honor steering.** Apply `directions.md` (highest priority) *before* any merge — pause/freeze,
   "don't merge #X", priorities, blockers. Steering is an **exogenous trigger** (a tick does real work
   on new directions, not only on completions).
2. **Liveness.** Ping the teammates *this session* spawned for a one-line progress report (advisory;
   the basis for the reset rule below).
3. **Merge / classify** (only PRs steering allows) — per `working` task's PR. **Mergeable** (CI +
   review green **and** GitHub merge-state clean — no conflict/behind) → **head-SHA-atomic merge**
   (`gh pr merge --squash --match-head-commit <SHA>`, §9; a green→red flap is rejected) → on **success**
   close issue + `task-loop close <seq>`; **blocked** → close task + work recreated in step 5 → reap.
   **Behind base only** → `gh pr update-branch` (mechanical sync; merge next pass). **Gate-failed /
   stuck / conflict** (check red, review failed, genuine conflict / deterministic rejection, or pending
   past bound / never posts) → **diagnose and re-attack, never give up**: `gh pr close` + `task-loop
   close <seq>`, then step 5 materializes the **next attempt against the same issue** with a
   materially-different, escalated, AIM-aligned strategy. (Recreation is safe because it is *diagnosed
   escalation*, not blind repetition — reversing the old "close-recreate spins → surface `needs-human`"
   rule — and `stop_at` bounds it.) **Pending** → leave for next pass.
4. **Findings → `proposal.md` (reconcile sweep).** The orchestrator is the **sole editor** of
   `proposal.md`. When merged findings change the roadmap, **recompute** the affected sections from
   *current default + the complete set of merged study-logs not yet reflected* (never a stale patch),
   PR it, merge it; regenerate if the base moved. Convergent under concurrent orchestrators — no lock.
5. **Materialize tasks (idempotent) — the goal-driver that never gives up.** Ensure the board carries
   the next work toward the **Success criteria**: planned stages not yet tasked (seed + decomposition,
   **including the riskiest / heavy-lifting work — never deferred for easy wins**), discovered blockers,
   `--dep` re-creation (re-linking the issue), direction-/finding-driven tasks, and **re-attacks** of
   every attempt step 3 closed non-mergeable. A re-attack is **diagnosed** (`discuss-with-codex`: what
   failed, what's untried), **materially different** from prior attempts on that issue, and **escalates
   the class of approach** when the same obstacle recurs. **AIM-fidelity:** every new task is
   codex-checked against the Success criteria — keep only AIM-aligned work, never drift to an easier
   goal. Create or adopt the issue, then `task-loop add … --issue N`; never duplicate. While the goal is
   unmet this **always** adds the next task(s); there is no give-up exit.
6. **Dispatch** (skip if draining). `task-loop claim` loop → spawn one `cycle-worker` per claim (`seq`,
   title, issue, branch), record its id, up to a soft capacity.
7. **Goal check / terminate.** Evaluate the **Success criteria** against the repo (run them; don't infer
   from "tasks closed"). **Met** → done (drain + stop). **Unmet** → **always continue**: step 5 keeps
   the board carrying the next diagnosed, AIM-aligned work, so there is **no exhaustion terminal and no
   idle-on-difficulty** — the only non-goal terminal is **`stop_at`** (Loop B guarantees it fires). If
   escalations converge on something genuinely beyond the loop's reach, drop a **non-blocking** note for
   async human steering (`directions.md`) and **keep attacking other angles** — never wait, never
   redefine the goal. *(Closure re-verified adversarially for the persistence model —
   `…-2026-06-16-task-loop-persistence-loop-conclusion.md`.)*

### Reset rule (the one subtle invariant)
`claim` makes `open → working` atomic but **not** `working → open`. A PR is durable (any orchestrator
may merge it); a PR-absent `working` task is **ambiguous** — alive-pre-PR vs dead — without an ownership
marker (which we don't keep). So it is reset **only** with positive "no live owner" knowledge: **(a)**
in-session observed death; **(b)** a human `task-loop reset <seq>`; or **(c)** a **single-orchestrator
cold start** — a fresh session in the default single-orchestrator mode safely reclaims **every** opaque
`working`-no-PR orphan (prior-session workers died with their session), so crash/restart **self-heals
with no human-wait**. Single-orchestrator is an *operator deployment declaration*, not a runtime
detection; accidental concurrency degrades to **bounded waste** (a reset may clobber a peer's branch →
that unit is re-attacked), never unrecoverable. Only **declared multi-orchestrator** operation refuses
to reclaim a foreign orphan (it surfaces it); `directions.md` never triggers reset. **Termination** is
independent of all this: at `stop_at` the drain is **bounded** (it waits only for genuinely-pending PRs,
never for orphans/stuck), so the run always stops within a bounded time.

**Recovery is just the next tick.** PR-present `working` tasks integrate; PR-absent ones are held +
surfaced. **The run finishes when the Success criteria are met** (goal achieved, step 7) **or** at
`stop_at` (the time bound). An empty board with the goal **unmet** is *never* a stop — step 5
materializes the next diagnosed, AIM-aligned work. So the loop always advances the goal, finishes it, or
runs out the clock having genuinely kept trying — it never quietly gives up short of the goal.

### Issues ↔ tasks
Every task is **paired with a GitHub issue** at creation (open new or adopt existing; `tasks.issue` holds it). **The issue is the persistent unit-of-work identity; a task is one *attempt* at it.** On a successful merge the orchestrator **closes the issue**. On **blocked / gate-failed / conflict** it closes only the *task* (the attempt) but **keeps the issue open and re-links** it to the next attempt step 5 materializes — so the unit is pursued across attempts until success or `stop_at`. The issue closes **only on success** (or by human steering).

---

## 9. Merge safety

- The orchestrator runs `gh pr merge` itself, after reading the PR and confirming readiness (CI + review green, findings OK). The merge is **head-SHA-atomic** — `gh pr merge --squash --match-head-commit <validated SHA>` — so a PR that flipped red or gained commits between the readiness check and the merge is **rejected**, not merged stale (re-evaluated next tick). When the work is done it **merges the PR and closes the task**. A **deterministic** block is **re-attacked, never surfaced for a human to fix**: *behind base* → `gh pr update-branch`; *conflict / other* → a diagnosed, materially-different next attempt (§8 step 3/5).
- **A task-loop-specific merge hook is NOT part of this harness.** Generic `gh pr merge` gating is already provided by a **separate plugin's hook**, and **branch protection** (required CI + an independent review check, posted by a CI workflow/Action — never the worker) is the structural backstop no merge can bypass.
- The task-specific decision ("is this PR's outcome mergeable; does anything block it?") is the **orchestrator's judgment** as it reads the PR — not a machine-enforced DB guard. (Codex argued for first-class findings + a DB-checking executor for structural impossibility; the operator chose the simpler "the orchestrator is smart and decides" model, backed by branch protection.)

---

## 10. Task lifecycle

- States: **`open → working → closed`** (monotone). The only backward edge is **`reset` (`working → open`)**, allowed only with positive "no live owner" knowledge — in-session observed death or a human `task-loop reset` (§8 reset rule), never a blind cold/foreign reset.
- **`blocked` is derived**, not a stored state: `open` with an unmet dependency (`claimable` excludes it). A worker that *discovers* it's blocked → the orchestrator **closes the task and creates a new one** carrying the remaining work + the blocking dep.
- A task **only** leaves `open`/`working` by being `closed`; nothing is silently dropped (a closed task's reason lives in its PR; a blocked task's work lives in its replacement).

---

## 11. What this replaces / retires

- `scripts/control_log.py`, `scripts/gh_store.py` (+ their tests) — the GitHub-comment single-sequencer event log → **remove**, replaced by Supabase + the CLI.
- Old `run-cycle` (single orchestrator, GitHub control issue, leases, `attempt_id`, seq-guard, scan-floor, two-loop stop model) → **rewrite** to §8.
- Old `cycle-worker` (control-event/recovery-comment protocol) → **rewrite** to §7.
- `preflight` → folded into / replaced by `setup`.
- `create-cycle` → **load-bearing**: it renders `docs/task-loop/task-loop.md` — the worker's actual per-project cycle + general rules. (Not optional; the worker follows it strictly.) Updated to the simple model (no control-issue/attempt machinery).
- `specify-aims` → authors `docs/task-loop/proposal.md` (the roadmap the orchestrator **reconciles** each loop, §8 step 4). Kept as the plan-authoring aid; to be slimmed only of dead control-issue references.

---

## 12. Done vs. to-build

**Done:**
- `db/schema.sql` — tables, `claimable` (security_invoker), `task_add`/`task_claim`, RLS. *(live-verified against real Supabase: `init → add → status → close`, `claim` + dependency-gating).*
- `cli/task-loop` — uv/REST CLI; `init/add/claim/close/reset/status/login`. *(live-verified.)*
- `skills/setup` — onboarding (account/machine/repo), MCP-optional.
- `references/pr-findings.md` — the study-log + PR contract (the `success/failed/blocked` outcomes).
- `agents/cycle-worker` — thin, isolated worker: follows `task-loop.md` via a TodoWrite, worktree-isolated, work → PR → report → idle; no merge/DB/issue/plan.
- `skills/create-cycle` + `assets/task-loop-skeleton.md` — renders the worker's per-project cycle + general rules (simple model; old control-issue/attempt machinery stripped).
- `skills/run-cycle` (SKILL + `references/orchestrator-loop.md`) — the §8 6-step pass, reset rule, proposal reconcile, Loop A/Loop B stop model.

**Retirement / cleanup — done:**
1. Removed old `scripts/` (`control_log.py`/`gh_store.py`) + their tests.
2. Folded `preflight` into `setup` (Agent-Teams enablement + the corrected 8-skill list); the
   per-session skill-loadability check moved to `run-cycle` preconditions.
3. Slimmed `specify-aims` + `proposal-template.md` of `plan_revision`/control-issue (the orchestrator
   reconciles `proposal.md`; an `incorporated_through` marker replaces the revision counter).
4. Updated `README` + `plugin.json` (v0.14.0).

**Not built here:** the merge hook — generic `gh pr merge` gating is provided by a separate plugin, with branch protection as the structural backstop (§9).

---

## 13. Resolved decisions (were open questions)

Most settled in the orchestrator-pass deliberation (`…-orchestrator-pass-conclusion.md`):

- **Pass shape** → a **6-step, directions-first pass** (§8): read state + steering → liveness → merge → reconcile `proposal.md` → materialize tasks → dispatch. Steering is read *before* any irreversible action and is an exogenous trigger.
- **Reset rule** → reset only on in-session observed death **or** a human `task-loop reset`; cold/foreign ticks surface but never auto-reset opaque `working`-no-PR tasks; `directions.md` never triggers reset (§8). Honest cost: concurrent multi-orchestrator loses auto pre-PR recovery; single/sequential keeps it.
- **`proposal.md` updates** → the orchestrator is the **sole editor**, and each update is a **reconcile sweep** (recompute from current default + the complete merged-evidence set), never a stale patch — convergent under concurrency, no lock.
- **Stop model** → fixed-interval **Loop A** self-stops (sole stop authority); **Loop B** is a *non-destructive* early-wake; both jobs are `run_generation`-named; `stop_at` rides in Loop A's prompt — no DB cell, no stored handle, no local file.
- **Study-log / findings format** → settled: `docs/task-loop/logs/<seq>_<task>.md` (Outcome + rubric + evidence + findings), committed in the PR; PR body = `Refs #<issue>` + Outcome + pointer (`references/pr-findings.md`).
- **Issue ↔ task pairing** → paired at creation; PR `Refs` (never `Closes`); orchestrator closes on success, re-links on blocked. Close-vs-keep is its judgment.
- **Worker scope** → does its one task, isolates in its own worktree, reports findings in the PR; no merge / DB / issue / plan management.
- **Capacity / concurrency** → not prescribed (soft knob). **Branch naming** → implementer's choice (`tl/<seq>` default; stale branch deleted on reset). **Multi-machine launch** → out of harness scope.
- **Persistence / no-human-wait (this revision)** → the loop **never gives up short of the goal** and **never waits on a human decision** (humans steer *direction* only, async via `directions.md`). Every non-mergeable attempt is **diagnosed** (`discuss-with-codex`) and **re-attacked** with a **materially-different, AIM-aligned** strategy, **escalating the class of approach** when the same obstacle recurs (decided: *diagnosis + escalation teeth*, with *codex as the diagnosis / AIM-fidelity engine*); merge-blocked → behind-base `gh pr update-branch`, else a diagnosed next attempt. The GitHub **issue is the persistent unit identity; a task is one attempt**. Terminal states reduce to **goal-met** or **`stop_at`** — no exhaustion/idle terminal. This **reverses** the old "close-recreate spins → surface `needs-human`" rule: recreation is safe because it is diagnosed escalation (not blind repetition) and `stop_at` bounds it. Worker-side: *don't skip the heavy lifting* — `failed`/`blocked` are last resorts backed by evidence, not escape hatches. Closure re-verified adversarially (`…-2026-06-16-task-loop-persistence-loop-conclusion.md`).

**Still genuinely open:**
- Which **CI / Action produces the independent review check** and how it's bound to the PR head.
