import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("gh_store", ROOT / "scripts" / "gh_store.py")
gh_store = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(gh_store)


class TestReadComments(unittest.TestCase):
    def test_parses_gh_json_into_id_ts_body_triples(self):
        fake_payload = json.dumps({
            "comments": [
                {"id": "IC_a", "createdAt": "2026-06-13T01:00:00Z", "body": "first"},
                {"id": "IC_b", "createdAt": "2026-06-13T02:00:00Z", "body": "second"},
            ]
        })
        captured = {}

        def fake_runner(args):
            captured["args"] = args
            return fake_payload

        comments = gh_store.read_comments(42, runner=fake_runner)
        self.assertEqual(comments, [
            ("IC_a", "2026-06-13T01:00:00Z", "first"),
            ("IC_b", "2026-06-13T02:00:00Z", "second"),
        ])
        self.assertIn("42", captured["args"])
        self.assertIn("--json", captured["args"])

    def test_sorts_oldest_first_by_created_at(self):
        # gh may return any order; read_comments must guarantee oldest-first.
        fake_payload = json.dumps({
            "comments": [
                {"id": "IC_b", "createdAt": "2026-06-13T02:00:00Z", "body": "second"},
                {"id": "IC_a", "createdAt": "2026-06-13T01:00:00Z", "body": "first"},
            ]
        })
        comments = gh_store.read_comments(42, runner=lambda args: fake_payload)
        self.assertEqual([c[2] for c in comments], ["first", "second"])

    def test_missing_comments_key_returns_empty(self):
        comments = gh_store.read_comments(42, runner=lambda args: json.dumps({}))
        self.assertEqual(comments, [])


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


if __name__ == "__main__":
    unittest.main()
