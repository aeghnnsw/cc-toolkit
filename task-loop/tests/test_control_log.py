import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "control_log", ROOT / "scripts" / "control_log.py"
)
control_log = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(control_log)

TS_A = "2026-06-13T10:00:00Z"
TS_EARLY = "2026-06-13T08:00:00Z"
TS_B = "2026-06-13T11:00:00Z"


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

    def test_parse_multiple_events_in_one_comment(self):
        e1 = {"kind": "control", "seq": 1, "ts": "t"}
        e2 = {"kind": "control", "seq": 2, "ts": "t"}
        body = control_log.format_event(e1) + "\n" + control_log.format_event(e2)
        self.assertEqual(control_log.parse_events(body), [e1, e2])

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

    def test_preserves_fields_and_does_not_mutate_input(self):
        original = {"type": "TASK_CREATED", "task_id": "T1"}
        stamped, _ = control_log.assign_seq([original], last_seq=0)
        self.assertEqual(stamped[0]["task_id"], "T1")
        self.assertEqual(stamped[0]["seq"], 1)
        self.assertNotIn("seq", original)  # input dict untouched


class TestUnacknowledgedUuids(unittest.TestCase):
    def _inbox(self, uuid):
        return {"kind": "inbox", "uuid": uuid, "type": "MERGE_REQUEST"}

    def test_flags_uuid_with_no_source_tagged_event(self):
        fresh = [self._inbox("u1"), self._inbox("u2")]
        emitted = [{"type": "MERGE_GRANTED", "source_uuid": "u1"},
                   {"type": "TASK_STALE"}]  # untagged reply loses u2
        self.assertEqual(control_log.unacknowledged_uuids(fresh, emitted), ["u2"])

    def test_empty_when_all_acked(self):
        fresh = [self._inbox("u1"), self._inbox("u2")]
        emitted = [{"type": "MERGE_GRANTED", "source_uuid": "u1"},
                   {"type": "MERGE_DENIED", "source_uuid": "u2"}]
        self.assertEqual(control_log.unacknowledged_uuids(fresh, emitted), [])


def _merge_granted(seq, uuid="u1", issue=12, ts=TS_A, task="T1"):
    return {"kind": "control", "seq": seq, "type": "MERGE_GRANTED", "task_id": task,
            "plan_revision": 1, "pr_head_sha": "abc", "source_issue": issue,
            "source_comment_id": "IC_node", "source_comment_ts": ts,
            "source_uuid": uuid, "ts": "t"}


class TestReplay(unittest.TestCase):
    def _events(self):
        # Valid log: revision materialized, task created on issue 12, dispatched,
        # merge granted from inbox uuid u1 (comment node-id, createdAt TS_A on issue 12).
        return [
            {"kind": "control", "seq": 1, "type": "PLAN_REVISION_BUMP",
             "plan_revision": 1, "proposal_sha": "deadbeef", "ts": "t"},
            {"kind": "control", "seq": 2, "type": "TASK_CREATED", "task_id": "T1",
             "plan_revision": 1, "issue_number": 12, "ts": "t"},
            {"kind": "control", "seq": 3, "type": "TASK_DISPATCHED", "task_id": "T1",
             "plan_revision": 1, "ts": "t"},
            _merge_granted(4),
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
        state = control_log.replay(self._events())
        self.assertEqual(state["seen_source_uuids"], {"u1"})
        self.assertEqual(state["source_uuid_to_seq"]["u1"], 4)
        self.assertEqual(state["last_ingested_comment_ts_by_issue"][12], TS_A)

    def test_task_issue_discovery_without_inbox_events(self):
        events = [
            {"kind": "control", "seq": 1, "type": "PLAN_REVISION_BUMP",
             "plan_revision": 1, "proposal_sha": "deadbeef", "ts": "t"},
            {"kind": "control", "seq": 2, "type": "TASK_CREATED", "task_id": "T1",
             "plan_revision": 1, "issue_number": 12, "ts": "t"},
            {"kind": "control", "seq": 3, "type": "TASK_DISPATCHED", "task_id": "T1",
             "plan_revision": 1, "ts": "t"},
        ]
        state = control_log.replay(events)
        self.assertEqual(state["last_ingested_comment_ts_by_issue"][12], "")
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

    def test_merge_denied_status_stale(self):
        events = self._events()[:3] + [
            {"kind": "control", "seq": 4, "type": "MERGE_DENIED", "task_id": "T1",
             "plan_revision": 1, "pr_head_sha": "abc", "source_issue": 12,
             "source_comment_id": "IC", "source_comment_ts": TS_A,
             "source_uuid": "u1", "ts": "t"},
        ]
        state = control_log.replay(events)
        self.assertEqual(state["tasks"]["T1"]["status"], "stale")

    def test_revision_compatible_status_active(self):
        events = self._events()[:3] + [
            {"kind": "control", "seq": 4, "type": "TASK_REVISION_COMPATIBLE",
             "task_id": "T1", "plan_revision": 1, "ts": "t"},
        ]
        state = control_log.replay(events)
        self.assertEqual(state["tasks"]["T1"]["status"], "active")

    def test_plan_finding_recorded_dedupe_status_watermark(self):
        events = [{"kind": "control", "seq": 1, "type": "PLAN_FINDING_RECORDED",
                   "task_id": "T1", "source_issue": 12, "source_comment_id": "IC",
                   "source_comment_ts": TS_EARLY, "source_uuid": "uf", "ts": "t"}]
        state = control_log.replay(events)
        self.assertEqual(state["seen_source_uuids"], {"uf"})
        self.assertEqual(state["last_ingested_comment_ts_by_issue"][12], TS_EARLY)
        self.assertIsNone(state["tasks"]["T1"]["status"])

    def test_plan_finding_recorded_requires_source_uuid(self):
        events = [{"kind": "control", "seq": 1, "type": "PLAN_FINDING_RECORDED",
                   "task_id": "T1", "source_issue": 12, "source_comment_id": "IC",
                   "source_comment_ts": TS_EARLY, "ts": "t"}]
        with self.assertRaises(ValueError):
            control_log.replay(events)

    def test_replay_sorts_unordered_input(self):
        events = self._events()
        shuffled = [events[2], events[0], events[3], events[1]]
        self.assertEqual(control_log.replay(shuffled), control_log.replay(events))

    def test_watermark_never_regresses(self):
        # A later (higher-seq) event on issue 12 with an EARLIER createdAt must not
        # lower the watermark.
        events = self._events() + [
            {"kind": "control", "seq": 5, "type": "PLAN_FINDING_RECORDED",
             "task_id": "T1", "source_issue": 12, "source_comment_id": "IC2",
             "source_comment_ts": TS_EARLY, "source_uuid": "u2", "ts": "t"}]
        state = control_log.replay(events)
        self.assertEqual(state["last_ingested_comment_ts_by_issue"][12], TS_A)

    def test_per_issue_watermarks_independent(self):
        events = [
            {"kind": "control", "seq": 1, "type": "PLAN_REVISION_BUMP",
             "plan_revision": 1, "proposal_sha": "x", "ts": "t"},
            {"kind": "control", "seq": 2, "type": "TASK_CREATED", "task_id": "T1",
             "plan_revision": 1, "issue_number": 12, "ts": "t"},
            {"kind": "control", "seq": 3, "type": "TASK_CREATED", "task_id": "T2",
             "plan_revision": 1, "issue_number": 13, "ts": "t"},
            _merge_granted(4, uuid="u1", issue=12, ts=TS_A, task="T1"),
            _merge_granted(5, uuid="u2", issue=13, ts=TS_B, task="T2"),
        ]
        state = control_log.replay(events)
        self.assertEqual(state["last_ingested_comment_ts_by_issue"][12], TS_A)
        self.assertEqual(state["last_ingested_comment_ts_by_issue"][13], TS_B)

    def test_duplicate_uuid_across_issues_last_seq_wins(self):
        events = [
            {"kind": "control", "seq": 1, "type": "PLAN_REVISION_BUMP",
             "plan_revision": 1, "proposal_sha": "x", "ts": "t"},
            {"kind": "control", "seq": 2, "type": "TASK_CREATED", "task_id": "T1",
             "plan_revision": 1, "issue_number": 12, "ts": "t"},
            {"kind": "control", "seq": 3, "type": "TASK_CREATED", "task_id": "T2",
             "plan_revision": 1, "issue_number": 13, "ts": "t"},
            _merge_granted(4, uuid="u1", issue=12, ts=TS_A, task="T1"),
            _merge_granted(5, uuid="u1", issue=13, ts=TS_B, task="T2"),
        ]
        state = control_log.replay(events)
        self.assertEqual(state["seen_source_uuids"], {"u1"})
        self.assertEqual(state["source_uuid_to_seq"]["u1"], 5)

    def test_replay_empty_log_returns_zero_state(self):
        state = control_log.replay([])
        self.assertEqual(state["current_plan_revision"], 0)
        self.assertIsNone(state["current_proposal_sha"])
        self.assertEqual(state["last_seq"], 0)
        self.assertEqual(state["tasks"], {})
        self.assertEqual(state["seen_source_uuids"], set())
        self.assertEqual(state["source_uuid_to_seq"], {})
        self.assertEqual(state["last_ingested_comment_ts_by_issue"], {})

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

    def test_raises_on_unknown_event_type(self):
        events = [{"kind": "control", "seq": 1, "type": "BOGUS", "ts": "t"}]
        with self.assertRaises(ValueError):
            control_log.replay(events)

    def test_raises_on_missing_seq(self):
        events = [{"kind": "control", "type": "PLAN_REVISION_BUMP",
                   "plan_revision": 1, "proposal_sha": "x", "ts": "t"}]
        with self.assertRaises(ValueError):
            control_log.replay(events)

    def test_raises_on_non_int_plan_revision(self):
        events = [{"kind": "control", "seq": 1, "type": "PLAN_REVISION_BUMP",
                   "plan_revision": "1", "proposal_sha": "x", "ts": "t"}]
        with self.assertRaises(ValueError):
            control_log.replay(events)

    def test_revision_bump_requires_proposal_sha(self):
        events = [{"kind": "control", "seq": 1, "type": "PLAN_REVISION_BUMP",
                   "plan_revision": 1, "ts": "t"}]
        with self.assertRaises(ValueError):
            control_log.replay(events)

    def test_merge_granted_requires_pr_head_sha(self):
        events = [{"kind": "control", "seq": 1, "type": "MERGE_GRANTED", "task_id": "T1",
                   "plan_revision": 1, "source_issue": 12, "source_comment_id": "IC",
                   "source_comment_ts": TS_A, "source_uuid": "u1", "ts": "t"}]
        with self.assertRaises(ValueError):
            control_log.replay(events)

    def test_merge_granted_requires_source_uuid(self):
        events = [{"kind": "control", "seq": 1, "type": "MERGE_GRANTED", "task_id": "T1",
                   "plan_revision": 1, "pr_head_sha": "abc", "source_issue": 12,
                   "source_comment_id": "IC", "source_comment_ts": TS_A, "ts": "t"}]
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
        fresh = control_log.filter_new_inbox(inbox, seen_uuids=state["seen_source_uuids"])
        self.assertEqual(len(fresh), 1)
        # Orchestrator grants the merge, stamping source provenance (node-id + createdAt).
        decision = {"kind": "control", "type": "MERGE_GRANTED", "task_id": "T1",
                    "plan_revision": 1, "pr_head_sha": fresh[0]["pr_head_sha"],
                    "source_issue": 12, "source_comment_id": "IC_node",
                    "source_comment_ts": TS_A, "source_uuid": fresh[0]["uuid"], "ts": "t"}
        # The ingest is complete (no unacknowledged fresh uuid).
        self.assertEqual(control_log.unacknowledged_uuids(fresh, [decision]), [])
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
        self.assertEqual(resumed["last_ingested_comment_ts_by_issue"][12], TS_A)


if __name__ == "__main__":
    unittest.main()
