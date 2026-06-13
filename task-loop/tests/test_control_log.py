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


if __name__ == "__main__":
    unittest.main()
