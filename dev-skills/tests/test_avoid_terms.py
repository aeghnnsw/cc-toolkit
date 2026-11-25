"""Command-line checks for avoid_terms.py, which matt-automode runs before a commit.

Each check builds a temporary Git repository with a small fixture glossary:
GLOSSARY.md at the root and lab/GLOSSARY.md in a subfolder. The base commit is
tagged "base", and the checks read the lines that the script prints. Other
checks name files instead of, or as well as, the base.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PLUGIN_ROOT / "scripts" / "avoid_terms.py"

ROOT_GLOSSARY = "# Fixture\n\n**Worker**:\nA child agent that runs a brief.\n_Avoid_: Subagent\n"
LAB_GLOSSARY = "# Lab\n\n**Flag**:\nA stop that the critic raises.\n_Avoid_: Safety stop, block\n"


@unittest.skipUnless(shutil.which("git"), "needs git")
class AvoidTermsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        (self.tmp / "gitconfig").write_text("")
        self.env = dict(
            os.environ,
            HOME=str(self.tmp),
            GIT_CONFIG_GLOBAL=str(self.tmp / "gitconfig"),
            GIT_CONFIG_NOSYSTEM="1",
            GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.invalid",
            GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.invalid",
        )
        self.repo = self.tmp / "repo"
        self.git("init", "-q", "-b", "master", str(self.repo), cwd=self.tmp)

    def git(self, *args: str, cwd: Path | None = None) -> None:
        subprocess.run(["git", *args], cwd=cwd or self.repo, env=self.env,
                       capture_output=True, text=True, check=True)

    def write(self, name: str, text: str) -> None:
        path = self.repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)

    def commit(self, files: dict[str, str], tag: str = "") -> None:
        for name, text in files.items():
            self.write(name, text)
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "change")
        if tag:
            self.git("tag", tag)

    def base(self, files: dict[str, str] | None = None) -> None:
        self.commit({"GLOSSARY.md": ROOT_GLOSSARY, "lab/GLOSSARY.md": LAB_GLOSSARY,
                     **(files or {})}, tag="base")

    def run_script(self, ref: str = "base", cwd: Path | None = None):
        return self.run_args("--base", ref, cwd=cwd)

    def run_args(self, *args: str, cwd: Path | None = None):
        return subprocess.run([sys.executable, str(SCRIPT), *args],
                              cwd=cwd or self.repo, env=self.env, capture_output=True, text=True)

    def test_committed_added_line_hits_from_a_subfolder(self):
        self.base()
        self.commit({"docs/a.md": "Intro.\nStart a Subagent, then a subagent.\n"})
        result = self.run_script(cwd=self.repo / "docs")
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertEqual(result.stdout, 'docs/a.md:2: "Subagent" (glossary term: Worker)\n')

    def test_uncommitted_and_untracked_lines_hit(self):
        self.base({"README.md": "Intro.\n", ".gitignore": "ignored.md\n"})
        self.write("README.md", "Intro.\nPass a SAFETY STOP.\n")
        self.write("notes.md", "Notes.\nA subagent ran.\n")
        self.write("ignored.md", "A subagent ran.\n")
        result = self.run_script()
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertEqual(result.stdout.splitlines(), [
            'README.md:2: "Safety stop" (glossary term: Flag)',
            'notes.md:2: "Subagent" (glossary term: Worker)',
        ])

    def test_code_other_files_old_lines_and_longer_words_do_not_hit(self):
        old = "Keep this subagent line.\n"
        self.base({"README.md": old + "Remove this subagent line.\n"})
        self.commit({"README.md": old, "notes.txt": "A subagent ran.\n"})
        self.write("README.md", old + "Run `subagent` or ``a block``.\n"
                   "Blocking and unblock are fine.\n```text\nsubagent\n```\nA block here.\n")
        self.write("GLOSSARY.md", ROOT_GLOSSARY + "\nA subagent is a worker.\n")
        result = self.run_script()
        # The last README.md line is the only hit; it shows that the file was read.
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertEqual(result.stdout, 'README.md:7: "block" (glossary term: Flag)\n')

    def test_no_glossary_checks_nothing_and_exits_0(self):
        self.commit({"README.md": "Intro.\n"}, tag="base")
        self.write("notes.md", "A subagent ran.\n")
        result = self.run_script()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("nothing was checked", result.stdout)

    def test_unknown_ref_exits_2(self):
        self.base()
        result = self.run_script(ref="no-such-ref")
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")
        self.assertIn("no-such-ref", result.stderr)

    def test_named_files_check_every_line_from_a_subfolder(self):
        self.base({"docs/a.md": "Start a subagent.\n", ".gitignore": "/.scratch/\n"})
        self.write(".scratch/draft.txt", "Intro.\nPass the block to a `subagent`.\n")
        self.write("docs/clean.md", "Start a worker.\n")
        outside = self.tmp / "outside.md"
        outside.write_text("A safety stop.\n")
        result = self.run_args("a.md", "../.scratch/draft.txt", "../GLOSSARY.md", "clean.md",
                               str(outside), cwd=self.repo / "docs")
        # The old docs/a.md line is a hit, and the glossary is not checked.
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertEqual(result.stdout.splitlines(), sorted([
            '.scratch/draft.txt:2: "block" (glossary term: Flag)',
            'docs/a.md:1: "Subagent" (glossary term: Worker)',
            f'{outside.resolve()}:1: "Safety stop" (glossary term: Flag)',
        ]))
        clean = self.run_args("docs/clean.md")
        self.assertEqual((clean.returncode, clean.stdout),
                         (0, "No checked line has a glossary _Avoid_ term.\n"), clean.stderr)

    def test_base_and_named_files_check_both_and_base_alone_is_unchanged(self):
        self.base({"README.md": "Old subagent line.\n", "notes.md": "Old block line.\n"})
        self.write("README.md", "Old subagent line.\nA new block.\n")
        result = self.run_args("--base", "base", "README.md", "notes.md")
        # README.md is in the diff and named: all its lines count, and each hit is listed once.
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertEqual(result.stdout.splitlines(), [
            'README.md:1: "Subagent" (glossary term: Worker)',
            'README.md:2: "block" (glossary term: Flag)',
            'notes.md:1: "block" (glossary term: Flag)',
        ])
        self.write("README.md", "Old subagent line.\nA new worker.\n")
        alone = self.run_script()
        self.assertEqual((alone.returncode, alone.stdout),
                         (0, "No added Markdown line has a glossary _Avoid_ term.\n"), alone.stderr)

    def test_missing_file_folder_or_no_argument_exits_2(self):
        self.commit({"README.md": "Intro.\n"}, tag="base")
        for args in (["README.md", "no-such.md"], ["--base", "base", "docs"], []):
            (self.repo / "docs").mkdir(exist_ok=True)
            with self.subTest(args=args):
                result = self.run_args(*args)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")
                self.assertTrue(result.stderr)
        self.assertIn("no-such.md", self.run_args("README.md", "no-such.md").stderr)


if __name__ == "__main__":
    unittest.main()
