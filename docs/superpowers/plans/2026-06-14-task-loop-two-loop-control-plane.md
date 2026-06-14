# Two-Loop Control Plane Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Collapse the `task-loop` orchestrator control plane from three jobs to two (a fixed-30-min-poll `/loop` orchestrator + a one-time stop early-wake), delete the watchdog, and add an artifact-aware recovery-disposition substep backed by one additive helper.

**Architecture:** Prose change to `run-cycle` SKILL.md + orchestrator-loop.md (loop topology, fixed-poll wake, tri-state manual resume, recovery-disposition table, lease-header diagnostics, stop-time control), plus ONE additive pure helper in `control_log.py` (`latest_recovery_with_metadata`) with tests. No control-event schema change; the 58 existing tests stay green.

**Tech Stack:** Python stdlib `unittest`; Markdown skill/reference prose.

**Source of truth:** `docs/superpowers/specs/2026-06-14-task-loop-two-loop-control-plane-design.md` (Codex-converged) and `…-conclusion.md`.

---

### Task 1: Additive helper `latest_recovery_with_metadata`

**Files:**
- Modify: `task-loop/scripts/control_log.py` (add a function after `latest_recovery`, ends line 77)
- Test: `task-loop/tests/test_control_log.py` (add to `class TestRecoveryComments`, ends line 411)

- [ ] **Step 1: Write the failing tests**

Add to `task-loop/tests/test_control_log.py` inside `class TestRecoveryComments` (after line 411):

```python
    def test_latest_recovery_with_metadata_returns_canonical_created_at(self):
        c1 = ("IC1", TS_EARLY,
              control_log.format_recovery({"attempt_id": "A", "status": "in_progress"}))
        c2 = ("IC2", TS_A,
              control_log.format_recovery({"attempt_id": "A", "status": "pr_open"}))
        meta = control_log.latest_recovery_with_metadata([c1, c2], "A")
        self.assertEqual(meta["comment_id"], "IC2")
        self.assertEqual(meta["created_at"], TS_A)
        self.assertEqual(meta["recovery"]["status"], "pr_open")

    def test_latest_recovery_with_metadata_ignores_other_attempts(self):
        c1 = ("IC1", TS_EARLY,
              control_log.format_recovery({"attempt_id": "A", "status": "pr_open"}))
        c2 = ("IC2", TS_A,
              control_log.format_recovery({"attempt_id": "B", "status": "merge_requested"}))
        meta = control_log.latest_recovery_with_metadata([c1, c2], "A")
        self.assertEqual(meta["comment_id"], "IC1")
        self.assertEqual(meta["created_at"], TS_EARLY)
        self.assertEqual(meta["recovery"]["status"], "pr_open")

    def test_latest_recovery_with_metadata_none_when_absent(self):
        c1 = ("IC1", TS_EARLY,
              control_log.format_recovery({"attempt_id": "A", "status": "pr_open"}))
        self.assertIsNone(control_log.latest_recovery_with_metadata([c1], "C"))

    def test_latest_recovery_with_metadata_last_block_in_one_comment_wins(self):
        # Two recovery blocks for attempt A in a single comment body: the LAST wins,
        # carrying that comment's canonical created_at.
        body = (control_log.format_recovery({"attempt_id": "A", "status": "in_progress"})
                + "\n"
                + control_log.format_recovery({"attempt_id": "A", "status": "merge_requesting"}))
        meta = control_log.latest_recovery_with_metadata([("IC9", TS_B, body)], "A")
        self.assertEqual(meta["comment_id"], "IC9")
        self.assertEqual(meta["created_at"], TS_B)
        self.assertEqual(meta["recovery"]["status"], "merge_requesting")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m unittest task-loop.tests.test_control_log -v 2>&1 | grep -i "metadata\|error\|fail" | head`
(Run from repo root with `task-loop/__init__.py`/`tests/__init__.py` absent — the suite is discovered, so use the discover form below if the dotted path fails.)
Run: `python3 -m unittest discover -s task-loop/tests -q`
Expected: FAIL — `AttributeError: module 'control_log' has no attribute 'latest_recovery_with_metadata'`.

- [ ] **Step 3: Implement the helper**

Insert into `task-loop/scripts/control_log.py` immediately after `latest_recovery` (after line 77, before `filter_new_inbox`):

```python
def latest_recovery_with_metadata(comments: list, attempt_id):
    """Like `latest_recovery`, but return the GitHub-canonical metadata of the
    winning comment, or None.

    Returns `{"comment_id": id, "created_at": created_at, "recovery": rec}` for the
    most recent recovery record tagged with `attempt_id` (LAST match wins, mirroring
    `latest_recovery`), carrying the comment's canonical `created_at` so the
    orchestrator's recovery-disposition "hold if recent" gate keys off durable GitHub
    time, NOT the worker-authored JSON `ts` (skew/spoof-prone) or session memory."""
    found = None
    for (cid, created_at, body) in comments:
        for rec in parse_recovery(body):
            if rec.get("attempt_id") == attempt_id:
                found = {"comment_id": cid, "created_at": created_at, "recovery": rec}
    return found
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m unittest discover -s task-loop/tests -q`
Expected: `OK` (62 tests: 58 existing + 4 new).

- [ ] **Step 5: Commit**

```bash
git add task-loop/scripts/control_log.py task-loop/tests/test_control_log.py
git commit -m "task-loop: add latest_recovery_with_metadata helper for canonical-time recovery hold gate"
```

---

### Task 2: orchestrator-loop.md — topology, wake, lease, recovery dispositions

**Files:**
- Modify: `task-loop/skills/run-cycle/references/orchestrator-loop.md`

Each step is one anchored edit. Use the spec §3–§9 as the wording source.

- [ ] **Step 1: Replace the fast-state header JSON** (current block lines 29–38).

New header block:

```json
{
  "lease": {"owner": "<id>", "expires_at": "<utc ~2x poll>"},
  "last_turn_started_at": "<utc>",
  "last_turn_completed_at": "<utc>",
  "next_wakeup_at": "<utc>",
  "phase": "dispatching|waiting|idle|draining|exiting_pending|exiting",
  "stop_at": "<utc>",
  "drain_deadline_at": null,
  "stop_schedule_id": null
}
```

Update the surrounding prose (lines 24–48) to: drop `watchdog_schedule_id` and the single `heartbeat`; state the header is soft/advisory/last-writer-wins and **sole-written**; describe `last_turn_started_at`/`last_turn_completed_at`/`next_wakeup_at` as **diagnostics that make manual resume informed** (sleeping vs hung-mid-turn vs dead); `expires_at` is the single-coordinator TTL (~2× the 1800 s poll); `stop_schedule_id` is the handle the orchestrator uses to cancel/recreate Loop B; **no sibling job consumes any of it — a human/preflight does.**

- [ ] **Step 2: Replace the "State machine" intro + phase list** (lines 50–76).

Reframe to two loops + fixed poll: the orchestrator is a `/loop` session ending each turn with a **fixed `ScheduleWakeup(1800)`**; **Step 2 stop-check is the sole stop decision**; `phase: exiting` is a **hard terminal guard at turn top** (a stray/late wake reading a clean `exiting` re-audits and stops; only a changed state reverts). Replace the `waiting` bullet's "idle notifications are the primary wake + jittered fallback + shorter backlog wake" with: **every non-terminal phase schedules the same fixed 1800 s wake; idle notifications are no longer part of the wake model.** Keep `dispatching`/`idle`/`draining`/`exiting_pending`/`exiting` meanings; `idle` now also uses the fixed wake.

- [ ] **Step 3: Update §1 Lease & rebuild** (lines 80–88) to add tri-state resume.

After the existing write-then-re-read fence prose, add: on resume/stale-lease, classify the prior lead from the advisory diagnostics — **`likely_alive`** (`next_wakeup_at` AND `expires_at` both future) → **default refuse takeover, allow explicit human force**; **`likely_dead`** (`now ≫ next_wakeup_at`, or `expires_at` well past) → acquire the lease but **observe/reconcile first** (do not eagerly mint attempts). The header is soft, so diagnostics are advisory inputs, never proof; human force is always available. Replace `heartbeat`-refresh references with `expires_at`/`next_wakeup_at`.

- [ ] **Step 4: Rewrite the Control-plane note** — find the paragraph describing loops 1/2/3 (the watchdog/`heartbeat`/`watchdog_schedule_id` prose around lines 43–47) and replace with: **Loop A** (this `/loop` orchestrator, fixed 1800 s wake) + **Loop B** (one-time stop early-wake at `stop_at`; fires into Loop A's session, sets nothing — the woken turn's Step 2 decides; carries a `stop_at`/generation payload as stale-trigger defense; recreated by the orchestrator on an active `stop_at` change). No watchdog.

- [ ] **Step 5: Add the recovery-disposition substep to §6 Dispatch** (insert before the "Dispatchable" bullet, line 195).

Add a **Recovery disposition (before classifying `active`-with-no-live-worker as dispatchable)** block with the exact table from spec §5:
- open PR / `merge_requesting` → reconcile (merge or deny); spawn no worker.
- branch, no PR → **hold if recent**; after one poll or human force → mint a NEW attempt with `adopt_from_branch`.
- recovery comments only → liveness hint; hold if recent; else mint fresh from `master`.
- nothing (no branch/PR/recent recovery) → mint fresh immediately.
- Invariant: never reuse `attempt_id` or write an existing attempt branch; `adopt_from_branch` only reads.
- **Recent gate (pure function of canonical time):** `hold_until = latest_recovery_comment_created_at + 1800 + skew_grace` via `control_log.latest_recovery_with_metadata(comments, current_attempt_id)["created_at"]`; reject worker JSON `ts` and session memory.

- [ ] **Step 6: Delete takeover damping** (lines 226–229, the "Takeover damping" bullet) and any "deferred recovery candidate" wake. Replace its role with a one-line pointer to the Step-5 disposition substep ("artifact-aware recovery replaces the old watchdog-era takeover damping").

- [ ] **Step 7: Rewrite §7 Wait / idle / exit** (lines 258–283) to the fixed poll.

Collapse to: any non-terminal state → **`ScheduleWakeup(1800)`** (one cadence). Remove the idle-notification-primary bullet, the jittered/backlog-shorter bullet, and the deferred-recovery-probe bullet. Keep `draining` (until `drain_deadline_at` → `orphaned_acknowledged`), `exiting_pending` (audit + cooldown), `exiting` (stop rescheduling). Add: **`phase: exiting` is a hard terminal guard** — a stray wake re-audits and stops; on exit the loop stops rescheduling.

- [ ] **Step 8: Update the Recovery (cold resume) section** (lines 336–367) so it names manual `/run-cycle` resume as the death/hang recovery path, points orphaned re-entry at the Step-5 disposition table, and references `latest_recovery_with_metadata` for the recent-gate; keep the per-attempt-branch / `adopt_from_branch` semantics.

- [ ] **Step 9: Add a Stop-time control note** (near §2/§7 or the Control-plane note): **active** stop update (re-invoke `/run-cycle`: runs as orchestrator, updates `stop_at`, cancels+recreates Loop B via `stop_schedule_id`, runs Step 2 — only ~0-latency path for shortening, sole-writer-clean) vs **passive** raw header edit (eventual, ≤ one poll; recreated on next wake; discouraged).

- [ ] **Step 10: Grep for leftovers and commit.**

```bash
grep -n "watchdog\|heartbeat\|idle notification\|jitter\|Tier-0\|Tier-1\|takeover damping" task-loop/skills/run-cycle/references/orchestrator-loop.md
```
Expected: only intentional mentions (e.g. a historical note). Fix any stragglers, then:
```bash
git add task-loop/skills/run-cycle/references/orchestrator-loop.md
git commit -m "task-loop: orchestrator-loop two-loop fixed-poll model + artifact-aware recovery"
```

---

### Task 3: SKILL.md — control plane, setup, turn §7, invariants

**Files:**
- Modify: `task-loop/skills/run-cycle/SKILL.md`

- [ ] **Step 1: Rewrite the "Control plane" section** (lines 43–78) from "one live loop + two guard jobs" to **"one live fixed-interval loop + one stop early-wake."** Describe Loop A (fixed 1800 s poll, monitor→merge→dispatch over the full re-derived frontier, self-bounds via Step 2, `phase: exiting` hard terminal guard) and Loop B (one-time stop early-wake at `stop_at`; the woken turn's Step 2 decides; recreated on active `stop_at` change). Delete the watchdog tiers and the `heartbeat`/`watchdog_schedule_id` prose. State death/intra-turn-hang recovery = **manual `/run-cycle` resume** (rebuilds 100% from GitHub); fixed poll structurally prevents inter-turn under-dispatch only.

- [ ] **Step 2: Update Setup** (lines 80–115): drop step 5 (create watchdog); keep the stop job (now "create Loop B — the stop early-wake," recording `stop_schedule_id`). In the header description, drop `watchdog_schedule_id`; keep `stop_at`, `lease`, `stop_schedule_id`, and the diagnostics. Step 7's self-bound prose stays (fixed wake capped to `stop_at`).

- [ ] **Step 3: Rewrite the high-level turn §7** (lines 158–163): not-draining → fixed 30-min wake; drained → exit; `phase: exiting` hard terminal guard. Remove "Teammate idle notifications are the primary wake" and the jittered/backlog/deferred-recovery language.

- [ ] **Step 4: Update Hard invariants** (lines 166–184): keep "Sole integrator," "Single writer," "Merge gates," "Proactive, seat-capped dispatch." Reword "Continuous service" to the fixed-poll model (no idle-notification wake; a scheduled stop early-wake; manual resume on death/hang). Remove watchdog references.

- [ ] **Step 5: Grep + commit.**

```bash
grep -n "watchdog\|heartbeat\|guard job\|idle notification\|Tier-0\|Tier-1\|three cooperating" task-loop/skills/run-cycle/SKILL.md
```
Fix stragglers, then:
```bash
git add task-loop/skills/run-cycle/SKILL.md
git commit -m "task-loop: run-cycle SKILL two-loop control plane + fixed-poll turn"
```

---

### Task 4: Design-spec §12 + version bump

**Files:**
- Modify: `docs/superpowers/specs/2026-06-13-task-loop-plugin-design.md` (control-plane / watchdog section)
- Modify: `task-loop/.claude-plugin/plugin.json`

- [ ] **Step 1: Update the older design spec's control-plane prose.**

```bash
grep -n "watchdog\|three\b\|Loop 3\|heartbeat\|external watchdog" docs/superpowers/specs/2026-06-13-task-loop-plugin-design.md | head
```
At the relevant section (§12 and the §1 "/loop self-paced" line ~30), add a short forward-pointer note: the control plane is superseded by the two-loop fixed-poll model in `2026-06-14-task-loop-two-loop-control-plane-design.md` (watchdog removed; manual resume only). Do not rewrite the whole spec — a dated note + pointer is enough.

- [ ] **Step 2: Bump the plugin version.**

In `task-loop/.claude-plugin/plugin.json`, change `"version": "0.8.1"` → `"version": "0.9.0"`.

- [ ] **Step 3: Commit.**

```bash
git add docs/superpowers/specs/2026-06-13-task-loop-plugin-design.md task-loop/.claude-plugin/plugin.json
git commit -m "task-loop: note two-loop supersession in design spec; bump to 0.9.0"
```

---

### Task 5: Full verification

**Files:** none (verification only).

- [ ] **Step 1: Run the full suite.**

Run: `python3 -m unittest discover -s task-loop/tests -q`
Expected: `OK` (62 tests).

- [ ] **Step 2: Validate plugin.json.**

Run: `python3 -c "import json;json.load(open('task-loop/.claude-plugin/plugin.json'))" && echo VALID`
Expected: `VALID`.

- [ ] **Step 3: Final leftover sweep across the skill.**

Run: `grep -rn "watchdog\|Tier-0\|Tier-1\|watchdog_schedule_id" task-loop/skills/ ; echo done`
Expected: no unintended hits (only deliberate historical references, if any).

- [ ] **Step 4: Confirm no schema/protocol drift.**

Run: `git diff --stat c2fe9a0 -- task-loop/scripts/control_log.py`
Expected: only the additive `latest_recovery_with_metadata` (no edits to `replay`, `_STATUS_BY_TYPE`, `_REQUIRED_FIELDS`).
