"""Command-line checks for the goal-rubric shape check, scripts/check_goal_rubric.py.

Each check writes a rubric to a temporary directory, runs the script in a
child process, and reads its exit status and output. The host copies of the
script are identical; tests/test_host_copies.py checks that.
"""

from __future__ import annotations

import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PLUGIN_ROOT / "skills" / "goal-rubric" / "scripts" / "check_goal_rubric.py"
SKILL_COPIES = [PLUGIN_ROOT / folder / "goal-rubric" / "SKILL.md"
                for folder in ("skills", "codex-skills", "antigravity-skills")]

CRITERIA = """\
1. Auth tests - End state: every test in test/auth passes. Check: `pytest test/auth` prints `0 failed`. Constraint: no file outside `src/auth/` changes.
2. Lint - End state: ruff reports no finding. Check:
   `ruff check src/auth` prints `All checks passed!`.
"""
STOP = "or stop after 20 turns\n"
CONDITION = ("all tests in test/auth pass (pytest prints 0 failed) and `git status` prints `working tree clean`, "
             "without modifying any file outside src/auth/, or stop after 20 turns\n")


def rubric(criteria: str = CRITERIA, stop: str = STOP, condition: str = CONDITION) -> str:
    return (f"# Goal rubric: fix the auth tests\n\n## Criteria (all must pass)\n{criteria}\n"
            f"## Stop clause\n{stop}\n## /goal condition (Claude Code)\n{condition}")


def run_check(text: str) -> tuple[int, list[str]]:
    """Run the script on a rubric; return its exit status and its output lines without the file path."""
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "goal-rubric-auth.md"
        path.write_text(text, encoding="utf-8")
        completed = subprocess.run([sys.executable, str(SCRIPT), str(path)], capture_output=True, text=True)
        lines = [line.replace(str(path), "rubric") for line in completed.stdout.splitlines()]
    return completed.returncode, lines


class ValidRubricTests(unittest.TestCase):
    def test_a_rubric_in_the_skill_shape_passes(self):
        # CONDITION quotes `working tree clean`, the output of git status: a vague word in inline code does not warn.
        status, lines = run_check(rubric())
        self.assertEqual(status, 0, lines)
        self.assertEqual(lines, [f"rubric: 2 criteria, a {len(CONDITION.strip())}-character condition (limit 4,000): "
                                 "0 errors, 0 warnings"])

    def test_the_rubric_shape_in_each_skill_copy_passes(self):
        for skill in SKILL_COPIES:
            with self.subTest(skill=skill.relative_to(PLUGIN_ROOT).as_posix()):
                shape = re.search(r"## Rubric Shape\n\n```markdown\n(.*?)\n```\n", skill.read_text(encoding="utf-8"),
                                  re.DOTALL)
                self.assertIsNotNone(shape, "the skill has no Rubric Shape block")
                # The "2. ..." line stands for more criteria; it is not a criterion.
                template = shape.group(1).replace("2. ...\n", "")
                status, lines = run_check(template)
                self.assertEqual(status, 0, lines)
                self.assertTrue(lines[-1].startswith("rubric: 1 criterion, "), lines)

    def test_a_condition_of_4000_characters_in_a_fence_passes(self):
        status, lines = run_check(rubric(condition="```text\n" + "x" * 4000 + "\n```\n"))
        self.assertEqual(status, 0, lines)
        self.assertIn("a 4,000-character condition", lines[-1])


class ErrorTests(unittest.TestCase):
    def assert_error(self, text: str, expected: str):
        status, lines = run_check(text)
        self.assertEqual(status, 1, lines)
        self.assertIn(expected, lines)

    def test_an_empty_criteria_list_fails(self):
        self.assert_error(rubric(criteria="- Auth tests pass.\n"),
                          "rubric:3: error: the Criteria section has no numbered criterion")
        self.assert_error(rubric().replace("## Criteria (all must pass)", "## Goals"),
                          "rubric: error: the rubric has no Criteria section")

    def test_a_criterion_without_an_end_state_fails(self):
        criteria = CRITERIA.replace("2. Lint - End state: ruff reports no finding.", "2. Lint - ruff reports no finding.")
        self.assert_error(rubric(criteria=criteria), 'rubric:5: error: criterion 2 has no "End state:" part')

    def test_a_criterion_without_a_check_fails(self):
        criteria = CRITERIA.replace("Check: `pytest test/auth`", "`pytest test/auth`")
        self.assert_error(rubric(criteria=criteria), 'rubric:4: error: criterion 1 has no "Check:" part')
        criteria = CRITERIA.replace("   `ruff check src/auth` prints `All checks passed!`.\n", "")
        self.assert_error(rubric(criteria=criteria), 'rubric:5: error: criterion 2 has an empty "Check:" part')

    def test_an_empty_stop_clause_fails(self):
        self.assert_error(rubric(stop="\n"), "rubric:8: error: the Stop clause section is empty")

    def test_a_condition_over_4000_characters_fails(self):
        self.assert_error(rubric(condition="x" * 4001 + "\n"),
                          "rubric:11: error: the /goal condition has 4,001 characters; the limit is 4,000")


class WarningTests(unittest.TestCase):
    def test_a_vague_word_warns_and_passes(self):
        criteria = CRITERIA.replace("ruff reports no finding", "the code is mostly clean")
        status, lines = run_check(rubric(criteria=criteria))
        self.assertEqual(status, 0, lines)
        self.assertEqual(lines[:2], ['rubric:5: warning: vague word "clean"', 'rubric:5: warning: vague word "mostly"'])
        self.assertTrue(lines[-1].endswith("0 errors, 2 warnings"), lines)


class ReadErrorTests(unittest.TestCase):
    def test_a_missing_file_exits_2(self):
        with tempfile.TemporaryDirectory() as tmp:
            completed = subprocess.run([sys.executable, str(SCRIPT), str(Path(tmp) / "missing.md")],
                                       capture_output=True, text=True)
        self.assertEqual(completed.returncode, 2)
        self.assertIn("cannot read", completed.stderr)


if __name__ == "__main__":
    unittest.main()
