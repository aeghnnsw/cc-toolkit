"""Command-line checks for planning_folder.py, which grill-with-research and matt-automode run.

Each check builds a temporary Git repository with an empty global Git
configuration, so no ignore rule of the user applies, and reads the lines that
the script prints. Issue #463 moves the mechanical rules of the planning folder
(issue #421) into the script. Issue #599 makes t3_project_lead.py and
cleanup_plan.py of repo-cleanup find their folders with this module.
"""

from __future__ import annotations

import datetime
import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PLUGIN_ROOT / "scripts" / "planning_folder.py"
REPOSITORY_GITIGNORE = PLUGIN_ROOT.parent / ".gitignore"
_SPEC = importlib.util.spec_from_file_location("planning_folder_under_test", SCRIPT)
PLANNING = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(PLANNING)
# The scripts that import this module for their folders (#599).
CALLERS = ("t3_project_lead.py", "cleanup_plan.py")


def today() -> str:
    return f"{datetime.date.today():%Y%m%d}"


@unittest.skipUnless(shutil.which("git"), "needs git")
class PlanningFolderTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        (self.tmp / "gitconfig").write_text("")
        inherited = {k: v for k, v in os.environ.items()
                     if k not in ("GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR", "GIT_INDEX_FILE")}
        self.env = dict(
            inherited,
            HOME=str(self.tmp),
            XDG_CONFIG_HOME=str(self.tmp / "xdg"),
            GIT_CONFIG_GLOBAL=str(self.tmp / "gitconfig"),
            GIT_CONFIG_NOSYSTEM="1",
            GIT_CEILING_DIRECTORIES=str(self.tmp),
            GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.invalid",
            GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.invalid",
        )
        self.repo = self.tmp / "repo"
        self.git("init", "-q", "-b", "master", str(self.repo), cwd=self.tmp)
        self.exclude = self.repo / ".git" / "info" / "exclude"

    def git(self, *args: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
        return subprocess.run(["git", *args], cwd=cwd or self.repo, env=self.env,
                              capture_output=True, text=True, check=True)

    def run_script(self, *args: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, str(SCRIPT), *args], cwd=cwd or self.repo,
                              env=self.env, capture_output=True, text=True)

    def ignored(self, cwd: Path | None = None) -> bool:
        return subprocess.run(["git", "check-ignore", "-q", ".scratch/"], cwd=cwd or self.repo,
                              env=self.env).returncode == 0

    def test_folder_that_git_does_not_ignore_gets_an_exclude_line(self):
        (self.repo / "src").mkdir()
        self.assertFalse(self.ignored())

        result = self.run_script("cache-layer", "--issue", "42", cwd=self.repo / "src")

        self.assertEqual(result.returncode, 0, result.stderr)
        folder = self.repo / ".scratch" / "42-cache-layer"
        self.assertEqual(result.stdout.splitlines(), [
            f"Ignore: Git did not ignore .scratch/; added /.scratch/ to {self.exclude}",
            f"Planning folder: {folder} (created)",
            "Next step prefix: 01_",
        ])
        self.assertTrue(folder.is_dir())
        self.assertTrue(self.exclude.read_text().endswith("\n/.scratch/\n"))
        self.assertTrue(self.ignored())
        self.assertEqual(self.git("status", "--porcelain", "--untracked-files=all").stdout, "")

    def test_exclude_file_without_a_final_newline_keeps_its_last_line(self):
        self.exclude.write_text("*.log")

        self.assertEqual(self.run_script("x").returncode, 0)

        self.assertEqual(self.exclude.read_text(), "*.log\n/.scratch/\n")

    def test_repository_gitignore_needs_no_exclude_line(self):
        shutil.copy(REPOSITORY_GITIGNORE, self.repo / ".gitignore")
        before = self.exclude.read_text()

        result = self.run_script("cache-layer", "--issue", "42")

        self.assertEqual(result.returncode, 0, result.stderr)
        line = next(i for i, text in enumerate(REPOSITORY_GITIGNORE.read_text().splitlines(), 1)
                    if text == "/.scratch/")
        self.assertEqual(result.stdout.splitlines()[0], f"Ignore: Git ignores .scratch/ (.gitignore:{line}:/.scratch/)")
        self.assertEqual(self.exclude.read_text(), before)

    def test_negated_rule_fails_and_creates_no_folder(self):
        (self.repo / ".gitignore").write_text("!/.scratch/\n")

        result = self.run_script("cache-layer", "--issue", "42")

        self.assertEqual(result.returncode, 1)
        self.assertIn("Git still does not ignore .scratch/", result.stderr)
        self.assertFalse((self.repo / ".scratch").exists())

    def test_linked_worktree_keeps_its_folder_and_shares_the_exclude_file(self):
        self.git("commit", "-q", "--allow-empty", "-m", "init")
        tree = self.tmp / "trees" / "feat-77"
        self.git("worktree", "add", "-q", "-b", "feat-77", str(tree))

        result = self.run_script("cache-layer", "--issue", "77", cwd=tree)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(f"added /.scratch/ to {self.exclude}", result.stdout)
        self.assertIn(f"Planning folder: {tree / '.scratch' / '77-cache-layer'} (created)", result.stdout)
        self.assertFalse((self.repo / ".scratch").exists())
        self.assertTrue(self.ignored(cwd=self.repo))

    def test_dated_folder_is_reused_then_renamed_for_the_issue(self):
        days = {today()}
        first = self.run_script("cache-layer")
        days.add(today())  # The run can cross midnight.
        self.assertEqual(first.returncode, 0, first.stderr)
        folder = next((self.repo / ".scratch").iterdir())
        self.assertIn(folder.name, {f"{day}-cache-layer" for day in days})
        self.assertIn(f"Planning folder: {folder} (created)", first.stdout)
        (folder / "01_research.md").write_text("")
        (folder / "01_1_flag_check.sh").write_text("")

        again = self.run_script("cache-layer")
        renamed = self.run_script("cache-layer", "--issue", "42")

        self.assertIn(f"Planning folder: {folder} (exists)", again.stdout)
        self.assertIn("Next step prefix: 02_", again.stdout)
        target = self.repo / ".scratch" / "42-cache-layer"
        self.assertEqual(renamed.returncode, 0, renamed.stderr)
        self.assertIn(f"Planning folder: {target} (renamed from {folder.name})", renamed.stdout)
        self.assertEqual(sorted(p.name for p in target.iterdir()), ["01_1_flag_check.sh", "01_research.md"])
        self.assertFalse(folder.exists())

    def test_folder_of_an_earlier_day_is_reused_without_an_issue(self):
        earlier = self.repo / ".scratch" / "20250102-cache-layer"
        earlier.mkdir(parents=True)

        result = self.run_script("cache-layer")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(f"Planning folder: {earlier} (exists)", result.stdout)
        self.assertEqual(sorted(p.name for p in earlier.parent.iterdir()), ["20250102-cache-layer"])

    def test_two_dated_folders_for_the_slug_fail(self):
        for name in ("20250102-cache-layer", "20250103-cache-layer", "20250104-other", "2025010x-cache-layer"):
            (self.repo / ".scratch" / name).mkdir(parents=True)

        result = self.run_script("cache-layer", "--issue", "42")

        self.assertEqual(result.returncode, 1)
        self.assertIn("more than one folder for cache-layer: 20250102-cache-layer, 20250103-cache-layer;",
                      result.stderr)
        self.assertFalse((self.repo / ".scratch" / "42-cache-layer").exists())

    def test_next_prefix_follows_the_greatest_step_and_keeps_its_width(self):
        folder = self.repo / ".scratch" / "42-cache-layer"
        folder.mkdir(parents=True)
        for name in ("001_plan.md", "012_1_check.sh", "notes.md", "a_1.md", "099"):
            (folder / name).write_text("")

        result = self.run_script("cache-layer", "--issue", "42")

        self.assertIn(f"Planning folder: {folder} (exists)", result.stdout)
        self.assertIn("Next step prefix: 013_", result.stdout)

    def test_list_prints_the_folders_and_changes_nothing(self):
        scratch = self.repo / ".scratch"
        for name in ("42-cache-layer", "20250102-draft"):
            (scratch / name).mkdir(parents=True)
        (scratch / "notes.txt").write_text("")
        before = self.exclude.read_text()

        result = self.run_script("--list", cwd=scratch / "42-cache-layer")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, f"{scratch / '20250102-draft'}\n{scratch / '42-cache-layer'}\n")
        self.assertEqual(self.exclude.read_text(), before)

    def test_list_without_a_scratch_folder_prints_nothing(self):
        result = self.run_script("--list")

        self.assertEqual((result.returncode, result.stdout), (0, ""))
        self.assertFalse((self.repo / ".scratch").exists())

    def test_bad_arguments_are_a_usage_error(self):
        for args in ((), ("--list", "x"), ("--list", "--issue", "4"), ("Cache_Layer",), ("x", "--issue", "0")):
            with self.subTest(args=args):
                self.assertEqual(self.run_script(*args).returncode, 2)
        self.assertFalse((self.repo / ".scratch").exists())

    def test_entries_list_files_too_at_any_location(self):
        # repo-cleanup keeps a worktree that holds a file in its planning location (#599).
        for location in (".scratch", "docs/plans"):
            with self.subTest(location=location):
                folder = self.repo / location
                (folder / "42-cache-layer").mkdir(parents=True)
                (folder / "notes.md").write_text("")
                self.assertEqual(PLANNING.entries(str(self.repo), location),
                                 [str(folder / "42-cache-layer"), str(folder / "notes.md")])
        self.assertEqual(PLANNING.list_folders(str(self.repo)), [str(self.repo / ".scratch" / "42-cache-layer")])
        self.assertEqual(PLANNING.entries(str(self.repo), "missing"), [])

    @unittest.skipIf(os.name != "posix" or os.geteuid() == 0, "root reads every folder")
    def test_an_unreadable_location_fails(self):
        scratch = self.repo / ".scratch"
        scratch.mkdir()
        scratch.chmod(0)
        self.addCleanup(scratch.chmod, 0o755)
        with self.assertRaisesRegex(PLANNING.Failed, f"cannot read {scratch}: "):
            PLANNING.list_folders(str(self.repo))

    def test_the_lead_and_cleanup_keep_no_folder_listing_of_their_own(self):
        # Both scripts list folders only through this module (#599).
        for name in CALLERS:
            with self.subTest(script=name):
                text = (SCRIPT.parent / name).read_text(encoding="utf-8")
                self.assertRegex(text, r"(?m)^(import planning_folder|from planning_folder import )")
                self.assertNotIn("listdir(", text)
                self.assertNotIn("scandir(", text)

    def test_outside_a_repository_fails(self):
        result = self.run_script("cache-layer", cwd=self.tmp)

        self.assertEqual(result.returncode, 1)
        self.assertIn("not in a Git working tree", result.stderr)


if __name__ == "__main__":
    unittest.main()
