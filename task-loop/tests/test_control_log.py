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
        self.assertEqual(control_log.parse_events(body), [event])

    def test_parse_ignores_surrounding_prose(self):
        event = {"kind": "control", "seq": 7, "type": "MERGE_GRANTED",
                 "task_id": "T1", "plan_revision": 4, "source_uuid": "u1",
                 "ts": "2026-06-13T00:00:00Z"}
        body = "Some human note.\n\n" + control_log.format_event(event) + "\n\ntrailing"
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
                "spawned_plan_revision": 1, "type": "PLAN_FINDING", "ts": "t"}

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
        self.assertEqual((stamped, new_last), ([], 5))

    def test_preserves_fields_and_does_not_mutate_input(self):
        original = {"type": "TASK_CREATED", "task_id": "T1"}
        stamped, _ = control_log.assign_seq([original], last_seq=0)
        self.assertEqual(stamped[0]["task_id"], "T1")
        self.assertEqual(stamped[0]["seq"], 1)
        self.assertNotIn("seq", original)


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


class TestCommentsAtOrAfterWatermark(unittest.TestCase):
    def test_inclusive_floor_keeps_same_second_drops_earlier(self):
        comments = [("IC_a", TS_A, "a"),
                    ("IC_b", TS_A, "b"),       # same second as the floor -> kept
                    ("IC_c", TS_EARLY, "c")]   # earlier than the floor -> dropped
        out = control_log.comments_at_or_after_watermark(comments, TS_A)
        self.assertEqual([c[0] for c in out], ["IC_a", "IC_b"])

    def test_empty_floor_returns_all(self):
        comments = [("IC_a", TS_A, "a")]
        self.assertEqual(control_log.comments_at_or_after_watermark(comments, ""), comments)


def _merge_granted(seq, uuid="u1", issue=12, ts=TS_A, task="T1"):
    return {"kind": "control", "seq": seq, "type": "MERGE_GRANTED", "task_id": task,
            "plan_revision": 1, "pr_head_sha": "abc", "source_issue": issue,
            "source_comment_id": "IC_node", "source_comment_ts": ts,
            "source_uuid": uuid, "ts": "t"}


def _bump(seq=1, rev=1, sha="deadbeef"):
    return {"kind": "control", "seq": seq, "type": "PLAN_REVISION_BUMP",
            "plan_revision": rev, "proposal_sha": sha, "ts": "t"}


def _created(seq, task="T1", issue=12, rev=1):
    return {"kind": "control", "seq": seq, "type": "TASK_CREATED", "task_id": task,
            "plan_revision": rev, "issue_number": issue, "ts": "t"}


def _dispatched(seq, task="T1", rev=1):
    return {"kind": "control", "seq": seq, "type": "TASK_DISPATCHED",
            "task_id": task, "plan_revision": rev, "ts": "t"}


def _checkpoint(seq, issue=12, through=TS_A):
    return {"kind": "control", "seq": seq, "type": "INBOX_SCAN_CHECKPOINT",
            "issue_number": issue, "through_ts": through, "ts": "t"}


class TestReplay(unittest.TestCase):
    def _events(self):
        return [_bump(1), _created(2), _dispatched(3), _merge_granted(4)]

    def test_folds_to_expected_state(self):
        state = control_log.replay(self._events())
        self.assertEqual(state["current_plan_revision"], 1)
        self.assertEqual(state["current_proposal_sha"], "deadbeef")
        self.assertEqual(state["last_seq"], 4)
        self.assertEqual(state["tasks"]["T1"]["status"], "merged")
        self.assertEqual(state["tasks"]["T1"]["issue_number"], 12)
        self.assertEqual(state["tasks"]["T1"]["pr_head_sha"], "abc")

    def test_reconstructs_dedupe_set(self):
        state = control_log.replay(self._events())
        self.assertEqual(state["seen_source_uuids"], {"u1"})
        self.assertEqual(state["source_uuid_to_seq"]["u1"], 4)

    def test_acked_event_does_not_advance_scan_floor(self):
        # A merge ack must NOT move the floor (only checkpoints do).
        state = control_log.replay(self._events())
        self.assertEqual(state["scan_floor_ts_by_issue"][12], "")

    def test_task_issue_discovery_initializes_floor_empty(self):
        state = control_log.replay([_bump(1), _created(2), _dispatched(3)])
        self.assertEqual(state["scan_floor_ts_by_issue"][12], "")
        inbox = [{"kind": "inbox", "uuid": "u9", "type": "MERGE_REQUEST"}]
        fresh = control_log.filter_new_inbox(inbox, seen_uuids=state["seen_source_uuids"])
        self.assertEqual([e["uuid"] for e in fresh], ["u9"])

    def test_checkpoint_advances_floor(self):
        state = control_log.replay([_bump(1), _created(2), _checkpoint(3, through=TS_A)])
        self.assertEqual(state["scan_floor_ts_by_issue"][12], TS_A)

    def test_checkpoint_unknown_issue_raises(self):
        events = [_bump(1), _created(2, issue=12), _checkpoint(3, issue=99)]
        with self.assertRaises(ValueError):
            control_log.replay(events)

    def test_checkpoint_regression_raises(self):
        events = [_bump(1), _created(2), _checkpoint(3, through=TS_B),
                  _checkpoint(4, through=TS_A)]  # regresses below TS_B
        with self.assertRaises(ValueError):
            control_log.replay(events)

    def test_crash_before_checkpoint_keeps_earlier_unacked_comment_scannable(self):
        # Barrier acked the LATER finding (u2 @ TS_B); crashed before acking the
        # EARLIER merge request (u1 @ TS_A); no checkpoint emitted.
        seeded = [_bump(1), _created(2), _dispatched(3),
                  {"kind": "control", "seq": 4, "type": "PLAN_FINDING_RECORDED",
                   "task_id": "T1", "source_issue": 12, "source_comment_id": "IC2",
                   "source_comment_ts": TS_B, "source_uuid": "u2", "ts": "t"}]
        state = control_log.replay(seeded)
        self.assertEqual(state["scan_floor_ts_by_issue"][12], "")  # floor did NOT advance
        comments = [("IC1", TS_A, "u1"), ("IC2", TS_B, "u2")]
        window = control_log.comments_at_or_after_watermark(
            comments, state["scan_floor_ts_by_issue"][12])
        self.assertEqual([c[0] for c in window], ["IC1", "IC2"])  # both rescanned
        inbox = [{"kind": "inbox", "uuid": "u1", "type": "MERGE_REQUEST"},
                 {"kind": "inbox", "uuid": "u2", "type": "PLAN_FINDING"}]
        fresh = control_log.filter_new_inbox(inbox, seen_uuids=state["seen_source_uuids"])
        self.assertEqual([e["uuid"] for e in fresh], ["u1"])  # earlier comment recovered

    def test_revision_bump_updates_current(self):
        events = self._events() + [_bump(5, rev=2, sha="cafe"),
                                   _created(6, task="T2", issue=13, rev=2),
                                   {"kind": "control", "seq": 7, "type": "TASK_STALE",
                                    "task_id": "T2", "plan_revision": 2, "ts": "t"}]
        state = control_log.replay(events)
        self.assertEqual(state["current_plan_revision"], 2)
        self.assertEqual(state["tasks"]["T2"]["status"], "stale")

    def test_merge_denied_status_stale(self):
        events = [_bump(1), _created(2), _dispatched(3),
                  {"kind": "control", "seq": 4, "type": "MERGE_DENIED", "task_id": "T1",
                   "plan_revision": 1, "pr_head_sha": "abc", "source_issue": 12,
                   "source_comment_id": "IC", "source_comment_ts": TS_A,
                   "source_uuid": "u1", "ts": "t"}]
        self.assertEqual(control_log.replay(events)["tasks"]["T1"]["status"], "stale")

    def test_revision_compatible_status_active(self):
        events = [_bump(1), _created(2), _dispatched(3),
                  {"kind": "control", "seq": 4, "type": "TASK_REVISION_COMPATIBLE",
                   "task_id": "T1", "plan_revision": 1, "ts": "t"}]
        self.assertEqual(control_log.replay(events)["tasks"]["T1"]["status"], "active")

    def test_plan_finding_recorded_dedupe_and_status(self):
        events = [{"kind": "control", "seq": 1, "type": "PLAN_FINDING_RECORDED",
                   "task_id": "T1", "source_issue": 12, "source_comment_id": "IC",
                   "source_comment_ts": TS_EARLY, "source_uuid": "uf", "ts": "t"}]
        state = control_log.replay(events)
        self.assertEqual(state["seen_source_uuids"], {"uf"})
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

    def test_raises_on_duplicate_source_uuid(self):
        # The same inbox uuid must never get two source-tagged control events.
        events = [_bump(1), _created(2), _dispatched(3),
                  _merge_granted(4, uuid="u1"),
                  {"kind": "control", "seq": 5, "type": "PLAN_FINDING_RECORDED",
                   "task_id": "T1", "source_issue": 12, "source_comment_id": "IC2",
                   "source_comment_ts": TS_B, "source_uuid": "u1", "ts": "t"}]
        with self.assertRaises(ValueError):
            control_log.replay(events)

    def test_replay_empty_log_returns_zero_state(self):
        state = control_log.replay([])
        self.assertEqual(state["current_plan_revision"], 0)
        self.assertIsNone(state["current_proposal_sha"])
        self.assertEqual(state["last_seq"], 0)
        self.assertEqual(state["tasks"], {})
        self.assertEqual(state["seen_source_uuids"], set())
        self.assertEqual(state["source_uuid_to_seq"], {})
        self.assertEqual(state["scan_floor_ts_by_issue"], {})

    def test_replay_is_idempotent(self):
        events = self._events()
        self.assertEqual(control_log.replay(events), control_log.replay(events))

    def test_raises_on_seq_gap(self):
        with self.assertRaises(ValueError):
            control_log.replay([_bump(1), _created(3)])

    def test_raises_on_duplicate_seq(self):
        with self.assertRaises(ValueError):
            control_log.replay([_bump(1), _created(1)])

    def test_raises_on_unknown_event_type(self):
        with self.assertRaises(ValueError):
            control_log.replay([{"kind": "control", "seq": 1, "type": "BOGUS", "ts": "t"}])

    def test_raises_on_missing_seq(self):
        with self.assertRaises(ValueError):
            control_log.replay([{"kind": "control", "type": "PLAN_REVISION_BUMP",
                                 "plan_revision": 1, "proposal_sha": "x", "ts": "t"}])

    def test_raises_on_non_int_plan_revision(self):
        with self.assertRaises(ValueError):
            control_log.replay([{"kind": "control", "seq": 1, "type": "PLAN_REVISION_BUMP",
                                 "plan_revision": "1", "proposal_sha": "x", "ts": "t"}])

    def test_raises_on_non_int_source_issue(self):
        bad = _merge_granted(1)
        bad["source_issue"] = "12"  # string, would split watermark keys
        with self.assertRaises(ValueError):
            control_log.replay([bad])

    def test_raises_on_fractional_source_comment_ts(self):
        bad = _merge_granted(1, ts="2026-06-13T10:00:00.100Z")  # fractional -> lexical-unsafe
        with self.assertRaises(ValueError):
            control_log.replay([bad])

    def test_revision_bump_requires_proposal_sha(self):
        with self.assertRaises(ValueError):
            control_log.replay([{"kind": "control", "seq": 1, "type": "PLAN_REVISION_BUMP",
                                 "plan_revision": 1, "ts": "t"}])

    def test_merge_granted_requires_pr_head_sha(self):
        bad = _merge_granted(1)
        del bad["pr_head_sha"]
        with self.assertRaises(ValueError):
            control_log.replay([bad])

    def test_merge_granted_requires_source_uuid(self):
        bad = _merge_granted(1)
        del bad["source_uuid"]
        with self.assertRaises(ValueError):
            control_log.replay([bad])


class TestEndToEnd(unittest.TestCase):
    def test_ingest_emit_replay_and_cold_resume_dedupe(self):
        inbox = [
            {"kind": "inbox", "uuid": "u1", "task_id": "T1", "type": "MERGE_REQUEST",
             "pr_head_sha": "abc", "ts": "t"},
            {"kind": "inbox", "uuid": "u1", "task_id": "T1", "type": "MERGE_REQUEST",
             "pr_head_sha": "abc", "ts": "t"},
        ]
        seeded = [_bump(1), _created(2), _dispatched(3)]
        state = control_log.replay(seeded)
        fresh = control_log.filter_new_inbox(inbox, seen_uuids=state["seen_source_uuids"])
        self.assertEqual(len(fresh), 1)
        decision = {"kind": "control", "type": "MERGE_GRANTED", "task_id": "T1",
                    "plan_revision": 1, "pr_head_sha": fresh[0]["pr_head_sha"],
                    "source_issue": 12, "source_comment_id": "IC_node",
                    "source_comment_ts": TS_A, "source_uuid": fresh[0]["uuid"], "ts": "t"}
        self.assertEqual(control_log.unacknowledged_uuids(fresh, [decision]), [])
        stamped, _ = control_log.assign_seq([decision], state["last_seq"])
        self.assertEqual(stamped[0]["seq"], 4)
        final = control_log.replay(seeded + stamped)
        self.assertEqual(final["tasks"]["T1"]["status"], "merged")
        # COLD RESUME: replay the log, re-read the same comment (uuid u1) -> nothing new.
        re_fresh = control_log.filter_new_inbox(
            inbox, seen_uuids=final["seen_source_uuids"])
        self.assertEqual(re_fresh, [])


if __name__ == "__main__":
    unittest.main()
