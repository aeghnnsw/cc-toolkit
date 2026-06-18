from __future__ import annotations

import contextlib
import importlib.machinery
import importlib.util
import io
import json
import pathlib
import types
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
CLI_PATH = ROOT / "cli" / "task-loop"


def load_cli():
    loader = importlib.machinery.SourceFileLoader("task_loop_cli", str(CLI_PATH))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


class FakeResponse:
    status_code = 200
    text = ""

    def __init__(self, data):
        self._data = data

    def json(self):
        return self._data


class FakeClient:
    def __init__(self, *, get_data=None, post_data=None, patch_data=None):
        self.get_data = get_data
        self.post_data = post_data
        self.patch_data = patch_data
        self.calls = []

    def get(self, path, **kwargs):
        self.calls.append(("get", path, kwargs))
        return FakeResponse(self.get_data)

    def post(self, path, **kwargs):
        self.calls.append(("post", path, kwargs))
        return FakeResponse(self.post_data)

    def patch(self, path, **kwargs):
        self.calls.append(("patch", path, kwargs))
        return FakeResponse(self.patch_data)


def capture_stdout(fn, *args):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        fn(*args)
    return out.getvalue().strip()


class TaskLoopCliStateTests(unittest.TestCase):
    def setUp(self):
        self.cli = load_cli()

    def test_status_json_includes_full_task_rows(self):
        rows = [
            {
                "seq": 1,
                "status": "open",
                "title": "First task",
                "deps": [],
                "issue": 11,
            },
            {
                "seq": 2,
                "status": "working",
                "title": "Second task",
                "deps": [1],
                "issue": None,
            },
        ]
        client = FakeClient(get_data=rows)

        output = capture_stdout(
            self.cli.cmd_status,
            client,
            "owner/repo",
            types.SimpleNamespace(json=True),
        )

        self.assertEqual(json.loads(output), rows)

    def test_status_json_prints_empty_array_for_empty_board(self):
        client = FakeClient(get_data=[])

        output = capture_stdout(
            self.cli.cmd_status,
            client,
            "owner/repo",
            types.SimpleNamespace(json=True),
        )

        self.assertEqual(json.loads(output), [])

    def test_claim_json_returns_claimed_task_row(self):
        task = {
            "seq": 7,
            "status": "working",
            "title": "Claimed task",
            "deps": [2, 3],
            "issue": 42,
        }
        client = FakeClient(post_data=task)

        output = capture_stdout(
            self.cli.cmd_claim,
            client,
            "owner/repo",
            types.SimpleNamespace(json=True),
        )

        self.assertEqual(json.loads(output), task)

    def test_claim_json_returns_null_when_no_task_is_ready(self):
        client = FakeClient(post_data=None)

        output = capture_stdout(
            self.cli.cmd_claim,
            client,
            "owner/repo",
            types.SimpleNamespace(json=True),
        )

        self.assertIsNone(json.loads(output))

    def test_set_issue_only_fills_missing_issue_without_overwriting_identity(self):
        row = {
            "seq": 7,
            "status": "working",
            "title": "Needs issue",
            "deps": [],
            "issue": 42,
        }
        client = FakeClient(patch_data=[row])

        output = capture_stdout(
            self.cli.cmd_set_issue,
            client,
            "owner/repo",
            types.SimpleNamespace(seq=7, issue=42, json=True),
        )

        method, path, kwargs = client.calls[0]
        self.assertEqual(method, "patch")
        self.assertEqual(path, "/tasks")
        self.assertEqual(kwargs["params"]["project_id"], "eq.owner/repo")
        self.assertEqual(kwargs["params"]["seq"], "eq.7")
        self.assertEqual(kwargs["params"]["issue"], "is.null")
        self.assertEqual(kwargs["params"]["status"], "in.(open,working)")
        self.assertEqual(kwargs["json"], {"issue": 42})
        self.assertEqual(json.loads(output), row)


if __name__ == "__main__":
    unittest.main()
