"""Command-line checks for open_closing_issues.py, which repo-cleanup runs after closure.

Each check runs the script with a fake gh (fake_gh.py) that answers from fixed
PR and issue data. No check reads or changes GitHub.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TESTS = Path(__file__).resolve().parent
SCRIPT = TESTS.parent / "scripts" / "open_closing_issues.py"
REPO_URL = "https://github.com/o/r"


def pr(number: int, state: str = "MERGED", closes: tuple[int, ...] = ()) -> dict:
    return {"number": number, "state": state, "url": f"{REPO_URL}/pull/{number}",
            "closingIssuesReferences": [{"number": n, "url": f"{REPO_URL}/issues/{n}"}
                                        for n in closes]}


def issue(number: int, state: str, reason: str = "") -> tuple[str, dict]:
    url = f"{REPO_URL}/issues/{number}"
    return url, {"number": number, "state": state, "stateReason": reason, "url": url}


class OpenClosingIssuesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        bin_dir = self.tmp / "bin"
        bin_dir.mkdir()
        gh = bin_dir / "gh"
        gh.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{TESTS / "fake_gh.py"}" "$@"\n')
        gh.chmod(0o755)
        self.env = dict(os.environ, PATH=f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}",
                        FAKE_GH_DATA=str(self.tmp / "gh.json"),
                        FAKE_GH_LOG=str(self.tmp / "gh.log"))
        self.data = {
            "pr_view": {"70": pr(70, closes=(80, 81)), "71": pr(71, closes=(82,)),
                        "72": pr(72), "73": pr(73, state="OPEN", closes=(83,))},
            "issues": dict([issue(80, "CLOSED", "COMPLETED"), issue(81, "OPEN"),
                            issue(82, "CLOSED", "COMPLETED"), issue(83, "OPEN")]),
        }

    def run_script(self, *prs: str) -> subprocess.CompletedProcess[str]:
        (self.tmp / "gh.json").write_text(json.dumps(self.data))
        return subprocess.run([sys.executable, str(SCRIPT), *prs], env=self.env,
                              capture_output=True, text=True)

    def test_lists_each_closing_issue_and_fails_when_one_is_open(self):
        result = self.run_script("70", "71")

        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertEqual(result.stdout.splitlines(), [
            f"CLOSED\t{REPO_URL}/issues/80\tmerged PR {REPO_URL}/pull/70",
            f"OPEN\t{REPO_URL}/issues/81\tmerged PR {REPO_URL}/pull/70",
            f"CLOSED\t{REPO_URL}/issues/82\tmerged PR {REPO_URL}/pull/71",
        ])

    def test_passes_when_every_closing_issue_is_closed(self):
        result = self.run_script("71")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout,
                         f"CLOSED\t{REPO_URL}/issues/82\tmerged PR {REPO_URL}/pull/71\n")

    def test_reports_a_merged_pr_with_no_closing_issue(self):
        result = self.run_script("72")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, f"NONE\t{REPO_URL}/pull/72\tno closing issue references\n")

    def test_cannot_check_a_pr_that_is_not_merged(self):
        result = self.run_script("71", "73")

        self.assertEqual(result.returncode, 2)
        self.assertIn(f"open_closing_issues: PR {REPO_URL}/pull/73 is not merged (state OPEN)",
                      result.stderr)

    def test_cannot_check_when_gh_fails(self):
        self.data["fail"] = "HTTP 401: Bad credentials (https://api.github.com/graphql)"

        result = self.run_script("70")

        self.assertEqual(result.returncode, 2)
        self.assertIn("HTTP 401: Bad credentials", result.stderr)
        self.assertEqual(result.stdout, "")

    def test_runs_only_read_commands(self):
        self.run_script("70", "71", "72")

        calls = [json.loads(line) for line in (self.tmp / "gh.log").read_text().splitlines()]
        self.assertEqual({tuple(call[:2]) for call in calls}, {("pr", "view"), ("issue", "view")})


if __name__ == "__main__":
    unittest.main()
