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
