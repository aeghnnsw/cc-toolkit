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
