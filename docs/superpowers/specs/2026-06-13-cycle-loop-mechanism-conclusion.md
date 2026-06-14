# Conclusion — orchestrator loop mechanism for the cycle-driven-dev skill suite

**Goal.** Choose the outer driver for the *orchestrator* (team-lead) agent of a new
skill suite that generalizes METBG's autonomous "study loop" — where the main agent
no longer runs the per-task cycle itself but instead computes task dependencies and
dispatches **worker teammates** (Claude Code experimental Agent Teams) that each run
one task's full cycle (issue → branch → binary rubric → spec → plan → TDD → verify →
PR → squash-merge). Candidates: **(A) built-in `/loop` self-paced** vs **(B) the
`ralph-loop` plugin** (Stop-hook re-feed, `--max-iterations`, `--completion-promise`).

## Settled position

**Use built-in `/loop` (self-paced, via `ScheduleWakeup`) as the orchestrator driver.
Not `ralph-loop`, and not any blocking Stop hook.** Liveness is protected by a durable
lease + an agent-run pre-exit audit, and termination is a graceful **drain-on-signal**
rather than an iteration count.

### Why `/loop`, not ralph
- The orchestrator's dominant activity is **dispatch-and-wait**: spawn worker
  teammates / background compute, then wait for completion before re-planning.
  `/loop` + `ScheduleWakeup` is the native wait primitive, and Agent Teams already
  deliver **idle notifications to the lead automatically**, re-invoking the
  orchestrator exactly when a worker finishes. `ralph` re-feeds *immediately* on every
  Stop with no delay primitive (foreground `sleep` is blocked) → spin/hacks for a
  coordinator that waits on others.
- `/loop` is a native harness feature (robust). Layering a Stop-hook loop on top of
  *experimental* Agent Teams (with their own fragile Stop/idle/`TeammateIdle`
  semantics) risks hook interactions.

### Termination — continuous service with graceful drain-on-signal
`--max-iterations` is **replaced** by a stop-signal model (user direction):

- The orchestrator runs **continuously**. A separate **scheduled job** (cron / the
  repo's `schedule`/`CronCreate` mechanism) emits a **stop signal** at a chosen time.
- On observing the signal: **dispatch no new cycles**; in-flight workers **finish
  their current cycle**; then the orchestrator stops.
- **"No ready work" is NOT terminal** in this model — it is an `idle` state (schedule a
  long wake / monitor). Terminal exit requires the stop signal. (A finite "drain the
  backlog then exit" mode is an optional flag, not the default.)

### Orchestrator state machine
**Dispatch is proactive and seat-capped, not a phase:** each turn merges completions **first**, then
dispatches ready tasks into free seats **up to a cap of 5 concurrent workers** (documented guideline,
not enforced) — active workers never suppress dispatch of newly-unblocked work while a seat is free
(a merge unblocks dependents the same turn).
- `dispatching` — ready work exists, no stop signal → create/assign tasks into free seats, ≤5 in
  flight per lead session (best-effort; a stale-lead false positive may transiently exceed it,
  correctness-safe via `attempt_id` fencing; entered even while other workers are active).
- `waiting` — after filling every free seat, work is in flight → idle notifications + a **bounded,
  jittered** fallback wake; never a reason to stop dispatching, never a busy-loop.
- `idle` — no ready work, no active workers, no stop signal → long `ScheduleWakeup` /
  Monitor; **do not exit**.
- `draining` — stop signal observed → no new dispatch; wait for active workers, bounded
  by `drain_deadline_at`.
- `exiting_pending` — drain complete → record audit, `ScheduleWakeup` short cooldown
  (60–120 s).
- `exiting` — re-audit from scratch still clean → final stop. If anything changed,
  revert to `dispatching`/`waiting`.

### Liveness & durable state
- **Lease/heartbeat**: `orchestrator-state.json` holds `phase`, `lease_expires_at`,
  `heartbeat`, `active_worker_ids`, `next_wake_reason` — same shape as METBG's
  `refs/heads/loop-lock` lease. **Single writer: only the orchestrator writes it.**
- **Stop signal channel**: the scheduled job writes a **separate** `stop-request.json`
  **atomically** (temp-file + rename). Cron never edits the lease file.
- **Pre-exit audit** (agent-run, not a hook): before writing `phase: exiting` the
  orchestrator runs a deterministic audit — `ready == 0`, `active == 0`,
  `blocked == acknowledged`, `unmerged == 0` — and records the **actual command
  outputs** into its decision record (`superpowers:verification-before-completion`
  rigor).
- **Drain deadline (non-destructive)**: after `drain_deadline_at`, overdue workers are
  marked `orphaned_acknowledged` with their worktree/issue/PR pointers and left for
  resume/manual handling. **No abrupt kill as the v1 default.**
- **Recovery**: the next `/run-cycle` invocation reads `orchestrator-state.json`,
  detects a stale or `exiting`-without-clean-audit lease, and resumes.

## Strongest objections raised and how each resolved
1. **Asymmetric early-exit risk** (R1) — a "frontier empty" misjudgment is the one
   failure where no worker exists to wake the lead. *Resolved:* deterministic pre-exit
   audit + lease, not "state is recoverable."
2. **Blocking Stop hook is unsafe** (R2) — can't distinguish final-exit from
   `/loop` turn-yield; repo's global empty-matcher `Stop`/`SubagentStop` hooks could
   gate workers and deadlock the team; existence-only artifact check is ceremonial.
   *Resolved:* dropped the Stop-hook gate entirely; lease + agent-run audit instead.
3. **Audit-passed-once ≠ quiescence** (R3) — async actors can land right after the
   audit. *Resolved:* two-phase quiescence exit (cooldown + re-audit).
4. **"Continuous" vs natural-exit conflict; unbounded drain; multi-writer flag** (R4).
   *Resolved:* frontier-empty → `idle` not exit; bounded drain deadline with
   non-destructive orphan-acknowledge; single-writer files with atomic stop-request.

## Unresolved / deferred
- **External watchdog**: deferred as YAGNI for v1. The residual single-run liveness gap
  (a wrong `phase: exiting`) is mitigated by the two-phase quiescence exit (in-run) and
  the stale-lease resume on re-run (across-run). Revisit if unattended multi-day runs
  become common.
- **Worker-internal completion rigor**: a worker's single-task cycle has a binary
  rubric that is a natural completion gate; whether to additionally wrap a worker in
  ralph-style `--completion-promise` is a separate, lower-stakes decision left to the
  worker/cycle design.

**How it ended:** converged after 4 rounds.
