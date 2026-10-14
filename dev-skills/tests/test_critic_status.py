"""Command-line checks for the pressure-test critic status script."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PLUGIN_ROOT / "codex-skills" / "pressure-test" / "scripts" / "critic_status.py"
ALLOWED = ["claude-opus-5-5", "claude-sonnet-5-5"]


def assistant(model: str, text: str = "", stop_reason: str | None = None) -> dict:
    content = [{"type": "text", "text": text}] if text else []
    return {
        "type": "assistant",
        "message": {"model": model, "content": content, "stop_reason": stop_reason},
    }


def result(text: str = "objection", **fields) -> dict:
    event = {
        "type": "result",
        "subtype": "success",
        "is_error": False,
        "result": text,
        "stop_reason": "end_turn",
        "safety_stops": 0,
    }
    event.update(fields)
    return event


def run_status(events: list[dict] | None, *, raw_lines: list[str] = ()) -> tuple[str, str]:
    """Run the script on a stream; return its status line and the reply file text.

    The reply file starts with a stale reply from an earlier round, so every
    test also checks that the script replaces it.
    """
    with tempfile.TemporaryDirectory() as tmp:
        events_path = Path(tmp) / "events.jsonl"
        reply_path = Path(tmp) / "msg.txt"
        reply_path.write_text("stale reply from an earlier round", encoding="utf-8")
        if events is not None:
            lines = [json.dumps(event) for event in events] + list(raw_lines)
            events_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        completed = subprocess.run(
            [sys.executable, str(SCRIPT), str(events_path), str(reply_path), *ALLOWED],
            capture_output=True,
            text=True,
            check=True,
        )
        return completed.stdout.strip(), reply_path.read_text(encoding="utf-8")


class CriticStatusTest(unittest.TestCase):
    def test_allowed_model_answer_is_ok(self):
        events = [
            {"type": "system", "subtype": "init", "model": "claude-opus-5-5"},
            assistant("claude-opus-5-5", "The weakest point is X."),
            result("The weakest point is X."),
        ]
        self.assertEqual(run_status(events), ("ok", "The weakest point is X."))

    def test_non_json_lines_are_skipped(self):
        events = [assistant("claude-opus-5-5", "ok"), result("ok")]
        self.assertEqual(run_status(events, raw_lines=["not json", "[]"]), ("ok", "ok"))

    def test_assistant_refusal_is_refused(self):
        events = [assistant("claude-opus-5-5", stop_reason="refusal"), result("", stop_reason="refusal")]
        self.assertEqual(run_status(events)[0], "refused")

    def test_result_refusal_is_refused(self):
        events = [assistant("claude-opus-5-5"), result("", is_error=True, stop_reason="refusal")]
        self.assertEqual(run_status(events)[0], "refused")

    def test_safety_stop_is_refused_even_when_the_answer_completed(self):
        events = [assistant("claude-opus-5-5", "objection"), result(safety_stops=1)]
        self.assertEqual(run_status(events)[0], "refused")

    def test_claude_code_refusal_events_are_refused(self):
        for subtype in ("model_refusal_fallback", "model_refusal_no_fallback"):
            with self.subTest(subtype=subtype):
                events = [
                    {"type": "system", "subtype": subtype, "original_model": "claude-opus-5-5"},
                    assistant("claude-opus-5-5", "objection"),
                    result(),
                ]
                self.assertEqual(run_status(events)[0], "refused")

    def test_crashed_call_without_result_is_not_refused(self):
        self.assertEqual(run_status([])[0], "error:no result event")

    def test_unlisted_model_is_reported(self):
        events = [assistant("claude-haiku-4-5", "objection"), result()]
        self.assertEqual(run_status(events)[0], "wrong_model:claude-haiku-4-5")

    def test_fallback_model_is_allowed(self):
        events = [assistant("claude-sonnet-5-5", "objection"), result()]
        self.assertEqual(run_status(events)[0], "ok")

    def test_synthetic_messages_are_not_model_output(self):
        events = [assistant("<synthetic>", "API Error: overloaded"), result("", is_error=True, subtype="error_during_execution")]
        self.assertEqual(run_status(events)[0], "error:error_during_execution")

    def test_missing_result_is_error(self):
        self.assertEqual(run_status([assistant("claude-opus-5-5", "partial")]), ("error:no result event", ""))

    def test_missing_events_file_is_error(self):
        status, reply = run_status(None)
        self.assertTrue(status.startswith("error:cannot read events"), status)
        self.assertEqual(reply, "")


if __name__ == "__main__":
    unittest.main()
