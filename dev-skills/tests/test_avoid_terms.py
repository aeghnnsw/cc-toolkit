"""Command-line checks for avoid_terms.py, which matt-automode runs before a commit.

Each check builds a temporary Git repository with a small fixture glossary:
GLOSSARY.md at the root and lab/GLOSSARY.md in a subfolder. The base commit is
tagged "base", and the checks read the lines that the script prints.
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
        return subprocess.run([sys.executable, str(SCRIPT), "--base", ref],
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


if __name__ == "__main__":
    unittest.main()
