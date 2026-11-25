"""Command-line checks for cleanup_plan.py, the plan that repo-cleanup acts on.

Cases 1-16 come from the scenario review of repo-cleanup before issue #459:
planning folders (#358), the worktrees that cleanup keeps (#419), and planning
folders in worktrees (#421). Cases 17-19 come from issue #543: the worktrees
that hold a lead state of t3-project-lead. Cases 20-25 come from issue #528:
branches with no commit of their own, and a worktree that contains another
worktree. Issue #528 also changed cases 7, 16, and 18. Cases 26-30 come from
issue #575: the worktrees that the tasks of a lead state record, and a lead
state that cannot be read; issue #575 also changed cases 17-19. Case 31 comes
from issue #577, which also changed case 16. Cases 32-35 come from issue #578:
the worktrees of T3 Code threads that are not settled, read with the t3 CLI.
Cases 36-41 come from issue #610: the session logs of a worktree whose task the
lead accepted, and the end of the 60-minute window. Cases 42 and 43 come from
issue #599: planning_folder.py lists the planning location and the lead folders
for the plan. Each check builds a temporary repository with a bare origin, runs the script with a fake gh
(fake_gh.py), and reads the lines that it prints. No check runs the real t3
CLI: the checks of #578 use a fake t3 (fake_t3.py), and the other checks run
with no t3 on PATH and no T3CODE_CLI_PATH. The real live_worktrees.py runs, so
most checks need lsof. Each class makes as few plan runs as it can, because
each run takes some seconds: one, or one for each mode. No check touches
another repository.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

TESTS = Path(__file__).resolve().parent
PLUGIN_ROOT = TESTS.parent
SCRIPT = PLUGIN_ROOT / "scripts" / "cleanup_plan.py"
# The plugin-root form of each host copy (CONTRIBUTING.md, "Skills for more than one host").
HOSTS = {"skills": "${CLAUDE_PLUGIN_ROOT}", "codex-skills": "<plugin-root>",
         "antigravity-skills": "<plugin-root>"}
NEEDS_LSOF_AND_GIT = unittest.skipUnless(shutil.which("lsof") and shutil.which("git"),
                                         "needs lsof and git")
COMMIT_PULLS = r"repos/\{owner\}/\{repo\}/commits/[0-9a-f]{40}/pulls\?per_page=100"
# PATH without the folders that hold a t3, so that no check runs the real t3 CLI.
PATH_WITHOUT_T3 = os.pathsep.join(
    folder for folder in os.environ.get("PATH", "").split(os.pathsep)
    if not os.access(os.path.join(folder, "t3"), os.X_OK))


def fake_t3(folder: Path) -> Path:
    """Write a t3 in the folder that runs fake_t3.py, and return its path."""
    folder.mkdir(exist_ok=True)
    t3 = folder / "t3"
    t3.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{TESTS / "fake_t3.py"}" "$@"\n')
    t3.chmod(0o755)
    return t3


class Repo:
    """A temporary repository: a bare origin, a main checkout on master, and a fake gh."""

    def __init__(self) -> None:
        # Resolved, so that the paths match the ones that git prints on macOS.
        self.tmp = Path(tempfile.mkdtemp()).resolve()
        self.claude_dir = self.tmp / "claude-config"
        self.bin = self.tmp / "bin"
        for folder in (self.tmp / "home", self.claude_dir, self.tmp / "codex-home", self.bin):
            folder.mkdir()
        (self.tmp / "gitconfig").write_text("")
        gh = self.bin / "gh"
        gh.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{TESTS / "fake_gh.py"}" "$@"\n')
        gh.chmod(0o755)
        self.gh_data: dict = {"prs": {}, "issues": {}}
        self.env = {key: value for key, value in os.environ.items()
                    if key not in ("CLAUDE_CODE_SESSION_ID", "CODEX_THREAD_ID",
                                   "T3CODE_CLI_PATH")}
        self.env.update(
            HOME=str(self.tmp / "home"),
            CLAUDE_CONFIG_DIR=str(self.claude_dir),
            CODEX_HOME=str(self.tmp / "codex-home"),
            GIT_CONFIG_GLOBAL=str(self.tmp / "gitconfig"),
            GIT_CONFIG_NOSYSTEM="1",
            GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.invalid",
            GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.invalid",
            PATH=f"{self.bin}{os.pathsep}{PATH_WITHOUT_T3}",
            FAKE_GH_DATA=str(self.tmp / "gh.json"),
            FAKE_GH_LOG=str(self.tmp / "gh.log"),
            FAKE_T3_DATA=str(self.tmp / "t3.json"),
            FAKE_T3_LOG=str(self.tmp / "t3.log"),
        )
        self.t3_data: dict = {}
        self.path = self.tmp / "repo"
        self.git("init", "-q", "--bare", "-b", "master", str(self.tmp / "origin.git"), cwd=self.tmp)
        self.git("init", "-q", "-b", "master", str(self.path), cwd=self.tmp)
        (self.path / ".gitignore").write_text("/.scratch/\n/trees/\n")
        self.git("add", ".gitignore")
        self.git("commit", "-q", "-m", "init")
        self.git("remote", "add", "origin", str(self.tmp / "origin.git"))
        self.git("push", "-q", "-u", "origin", "master")
        self.git("remote", "set-head", "origin", "master")
        self.processes: list[subprocess.Popen] = []

    def cleanup(self) -> None:
        for proc in self.processes:
            proc.kill()
            proc.wait()
        shutil.rmtree(self.tmp, True)

    def git(self, *args: str, cwd: Path | None = None, env: dict[str, str] | None = None) -> str:
        result = subprocess.run(["git", *args], cwd=cwd or self.path, env=env or self.env,
                                capture_output=True, text=True, check=True)
        return result.stdout

    def tip(self, ref: str = "HEAD") -> str:
        return self.git("rev-parse", ref).strip()

    def commit(self, cwd: Path, name: str, env: dict[str, str] | None = None) -> None:
        (cwd / name).write_text(f"{name}\n")
        self.git("add", name, cwd=cwd, env=env)
        self.git("commit", "-q", "-m", name, cwd=cwd, env=env)

    def worktree(self, name: str, own_commit: bool = True, start: str = "master",
                 old: bool = False, parent: Path | None = None) -> Path:
        """Add <parent>/<name> on a new branch from start, and push the branch.

        The parent folder is trees/ when parent is None. An old branch has reflog entries of two
        hours ago, so the plan reads it as created 120 minutes ago.
        """
        path = (parent or self.path / "trees") / name
        env = dict(self.env, GIT_COMMITTER_DATE=f"{int(time.time()) - 7200} +0000") if old else None
        self.git("worktree", "add", "-q", "-b", name, str(path), start, env=env)
        if own_commit:
            self.commit(path, f"{name}.txt", env=env)
        self.git("push", "-q", "origin", name, env=env)
        return path

    def record_pr(self, branch: str, number: int, head: str) -> None:
        self.gh_data["prs"].setdefault(branch, []).append({"number": number, "headRefOid": head})

    def record_commit_pr(self, commit: str, number: int, merged: bool = True) -> None:
        """Record a PR with the head commit, for the PRs of a commit on GitHub."""
        self.gh_data.setdefault("commit_prs", {}).setdefault(commit, []).append(
            {"number": number, "merged_at": "2026-11-23T10:00:00Z" if merged else None,
             "head": {"sha": commit}})

    def squash_merge(self, branch: str, number: int, pr_head: str | None = None) -> None:
        """Squash-merge the branch into master; its PR has head branch pr_head or its name."""
        head = self.tip(branch)
        self.git("merge", "-q", "--squash", branch)
        self.git("commit", "-q", "-m", f"{branch} (#{number})")
        self.git("push", "-q", "origin", "master")
        self.record_pr(pr_head or branch, number, head)

    def merge_commit(self, branch: str, number: int) -> None:
        head = self.tip(branch)
        self.git("merge", "-q", "--no-ff", "-m", f"Merge #{number}", branch)
        self.git("push", "-q", "origin", "master")
        self.record_pr(branch, number, head)

    def folder(self, root: Path, name: str) -> Path:
        path = root / ".scratch" / name
        path.mkdir(parents=True)
        (path / "01_notes.md").write_text("notes\n")
        return path

    def issue(self, number: int, state: str, reason: str = "") -> None:
        self.gh_data["issues"][str(number)] = {"number": number, "state": state,
                                               "stateReason": reason}

    def start(self, cwd: Path) -> None:
        self.processes.append(subprocess.Popen(["sleep", "60"], cwd=cwd, env=self.env))

    def run(self, *args: str, cwd: Path | None = None,
            env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
        (self.tmp / "gh.json").write_text(json.dumps(self.gh_data))
        (self.tmp / "t3.json").write_text(json.dumps(self.t3_data))
        return subprocess.run([sys.executable, str(SCRIPT), *args], cwd=cwd or self.path,
                              env=env or self.env, capture_output=True, text=True)

    def plan(self, *args: str, cwd: Path | None = None,
             env: dict[str, str] | None = None) -> dict[tuple[str, str], tuple[str, str]]:
        """Return {(kind, item): (action, reason)} from a plan run that must succeed."""
        result = self.run(*args, cwd=cwd, env=env)
        if result.returncode != 0:
            raise AssertionError(f"cleanup_plan.py exited {result.returncode}: {result.stderr}")
        plan = {}
        for line in result.stdout.splitlines():
            action, kind, item, reason = line.split("\t")
            plan[(kind, item)] = (action, reason)
        return plan

    def gh_calls(self) -> list[list[str]]:
        log = self.tmp / "gh.log"
        return [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []

    def t3_calls(self) -> list[list[str]]:
        log = self.tmp / "t3.log"
        return [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []

    def snapshot(self) -> tuple[str, str, str, list[str]]:
        """Return the worktrees, local and remote refs, origin refs, and files of the checkout."""
        files = []
        for folder, dirs, names in os.walk(self.path):
            dirs[:] = [name for name in dirs if name != ".git"]
            files += [os.path.relpath(os.path.join(folder, name), self.path)
                      for name in dirs + names]
        return (self.git("worktree", "list", "--porcelain"), self.git("for-each-ref"),
                self.git("for-each-ref", cwd=self.tmp / "origin.git"), sorted(files))


class PlanTestCase(unittest.TestCase):
    repo: Repo
    plan: dict[tuple[str, str], tuple[str, str]]

    @classmethod
    def make_repo(cls) -> Repo:
        repo = Repo()
        cls.addClassCleanup(repo.cleanup)
        return repo

    def line(self, kind: str, item: Path | str) -> tuple[str, str]:
        self.assertIn((kind, str(item)), self.plan, f"no {kind} line for {item}")
        return self.plan[(kind, str(item))]

    def assert_action(self, expected: str, kind: str, item: Path | str, *phrases: str) -> None:
        action, reason = self.line(kind, item)
        self.assertEqual(action, expected, reason)
        for phrase in phrases:
            self.assertIn(phrase, reason)

    def assert_kept(self, kind: str, item: Path | str, *phrases: str) -> None:
        self.assert_action("KEEP", kind, item, *phrases)

    def assert_removed(self, kind: str, item: Path | str, *phrases: str) -> None:
        self.assert_action("REMOVE", kind, item, *phrases)

    def assert_with_branches(self, expected: str, worktree: Path, *phrases: str) -> None:
        """Check the worktree, its local branch, and its remote branch of the same name."""
        for kind, item in (("worktree", worktree), ("branch", worktree.name),
                           ("remote-branch", f"origin/{worktree.name}")):
            self.assert_action(expected, kind, item, *phrases)

    def assert_kept_with_branches(self, worktree: Path, *phrases: str) -> None:
        self.assert_with_branches("KEEP", worktree, *phrases)

    def assert_removed_with_branches(self, worktree: Path, *phrases: str) -> None:
        self.assert_with_branches("REMOVE", worktree, *phrases)

    def issues_read(self) -> list[str]:
        return sorted(call[2] for call in self.repo.gh_calls() if call[:2] == ["issue", "view"])


@NEEDS_LSOF_AND_GIT
class PlanningFolderCases(PlanTestCase):
    """Cases 1-4: planning folders in the main checkout, where the session runs."""

    @classmethod
    def setUpClass(cls):
        repo = cls.repo = cls.make_repo()
        for name in ("42-cache-layer", "43-old-idea", "44-auth", "20261105-cache-layer"):
            repo.folder(repo.path, name)
        (repo.path / ".scratch" / "notes.md").write_text("notes\n")
        repo.issue(42, "CLOSED", "COMPLETED")
        repo.issue(43, "CLOSED", "NOT_PLANNED")
        repo.issue(44, "OPEN")
        cls.plan = repo.plan()

    def folder(self, name: str) -> Path:
        return self.repo.path / ".scratch" / name

    def test_case_01_removes_the_folder_of_a_completed_issue(self):
        self.assertEqual(self.line("folder", self.folder("42-cache-layer")),
                         ("REMOVE", "issue #42 is closed as completed"))

    def test_case_02_keeps_the_folder_of_a_not_planned_issue(self):
        self.assertEqual(self.line("folder", self.folder("43-old-idea")),
                         ("KEEP", "issue #43 is closed as not planned"))

    def test_case_03_keeps_the_folder_of_an_open_issue(self):
        self.assertEqual(self.line("folder", self.folder("44-auth")), ("KEEP", "issue #44 is open"))

    def test_case_04_keeps_entries_with_no_issue_key_without_guessing_one(self):
        self.assert_kept("folder", self.folder("20261105-cache-layer"), "no issue key", "date")
        self.assert_kept("folder", self.folder("notes.md"), "no issue key")
        self.assertEqual(self.issues_read(), ["42", "43", "44"])

    def test_keeps_the_main_checkout_and_the_default_branch(self):
        self.assertEqual(self.line("worktree", self.repo.path), ("KEEP", "the main checkout"))
        self.assertEqual(self.line("branch", "master"), ("KEEP", "the Default Branch"))


@NEEDS_LSOF_AND_GIT
class TrackerFailureCase(PlanTestCase):
    """Case 5: gh fails with an authentication error."""

    @classmethod
    def setUpClass(cls):
        repo = cls.repo = cls.make_repo()
        repo.folder(repo.path, "45-logging")
        cls.feat = repo.worktree("feat-l")
        repo.squash_merge("feat-l", 55)
        repo.gh_data["fail"] = "HTTP 401: Bad credentials (https://api.github.com/graphql)"
        cls.plan = repo.plan()

    def test_case_05_keeps_the_folder_and_reports_the_tracker_failure(self):
        self.assert_kept("folder", self.repo.path / ".scratch" / "45-logging",
                         "issue #45", "HTTP 401: Bad credentials")

    def test_keeps_a_worktree_whose_pr_state_cannot_be_read(self):
        self.assert_kept_with_branches(self.feat, "PR state cannot be read", "HTTP 401")


@NEEDS_LSOF_AND_GIT
class WorktreeCases(PlanTestCase):
    """Cases 6-9 and 11: the worktrees that cleanup keeps; the session runs in the main checkout."""

    @classmethod
    def setUpClass(cls):
        repo = cls.repo = cls.make_repo()
        first = repo.tip()
        cls.feat_a = repo.worktree("feat-a")
        repo.squash_merge("feat-a", 50)
        cls.feat_c = repo.worktree("feat-c")
        repo.merge_commit("feat-c", 51)
        cls.dirty = repo.worktree("feat-dirty")
        repo.squash_merge("feat-dirty", 53)
        (cls.dirty / "wip.txt").write_text("unsaved work\n")
        # A merged branch with no worktree, and a pushed branch with work but no PR.
        repo.git("switch", "-q", "-c", "old-merged")
        repo.commit(repo.path, "old-merged.txt")
        repo.git("push", "-q", "origin", "old-merged")
        repo.git("switch", "-q", "master")
        repo.squash_merge("old-merged", 54)
        repo.git("switch", "-q", "-c", "unmerged")
        repo.commit(repo.path, "unmerged.txt")
        repo.git("push", "-q", "origin", "unmerged")
        repo.git("switch", "-q", "master")
        # Branches whose upstream has another name; the PR head is the upstream name.
        cls.renamed = repo.worktree("feat-u")
        repo.git("push", "-q", "-u", "origin", "feat-u:steven/feat-u", cwd=cls.renamed)
        repo.squash_merge("feat-u", 56, pr_head="steven/feat-u")
        (cls.renamed / "wip.txt").write_text("unsaved work\n")
        repo.git("switch", "-q", "-c", "old-renamed")
        repo.commit(repo.path, "old-renamed.txt")
        repo.git("push", "-q", "-u", "origin", "old-renamed:steven/old-renamed")
        repo.git("switch", "-q", "master")
        repo.squash_merge("old-renamed", 57, pr_head="steven/old-renamed")
        # These start at the final tip of the Default Branch.
        cls.feat_b = repo.worktree("feat-b", own_commit=False)
        cls.fix_x = repo.worktree("fix-x", own_commit=False)
        repo.record_pr("fix-x", 30, first)
        cls.scratch = repo.path / "trees" / "scratch"
        repo.git("worktree", "add", "-q", "--detach", str(cls.scratch), "master")
        log = repo.claude_dir / "projects" / "-repo" / "s1.jsonl"
        log.parent.mkdir(parents=True)
        log.write_text(json.dumps({"type": "user", "cwd": str(cls.feat_a)}) + "\n")
        cls.before = repo.snapshot()
        cls.plan = repo.plan()
        cls.after = repo.snapshot()

    def test_case_06_keeps_a_worktree_with_a_live_session(self):
        self.assert_kept_with_branches(self.feat_a, "live session", "session log")

    def test_case_07_keeps_a_new_branch_at_the_default_tip(self):
        self.assert_kept_with_branches(self.feat_b, "no commit of its own",
                                       "less than 60 minutes ago")

    def test_case_08_removes_a_worktree_merged_with_a_merge_commit(self):
        self.assert_removed_with_branches(self.feat_c, "merged PR #51")

    def test_case_09_keeps_a_detached_worktree_in_the_default_branch(self):
        self.assert_kept("worktree", self.scratch, "detached HEAD", "no commit of its own")

    def test_case_11_keeps_a_reused_branch_name_whose_old_pr_has_another_head(self):
        self.assert_kept_with_branches(self.fix_x, "no commit of its own", "#30")

    def test_keeps_a_merged_worktree_with_uncommitted_changes(self):
        self.assert_kept_with_branches(self.dirty, "uncommitted changes")

    def test_removes_a_merged_branch_without_a_worktree(self):
        self.assert_removed("branch", "old-merged", "merged PR #54")
        self.assert_removed("remote-branch", "origin/old-merged", "merged PR #54")

    def test_keeps_the_upstream_of_a_kept_worktree_branch_with_another_name(self):
        self.assert_kept("worktree", self.renamed, "uncommitted changes")
        self.assert_kept("branch", "feat-u", "uncommitted changes")
        self.assert_kept("remote-branch", "origin/steven/feat-u", "its local branch feat-u is kept")

    def test_finds_the_merged_pr_of_a_branch_by_its_upstream_name(self):
        self.assert_removed("branch", "old-renamed", "merged PR #57")
        self.assert_removed("remote-branch", "origin/steven/old-renamed", "merged PR #57")

    def test_keeps_a_branch_with_work_and_no_merged_pr(self):
        self.assert_kept("branch", "unmerged", "not merged")
        self.assert_kept("remote-branch", "origin/unmerged", "not merged")

    def test_changes_nothing_and_runs_only_read_commands(self):
        self.assertEqual(self.before, self.after)
        for call in self.repo.gh_calls():
            with self.subTest(call=call):
                self.assertTrue(call[:2] == ["pr", "list"] or (
                    len(call) == 2 and call[0] == "api" and re.fullmatch(COMMIT_PULLS, call[1])))


@NEEDS_LSOF_AND_GIT
class ScriptFailureCase(PlanTestCase):
    """Case 10: live_worktrees.py fails, because lsof is not installed."""

    @classmethod
    def setUpClass(cls):
        repo = cls.repo = cls.make_repo()
        cls.feat_d = repo.worktree("feat-d")
        repo.squash_merge("feat-d", 52)
        # Only git, ps, and the fake gh are on PATH.
        for tool in ("git", "ps"):
            (repo.bin / tool).symlink_to(shutil.which(tool))
        cls.plan = repo.plan(env=dict(repo.env, PATH=str(repo.bin)))

    def test_case_10_keeps_every_worktree_and_reports_the_error(self):
        self.assert_kept_with_branches(self.feat_d, "live_worktrees.py exited with status 1",
                                       "lsof is not installed")


@NEEDS_LSOF_AND_GIT
class WorktreeFolderCases(PlanTestCase):
    """Cases 12-15: planning folders in worktrees; the session runs in trees/feat-e."""

    @classmethod
    def setUpClass(cls):
        repo = cls.repo = cls.make_repo()
        worktrees = {}
        for number, name in enumerate(("feat-e", "feat-f", "feat-g", "feat-h"), start=60):
            worktrees[name] = repo.worktree(name)
            repo.squash_merge(name, number)
        cls.feat_e, cls.feat_f, cls.feat_g, cls.feat_h = worktrees.values()
        cls.search = repo.folder(cls.feat_e, "46-search")
        cls.export = repo.folder(cls.feat_f, "47-export")
        cls.imports = repo.folder(cls.feat_g, "48-import")
        cls.retry = repo.folder(cls.feat_h, "49-retry")
        repo.issue(46, "CLOSED", "COMPLETED")
        repo.issue(47, "OPEN")
        repo.issue(48, "CLOSED", "COMPLETED")
        repo.issue(49, "CLOSED", "COMPLETED")
        repo.start(cls.feat_h)
        cls.plan = repo.plan(cwd=cls.feat_e)

    def test_case_12_removes_a_completed_folder_in_the_current_worktree(self):
        self.assert_removed("folder", self.search, "issue #46 is closed as completed")
        self.assert_kept_with_branches(self.feat_e, "current session", "merged PR #60")

    def test_case_13_keeps_a_merged_worktree_that_holds_an_open_issue_folder(self):
        self.assert_kept("folder", self.export, "issue #47 is open")
        self.assert_kept_with_branches(self.feat_f, str(self.export), "issue #47 is open")

    def test_case_14_removes_a_completed_folder_and_its_merged_worktree(self):
        self.assert_removed("folder", self.imports, "issue #48 is closed as completed")
        self.assert_removed_with_branches(self.feat_g, "merged PR #62")

    def test_case_15_leaves_the_folders_of_a_live_worktree_alone(self):
        self.assert_kept_with_branches(self.feat_h, "live session", "process")
        self.assertNotIn(("folder", str(self.retry)), self.plan)
        self.assertNotIn("49", self.issues_read())


@NEEDS_LSOF_AND_GIT
class DocumentedLocationCase(PlanTestCase):
    """Case 16: the repository documents its planning folders in the main checkout."""

    @classmethod
    def setUpClass(cls):
        repo = cls.repo = cls.make_repo()
        worktrees = {}
        for number, name in enumerate(("feat-e", "feat-i", "feat-j"), start=64):
            worktrees[name] = repo.worktree(name)
            repo.squash_merge(name, number)
        cls.feat_e, cls.feat_i, cls.feat_j = worktrees.values()
        cls.feat_k = repo.worktree("feat-k")
        repo.squash_merge("feat-k", 67)
        cls.metrics = repo.folder(cls.feat_i, "50-metrics")
        cls.done = repo.folder(cls.feat_i, "51-done")
        cls.other = repo.folder(cls.feat_j, "52-done")
        cls.current = repo.folder(cls.feat_e, "53-done")
        # Folder names sort as text: 12-done comes before 5-open.
        cls.early = repo.folder(cls.feat_k, "12-done")
        cls.late = repo.folder(cls.feat_k, "5-open")
        repo.issue(50, "OPEN")
        repo.issue(5, "OPEN")
        for number in (12, 51, 52, 53):
            repo.issue(number, "CLOSED", "COMPLETED")
        cls.plan = repo.plan("--main-only", cwd=cls.feat_e)

    def test_case_16_lists_outside_main_only_the_folders_that_a_worktree_removal_deletes(self):
        self.assert_kept("folder", self.metrics, "issue #50 is open")
        self.assert_kept_with_branches(self.feat_i, "holds the kept planning folder",
                                       str(self.metrics))
        self.assert_removed_with_branches(self.feat_j, "merged PR #66")
        self.assertEqual(self.line("folder", self.other), (
            "REMOVE", f"issue #52 is closed as completed; removing the worktree {self.feat_j} "
            "deletes it"))
        for folder in (self.done, self.current):
            with self.subTest(folder=folder.name):
                self.assertNotIn(("folder", str(folder)), self.plan)
        self.assertEqual(self.issues_read(), ["12", "5", "50", "51", "52"])

    def test_case_31_a_kept_folder_later_in_the_order_keeps_the_worktree_and_its_folders(self):
        self.assert_kept("folder", self.late, "issue #5 is open")
        self.assert_kept_with_branches(self.feat_k, "holds the kept planning folder",
                                       str(self.late))
        self.assertNotIn(("folder", str(self.early)), self.plan)


def lead_state(folder: Path, *tasks: dict) -> None:
    """Write a lead state with schema 1 and the tasks; the worktrees of a task are paths."""
    (folder / "state.json").write_text(json.dumps({"schema": 1, "tasks": [
        dict(task, worktrees=[str(path) for path in task["worktrees"]]) for task in tasks]}))


@NEEDS_LSOF_AND_GIT
class LeadStateCases(PlanTestCase):
    """Cases 17, 18, and 26-28: merged worktrees and lead states, with and without --main-only.

    The lead state in the main checkout records task-a, task-b, and the branch
    of task-c. The lead state in lead-a records task-d.
    """

    plans: dict[str, dict[tuple[str, str], tuple[str, str]]]

    @classmethod
    def setUpClass(cls):
        repo = cls.repo = cls.make_repo()
        worktrees = {}
        for number, name in enumerate(("lead-a", "lead-b", "task-a", "task-b", "task-c", "task-d"),
                                      start=70):
            worktrees[name] = repo.worktree(name)
            repo.squash_merge(name, number)
        cls.lead_a, cls.lead_b, cls.task_a, cls.task_b, cls.task_c, cls.task_d = worktrees.values()
        cls.state = repo.folder(cls.lead_a, "20261122-lead-batch")
        lead_state(cls.state, {"name": "check-574", "state": "pr-open", "worktrees": [cls.task_d]})
        repo.folder(cls.lead_b, "20261122-lead-old")
        cls.main_state = repo.folder(repo.path, "20261124-lead-main")
        lead_state(cls.main_state,
                   {"name": "grill-571", "state": "verified", "worktrees": [cls.task_a]},
                   {"name": "fix-572", "state": "settled", "worktrees": [cls.task_b]},
                   # A task with a branch and no worktree path.
                   {"name": "fix-573", "state": "running", "branch": "task-c", "worktrees": []})
        cls.plans = {"default": repo.plan(), "--main-only": repo.plan("--main-only")}

    def test_case_17_keeps_a_merged_worktree_that_holds_a_lead_state_in_every_mode(self):
        for mode, plan in self.plans.items():
            with self.subTest(mode=mode):
                self.plan = plan
                self.assert_kept_with_branches(self.lead_a, "holds a lead state", str(self.state))

    def test_case_18_a_lead_folder_without_state_json_keeps_no_worktree_by_this_rule(self):
        # The folder still has no issue key, so the planning folder rule keeps the worktree.
        for mode, plan in self.plans.items():
            with self.subTest(mode=mode):
                self.plan = plan
                self.assert_kept("worktree", self.lead_b, "holds the kept planning folder",
                                 "no issue key")
                self.assertNotIn("holds a lead state", self.line("worktree", self.lead_b)[1])

    def test_case_26_keeps_the_worktree_of_a_task_that_is_not_settled_in_every_mode(self):
        for mode, plan in self.plans.items():
            with self.subTest(mode=mode):
                self.plan = plan
                self.assert_kept_with_branches(
                    self.task_a, f"task grill-571 of the lead state {self.main_state} is verified, "
                    "not settled")
                self.assert_kept_with_branches(
                    self.task_d, f"task check-574 of the lead state {self.state} is pr-open, "
                    "not settled")

    def test_case_27_removes_the_worktree_of_a_settled_task(self):
        for mode, plan in self.plans.items():
            with self.subTest(mode=mode):
                self.plan = plan
                self.assert_removed_with_branches(self.task_b, "merged PR #73")

    def test_case_28_a_task_matches_no_worktree_by_its_branch(self):
        for mode, plan in self.plans.items():
            with self.subTest(mode=mode):
                self.plan = plan
                self.assert_removed_with_branches(self.task_c, "merged PR #74")


@NEEDS_LSOF_AND_GIT
class AcceptedTaskCases(PlanTestCase):
    """Cases 36-41: merged worktrees with a session log of the last 60 minutes (#610).

    The lead state in the main checkout records done-a, done-b, and dirty-f
    for settled tasks, and gone-c for a task that was cancelled and then
    settled. It records shared-e for a settled task and for a cancelled task.
    No lead state records free-d. A process also runs in done-b, and dirty-f
    has uncommitted changes.
    """

    @classmethod
    def setUpClass(cls):
        repo = cls.repo = cls.make_repo()
        worktrees = {}
        for number, name in enumerate(("done-a", "done-b", "gone-c", "free-d", "shared-e",
                                       "dirty-f"), start=120):
            worktrees[name] = repo.worktree(name)
            repo.squash_merge(name, number)
            log = repo.claude_dir / "projects" / "-repo" / f"{name}.jsonl"
            log.parent.mkdir(parents=True, exist_ok=True)
            log.write_text(json.dumps({"type": "user", "cwd": str(worktrees[name])}) + "\n")
        (cls.done_a, cls.done_b, cls.gone_c, cls.free_d, cls.shared_e,
         cls.dirty_f) = worktrees.values()
        repo.start(cls.done_b)
        (cls.dirty_f / "wip.txt").write_text("unsaved work\n")
        cls.state = repo.folder(repo.path, "20261124-lead-main")
        lead_state(cls.state,
                   {"name": "fix-610", "state": "settled", "worktrees": [cls.done_a]},
                   {"name": "fix-611", "state": "settled", "worktrees": [cls.done_b]},
                   {"name": "drop-612", "state": "settled", "cancelled": True,
                    "worktrees": [cls.gone_c]},
                   {"name": "fix-613", "state": "settled", "worktrees": [cls.shared_e]},
                   {"name": "drop-614", "state": "settled", "cancelled": True,
                    "worktrees": [cls.shared_e]},
                   {"name": "fix-615", "state": "settled", "worktrees": [cls.dirty_f]})
        cls.plan = repo.plan()

    def test_case_36_a_session_log_does_not_keep_the_worktree_of_an_accepted_task(self):
        self.assert_removed_with_branches(self.done_a, "merged PR #120")
        # The remote branch has its own reason: no worktree keeps it.
        for kind, item in (("worktree", self.done_a), ("branch", self.done_a.name)):
            self.assert_removed(
                kind, item, f"task fix-610 of the lead state {self.state} is settled, so its "
                "session logs and Antigravity conversations do not keep it")

    def test_case_37_a_process_still_keeps_the_worktree_of_an_accepted_task(self):
        self.assert_kept_with_branches(self.done_b, "live session", "process", "session log")
        self.assertNotIn("window", self.line("worktree", self.done_b)[1])

    def test_case_38_a_session_log_keeps_the_worktree_of_a_cancelled_task(self):
        self.assert_kept_with_branches(self.gone_c, "live session: session log",
                                       "its 60-minute window ends at")

    def test_case_39_the_reason_gives_the_end_of_the_window(self):
        self.assert_kept_with_branches(self.free_d, "live session: session log")
        self.assertRegex(self.line("worktree", self.free_d)[1],
                         r"; its 60-minute window ends at \d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")

    def test_case_40_a_cancelled_task_that_records_the_worktree_keeps_its_session_log(self):
        self.assert_kept_with_branches(self.shared_e, "live session: session log",
                                       "its 60-minute window ends at")

    def test_case_41_another_rule_keeps_the_worktree_and_the_reason_names_the_task(self):
        self.assert_kept_with_branches(
            self.dirty_f, f"uncommitted changes; task fix-615 of the lead state {self.state} is "
            "settled, so its session logs and Antigravity conversations do not keep it")


@NEEDS_LSOF_AND_GIT
class UnreadableLeadStateCases(PlanTestCase):
    """Cases 19, 29, and 30: a .scratch or a lead state that the plan cannot read.

    feat-m would be removed, and feat-n has uncommitted changes. One plan runs
    for each mode with the .scratch of lead-c that the plan cannot list, then
    one for each lead state in the main checkout that cannot be read.
    """

    plans: dict[str, dict[tuple[str, str], tuple[str, str]]]

    @classmethod
    def setUpClass(cls):
        repo = cls.repo = cls.make_repo()
        worktrees = {}
        for number, name in enumerate(("feat-m", "feat-n", "lead-c"), start=90):
            worktrees[name] = repo.worktree(name)
            repo.squash_merge(name, number)
        cls.feat_m, cls.feat_n, cls.lead_c = worktrees.values()
        (cls.feat_n / "wip.txt").write_text("unsaved work\n")
        unreadable = cls.lead_c / ".scratch"
        unreadable.mkdir()
        unreadable.chmod(0)
        cls.addClassCleanup(unreadable.chmod, 0o755)
        cls.plans = {"default": repo.plan(), "--main-only": repo.plan("--main-only")}
        unreadable.chmod(0o755)
        cls.state = repo.folder(repo.path, "20261124-lead-main")
        for name, text in (("invalid JSON", "{\n"), ("schema 2", '{"schema": 2, "tasks": []}\n')):
            (cls.state / "state.json").write_text(text)
            cls.plans[name] = repo.plan()

    @unittest.skipIf(os.name != "posix" or os.geteuid() == 0, "root reads every folder")
    def test_case_19_keeps_every_worktree_when_a_scratch_cannot_be_read(self):
        for mode in ("default", "--main-only"):
            with self.subTest(mode=mode):
                self.plan = self.plans[mode]
                for worktree in (self.lead_c, self.feat_m):
                    self.assert_kept_with_branches(worktree, "cannot look for a lead state",
                                                   str(self.lead_c / ".scratch"))
                self.assert_kept_with_branches(self.feat_n, "uncommitted changes")

    def test_case_29_keeps_every_worktree_when_a_lead_state_is_not_json(self):
        self.plan = self.plans["invalid JSON"]
        for worktree in (self.feat_m, self.lead_c):
            self.assert_kept_with_branches(worktree, f"cannot read the lead state {self.state}",
                                           "JSONDecodeError")
        self.assert_kept_with_branches(self.feat_n, "uncommitted changes")

    def test_case_30_keeps_every_worktree_when_a_lead_state_has_another_schema(self):
        self.plan = self.plans["schema 2"]
        self.assert_kept_with_branches(self.feat_m, f"cannot read the lead state {self.state}",
                                       "unknown lead state schema")


@NEEDS_LSOF_AND_GIT
class PlanningEntryCases(PlanTestCase):
    """Cases 42 and 43: planning_folder.py lists the entries of the planning location (#599).

    feat-p holds a file, not a folder, in its .scratch, and feat-r is a merged worktree with no
    planning folder. One plan runs; then the .scratch of feat-r becomes a file, and a second plan runs.
    """

    plans: dict[str, dict[tuple[str, str], tuple[str, str]]]

    @classmethod
    def setUpClass(cls):
        repo = cls.repo = cls.make_repo()
        cls.feat_p, cls.feat_r = repo.worktree("feat-p"), repo.worktree("feat-r")
        repo.squash_merge("feat-p", 96)
        repo.squash_merge("feat-r", 97)
        cls.notes = cls.feat_p / ".scratch" / "notes.md"
        cls.notes.parent.mkdir()
        cls.notes.write_text("notes\n")
        cls.plans = {"file in .scratch": repo.plan()}
        (cls.feat_r / ".scratch").write_text("not a folder\n")
        cls.plans[".scratch is a file"] = repo.plan()

    def test_case_42_a_file_in_the_planning_location_keeps_its_worktree(self):
        # The plan reads every entry, not only the folders that planning_folder.py --list prints.
        self.plan = self.plans["file in .scratch"]
        self.assert_kept("folder", self.notes, "no issue key")
        self.assert_kept_with_branches(self.feat_p, f"holds the kept planning folder {self.notes}")
        self.assert_removed_with_branches(self.feat_r, "merged PR #97")

    def test_case_43_a_scratch_that_is_a_file_keeps_every_worktree(self):
        # A .scratch that is a file cannot be listed, as in case 19.
        self.plan = self.plans[".scratch is a file"]
        for worktree in (self.feat_r, self.feat_p):
            self.assert_kept_with_branches(worktree, "cannot look for a lead state",
                                           str(self.feat_r / ".scratch"))


@NEEDS_LSOF_AND_GIT
class T3ThreadCases(PlanTestCase):
    """Cases 32-35: merged worktrees and the T3 Code threads that a fake t3 lists.

    An unsettled thread owns owned, through a symlink to its parent folder. A
    settled thread owns done, and no thread owns free. An unsettled thread
    without a worktree path owns no worktree. One plan runs for each case.
    """

    plans: dict[str, dict[tuple[str, str], tuple[str, str]]]

    @classmethod
    def setUpClass(cls):
        repo = cls.repo = cls.make_repo()
        worktrees = {}
        for number, name in enumerate(("owned", "done", "free"), start=110):
            worktrees[name] = repo.worktree(name)
            repo.squash_merge(name, number)
        cls.owned, cls.done, cls.free = worktrees.values()
        link = repo.tmp / "trees-link"
        link.symlink_to(repo.path / "trees")
        repo.t3_data = {
            "projects": {str(repo.path): [
                {"threadId": "thread-a", "settled": False, "status": "running"},
                {"threadId": "thread-b", "settled": True, "status": "completed"},
                {"threadId": "thread-c", "settled": False, "status": "waiting"}]},
            "threads": {"thread-a": {"thread": {"worktreePath": str(link / "owned")}},
                        "thread-b": {"thread": {"worktreePath": str(cls.done)}},
                        "thread-c": {"thread": {"worktreePath": None}}}}
        # T3CODE_CLI_PATH comes before PATH, whose t3 fails.
        wrong = repo.tmp / "t3-wrong"
        wrong.mkdir()
        (wrong / "t3").write_text("#!/bin/sh\necho wrong t3 >&2\nexit 3\n")
        (wrong / "t3").chmod(0o755)
        named = dict(repo.env, T3CODE_CLI_PATH=str(fake_t3(repo.tmp / "t3-named")),
                     PATH=f"{wrong}{os.pathsep}{repo.env['PATH']}")
        on_path = dict(repo.env, PATH=f"{fake_t3(repo.tmp / 't3-bin').parent}{os.pathsep}"
                                      f"{repo.env['PATH']}")
        cls.plans = {"threads": repo.plan(env=named)}
        cls.calls = repo.t3_calls()
        cls.plans["no CLI"] = repo.plan()
        cls.calls_without_cli = repo.t3_calls()[len(cls.calls):]
        repo.t3_data["projects"] = {}
        cls.plans["no project"] = repo.plan(env=on_path)
        repo.t3_data = {"fail": [1, "No running T3 Code server uses /home/.t3. "
                                    "Start T3 Code, then retry."]}
        cls.plans["no server"] = repo.plan(env=on_path)

    def test_case_32_keeps_the_merged_worktree_of_an_unsettled_thread(self):
        self.plan = self.plans["threads"]
        self.assert_kept_with_branches(self.owned, "T3 thread thread-a is not settled")
        self.assert_removed_with_branches(self.done, "merged PR #111")
        self.assert_removed_with_branches(self.free, "merged PR #112")
        self.assertEqual(self.calls, [
            ["thread", "list", "--json", "--project", str(self.repo.path)],
            ["thread", "show", "--json", "--messages", "1", "thread-a"],
            ["thread", "show", "--json", "--messages", "1", "thread-c"]])

    def test_case_33_without_a_t3_cli_the_other_rules_decide(self):
        self.plan = self.plans["no CLI"]
        self.assert_removed_with_branches(self.owned, "merged PR #110")
        self.assertEqual(self.calls_without_cli, [])

    def test_case_34_a_repository_that_is_no_t3_code_project_gives_no_evidence(self):
        self.plan = self.plans["no project"]
        self.assert_removed_with_branches(self.owned, "merged PR #110")

    def test_case_35_keeps_every_worktree_when_t3_fails(self):
        # The t3 CLI fails so while the T3 Code app is closed.
        self.plan = self.plans["no server"]
        for worktree in (self.owned, self.done, self.free):
            self.assert_kept_with_branches(
                worktree, "cannot read the T3 Code threads: t3 thread list exited with status 1: "
                "No running T3 Code server uses")


class T3FailureCases(unittest.TestCase):
    """Case 35 for each other failure of t3: no worktree, and the error.

    The checks call unsettled_thread_worktrees of cleanup_plan.py with a fake t3
    that T3CODE_CLI_PATH names.
    """

    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, str(PLUGIN_ROOT / "scripts"))
        cls.addClassCleanup(sys.path.remove, str(PLUGIN_ROOT / "scripts"))
        import cleanup_plan
        cls.module = cleanup_plan
        cls.tmp = Path(tempfile.mkdtemp())
        cls.addClassCleanup(shutil.rmtree, cls.tmp, True)
        cls.t3 = fake_t3(cls.tmp / "bin")

    def threads(self, data: dict, cli: Path | None = None) -> tuple[dict[str, str], str | None]:
        (self.tmp / "t3.json").write_text(json.dumps(data))
        with mock.patch.dict(os.environ, T3CODE_CLI_PATH=str(cli or self.t3),
                             FAKE_T3_DATA=str(self.tmp / "t3.json"),
                             FAKE_T3_LOG=str(self.tmp / "t3.log")):
            return self.module.unsettled_thread_worktrees("/project")

    def test_case_35_each_failure_gives_the_error_and_no_worktree(self):
        row = {"threadId": "thread-a", "settled": False}
        listed = {"/project": [row]}
        cases = {
            "the launcher finds no app": (
                {"fail": [127, "T3 Code has moved or been removed. Open the app once to update "
                               "this command."]},
                "t3 thread list exited with status 127: T3 Code has moved or been removed"),
            "the list is no JSON": ({"projects": {"/project": "not JSON"}},
                                    "t3 thread list printed no JSON"),
            "a row has no threadId": ({"projects": {"/project": [{"settled": False}]}},
                                      "KeyError: 'threadId'"),
            "a row has no settled": ({"projects": {"/project": [{"threadId": "thread-a"}]}},
                                     "KeyError: 'settled'"),
            "settled is no boolean": ({"projects": {"/project": [dict(row, settled="no")]}},
                                      "TypeError: thread thread-a has settled 'no'"),
            "show fails": ({"projects": listed},
                           "t3 thread show exited with status 1: Thread thread-a is no longer"),
            "a thread has no worktreePath": (
                {"projects": listed, "threads": {"thread-a": {"thread": {}}}},
                "KeyError: 'worktreePath'"),
        }
        for name, (data, phrase) in cases.items():
            with self.subTest(name):
                kept, error = self.threads(data)
                self.assertEqual(kept, {})
                self.assertIn("cannot read the T3 Code threads: ", error)
                self.assertIn(phrase, error)

    def test_case_35_a_timeout_gives_the_error(self):
        with mock.patch.object(self.module, "T3_TIMEOUT", 0.5):
            kept, error = self.threads({"sleep": 5, "projects": {}})
        self.assertEqual((kept, error), ({}, "cannot read the T3 Code threads: "
                                             "t3 thread list timed out after 0.5 seconds"))

    def test_case_35_a_t3code_cli_path_that_cannot_run_gives_the_error(self):
        kept, error = self.threads({}, cli=self.tmp / "missing" / "t3")
        self.assertEqual(kept, {})
        self.assertIn("cannot read the T3 Code threads: t3 thread list cannot run: ", error)


@NEEDS_LSOF_AND_GIT
class MergedTipCases(PlanTestCase):
    """Cases 20-25: branches with no commit of their own, and a worktree in a worktree.

    The t3-* branches have no commit of their own. Their tip is the head of
    merged PR #80 of feat-p, which is not in the Default Branch, or the tip
    of the Default Branch. An old branch was created two hours ago.
    """

    plans: dict[str, dict[tuple[str, str], tuple[str, str]]]

    @classmethod
    def setUpClass(cls):
        repo = cls.repo = cls.make_repo()
        repo.worktree("feat-p")
        pr_head = repo.tip("feat-p")
        repo.squash_merge("feat-p", 80)
        repo.record_commit_pr(pr_head, 80)
        cls.queued = repo.worktree("feat-q", old=True)
        repo.record_commit_pr(repo.tip("feat-q"), 81, merged=False)
        made = {}
        for name, start, old in (("t3-pr-old", "feat-p", True), ("t3-main-old", "master", True),
                                 ("t3-pr-new", "feat-p", False), ("t3-main-new", "master", False),
                                 ("t3-pr-live", "feat-p", True), ("t3-main-live", "master", True),
                                 ("t3-outer", "master", True)):
            made[name] = repo.worktree(name, own_commit=False, start=start, old=old)
        (cls.pr_old, cls.main_old, cls.pr_new, cls.main_new, cls.pr_live, cls.main_live,
         cls.outer) = made.values()
        cls.inner = repo.worktree("t3-inner", own_commit=False, old=True,
                                  parent=cls.outer / "trees")
        repo.start(cls.pr_live)
        repo.start(cls.main_live)
        cls.plans = {"default": repo.plan(), "--main-only": repo.plan("--main-only")}
        cls.plan = cls.plans["default"]

    def test_case_20_removes_an_old_branch_at_the_head_of_another_branchs_merged_pr(self):
        self.assert_removed_with_branches(self.pr_old, "no commit of its own",
                                          "head commit of merged PR #80")

    def test_case_21_removes_an_old_branch_at_a_default_branch_commit(self):
        self.assert_removed_with_branches(self.main_old, "no commit of its own",
                                          "in the Default Branch")

    def test_case_22_keeps_such_a_branch_created_less_than_60_minutes_ago(self):
        for worktree in (self.pr_new, self.main_new):
            with self.subTest(worktree=worktree.name):
                self.assert_kept_with_branches(worktree, "no commit of its own",
                                               "less than 60 minutes ago")

    def test_case_23_keeps_such_a_branch_with_a_live_session(self):
        for worktree in (self.pr_live, self.main_live):
            with self.subTest(worktree=worktree.name):
                self.assert_kept_with_branches(worktree, "live session", "process")

    def test_case_24_keeps_a_worktree_that_contains_another_worktree_in_every_mode(self):
        for mode, plan in self.plans.items():
            with self.subTest(mode=mode):
                self.plan = plan
                self.assert_kept_with_branches(self.outer, "contains the worktree",
                                               str(self.inner))
                self.assert_removed_with_branches(self.inner, "in the Default Branch")

    def test_case_25_keeps_a_branch_whose_tip_is_the_head_of_an_open_pr(self):
        self.assert_kept_with_branches(self.queued, "not merged")


@unittest.skipUnless(shutil.which("git"), "needs git")
class NoPlanCases(unittest.TestCase):
    def setUp(self):
        self.repo = Repo()
        self.addCleanup(self.repo.cleanup)

    def test_fails_without_a_known_default_branch(self):
        self.repo.git("remote", "set-head", "origin", "-d")

        result = self.repo.run()

        self.assertEqual(result.returncode, 1)
        self.assertIn("cleanup_plan: cannot find the Default Branch", result.stderr)
        self.assertEqual(result.stdout, "")

    @unittest.skipUnless(shutil.which("lsof"), "needs lsof")
    def test_takes_the_default_branch_from_the_option_when_the_remote_names_none(self):
        self.repo.git("remote", "set-head", "origin", "-d")

        plan = self.repo.plan("--default-branch", "master")

        self.assertEqual(plan[("branch", "master")], ("KEEP", "the Default Branch"))

    def test_fails_outside_a_repository(self):
        result = self.repo.run("--repo", str(self.repo.tmp / "home"))

        self.assertEqual(result.returncode, 1)
        self.assertIn("cleanup_plan:", result.stderr)
        self.assertEqual(result.stdout, "")


class HostCopyTests(unittest.TestCase):
    """Every host copy runs the scripts (issue #459)."""

    def test_every_repo_cleanup_copy_runs_both_scripts(self):
        for folder, root in HOSTS.items():
            text = (PLUGIN_ROOT / folder / "repo-cleanup" / "SKILL.md").read_text(encoding="utf-8")
            for script in ("cleanup_plan.py", "open_closing_issues.py"):
                command = f'python3 "{root}/scripts/{script}"'
                with self.subTest(folder=folder, script=script):
                    self.assertTrue(command in text,
                                    f"{folder}/repo-cleanup does not run {command}")

    def test_every_matt_automode_copy_runs_the_closure_check_in_phase_7(self):
        for folder, root in HOSTS.items():
            text = (PLUGIN_ROOT / folder / "matt-automode" / "SKILL.md").read_text(encoding="utf-8")
            self.assertIn("7. **Cleanup", text)
            phase = text.partition("7. **Cleanup")[2].partition("8. **Retro")[0]
            command = f'python3 "{root}/scripts/open_closing_issues.py"'
            with self.subTest(folder=folder):
                self.assertTrue(command in phase,
                                f"phase 7 of {folder}/matt-automode does not run {command}")


if __name__ == "__main__":
    unittest.main()
