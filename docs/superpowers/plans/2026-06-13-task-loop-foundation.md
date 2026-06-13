# task-loop Foundation (Phase 0 + Phase 1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** De-risk the experimental Agent-Teams primitives (Phase 0 spike), then build and test the single-sequencer **control protocol** (Phase 1) that the whole orchestrator/worker system rests on.

**Architecture:** A single pinned GitHub "control issue" is the one canonical ordered event log. Workers post *unsequenced* UUID-tagged inbox events to their own task issues; the orchestrator is the *only* sequencer — it ingests inbox events, dedupes by UUID, assigns a monotonic `seq`, and emits normalized `CONTROL_EVENT` comments. Fast state is rebuilt by replaying the control issue. The protocol logic is pure Python (stdlib only) so it is deterministic and unit-testable without GitHub or Agent Teams.

**Tech Stack:** Python 3 standard library (`json`, `re`, `pathlib`, `unittest`), `gh` CLI (thin adapter, integration-tested), Claude Code Agent Teams + `/loop` (Phase 0 spike only).

**Scope:** This plan delivers Phase 0 (a throwaway spike + findings note) and Phase 1 (the tested control-protocol library + gh adapter). It does **not** build the skills/agent/orchestrator prose — those are Phase 2+, each its own plan (see "Follow-on plans"), because their exact steps depend on Phase 0's findings about the real primitives.

> **Execution note (2026-06-13):** Phase 1 shipped standalone; the **interactive Phase 0 spike was deferred** (it needs a live `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` session). This is safe precisely because Phase 1 has *zero* dependency on the Agent-Teams/`/loop` primitives — so the plugin-registration step that Phase 0 Task 0.2 would have done was performed in Phase 1 Task 1.8 instead.

**Spec:** `docs/superpowers/specs/2026-06-13-task-loop-plugin-design.md` (§8 control protocol, §16 phasing).

---

## File Structure

| File | Responsibility |
|---|---|
| `task-loop/scripts/control_log.py` | Pure protocol logic: event format/parse, idempotent inbox filtering, monotonic seq assignment, replay/fold to fast state. **No I/O.** |
| `task-loop/scripts/gh_store.py` | Thin `gh`-CLI adapter: read comments from an issue, post a comment. The only module that touches GitHub. |
| `task-loop/tests/test_control_log.py` | `unittest` for `control_log.py` (round-trip, idempotency, ordering, replay, gap detection). |
| `task-loop/tests/test_gh_store.py` | `unittest` for `gh_store.py` parsing, with `gh` invocation mocked via `subprocess` injection. |
| `task-loop/PHASE0_FINDINGS.md` | Phase 0 spike results (reference doc; records what the real primitives do). |
| `task-loop/.claude-plugin/plugin.json` | Plugin manifest (added in Phase 1, last task). |

**Event JSON shapes** (single source of truth — used across all tasks):

```python
# Inbox event (worker -> its own task issue, UNSEQUENCED):
{"kind": "inbox", "uuid": "f3c1...", "task_id": "T12", "spawned_plan_revision": 4,
 "type": "MERGE_REQUEST", "pr_head_sha": "abc123", "ts": "2026-06-13T10:00:00Z"}
# type is one of: "PLAN_FINDING", "MERGE_REQUEST". pr_head_sha only on MERGE_REQUEST.

# Control event (orchestrator -> control issue, SEQUENCED). Two families:
# (1) orchestrator-originated (no source provenance):
{"kind": "control", "seq": 2, "type": "TASK_CREATED", "task_id": "T12",
 "plan_revision": 4, "issue_number": 12, "ts": "..."}
{"kind": "control", "seq": 5, "type": "PLAN_REVISION_BUMP", "plan_revision": 5,
 "proposal_sha": "deadbeef", "ts": "..."}
# orchestrator-originated types: "TASK_CREATED" (carries issue_number),
# "TASK_DISPATCHED", "PLAN_REVISION_BUMP" (carries proposal_sha),
# "TASK_STALE", "TASK_REVISION_COMPATIBLE".
# (2) inbox-DERIVED (carry source provenance so replay reconstructs dedupe+watermark):
{"kind": "control", "seq": 7, "type": "MERGE_GRANTED", "task_id": "T12",
 "plan_revision": 4, "pr_head_sha": "abc123",
 "source_issue": 12, "source_comment_id": 111, "source_uuid": "f3c1...", "ts": "..."}
# inbox-derived types: "MERGE_GRANTED"/"MERGE_DENIED" (require pr_head_sha + source_*),
# "PLAN_FINDING_RECORDED" (require source_*). Every ingested inbox uuid produces
# exactly one inbox-derived control event, so replay alone reconstructs what was ingested.
```

Both are serialized as a fenced block with info-string `task-loop-event`, one JSON object per block.

**Recovery model (why the shapes above):** `replay()` rebuilds, *from the control log alone*, the dedupe set (`seen_source_uuids`) and the per-issue scan watermark (`last_ingested_comment_id_by_issue`) — so a cold-resumed orchestrator never re-ingests a comment and knows every task issue to scan. `TASK_CREATED.issue_number` makes a freshly-created task issue scannable *before* its worker's first inbox event. Note: `proposal_sha`/`pr_head_sha` are *carried* here so the Phase 2 orchestrator can enforce the revision-materialization and head-SHA merge gates; Phase 1 tests that the data is present and validated, not that the gates fire (that is Phase 2).

---

## Phase 0 — Primitive spike (throwaway, runnable)

> Goal: prove the Claude Code primitive contract *before* building on it. Output is `task-loop/PHASE0_FINDINGS.md`. If a primitive cannot be made to work, STOP and adapt the spec before Phase 1. These tasks are verification, not TDD.

### Task 0.1: Confirm Agent Teams + loop availability

**Files:**
- Create: `task-loop/PHASE0_FINDINGS.md`

- [ ] **Step 1: Check enablement + version**

Run:
```bash
claude --version
echo "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=${CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS:-unset}"
grep -r CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS ~/.claude/settings.json 2>/dev/null || echo "not in settings.json"
```
Expected: version ≥ v2.1.32; the env var resolves to `1` (or is set in settings.json). If unset, set it in `~/.claude/settings.json` `env` block and restart, then re-check.

- [ ] **Step 2: Record the result**

Write `task-loop/PHASE0_FINDINGS.md` with a heading `## 0.1 Enablement` and the observed version + flag state, and whether a restart was needed.

### Task 0.2: Prove a plugin-packaged agent resolves as a teammate `agentType`

**Files:**
- Create: `task-loop/agents/cycle-worker.md` (minimal stub for the spike)
- Create: `task-loop/.claude-plugin/plugin.json` (minimal, so the agent is discoverable)
- Modify: `task-loop/PHASE0_FINDINGS.md`

- [ ] **Step 1: Write a minimal worker agent stub**

`task-loop/agents/cycle-worker.md`:
```markdown
---
name: cycle-worker
description: Spike stub — confirms a plugin-packaged agent resolves as a teammate agentType.
tools: Bash, Read, Write
---
You are a spike worker. When spawned, read your spawn prompt, write the single line
`SPIKE_OK <task_id> <plan_revision>` to a file named `spike-<task_id>.txt` in the repo
root using Bash, then report "done" and go idle.
```

- [ ] **Step 2: Write a minimal plugin manifest**

`task-loop/.claude-plugin/plugin.json`:
```json
{
  "name": "task-loop",
  "description": "Autonomous orchestrated cycle-driven development (spike).",
  "version": "0.0.1"
}
```

- [ ] **Step 3: Register + install the local plugin so the agent is discoverable**

Add `{ "name": "task-loop", "source": "./task-loop" }` to the `plugins` array in
`.claude-plugin/marketplace.json` (this repo is itself a marketplace), then install/enable
the local plugin so `cycle-worker` resolves as an `agentType`:
```bash
python -c "import json; json.load(open('.claude-plugin/marketplace.json')); print('marketplace OK')"
```
Then in Claude Code, add the local marketplace and install: `/plugin` → add this repo as a
local marketplace → install `task-loop` (or `claude plugin marketplace add .` then
`claude plugin install task-loop`). Confirm `cycle-worker` appears as an available agent
type. **Without this step the spawn in Step 4 has no agent to resolve.**

- [ ] **Step 4: Spawn one teammate using that agentType and pass metadata**

In a Claude Code session with the plugin installed and teams enabled, instruct the lead:
"Create an agent team and spawn exactly one teammate using the `cycle-worker` agent type, with the prompt: `task_id=T1 plan_revision=4`. Wait for its idle/completion notification."

- [ ] **Step 5: Verify and record**

Run:
```bash
cat spike-T1.txt 2>/dev/null
```
Expected: `SPIKE_OK T1 4`. Record under `## 0.2 agentType + spawn + metadata`: whether the agent resolved by name, whether metadata reached it, and whether the lead received an idle notification. Note the exact tool calls the lead used (TeamCreate/TaskCreate/spawn) for Phase 2 reference. Delete `spike-T1.txt` afterward.

### Task 0.3: Prove `ScheduleWakeup` from the lead inside `/loop`, and the stop-signal primitive

**Files:**
- Modify: `task-loop/PHASE0_FINDINGS.md`

- [ ] **Step 1: Test loop entry + self-wake**

In a session, run `/loop` self-paced with a trivial prompt that calls `ScheduleWakeup` once with a 60s delay, then check that the harness re-invokes. Record whether `/loop` can be entered/required from a skill and whether `ScheduleWakeup` fired from inside it.

- [ ] **Step 2: Test the stop-signal writer primitive**

Attempt the intended stop-writer: a `CronCreate`/`schedule` job that writes `.claude/task-loop/stop-request.json` atomically. If `CronCreate` is unavailable/unsuitable, fall back to documenting a background scheduled shell job (e.g. `Bash(run_in_background)` that sleeps then writes the file via temp+rename).

- [ ] **Step 3: Record the contract**

Under `## 0.3 loop + ScheduleWakeup + stop-writer`, record exactly which primitive works for each role and the chosen stop-writer mechanism + fallback. **This section is the input to Phase 2's `run-cycle` design.**

### Task 0.4: Prove worker skill-dependency detection

**Files:**
- Modify: `task-loop/PHASE0_FINDINGS.md`

- [ ] **Step 1: Probe for a required skill**

Determine a reliable way to detect whether `superpowers:brainstorming` and `dev-skills:discuss-with-codex` are available before relying on them (e.g. check installed plugin dirs under `~/.claude/plugins`, or attempt-and-catch). Record the chosen detection method.

- [ ] **Step 2: Commit the Phase 0 findings**

```bash
git add task-loop/PHASE0_FINDINGS.md task-loop/agents/cycle-worker.md task-loop/.claude-plugin/plugin.json
git commit -m "task-loop: Phase 0 primitive spike findings"
```

> **Gate:** if any primitive in 0.2–0.4 cannot be made to work, STOP and revise the spec (§7/§12/§16) before starting Phase 1.

---

## Phase 1 — Control protocol (TDD, pure Python)

> Build `control_log.py` (pure logic) test-first, then the thin `gh_store.py` adapter. No Agent Teams needed — workers are simulated by posting inbox dicts.

### Task 1.1: Event format + parse (round-trip serialization)

**Files:**
- Create: `task-loop/scripts/control_log.py`
- Test: `task-loop/tests/test_control_log.py`

- [ ] **Step 1: Write the failing test**

`task-loop/tests/test_control_log.py`:
```python
import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "control_log", ROOT / "scripts" / "control_log.py"
)
control_log = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(control_log)


class TestFormatParse(unittest.TestCase):
    def test_round_trip_single_event(self):
        event = {"kind": "inbox", "uuid": "u1", "task_id": "T1",
                 "spawned_plan_revision": 4, "type": "PLAN_FINDING",
                 "ts": "2026-06-13T00:00:00Z"}
        body = control_log.format_event(event)
        self.assertIn("```task-loop-event", body)
        parsed = control_log.parse_events(body)
        self.assertEqual(parsed, [event])

    def test_parse_ignores_surrounding_prose(self):
        event = {"kind": "control", "seq": 7, "type": "MERGE_GRANTED",
                 "task_id": "T1", "plan_revision": 4, "source_uuid": "u1",
                 "ts": "2026-06-13T00:00:00Z"}
        body = "Some human note.\n\n" + control_log.format_event(event) + "\n\ntrailing text"
        self.assertEqual(control_log.parse_events(body), [event])

    def test_parse_returns_empty_for_no_event(self):
        self.assertEqual(control_log.parse_events("just a comment"), [])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest -v task-loop.tests.test_control_log` (from repo root; or `python task-loop/tests/test_control_log.py`)
Expected: FAIL — `control_log.py` does not exist / `format_event` undefined.

- [ ] **Step 3: Write minimal implementation**

`task-loop/scripts/control_log.py`:
```python
"""Pure, deterministic control-protocol logic for the task-loop plugin.

No I/O. GitHub access lives in gh_store.py. Stdlib only.
"""
import json
import re

EVENT_FENCE = "task-loop-event"
_FENCE_RE = re.compile(
    r"```" + EVENT_FENCE + r"\s*\n(.*?)\n```", re.DOTALL
)


def format_event(event: dict) -> str:
    """Serialize one event as a fenced ```task-loop-event JSON block."""
    return "```{fence}\n{body}\n```".format(
        fence=EVENT_FENCE, body=json.dumps(event, sort_keys=True)
    )


def parse_events(comment_body: str) -> list:
    """Extract all task-loop-event JSON objects from a comment body, in order."""
    return [json.loads(m.group(1)) for m in _FENCE_RE.finditer(comment_body)]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest -v task-loop.tests.test_control_log`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add task-loop/scripts/control_log.py task-loop/tests/test_control_log.py
git commit -m "task-loop: control_log event format/parse round-trip"
```

### Task 1.2: Idempotent inbox filtering (dedupe by UUID)

**Files:**
- Modify: `task-loop/scripts/control_log.py`
- Test: `task-loop/tests/test_control_log.py`

- [ ] **Step 1: Write the failing test**

Append to `test_control_log.py`:
```python
class TestFilterNewInbox(unittest.TestCase):
    def _ev(self, uuid):
        return {"kind": "inbox", "uuid": uuid, "task_id": "T1",
                "spawned_plan_revision": 1, "type": "PLAN_FINDING",
                "ts": "2026-06-13T00:00:00Z"}

    def test_drops_seen_uuids_preserves_order(self):
        events = [self._ev("a"), self._ev("b"), self._ev("c")]
        fresh = control_log.filter_new_inbox(events, seen_uuids={"b"})
        self.assertEqual([e["uuid"] for e in fresh], ["a", "c"])

    def test_dedupes_repeats_within_batch(self):
        events = [self._ev("a"), self._ev("a"), self._ev("b")]
        fresh = control_log.filter_new_inbox(events, seen_uuids=set())
        self.assertEqual([e["uuid"] for e in fresh], ["a", "b"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest -v task-loop.tests.test_control_log`
Expected: FAIL — `filter_new_inbox` undefined.

- [ ] **Step 3: Write minimal implementation**

Append to `control_log.py`:
```python
def filter_new_inbox(inbox_events: list, seen_uuids) -> list:
    """Return inbox events whose uuid has not been seen, in order, deduping
    repeats within the batch. `seen_uuids` is any container supporting `in`."""
    seen = set(seen_uuids)
    fresh = []
    for event in inbox_events:
        uuid = event["uuid"]
        if uuid in seen:
            continue
        seen.add(uuid)
        fresh.append(event)
    return fresh
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest -v task-loop.tests.test_control_log`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add task-loop/scripts/control_log.py task-loop/tests/test_control_log.py
git commit -m "task-loop: idempotent inbox dedupe by uuid"
```

### Task 1.3: Monotonic seq assignment

**Files:**
- Modify: `task-loop/scripts/control_log.py`
- Test: `task-loop/tests/test_control_log.py`

- [ ] **Step 1: Write the failing test**

Append:
```python
class TestAssignSeq(unittest.TestCase):
    def test_assigns_increasing_seq_from_last(self):
        events = [{"type": "TASK_CREATED", "task_id": "T1"},
                  {"type": "TASK_CREATED", "task_id": "T2"}]
        stamped, new_last = control_log.assign_seq(events, last_seq=5)
        self.assertEqual([e["seq"] for e in stamped], [6, 7])
        self.assertEqual(new_last, 7)

    def test_empty_is_noop(self):
        stamped, new_last = control_log.assign_seq([], last_seq=5)
        self.assertEqual(stamped, [])
        self.assertEqual(new_last, 5)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest -v task-loop.tests.test_control_log`
Expected: FAIL — `assign_seq` undefined.

- [ ] **Step 3: Write minimal implementation**

Append:
```python
def assign_seq(events: list, last_seq: int):
    """Stamp each event with a monotonically increasing integer `seq` starting
    at last_seq+1. Returns (stamped_events, new_last_seq). Does not mutate input."""
    stamped = []
    seq = last_seq
    for event in events:
        seq += 1
        stamped.append({**event, "seq": seq})
    return stamped, seq
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest -v task-loop.tests.test_control_log`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add task-loop/scripts/control_log.py task-loop/tests/test_control_log.py
git commit -m "task-loop: monotonic seq assignment"
```

### Task 1.4: Replay/fold control events to fast state (+ gap detection)

**Files:**
- Modify: `task-loop/scripts/control_log.py`
- Test: `task-loop/tests/test_control_log.py`

- [ ] **Step 1: Write the failing test**

Append:
```python
class TestReplay(unittest.TestCase):
    def _events(self):
        # Valid log: revision materialized (proposal_sha), task created on issue 12,
        # dispatched, merge granted from inbox uuid u1 (comment 111 on issue 12).
        return [
            {"kind": "control", "seq": 1, "type": "PLAN_REVISION_BUMP",
             "plan_revision": 1, "proposal_sha": "deadbeef", "ts": "t"},
            {"kind": "control", "seq": 2, "type": "TASK_CREATED", "task_id": "T1",
             "plan_revision": 1, "issue_number": 12, "ts": "t"},
            {"kind": "control", "seq": 3, "type": "TASK_DISPATCHED", "task_id": "T1",
             "plan_revision": 1, "ts": "t"},
            {"kind": "control", "seq": 4, "type": "MERGE_GRANTED", "task_id": "T1",
             "plan_revision": 1, "pr_head_sha": "abc", "source_issue": 12,
             "source_comment_id": 111, "source_uuid": "u1", "ts": "t"},
        ]

    def test_folds_to_expected_state(self):
        state = control_log.replay(self._events())
        self.assertEqual(state["current_plan_revision"], 1)
        self.assertEqual(state["current_proposal_sha"], "deadbeef")
        self.assertEqual(state["last_seq"], 4)
        self.assertEqual(state["tasks"]["T1"]["status"], "merged")
        self.assertEqual(state["tasks"]["T1"]["issue_number"], 12)
        self.assertEqual(state["tasks"]["T1"]["pr_head_sha"], "abc")

    def test_reconstructs_seen_uuids_and_watermark(self):
        # Cold-resume idempotency state is rebuilt from the log alone.
        state = control_log.replay(self._events())
        self.assertEqual(state["seen_source_uuids"], {"u1"})
        self.assertEqual(state["source_uuid_to_seq"]["u1"], 4)
        self.assertEqual(state["last_ingested_comment_id_by_issue"][12], 111)

    def test_task_issue_discovery_without_inbox_events(self):
        # A task created+dispatched but no inbox-derived events: issue 12 must still be
        # scannable on cold resume (watermark initialized to 0), and a fresh uuid is new.
        events = [
            {"kind": "control", "seq": 1, "type": "PLAN_REVISION_BUMP",
             "plan_revision": 1, "proposal_sha": "deadbeef", "ts": "t"},
            {"kind": "control", "seq": 2, "type": "TASK_CREATED", "task_id": "T1",
             "plan_revision": 1, "issue_number": 12, "ts": "t"},
            {"kind": "control", "seq": 3, "type": "TASK_DISPATCHED", "task_id": "T1",
             "plan_revision": 1, "ts": "t"},
        ]
        state = control_log.replay(events)
        self.assertEqual(state["last_ingested_comment_id_by_issue"][12], 0)
        inbox = [{"kind": "inbox", "uuid": "u9", "task_id": "T1",
                  "spawned_plan_revision": 1, "type": "MERGE_REQUEST",
                  "pr_head_sha": "z", "ts": "t"}]
        fresh = control_log.filter_new_inbox(inbox, seen_uuids=state["seen_source_uuids"])
        self.assertEqual([e["uuid"] for e in fresh], ["u9"])

    def test_revision_bump_updates_current(self):
        events = self._events() + [
            {"kind": "control", "seq": 5, "type": "PLAN_REVISION_BUMP",
             "plan_revision": 2, "proposal_sha": "cafe", "ts": "t"},
            {"kind": "control", "seq": 6, "type": "TASK_CREATED", "task_id": "T2",
             "plan_revision": 2, "issue_number": 13, "ts": "t"},
            {"kind": "control", "seq": 7, "type": "TASK_STALE", "task_id": "T2",
             "plan_revision": 2, "ts": "t"},
        ]
        state = control_log.replay(events)
        self.assertEqual(state["current_plan_revision"], 2)
        self.assertEqual(state["tasks"]["T2"]["status"], "stale")

    def test_replay_is_idempotent(self):
        events = self._events()
        self.assertEqual(control_log.replay(events), control_log.replay(events))

    def test_raises_on_seq_gap(self):
        events = [{"kind": "control", "seq": 1, "type": "PLAN_REVISION_BUMP",
                   "plan_revision": 1, "proposal_sha": "x", "ts": "t"},
                  {"kind": "control", "seq": 3, "type": "TASK_CREATED", "task_id": "T1",
                   "plan_revision": 1, "issue_number": 12, "ts": "t"}]
        with self.assertRaises(ValueError):
            control_log.replay(events)

    def test_raises_on_duplicate_seq(self):
        events = [{"kind": "control", "seq": 1, "type": "PLAN_REVISION_BUMP",
                   "plan_revision": 1, "proposal_sha": "x", "ts": "t"},
                  {"kind": "control", "seq": 1, "type": "TASK_CREATED", "task_id": "T1",
                   "plan_revision": 1, "issue_number": 12, "ts": "t"}]
        with self.assertRaises(ValueError):
            control_log.replay(events)

    def test_revision_bump_requires_proposal_sha(self):
        events = [{"kind": "control", "seq": 1, "type": "PLAN_REVISION_BUMP",
                   "plan_revision": 1, "ts": "t"}]
        with self.assertRaises(ValueError):
            control_log.replay(events)

    def test_merge_granted_requires_pr_head_sha(self):
        events = [{"kind": "control", "seq": 1, "type": "MERGE_GRANTED", "task_id": "T1",
                   "plan_revision": 1, "source_issue": 12, "source_comment_id": 111,
                   "source_uuid": "u1", "ts": "t"}]
        with self.assertRaises(ValueError):
            control_log.replay(events)

    def test_merge_granted_requires_source_uuid(self):
        events = [{"kind": "control", "seq": 1, "type": "MERGE_GRANTED", "task_id": "T1",
                   "plan_revision": 1, "pr_head_sha": "abc", "source_issue": 12,
                   "source_comment_id": 111, "ts": "t"}]
        with self.assertRaises(ValueError):
            control_log.replay(events)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest -v task-loop.tests.test_control_log`
Expected: FAIL — `replay` undefined.

- [ ] **Step 3: Write minimal implementation**

Append:
```python
_STATUS_BY_TYPE = {
    "TASK_CREATED": "ready",
    "TASK_DISPATCHED": "active",
    "MERGE_GRANTED": "merged",
    "MERGE_DENIED": "stale",
    "TASK_STALE": "stale",
    "TASK_REVISION_COMPATIBLE": "active",
}

# Required fields per control-event type (beyond kind/seq/type/ts).
_REQUIRED_FIELDS = {
    "PLAN_REVISION_BUMP": ("plan_revision", "proposal_sha"),
    "TASK_CREATED": ("task_id", "plan_revision", "issue_number"),
    "TASK_DISPATCHED": ("task_id", "plan_revision"),
    "TASK_STALE": ("task_id", "plan_revision"),
    "TASK_REVISION_COMPATIBLE": ("task_id", "plan_revision"),
    "MERGE_GRANTED": ("task_id", "plan_revision", "pr_head_sha",
                      "source_issue", "source_comment_id", "source_uuid"),
    "MERGE_DENIED": ("task_id", "plan_revision", "pr_head_sha",
                     "source_issue", "source_comment_id", "source_uuid"),
    "PLAN_FINDING_RECORDED": ("task_id", "source_issue", "source_comment_id",
                              "source_uuid"),
}


def _validate(event):
    """Raise ValueError if a control event is malformed for its type."""
    if event.get("kind") != "control":
        raise ValueError("not a control event: kind=%r" % (event.get("kind"),))
    etype = event.get("type")
    if etype not in _REQUIRED_FIELDS:
        raise ValueError("unknown control event type: %r" % (etype,))
    if "ts" not in event:
        raise ValueError("control event missing ts at seq=%r" % (event.get("seq"),))
    for field in _REQUIRED_FIELDS[etype]:
        if event.get(field) in (None, ""):
            raise ValueError("%s missing required field %r" % (etype, field))


def replay(control_events: list) -> dict:
    """Fold seq-ordered control events into recoverable fast state. Pure; raises
    ValueError on a seq gap/duplicate or a schema violation. Reconstructs the dedupe
    set and per-issue scan watermark FROM THE LOG, so a cold resume is exact."""
    events = sorted(control_events, key=lambda e: e["seq"])
    state = {
        "current_plan_revision": 0,
        "current_proposal_sha": None,
        "last_seq": 0,
        "tasks": {},
        "seen_source_uuids": set(),
        "source_uuid_to_seq": {},
        "last_ingested_comment_id_by_issue": {},
    }
    expected = 0
    for event in events:
        expected += 1
        if event["seq"] != expected:
            raise ValueError(
                "non-contiguous control log: expected seq %d, got %d"
                % (expected, event["seq"])
            )
        _validate(event)
        etype = event["type"]
        if etype == "PLAN_REVISION_BUMP":
            state["current_plan_revision"] = event["plan_revision"]
            state["current_proposal_sha"] = event["proposal_sha"]
        else:
            task = state["tasks"].setdefault(
                event["task_id"],
                {"status": None, "plan_revision": None, "issue_number": None,
                 "pr_head_sha": None},
            )
            task["status"] = _STATUS_BY_TYPE.get(etype, task["status"])
            if event.get("plan_revision") is not None:
                task["plan_revision"] = event["plan_revision"]
            if etype == "TASK_CREATED":
                task["issue_number"] = event["issue_number"]
                # Discover the task issue so a cold resume scans it even before any
                # inbox event has been ingested from it.
                state["last_ingested_comment_id_by_issue"].setdefault(
                    event["issue_number"], 0
                )
            if event.get("pr_head_sha"):
                task["pr_head_sha"] = event["pr_head_sha"]
        # Inbox-derived events carry source provenance -> rebuild dedupe + watermark.
        if event.get("source_uuid"):
            state["seen_source_uuids"].add(event["source_uuid"])
            state["source_uuid_to_seq"][event["source_uuid"]] = event["seq"]
            issue = event["source_issue"]
            prev = state["last_ingested_comment_id_by_issue"].get(issue, 0)
            state["last_ingested_comment_id_by_issue"][issue] = max(
                prev, event["source_comment_id"]
            )
        state["last_seq"] = event["seq"]
    return state
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest -v task-loop.tests.test_control_log`
Expected: PASS (all classes).

- [ ] **Step 5: Commit**

```bash
git add task-loop/scripts/control_log.py task-loop/tests/test_control_log.py
git commit -m "task-loop: replay/fold control events with gap detection"
```

### Task 1.5: End-to-end protocol test (worker inbox → orchestrator ingest → replay)

**Files:**
- Test: `task-loop/tests/test_control_log.py`

- [ ] **Step 1: Write the failing test**

Append — this composes the units the way the orchestrator will use them:
```python
class TestEndToEnd(unittest.TestCase):
    def test_ingest_emit_replay_and_cold_resume_dedupe(self):
        # Worker posts the same MERGE_REQUEST twice (uuid u1) on its task issue 12.
        inbox = [
            {"kind": "inbox", "uuid": "u1", "task_id": "T1", "spawned_plan_revision": 1,
             "type": "MERGE_REQUEST", "pr_head_sha": "abc", "ts": "t"},
            {"kind": "inbox", "uuid": "u1", "task_id": "T1", "spawned_plan_revision": 1,
             "type": "MERGE_REQUEST", "pr_head_sha": "abc", "ts": "t"},
        ]
        seeded = [
            {"kind": "control", "seq": 1, "type": "PLAN_REVISION_BUMP",
             "plan_revision": 1, "proposal_sha": "deadbeef", "ts": "t"},
            {"kind": "control", "seq": 2, "type": "TASK_CREATED", "task_id": "T1",
             "plan_revision": 1, "issue_number": 12, "ts": "t"},
            {"kind": "control", "seq": 3, "type": "TASK_DISPATCHED", "task_id": "T1",
             "plan_revision": 1, "ts": "t"},
        ]
        state = control_log.replay(seeded)
        # Dedupe uses the set reconstructed from the log (empty so far) -> one fresh.
        fresh = control_log.filter_new_inbox(inbox, seen_uuids=state["seen_source_uuids"])
        self.assertEqual(len(fresh), 1)
        # Orchestrator grants the merge, stamping source provenance from the inbox event.
        decision = {"kind": "control", "type": "MERGE_GRANTED", "task_id": "T1",
                    "plan_revision": 1, "pr_head_sha": fresh[0]["pr_head_sha"],
                    "source_issue": 12, "source_comment_id": 111,
                    "source_uuid": fresh[0]["uuid"], "ts": "t"}
        stamped, new_last = control_log.assign_seq([decision], state["last_seq"])
        self.assertEqual(stamped[0]["seq"], 4)
        final = control_log.replay(seeded + stamped)
        self.assertEqual(final["tasks"]["T1"]["status"], "merged")
        self.assertEqual(final["last_seq"], 4)
        # COLD RESUME: a fresh orchestrator replays the log and re-reads issue 12's same
        # comment (uuid u1). It must ingest NOTHING new — the dedupe invariant.
        resumed = control_log.replay(seeded + stamped)
        re_fresh = control_log.filter_new_inbox(
            inbox, seen_uuids=resumed["seen_source_uuids"])
        self.assertEqual(re_fresh, [])
        self.assertEqual(resumed["last_ingested_comment_id_by_issue"][12], 111)
```

- [ ] **Step 2: Run test to verify it passes (no new code expected)**

Run: `python -m unittest -v task-loop.tests.test_control_log`
Expected: PASS — composing existing functions. If it fails, fix the unit that broke (do not add new behavior here).

- [ ] **Step 3: Commit**

```bash
git add task-loop/tests/test_control_log.py
git commit -m "task-loop: end-to-end ingest->emit->replay protocol test"
```

### Task 1.6: gh adapter — read issue comments

**Files:**
- Create: `task-loop/scripts/gh_store.py`
- Test: `task-loop/tests/test_gh_store.py`

- [ ] **Step 1: Write the failing test (inject a fake runner)**

`task-loop/tests/test_gh_store.py`:
```python
import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("gh_store", ROOT / "scripts" / "gh_store.py")
gh_store = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(gh_store)


class TestReadComments(unittest.TestCase):
    def test_parses_gh_json_into_id_body_pairs(self):
        fake_payload = json.dumps({
            "comments": [
                {"id": 11, "body": "first"},
                {"id": 22, "body": "second"},
            ]
        })
        captured = {}

        def fake_runner(args):
            captured["args"] = args
            return fake_payload

        comments = gh_store.read_comments(42, runner=fake_runner)
        self.assertEqual(comments, [(11, "first"), (22, "second")])
        # Confirms it called gh for issue 42 with JSON output.
        self.assertIn("42", captured["args"])
        self.assertIn("--json", captured["args"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest -v task-loop.tests.test_gh_store`
Expected: FAIL — `gh_store.py` / `read_comments` undefined.

- [ ] **Step 3: Write minimal implementation**

`task-loop/scripts/gh_store.py`:
```python
"""Thin gh-CLI adapter for the task-loop control protocol. The only module that
touches GitHub. `runner` is injectable so the logic is testable without gh."""
import json
import subprocess


def _default_runner(args: list) -> str:
    return subprocess.run(
        ["gh", *args], check=True, capture_output=True, text=True
    ).stdout


def read_comments(issue_number, runner=_default_runner) -> list:
    """Return [(comment_id, body), ...] for an issue, oldest first."""
    out = runner(["issue", "view", str(issue_number), "--json", "comments"])
    data = json.loads(out)
    return [(c["id"], c["body"]) for c in data.get("comments", [])]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest -v task-loop.tests.test_gh_store`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add task-loop/scripts/gh_store.py task-loop/tests/test_gh_store.py
git commit -m "task-loop: gh adapter read_comments with injectable runner"
```

### Task 1.7: gh adapter — post a comment

**Files:**
- Modify: `task-loop/scripts/gh_store.py`
- Test: `task-loop/tests/test_gh_store.py`

- [ ] **Step 1: Write the failing test**

Append to `test_gh_store.py`:
```python
class TestPostComment(unittest.TestCase):
    def test_posts_body_via_stdin_to_issue(self):
        captured = {}

        def fake_runner(args, input_text=None):
            captured["args"] = args
            captured["input_text"] = input_text
            return ""

        gh_store.post_comment(42, "hello body", runner=fake_runner)
        self.assertIn("42", captured["args"])
        self.assertIn("comment", captured["args"])
        # Body must be passed via --body-file - to avoid attribution-hook issues.
        self.assertIn("--body-file", captured["args"])
        self.assertEqual(captured["input_text"], "hello body")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest -v task-loop.tests.test_gh_store`
Expected: FAIL — `post_comment` undefined / runner signature mismatch.

- [ ] **Step 3: Write minimal implementation**

In `gh_store.py`, update the default runner to accept stdin and add `post_comment`:
```python
def _default_runner(args: list, input_text=None) -> str:
    return subprocess.run(
        ["gh", *args], check=True, capture_output=True, text=True,
        input=input_text,
    ).stdout


def post_comment(issue_number, body: str, runner=_default_runner) -> None:
    """Append a comment to an issue, passing the body via stdin (--body-file -)
    so control-event JSON never appears in the command text."""
    runner(["issue", "comment", str(issue_number), "--body-file", "-"],
           input_text=body)
```
Note: `read_comments` calls `runner(["issue", ...])` with no `input_text`; keep its call site unchanged (the new default runner makes `input_text` optional).

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest -v task-loop.tests.test_gh_store`
Expected: PASS (both classes).

- [ ] **Step 5: Commit**

```bash
git add task-loop/scripts/gh_store.py task-loop/tests/test_gh_store.py
git commit -m "task-loop: gh adapter post_comment via stdin body-file"
```

### Task 1.8: Wire plugin manifest + run the full suite

**Files:**
- Modify: `task-loop/.claude-plugin/plugin.json` (bump from spike `0.0.1` to `0.1.0`)
- Verify: `.claude-plugin/marketplace.json` (entry was added in Phase 0 Task 0.2)

- [ ] **Step 1: Update the plugin manifest**

Set `task-loop/.claude-plugin/plugin.json` version to `0.1.0` and description to
`"Autonomous, orchestrated cycle-driven development (foundation: control protocol)."`

- [ ] **Step 2: Confirm the marketplace entry**

The `{ "name": "task-loop", "source": "./task-loop" }` entry was added to
`.claude-plugin/marketplace.json` in Phase 0 (Task 0.2, Step 3). Confirm it is present
(do not duplicate it):
```bash
python -c "import json; ps=json.load(open('.claude-plugin/marketplace.json'))['plugins']; assert any(p['name']=='task-loop' for p in ps), 'missing task-loop'; print('entry present')"
```

- [ ] **Step 3: Run the entire Phase 1 suite**

Run: `python -m unittest discover -s task-loop/tests -v`
Expected: PASS — all tests across `test_control_log.py` and `test_gh_store.py`.

- [ ] **Step 4: Validate marketplace JSON**

Run: `python -c "import json,sys; json.load(open('.claude-plugin/marketplace.json')); print('marketplace OK')"`
Expected: `marketplace OK`.

- [ ] **Step 5: Commit**

```bash
git add task-loop/.claude-plugin/plugin.json .claude-plugin/marketplace.json
git commit -m "task-loop: register plugin and finalize Phase 1 foundation"
```

---

## Follow-on plans (Phase 2+, each its own plan after this foundation merges)

These are intentionally **not** detailed here: their exact steps depend on Phase 0's
findings about the real Agent-Teams/`/loop` primitives, and each is a working, testable
unit on its own. Write each via `writing-plans` when its predecessor is green.

1. **`specify-aims` skill** — interview + `discuss-with-codex` → `docs/task-loop/proposal.md` (charter + roadmap zones).
2. **`create-cycle` skill + generic `task-loop.md` skeleton** — generate the per-task playbook (the 11-step cycle, §6), scaffold `directions.md`/`logs/`/`.gitignore`/labels.
3. **`cycle-worker` agent (full)** — replace the spike stub; the per-task executor that ends at *open-PR + `MERGE_REQUEST`*, never merges, never edits `proposal.md`.
4. **`run-cycle` orchestrator** — the state machine (dispatching/waiting/idle/draining/exiting), lease/heartbeat, replan barrier + revision materialization, pre-merge event-drain barrier, orchestrator-only head-SHA-bound merge — built on the Phase 1 `control_log` + `gh_store` + the Phase 0 primitive contract.
5. **README + enablement + fail-fast dependency checks** (§2, §12).

---

## Self-Review

- **Spec coverage (foundation scope):** §8 control protocol → Tasks 1.1–1.5; gh transport → 1.6–1.7; §16 Phase 0 spike → Tasks 0.1–0.4 (with plugin registration/install in 0.2); §16 Phase 1 → 1.1–1.8; §13 packaging (partial) → 0.2 + 1.8. Phase 2+ spec sections (§4–§7, §9–§12) are explicitly deferred to follow-on plans — not gaps.
- **Recovery/idempotency coverage (the protocol's reason to exist):** `replay()` reconstructs `seen_source_uuids` + per-issue `last_ingested_comment_id_by_issue` from the log alone (Task 1.4 `test_reconstructs_seen_uuids_and_watermark`); task-issue discovery makes a fresh issue scannable before its first inbox event (`test_task_issue_discovery_without_inbox_events`); cold-resume dedupe is end-to-end tested (Task 1.5 `test_..._cold_resume_dedupe`). Schema validation enforces `proposal_sha` on `PLAN_REVISION_BUMP` and `pr_head_sha`/`source_*` on merge events (Task 1.4 validation tests).
- **Honest gate scope:** Phase 1 *carries and validates* `proposal_sha`/`pr_head_sha`, but the **revision-materialization** gate (bump only after the proposal commit is on `master`) and the **head-SHA merge gate** (`gh pr merge --match-head-commit`) are *enforced and tested in Phase 2* (the `run-cycle` orchestrator), not here. This is intentional, not a gap.
- **Placeholder scan:** none — every code/test step contains complete code and exact run commands.
- **Type/name consistency:** `format_event`/`parse_events`/`filter_new_inbox`/`assign_seq`/`replay` are used identically in Tasks 1.1–1.5; `replay()` returns `current_plan_revision`/`current_proposal_sha`/`last_seq`/`tasks`/`seen_source_uuids`/`source_uuid_to_seq`/`last_ingested_comment_id_by_issue` consistently across all replay/e2e tests; `read_comments(issue, runner)` and `post_comment(issue, body, runner)` are consistent across 1.6–1.7; event JSON shapes match the "Event JSON shapes" block throughout (control events carry `kind:"control"` + `ts`; inbox-derived carry `source_*`).
