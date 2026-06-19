# Task-loop persistence-model loop — closure verification (Codex)

**Date:** 2026-06-16
**Topic:** Does the redesigned "persistence model" orchestrator loop (never-give-up; no human-wait)
remain **closed and terminating**?
**Method:** `dev-skills:discuss-with-codex` — adversarial, read-only, **4 rounds, converged (NO FURTHER
OBJECTIONS)**.
**Subject files:** `task-loop/skills/run-cycle/references/orchestrator-loop.md`, `…/run-cycle/SKILL.md`,
`task-loop/references/pr-findings.md`, `task-loop/db/schema.sql`.
**Supersedes** the human-wait closure addendum in `2026-06-15-task-loop-orchestrator-pass-conclusion.md`.
**Stop-model supersession:** the bounded-drain termination text below is superseded by
`2026-06-19-task-loop-loop-c-drain-monitor-design.md`: `stop_at` now bounds new starts, Loop B installs
recurring Loop C, and Loop C drains observable in-flight work before generation cancellation.

## Settled position

The loop rests on **two hard, independent guarantees plus one adversarially-enforced bias**:

- **(T) Termination / drain — updated by the 2026-06-19 Loop C design.** The original bounded-drain text
  below is historical. Current semantics: `stop_at` stops new starts, Loop B installs recurring Loop C,
  and Loop C waits only for positively live in-session workers/monitored detached jobs and PR-present
  work before cancelling the generation. Opaque `working`-no-PR rows follow the reset rule and do not
  block the drain forever. Crash/restart **self-heals**: a single-orchestrator cold start reclaims every
  opaque orphan (reset case (c)), so recovery never waits on a human.
- **(P) Progress — rests on a never-empty board.** While the goal is unmet, step 5 always materializes
  the next work (planned-stage decomposition, blockers, and a **diagnosed re-attack** for every
  non-mergeable attempt). Step 7: unmet ⇒ always continue.
- **(N) Non-spin — a bias, not a hard invariant.** Every re-attack reads the unit's **durably-derivable
  attempt history** (all PRs that `Refs #<issue>`, open+closed) and is pushed by `discuss-with-codex`
  to be **materially different** and to **escalate the class of approach** when the same obstacle
  recurs. The budget is spent exploring, not blindly repeating, with `stop_at` as the backstop if a
  round's novelty is imperfect.

Terminal states reduce to **goal-met** or **`stop_at`**. Humans steer *direction* asynchronously
(`directions.md`); the loop never waits on a human decision and never redefines the goal to an easier one.

## Key decisions

- The GitHub **issue is the persistent unit-of-work identity; a task is one *attempt***. Attempt history
  is derived from the issue's PR set — **no** DB attempt-counter / strategy-class column (semantic
  novelty can't be a schema field without brittleness).
- **No-give-up replaces the old surface-and-idle branches**, *reversing* the prior surface-and-wait
  rule: recreation is safe **because** it is diagnosed escalation (not blind repetition) and `stop_at`
  bounds new starts.
- **Drain model updated:** the historical bounded PR-only drain is superseded by Loop C, which drains
  observable live workers/monitored jobs and PR-present work while still never hanging on opaque no-PR
  rows.
- **Reset rule gains case (c)** — single-orchestrator cold-start reclaim — so crash/restart self-heals
  without a human. Single-orchestrator is an **operator deployment declaration**, not runtime detection.
- **Anti-laziness enforced at three points:** materialize (the riskiest/heavy work must be *on the
  board*), worker (don't skip the hard part; `failed`/`blocked` are last resorts with evidence),
  failure-handling (diagnose + re-attack).

## Strongest objections and how each resolved

1. **`stop_at` can't force termination — an opaque `working`-no-PR orphan blocks the drain forever, and
   that waits on a human.** *Conceded — a real bug introduced in the rewrite.* Current fix: Loop C waits
   only for positively live in-session workers/monitored jobs and PR-present work; opaque no-PR rows
   follow the reset rule and never block the drain forever. Crash/restart self-heals through reset case
   (c) in single-orchestrator mode.
2. **Duplicate attempts aren't structurally prevented (materialization is lock-free).** *Conceded as
   bounded, non-fatal, scoped.* Possible only under *declared* multi-orchestrator; the issue is the unit
   identity and at most one attempt merges; the default single-orchestrator mode incurs none. Kept the
   lock-free design; documented the cost rather than adding a DB lock.
3. **"Materially-different + escalate" is policy, not a DB invariant → possible livelock-until-`stop_at`.**
   *Conceded and reframed.* Non-spin is an adversarially-enforced **bias**, not a hard guarantee;
   termination doesn't depend on it (`stop_at` does). A "strategy-class" column would be brittle, so
   adversarial codex judgment + derivable history is the correct enforcement.
4. **"single-orchestrator" is an unverifiable runtime premise; accidental concurrency → branch clobber.**
   *Conceded and reframed honestly:* it's an operator deployment declaration, not runtime detection;
   accidental concurrency is operator error that degrades to **bounded waste** (clobber → re-attack),
   never unrecoverable. No lease/heartbeat added (the design rejects per-task runtime state).
5. **Undefined "CI bound"; stale `SKILL.md` reset text; "board is drained" ambiguity; stale "only basis
   for auto-reset" note.** *All fixed:* CI bound defined inline; the SKILL reset bullet and the "Where
   state lives" note reconciled with case (c); "board is drained" replaced by the bounded-drain phrasing
   in both files.

## Unresolved tensions

None blocking. Accepted, documented costs (not closure breaks):
- Under *declared* multi-orchestrator operation: duplicate attempts and a possible foreign-orphan human
  reset / branch clobber — all **bounded waste** (issue is the identity; at most one attempt merges).
  The default single-orchestrator mode incurs neither.
- Non-spin remains a **bias** (judgment-enforced), backstopped by `stop_at`.

## How it ended

**Converged after 4 rounds** — Codex returned **NO FURTHER OBJECTIONS**, confirming no remaining
closure or safety break under the stated default/operator model.
