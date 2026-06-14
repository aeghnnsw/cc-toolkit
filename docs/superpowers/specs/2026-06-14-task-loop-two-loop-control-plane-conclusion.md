# task-loop two-loop control plane — Codex deliberation conclusion

**Date:** 2026-06-14 · **Method:** `dev-skills:discuss-with-codex` (adversarial), 6 rounds (round cap).
**Outcome:** **Substantively converged.** Every objection was conceded and folded into the design; no
standoff remained at the cap. An always-adversarial critic kept surfacing narrower refinements of one
corner (stop-time control), but the core topology was stable from round 2.

## Problem

`run-cycle` ran as **three jobs**: a self-paced `/loop` orchestrator (Loop 1), a one-time stop (Loop
2), and a recurring 30-min watchdog (Loop 3). The watchdog conflated two failure modes, and as an
in-session `CronCreate` job it could not survive the very session-death it nominally watched. The
self-paced wake model (idle-notification-primary + jittered fallbacks + backlog + recovery-probe
wakes) was complex and unpredictable. Goal: collapse to **two loops + a pure fixed 30-min poll**.

## Settled position

**Topology — two loops.**
- **Loop A** = the `/loop` orchestrator; every turn ends with a **fixed `ScheduleWakeup(1800)`**.
  Per-turn steps 1–5 unchanged (lease & rebuild; **Step 2 stop-check is the sole stop decision**;
  ingest worker events = "monitor team status"; replan; **merge first**). Step 6 (dispatch) gains a
  **recovery-disposition substep** (below). Step 7 simplifies to: not-draining → fixed 30-min wake;
  drained → exit. `phase: exiting` is a **hard terminal guard** at turn top; on exit, stop rescheduling.
- **Loop B** = a one-time scheduled **early-wake** at `stop_at`. It does **not** force `phase: exiting`;
  it triggers a normal turn whose Step-2 check (against the **current** header `stop_at`) decides. A
  stale early fire is therefore harmless (turn continues). Loop B carries a `stop_at`/generation payload
  as stale-trigger defense.

**Wake claim — narrowed (R1).** The fixed poll eliminates **inter-turn under-dispatch only** (stale
carried frontier + missed idle notifications — the "reluctance" class). It does **not** eliminate an
**intra-turn hang** (a long/blocking `gh`/CI/spawn call that never reaches Step 7). Mitigation:
**best-effort per-command deadlines** on the orchestrator's own calls with **reconcile-on-timeout**
(re-inspect ambiguous side effects, e.g. did `gh pr merge` land, before rescheduling). An intra-turn
hang is **not fully eliminable** and is a **documented capability reduction** vs the old watchdog,
handled by **manual `/run-cycle` resume**. (User decision: manual resume only.)

**Lease header — diagnostics, soft/advisory, sole-written.**
`{owner, expires_at (~2× poll), last_turn_started_at, last_turn_completed_at, next_wakeup_at, stop_at,
stop_schedule_id, drain_deadline_at}`. **Dropped:** `watchdog_schedule_id` and the single `heartbeat`
field. `stop_schedule_id` is **kept** (R5) so the orchestrator can cancel/recreate Loop B.

**Manual resume — tri-state, artifact-aware (R2/R3), on advisory diagnostics, human force always available.**
- `likely_alive` (`next_wakeup_at` **and** `expires_at` both future) → **default refuse**, allow
  explicit human force-takeover (the header is soft, never an absolute proof).
- `likely_dead` (`now ≫ next_wakeup_at`, or `expires_at` well past) → acquire lease, **observe/reconcile
  first**.
- **Recovery-disposition substep** gating "active with no live worker → dispatchable":
  - open PR / `merge_requesting` → **reconcile** (merge or deny); spawn **no** worker.
  - branch, no PR → **hold if recent**; after one poll or human force → mint a **new** attempt with
    `adopt_from_branch`.
  - recovery comments only → liveness hint; hold if recent; else mint **fresh from `master`**.
  - nothing (no branch/PR/recent recovery) → mint **fresh** immediately.
  - **Invariant (unchanged):** never reuse `attempt_id` or write an existing attempt branch;
    `adopt_from_branch` only **reads** the old branch.
- **The "recent" gate is a pure function of canonical GitHub time (R4):**
  `hold_until = latest_recovery_comment_created_at + 1800 + skew_grace`. This requires a new **additive**
  helper `control_log.latest_recovery_with_metadata(comments, attempt_id) → {comment_id, created_at,
  recovery}` (the existing `latest_recovery` discards `created_at`). Worker-authored JSON `ts` and
  session memory are both rejected as the gate source.

**Stop-time control — passive vs active (R6).**
- **Active stop update** (re-invoke `/run-cycle` to resume / stop-now / new `stop_at`): runs **as the
  orchestrator**, acquires the lease, updates `stop_at`, **cancels+recreates Loop B immediately**, runs
  Step 2. The **only** path that honestly claims ~0 latency for **shortening**.
- **Passive raw header edit** while Loop A sleeps: allowed but only **eventually observed** (≤ one poll,
  ~30 min); reconciled (Loop B recreated) on next wake. Discouraged vs the active path because it also
  races the sole-writer model.
- ~0 stop latency holds at the **original** `stop_at` (unedited) via Loop B.

**Kept unchanged (orthogonal correctness machinery):** intra-turn lease fences (R2 — they guard a
manual double-start's same-identity irreversible merge, not the watchdog), attempt-fencing + per-attempt
branches, all merge gates, the check-then-append seq guard, and the `control_log.py` **event schema**
(no new event types; `replay`/dedupe/checkpoints + the 58 existing tests untouched).

**Deleted:** the watchdog job, `watchdog_schedule_id`, takeover damping (replaced by artifact-aware
recovery), and the Tier-0/Tier-1 alert/auto-relaunch machinery.

## Strongest objections & how each resolved

1. **(R1) "Stuck impossible" overclaimed.** A fixed poll self-corrects only **between** turns; an
   intra-turn hang never reschedules. Conceded: narrowed the claim to inter-turn under-dispatch; added
   best-effort deadlines + reconcile-on-timeout; documented the intra-turn-hang reduction → manual resume.
2. **(R2) Binary resume over-trusts a soft header.** Write-then-die = false "alive"; alive-but-late =
   false "dead". Conceded: tri-state + artifact-aware damping; richer advisory diagnostics; human force
   always available. Kept intra-turn lease fences (they are not watchdog leftovers).
3. **(R3) Artifact-aware prose collides with attempt-fencing** (`adopt_from_branch` *is* a fresh
   attempt). Conceded: exact disposition table; "steps 1–6 unchanged" retracted — Step 6/recovery gains
   a disposition substep (prose), schema still untouched.
4. **(R4) The hold gate needs canonical time, not worker `ts` or session memory.** Conceded: additive
   helper `latest_recovery_with_metadata` + tests; hold rule as a pure function of GitHub `created_at`.
   "No code change" retracted; "no schema change / existing tests green" stands.
5. **(R5) Stale stop-trigger under mutable `stop_at`.** Conceded: keep `stop_schedule_id`; Loop B
   demoted to an early-wake (turn decides via Step 2), never force-exit; `phase: exiting` reachable only
   via the legitimate drain path.
6. **(R6) "Recreate Loop B on any edit" assumes the orchestrator is awake.** Conceded: split passive
   (eventual, ≤ one poll) from active (`/run-cycle` resume, ~0 latency) stop updates; Loop B generation
   payload is stale-trigger defense, not edit detection.

## Unresolved tensions

None as a standoff. Two **accepted residuals**, both consequences of locked user decisions, documented
honestly rather than hidden:
- **Intra-turn hang has no in-protocol detection** (manual resume only) — a real reduction vs the
  watchdog, mitigated but not eliminated by best-effort deadlines.
- **Passive `stop_at` edits incur up to one-poll latency** and race the sole-writer model; the active
  `/run-cycle` path is the ~0-latency, sole-writer-clean alternative.

## How it ended

Six rounds (round cap). Substantively converged: the core two-loop + fixed-poll + manual-resume design
was stable from round 2; rounds 3–6 hardened recovery dispositions, the canonical-time hold gate, and
stop-time control. Every objection was conceded and integrated; no live disagreement remained.
