# task-loop control plane — "three jobs, no local files": Codex deliberation conclusion

**Date:** 2026-06-13 · **Outcome:** converged after 4 rounds (Codex: `NO FURTHER OBJECTIONS`).

Pressure-test of PR #120's redesign: move all orchestrator runtime state off local disk into
the GitHub control issue, and run the control plane as a small set of cooperating jobs. The
deliberation hardened the design and corrected several over-claims.

## Settled position

**State (no local runtime files).**
- Control-issue **comments** = the append-only, single-sequencer control-event log; `replay`
  rebuilds all fast state (`plan_revision`, frontier, scan floors, dedupe) every turn.
- Control-issue **body** = the single mutable **runtime header** (fenced JSON): `lease`
  (`owner`/`expires_at`/`heartbeat`), `stop_at`, `watchdog_schedule_id`, `stop_schedule_id`,
  advisory `phase`. The orchestrator is its **sole writer**; sibling jobs only read it.
- Fast state is **never** persisted to disk — always reconstructed from GitHub. This is what
  makes recovery clean: any session running `/run-cycle` rebuilds 100% from GitHub.

**Execution model (one model, chosen).**
- **Loop 1 = a live `/loop` Agent-Teams lead session** — NOT a scheduler job.
- Teammate **idle notifications are a within-session latency optimization, not part of the
  correctness model.** Correctness rests entirely on GitHub replay + idempotent respawn.
- A watchdog "resubmit" launches a **fresh** `/run-cycle` session (new lead, new team) that
  enters recovery; it does not inherit the dead lead's teammates (teammates die with the lead's
  session).

**Lease safety (required guards, not asserted outcomes).**
- Before **any** side effect (emit a control event, merge, write the body): write the lease
  epoch to the body, **re-read**, confirm ownership; and immediately before posting `seq=N+1`,
  **re-read the comment log and confirm the true max seq is still N** (check-then-append). On
  mismatch a competing sequencer is detected → re-ingest; if it persists, the non-owner **exits**.
- If `replay` ever raises on a dup/gap seq → **halt and escalate to a human**, never continue.
- GitHub gives no atomic CAS, so a vanishingly-small TOCTOU window remains between re-read and
  append. Accepted because (a) the watchdog only acts when the heartbeat is already stale, so
  concurrent orchestrators are rare by construction, and (b) the residual corruption is
  detectable + halting, not silent. Structural alternative (if ever needed): make GitHub the
  sequencer by deriving order from server `createdAt`/node-id instead of a self-assigned seq.

**Recovery semantics (Option 1 — disposable pre-PR work).** The dividing line is *"is there a
GitHub-visible artifact?"*:
- A dispatched/`in_progress` task with **no remote branch and no PR** is treated as
  not-yet-started → **abandon and re-dispatch a fresh attempt** (new `attempt_id`) from clean
  `master`. At most one in-flight task's un-pushed local WIP is lost and simply redone — zero
  correctness loss.
- A task **with** a GitHub-visible artifact (remote branch / PR, recorded as `attempt_id` +
  head SHA in the `RECOVERY` ledger) is **adopted** via GitHub and driven to merge.
- Local-worktree adoption is **only a same-machine optimization**, never a correctness
  requirement. Deterministic per-task branch naming + `attempt_id` make re-dispatch and adoption
  idempotent (a second worker finds the branch/PR and adopts/aborts — never opens a 2nd PR).

**Watchdog — two tiers (do not over-claim auto-resurrection).**
- **Tier 0 (guaranteed floor): detect + alert.** A scheduled job reads the body heartbeat; if
  stale **and** `now < stop_at`, it posts a **plain non-control comment** (no `task-loop-event`
  fence, no seq — invisible to the sequencer) + a push notification "orchestrator down, resume
  needed." Needs gh **read** for liveness and gh **write** only for the alert. Works from
  anywhere. Manual `/run-cycle` is a clean resume (thanks to no-local-files).
- **Tier 1 (optional, explicitly configured + tested): unattended auto-relaunch.** Requires a
  named **local supervisor** (OS launchd/cron, or a verified locally-running scheduled job) with
  a tested command template: `cwd`=repo, env incl. `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`,
  plugin loaded, `gh` authenticated, entry launches `/run-cycle` under `/loop`, log capture.
  This is **setup/config, not runtime state** (it does not reintroduce runtime local files), but
  it is a real precondition that must be installed and validated by the Phase-0 spike before any
  claim of unattended resurrection.
- The `now < stop_at` guard ensures neither tier resurrects the run after an intentional stop.
- **Loop 2 = scheduled one-time stop** at `stop_at`: reads `watchdog_schedule_id` from the body,
  cancels the watchdog, confirms loop 1 has drained.

**Precondition surfaced:** the watchdog/stop jobs and any auto-relaunch must run in the **same
local environment** where Agent Teams is enabled — a cloud-only routine cannot spawn local
teammates.

## Strongest objections & how each resolved

1. **Execution-model contradiction** (loop 1 = scheduler job *and* live `/loop` lead). Resolved
   by choosing one model: loop 1 is the live `/loop` lead; idle-notify demoted to a within-session
   optimization; correctness = GitHub replay + respawn.
2. **No durable worker identity → double-spawn.** Resolved with deterministic branch naming +
   `attempt_id` + GitHub-visible-artifact adoption; teammates die with the lead so a restart has
   no surviving workers.
3. **Soft lease poisons the seq log.** Resolved by *requiring* a write-then-re-read fence +
   check-then-append guard + halt-on-corruption (vs. asserting the loser exits).
4. **Missing launcher contract** (a dead `/loop` can't relaunch itself; `ScheduleWakeup` dies
   with it; cloud can't spawn local teammates). Resolved with the Tier-0/Tier-1 split — detect+alert
   floor + explicit tested local-supervisor for auto-relaunch.
5. **"Resume 100% from GitHub" is false for pre-PR local WIP.** Resolved with Option 1
   (disposable pre-PR work; GitHub-visible = adoptable, local-only = disposable).

## Unresolved tensions

None blocking. One **accepted residual**: the lease's non-CAS TOCTOU window (bounded + detectable
+ halting, per above); the server-order-sequencer rewrite is the escape hatch if it ever proves
insufficient in practice — to be confirmed by the Phase-0 spike.

## Follow-up edits to land in PR #120

- run-cycle SKILL.md: stop calling all three "scheduler jobs"; loop 1 = `/loop` lead, loops 2/3 =
  scheduler guard jobs; watchdog = Tier-0 detect+alert floor, Tier-1 = tested launcher contract;
  add the local-environment precondition.
- orchestrator-loop.md: idle-notify = optimization; lease write-then-reread + check-then-append +
  halt-on-corruption; recovery Option 1 (disposable pre-PR WIP, GitHub-visible adoption,
  `attempt_id`, deterministic branch).
- create-cycle skeleton: RECOVERY semantics — pre-PR WIP disposable; deterministic branch +
  `attempt_id`.
- preflight: optional Tier-1 local-supervisor check; phase-0 spike validates the launcher contract.

How it ended: **converged after 4 rounds** — Codex issued `NO FURTHER OBJECTIONS`.
