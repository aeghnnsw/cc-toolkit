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
    def __init__(self, *, get_data=None, get_responses=None, post_data=None, patch_data=None):
        self.get_data = get_data
        self.get_responses = list(get_responses or [])
        self.post_data = post_data
        self.patch_data = patch_data
        self.calls = []

    def get(self, path, **kwargs):
        self.calls.append(("get", path, kwargs))
        data = self.get_responses.pop(0) if self.get_responses else self.get_data
        return FakeResponse(data)

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

    def test_set_seq_updates_project_counter_when_above_existing_tasks(self):
        client = FakeClient(
            get_responses=[
                [{"next_seq": 1}],
                [{"seq": 18}],
            ],
            patch_data=[{"next_seq": 19}],
        )

        output = capture_stdout(
            self.cli.cmd_set_seq,
            client,
            "owner/repo",
            types.SimpleNamespace(next_seq=19, force=False, json=True),
        )

        self.assertEqual(client.calls[0][0], "get")
        self.assertEqual(client.calls[0][1], "/projects")
        self.assertEqual(client.calls[0][2]["params"]["id"], "eq.owner/repo")
        self.assertEqual(client.calls[0][2]["params"]["select"], "next_seq")
        self.assertEqual(client.calls[1][0], "get")
        self.assertEqual(client.calls[1][1], "/tasks")
        self.assertEqual(client.calls[1][2]["params"]["project_id"], "eq.owner/repo")
        self.assertEqual(client.calls[1][2]["params"]["select"], "seq")
        self.assertEqual(client.calls[1][2]["params"]["order"], "seq.desc")
        self.assertEqual(client.calls[1][2]["params"]["limit"], "1")
        self.assertEqual(client.calls[2][0], "patch")
        self.assertEqual(client.calls[2][1], "/projects")
        self.assertEqual(client.calls[2][2]["params"]["id"], "eq.owner/repo")
        self.assertEqual(client.calls[2][2]["json"], {"next_seq": 19})
        self.assertEqual(
            json.loads(output),
            {
                "project": "owner/repo",
                "old_next_seq": 1,
                "next_seq": 19,
                "max_task_seq": 18,
            },
        )

    def test_set_seq_refuses_value_that_would_collide_with_existing_task(self):
        client = FakeClient(
            get_responses=[
                [{"next_seq": 20}],
                [{"seq": 18}],
            ],
        )

        with self.assertRaises(SystemExit):
            self.cli.cmd_set_seq(
                client,
                "owner/repo",
                types.SimpleNamespace(next_seq=18, force=False, json=False),
            )

        self.assertEqual([call[0] for call in client.calls], ["get", "get"])

    def test_set_seq_force_allows_lower_counter(self):
        client = FakeClient(
            get_responses=[
                [{"next_seq": 20}],
                [{"seq": 18}],
            ],
            patch_data=[{"next_seq": 18}],
        )

        output = capture_stdout(
            self.cli.cmd_set_seq,
            client,
            "owner/repo",
            types.SimpleNamespace(next_seq=18, force=True, json=False),
        )

        self.assertEqual(client.calls[2][0], "patch")
        self.assertEqual(client.calls[2][2]["json"], {"next_seq": 18})
        self.assertEqual(output, "next_seq owner/repo: 020 -> 018")


if __name__ == "__main__":
    unittest.main()
