"""Command-line checks for the lead state of t3_project_lead.py (issue #530).

Each check builds a temporary Git repository and runs the script in it, as a
project lead does. The checks read the script's output, exit status, and the
files of the lead folder: the life cycle and its refusals, UTC times, the
view, the due lines, what waits on the user, and finish. Issue #493 adds the
tasks that are ready to start: a task starts as soon as each task that it waits
for is verified, and does not wait for the rest of its batch.
"""

from __future__ import annotations

import datetime
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "t3_project_lead.py"
UTC = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z")
WORKER = "t3-thread://v2/env/thread-{}"


@unittest.skipUnless(shutil.which("git"), "needs git")
class LeadStateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.repo = self.tmp / "repo"
        (self.repo / "sub").mkdir(parents=True)
        self.env = dict(os.environ, GIT_CONFIG_GLOBAL=str(self.tmp / "gitconfig"),
                        GIT_CONFIG_NOSYSTEM="1", GIT_CEILING_DIRECTORIES=str(self.tmp))
        subprocess.run(["git", "init", "-q"], cwd=self.repo, env=self.env, check=True)

    def run_lead(self, *args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
        return subprocess.run([sys.executable, str(SCRIPT), *args], cwd=cwd or self.repo,
                              env=self.env, capture_output=True, text=True, check=False)

    def ok(self, *args: str) -> str:
        result = self.run_lead(*args)
        self.assertEqual(result.returncode, 0, f"{args}: {result.stderr}")
        return result.stdout

    def refused(self, *args: str, reason: str) -> None:
        before = self.state_text()
        result = self.run_lead(*args)
        self.assertEqual(result.returncode, 1, f"{args}: {result.stdout}")
        self.assertIn(reason, result.stderr)
        self.assertEqual(self.state_text(), before, "a refused command changed the state")

    def folder(self) -> Path:
        (folder,) = (self.repo / ".scratch").glob("*-lead-*")
        return folder

    def state_text(self) -> str:
        return (self.folder() / "state.json").read_text(encoding="utf-8")

    def task(self, name: str) -> dict:
        state = json.loads(self.state_text())
        return next(task for task in state["tasks"] if task["name"] == name)

    def events(self) -> list[dict]:
        lines = (self.folder() / "events.jsonl").read_text(encoding="utf-8").splitlines()
        return [json.loads(line) for line in lines]

    def merged_task(self, name: str, pr: str, batch: str = "1") -> None:
        """Add a task and take it to verified through one merged PR."""
        self.ok("task", "add", name, f"Title of {name}", "--batch", batch)
        self.ok("task", "start", name, WORKER.format(name))
        self.ok("task", "pr", name, pr)
        self.ok("task", "merged", name, pr, "abcdef1")
        self.ok("task", "verified", name)

    def test_start_without_a_lead_state_prints_how_to_create_one(self) -> None:
        output = self.ok("start")
        self.assertIn("Do only these lead actions yourself:", output)
        self.assertIn(f'python3 "{SCRIPT}" init <slug>', output)

    def test_init_creates_one_folder_that_git_ignores(self) -> None:
        self.ok("init", "demo")
        folder = self.folder()
        today = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d")
        self.assertEqual(folder.name, f"{today}-lead-demo")
        self.assertEqual((folder / ".gitignore").read_text(encoding="utf-8"), "*\n")
        status = subprocess.run(["git", "status", "--porcelain", "--untracked-files=all"],
                                cwd=self.repo, env=self.env, capture_output=True, text=True, check=True)
        self.assertEqual(status.stdout, "")
        result = self.run_lead("init", "other", cwd=self.repo / "sub")
        self.assertEqual(result.returncode, 1)
        self.assertIn("a lead state already exists here", result.stderr)
        self.assertIn("Lead state: demo", self.ok("show"))

    def test_a_command_from_a_subfolder_finds_the_lead_state(self) -> None:
        self.ok("init", "demo")
        result = self.run_lead("outcome", "Ship it.", cwd=self.repo / "sub")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Outcome: Ship it.", self.ok("show"))

    def test_a_command_without_a_lead_state_is_refused(self) -> None:
        result = self.run_lead("task", "add", "a", "Title")
        self.assertEqual(result.returncode, 1)
        self.assertIn("run init <slug> first", result.stderr)

    def test_a_task_runs_its_life_cycle_with_utc_times(self) -> None:
        self.ok("init", "demo")
        self.ok("task", "add", "fix-503", "Fix the lean-tests history check", "--issue", "503")
        self.ok("task", "start", "fix-503", WORKER.format(1), "--branch", "fix-503")
        self.ok("task", "pr", "fix-503", "540")
        self.ok("task", "pr", "fix-503", "541")
        self.ok("task", "merged", "fix-503", "540", "abcdef1")
        self.assertEqual(self.task("fix-503")["state"], "pr-open")
        self.ok("task", "merged", "fix-503", "541", "abcdef2")
        self.assertEqual(self.task("fix-503")["state"], "merged")
        self.ok("task", "verified", "fix-503")
        self.ok("task", "add", "closeout-1", "Close out batch 1", "--kind", "closeout")
        self.ok("task", "start", "closeout-1", WORKER.format(2))
        output = self.ok("task", "verified", "closeout-1")
        self.assertIn("Batch 1 is closed out: fix-503.", output)
        self.assertEqual(self.task("fix-503")["state"], "closed-out")
        self.ok("task", "settled", "fix-503")
        self.ok("task", "settled", "closeout-1")
        events = self.events()
        self.assertEqual([event["command"] for event in events][:3], ["init", "task add", "task start"])
        self.assertEqual([event.get("to") for event in events if event.get("task") == "fix-503"],
                         ["planned", "running", "pr-open", "pr-open", "pr-open", "merged", "verified",
                          "settled"])
        now = datetime.datetime.now(datetime.timezone.utc)
        for event in events:
            self.assertRegex(event["time"], UTC)
            stamped = datetime.datetime.strptime(event["time"], "%Y-%m-%dT%H:%M:%SZ").replace(
                tzinfo=datetime.timezone.utc)
            self.assertLess(abs((now - stamped).total_seconds()), 120)

    def test_illegal_transitions_are_refused(self) -> None:
        self.ok("init", "demo")
        self.ok("task", "add", "a", "Task a")
        self.refused("task", "pr", "a", "5", reason="a is planned; task pr needs running or pr-open")
        self.refused("task", "verified", "a", reason="a is planned")
        self.refused("task", "resume", "a", reason="task resume needs paused")
        self.refused("task", "start", "a", "two words", reason="the worker link must be one word")
        self.ok("task", "start", "a", WORKER.format(1))
        self.refused("task", "start", "a", WORKER.format(1), reason="a is running")
        self.ok("task", "pr", "a", "5")
        self.refused("task", "pr", "a", "5", reason="not a new positive PR number")
        self.refused("task", "verified", "a", reason="a has an open PR; verify it after task merged")
        self.refused("task", "merged", "a", "6", "abcdef1", reason="not an open PR of a")
        self.refused("task", "merged", "a", "5", "XYZ", reason="a commit is 7 to 40")
        self.refused("task", "settled", "a", reason="settle needs closed-out, cancelled, or verified")
        self.ok("task", "merged", "a", "5", "abcdef1")
        self.ok("task", "verified", "a")
        self.refused("task", "cancel", "a", reason="a is verified")
        self.refused("task", "verified", "missing", reason="no task named missing")

    def test_settle_waits_for_the_close_out_of_a_batch_with_a_merged_pr(self) -> None:
        self.ok("init", "demo")
        self.merged_task("a", "5")
        self.refused("task", "settled", "a", reason="batch 1 has a merged PR; settle a after the batch's "
                                                    "close-out task is verified")
        self.ok("task", "add", "close-1", "Close out batch 1", "--kind", "closeout")
        self.ok("task", "start", "close-1", WORKER.format(9))
        self.refused("task", "settled", "a", reason="close-out task is verified")
        self.ok("task", "verified", "close-1")
        self.ok("task", "settled", "a")

    def test_a_batch_with_no_pr_settles_when_every_task_is_verified(self) -> None:
        self.ok("init", "demo")
        self.ok("task", "add", "research", "Research the cache")
        self.ok("task", "add", "audit", "Audit the hooks")
        self.ok("task", "start", "research", WORKER.format(1))
        self.ok("task", "verified", "research")
        self.refused("task", "settled", "research", reason="batch 1 still has open tasks")
        self.ok("task", "start", "audit", WORKER.format(2))
        self.ok("task", "verified", "audit")
        self.ok("task", "settled", "research")

    def test_after_blocks_the_start_until_the_task_is_verified(self) -> None:
        self.ok("init", "demo")
        self.ok("task", "add", "research", "Research the cache")
        self.ok("task", "add", "impl", "Build the cache", "--after", "research")
        self.refused("task", "start", "impl", WORKER.format(2), reason="impl waits for research to be "
                                                                      "verified")
        self.ok("task", "start", "research", WORKER.format(1))
        self.refused("task", "start", "impl", WORKER.format(2), reason="waits for research")
        self.ok("task", "verified", "research")
        self.ok("task", "start", "impl", WORKER.format(2))

    def test_a_task_is_ready_when_the_task_that_it_waits_for_is_verified(self) -> None:
        self.ok("init", "demo")
        self.ok("task", "add", "a", "Task a")
        self.ok("task", "add", "b", "Task b")
        self.ok("task", "add", "c", "Task c", "--after", "a")
        self.ok("task", "add", "d", "Task d", "--after", "c")
        view = self.ok("show")
        for name in ("a", "b"):
            self.assertIn(f"- {name} is ready to start: run t3_project_lead.py dispatch for it now.", view)
        self.assertNotIn("c is ready", view)
        self.ok("task", "start", "a", WORKER.format("a"))
        self.ok("task", "start", "b", WORKER.format("b"))
        self.assertNotIn("is ready to start", self.ok("show"))
        self.ok("task", "pr", "a", "5")
        self.ok("task", "merged", "a", "5", "abcdef1")
        # b of the same batch still runs: c is ready now, and d still waits for c.
        self.assertEqual(self.ok("task", "verified", "a").strip(),
                         "a is verified. Ready to start now: c.")
        view = self.ok("show")
        self.assertIn("- c is ready to start: run t3_project_lead.py dispatch for it now.", view)
        self.assertNotIn("d is ready", view)
        self.assertEqual(self.task("b")["state"], "running")
        self.ok("task", "start", "c", WORKER.format("c"))
        self.assertNotIn("is ready to start", self.ok("show"))

    def test_a_close_out_starts_only_for_a_verified_batch_with_a_merged_pr(self) -> None:
        self.ok("init", "demo")
        self.ok("task", "add", "close-1", "Close out batch 1", "--kind", "closeout")
        self.refused("task", "add", "close-again", "Second close-out", "--kind", "closeout",
                     reason="batch 1 already has a close-out task")
        self.ok("task", "add", "a", "Task a")
        self.ok("task", "start", "a", WORKER.format(1))
        self.refused("task", "start", "close-1", WORKER.format(9), reason="batch 1 still has tasks")
        self.ok("task", "verified", "a")
        self.refused("task", "start", "close-1", WORKER.format(9), reason="batch 1 has no merged PR")
        self.merged_task("b", "7")
        self.ok("task", "start", "close-1", WORKER.format(9))
        self.ok("task", "verified", "close-1")
        self.refused("task", "add", "late", "Late task", "--batch", "1",
                     reason="the close-out of batch 1 has started; use --batch 2")
        self.refused("task", "add", "far", "Far task", "--batch", "3", reason="the batch must be from 1 to 2")
        self.ok("task", "add", "next", "Next task", "--batch", "2")

    def test_a_task_opens_its_next_pr_after_one_merges(self) -> None:
        self.ok("init", "demo")
        self.ok("task", "add", "tickets", "Two matt-automode tickets")
        self.ok("task", "start", "tickets", WORKER.format(1))
        self.ok("task", "pr", "tickets", "11")
        self.ok("task", "merged", "tickets", "11", "abcdef1")
        self.assertEqual(self.task("tickets")["state"], "merged")
        self.ok("task", "pr", "tickets", "12")
        self.assertEqual(self.task("tickets")["state"], "pr-open")
        self.refused("task", "verified", "tickets", reason="tickets has an open PR")
        self.ok("task", "merged", "tickets", "12", "abcdef2")
        self.ok("task", "verified", "tickets")

    def test_a_cancelled_task_does_not_release_a_task_after_it(self) -> None:
        self.ok("init", "demo")
        self.ok("task", "add", "research", "Research the cache")
        self.ok("task", "add", "impl", "Build the cache", "--after", "research")
        self.ok("task", "cancel", "research")
        self.ok("task", "settled", "research")
        self.refused("task", "start", "impl", WORKER.format(2), reason="impl waits for research")
        self.assertNotIn("impl is ready", self.ok("show"))

    def test_no_task_joins_a_batch_whose_close_out_has_started(self) -> None:
        self.ok("init", "demo")
        self.merged_task("w", "5")
        self.ok("task", "add", "co", "Close out batch 1", "--kind", "closeout")
        self.ok("task", "start", "co", WORKER.format(9))
        self.refused("task", "add", "late", "Late task", "--batch", "1",
                     reason="the close-out of batch 1 has started; use --batch 2")
        self.assertIn("Task late added to batch 2.", self.ok("task", "add", "late", "Late task"))
        self.ok("task", "verified", "co")
        self.ok("task", "settled", "w")
        self.ok("task", "settled", "co")

    def test_a_cancelled_close_out_lets_the_batch_add_another(self) -> None:
        self.ok("init", "demo")
        self.merged_task("w", "5")
        self.ok("task", "add", "co", "Close out batch 1", "--kind", "closeout")
        self.ok("task", "cancel", "co")
        self.ok("task", "settled", "co")
        self.ok("task", "add", "co-2", "Close out batch 1 again", "--kind", "closeout", "--batch", "1")
        self.ok("task", "start", "co-2", WORKER.format(9))
        self.ok("task", "verified", "co-2")
        self.assertEqual(self.task("w")["state"], "closed-out")

    def test_names_and_text_are_checked(self) -> None:
        self.ok("init", "demo")
        self.refused("task", "add", "Fix", "Title", reason="a task name has lowercase letters")
        self.refused("task", "add", "a" * 25, "Title", reason="at most 24 characters")
        self.refused("task", "add", "a", "x" * 201, reason="the title has 201 characters; the limit is 200")
        self.refused("decision", "add", "x" * 201, reason="the limit is 200")
        self.refused("wait", "x" * 201, reason="the limit is 200")
        self.refused("outcome", "x" * 201, reason="the limit is 200")
        self.ok("task", "add", "a", "x" * 200)
        self.refused("task", "add", "a", "Title", reason="a task named a already exists")
        self.refused("task", "add", "c", "Check", "--kind", "check", reason="a check task needs --of")
        self.refused("task", "add", "c", "Check", "--of", "a", reason="only a check task takes --of")
        self.refused("task", "add", "c", "Check", "--after", "missing", reason="no task named missing")

    def test_waiting_items_keep_their_numbers_and_point_to_the_worker(self) -> None:
        self.ok("init", "demo")
        self.ok("task", "add", "grill", "Design the cache")
        self.ok("task", "start", "grill", WORKER.format(1))
        self.assertIn("Item 1 added: 1 [grill] 5 decisions. " + WORKER.format(1),
                      self.ok("wait", "--task", "grill", "--decisions", "5"))
        self.ok("wait", "Triage #503", "--recommend", "ready-for-agent")
        self.ok("done", "1")
        self.refused("done", "1", reason="no waiting item 1")
        self.ok("wait", "Delete the backup files?", "--link", "https://example.com/x")
        waiting = self.ok("waiting")
        self.assertEqual(waiting.splitlines(), [
            "Waiting on you (2):",
            "2 Triage #503. Lead recommends: ready-for-agent.",
            "3 Delete the backup files?. https://example.com/x",
        ])
        self.assertTrue(self.ok("start").rstrip().endswith("3 Delete the backup files?. https://example.com/x"))
        self.assertIn("2 Triage #503. Lead recommends: ready-for-agent.", self.ok("report"))
        self.refused("wait", "--decisions", "2", reason="give the item's text, or --task")

    def test_a_worker_item_holds_no_detail_of_the_decisions(self) -> None:
        self.ok("init", "demo")
        self.ok("task", "add", "grill", "Design the cache")
        self.refused("wait", "--task", "grill", "--decisions", "2", reason="grill has no worker that is not settled")
        self.ok("task", "start", "grill", WORKER.format(1))
        for extra in (["Choose JSON or SQLite"], ["--recommend", "SQLite"], ["--link", "https://x"]):
            with self.subTest(extra=extra):
                self.refused("wait", "--task", "grill", "--decisions", "2", *extra,
                             reason="a worker item takes only --decisions")

    def test_the_view_hides_settled_tasks_and_counts_closed_out_tasks(self) -> None:
        self.ok("init", "demo")
        self.merged_task("a", "5")
        self.merged_task("b", "6")
        self.ok("task", "add", "close-1", "Close out batch 1", "--kind", "closeout")
        self.ok("task", "start", "close-1", WORKER.format(9))
        self.ok("task", "verified", "close-1")
        self.ok("task", "settled", "a")
        self.ok("task", "add", "c", "Task c", "--batch", "2")
        self.ok("task", "start", "c", WORKER.format(3))
        view = self.ok("show")
        self.assertNotIn("- a (", view)
        self.assertNotIn("- b (", view)
        self.assertIn("Closed out, worker not settled: 1 task.", view)
        self.assertRegex(view, r"- c \(batch 2\) running, 0 min: Task c\. Worker: t3-thread://")
        self.assertRegex(view, r"Now: " + UTC.pattern)

    def test_due_lines_name_the_next_mechanical_steps(self) -> None:
        self.ok("init", "demo")
        self.merged_task("a", "5")
        self.ok("wait", "--task", "a", "--decisions", "1")
        view = self.ok("show")
        self.assertIn("- Batch 1: every task is verified; merged PRs #5. Run t3_project_lead.py "
                      "closeout.", view)
        self.assertIn("- Item 1: task a is verified. Run done 1, or keep it.", view)
        closeout = self.ok("closeout")
        self.assertIn("Workers: " + WORKER.format("a"), closeout)
        self.assertIn("Merged PRs in merge order: #5", closeout)
        self.assertIn(f"History: {self.folder() / 'events.jsonl'}", closeout)
        self.ok("task", "add", "close-1", "Close out batch 1", "--kind", "closeout")
        self.ok("task", "start", "close-1", WORKER.format(9))
        self.ok("task", "verified", "close-1")
        view = self.ok("show")
        self.assertIn("- Settle the worker of a, then run task settled a: " + WORKER.format("a"), view)
        self.assertIn("- Settle the worker of close-1, then run task settled close-1:", view)
        self.ok("task", "settled", "a")
        self.ok("task", "settled", "close-1")
        self.ok("done", "1")
        self.assertIn("Every task is settled and nothing waits: run t3_project_lead.py finish.",
                      self.ok("show"))

    def test_merge_order_follows_the_merge_times(self) -> None:
        self.ok("init", "demo")
        self.ok("task", "add", "a", "Task a")
        self.ok("task", "start", "a", WORKER.format(1))
        self.ok("task", "pr", "a", "9")
        self.ok("task", "pr", "a", "3")
        self.ok("task", "merged", "a", "9", "abcdef1")
        state = json.loads(self.state_text())
        state["tasks"][0]["prs"][0]["merged"] = "2026-01-01T00:00:00Z"
        (self.folder() / "state.json").write_text(json.dumps(state), encoding="utf-8")
        self.ok("task", "merged", "a", "3", "abcdef2")
        self.ok("task", "verified", "a")
        self.assertIn("Merged PRs in merge order: #9, #3", self.ok("closeout"))

    def test_a_replaced_worker_is_named_once_to_settle(self) -> None:
        self.ok("init", "demo")
        self.ok("task", "add", "a", "Task a")
        self.ok("task", "start", "a", WORKER.format(1))
        output = self.ok("task", "worker", "a", WORKER.format(2))
        self.assertIn("Settle the replaced worker now: " + WORKER.format(1), output)
        self.assertEqual(self.task("a")["worker"], WORKER.format(2))
        self.assertNotIn(WORKER.format(1), self.ok("show"))

    def test_pause_resume_and_cancel(self) -> None:
        self.ok("init", "demo")
        self.ok("task", "add", "a", "Task a")
        self.ok("task", "pause", "a")
        self.assertIn("- a (batch 1) paused: Task a.", self.ok("show"))
        self.refused("task", "start", "a", WORKER.format(1), reason="a is paused")
        self.ok("task", "resume", "a")
        self.assertIn("It has no worker: run task settled a.", self.ok("task", "cancel", "a"))
        self.assertEqual(self.task("a")["state"], "cancelled")
        self.assertIn("- a has no worker: run task settled a.", self.ok("show"))
        self.ok("task", "settled", "a")
        self.ok("task", "add", "b", "Task b")
        self.ok("task", "start", "b", WORKER.format(2))
        self.ok("task", "cancel", "b")
        self.assertIn("- Settle the worker of b, then run task settled b:", self.ok("show"))
        self.ok("task", "settled", "b")

    def test_decisions_are_added_and_dropped_by_id(self) -> None:
        self.ok("init", "demo")
        self.assertIn("Decision D1 added.", self.ok("decision", "add", "Squash each merge."))
        self.ok("decision", "add", "Merge one PR at a time.")
        self.ok("decision", "drop", "D1")
        self.refused("decision", "drop", "D1", reason="no decision D1")
        self.assertIn("Decision D3 added.", self.ok("decision", "add", "Workers start from master."))
        view = self.ok("show")
        self.assertNotIn("D1 ", view)
        self.assertIn("- D2 Merge one PR at a time.", view)

    def test_finish_deletes_the_state_only_when_everything_is_settled(self) -> None:
        self.ok("init", "demo")
        self.ok("task", "add", "a", "Task a")
        self.ok("wait", "Approve the release?")
        self.refused("finish", reason="tasks not settled: a; items that wait: 1")
        self.ok("task", "cancel", "a")
        self.refused("finish", reason="tasks not settled: a")
        self.ok("task", "settled", "a")
        self.ok("done", "1")
        folder = self.folder()
        self.assertIn("Settle this thread.", self.ok("finish"))
        self.assertFalse(folder.exists())

    def test_each_change_appends_one_event(self) -> None:
        self.ok("init", "demo")
        self.ok("outcome", "Ship the cache.")
        self.ok("criteria", "Tests pass.")
        self.ok("task", "add", "a", "Task a")
        self.run_lead("task", "verified", "a")
        self.ok("show")
        self.assertEqual([event["command"] for event in self.events()],
                         ["init", "outcome", "criteria", "task add"])


if __name__ == "__main__":
    unittest.main()
