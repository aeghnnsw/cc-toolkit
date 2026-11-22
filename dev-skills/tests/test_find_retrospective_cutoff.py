"""Command-line checks for find_retrospective_cutoff.py, which matt-automode runs.

Each check runs the script with a fake gh (fake_gh.py) that answers from fixed
comment and PR data. No check reads or changes GitHub. The record bodies copy
the record forms on the merged cc-toolkit PRs #355, #393, #424, and #444.
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
SCRIPT = TESTS.parent / "scripts" / "find_retrospective_cutoff.py"
COMMENTS = "repos/{owner}/{repo}/issues/comments?per_page=100"

PR_355 = ("Standards and Spec reviews passed at `50e45e2` against `f90896b`.\n\n"
          "### Navigation retrospective\n\nReviewed through: 2026-10-27T15:02:52.722Z\n")
PR_393 = ("## Navigation retrospective\n\n**Reviewed through:** "
          "`2026-11-09T00:22:55.226+00:00`, after PR #387's cutoff.\n")
PR_424 = ("## Navigation retrospective\n\n**Reviewed through:** "
          "`2026-11-18T16:26:08.234+00:00`, after PR #423's `2026-11-18T15:16:58.363+00:00`.\n")
PR_444 = "## Navigation retrospective\n\n**Reviewed through:** 2026-11-21T05:16:55Z\n"


def record(cutoff: str) -> str:
    return f"## Navigation retrospective\n\n**Reviewed through:** {cutoff}\n\nFindings: none.\n"


def comment(number: int, body: str) -> dict:
    return {"issue_url": f"https://api.github.com/repos/o/r/issues/{number}", "body": body}


class FindRetrospectiveCutoffTests(unittest.TestCase):
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

    def find(self, data: dict) -> subprocess.CompletedProcess[str]:
        (self.tmp / "gh.json").write_text(json.dumps(data))
        return subprocess.run([sys.executable, str(SCRIPT)], env=self.env,
                              capture_output=True, text=True, timeout=60)

    def gh_calls(self) -> list[list[str]]:
        log = self.tmp / "gh.log"
        return [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []

    def assert_cutoff(self, data: dict, expected: str) -> None:
        result = self.find(data)
        self.assertEqual((result.returncode, result.stdout), (0, expected + "\n"), result.stderr)

    def test_reads_each_record_form(self):
        for number, body, expected in (
                (355, PR_355, "2026-10-27T15:02:52.722Z PR #355"),
                (393, PR_393, "2026-11-09T00:22:55.226Z PR #393"),
                (444, PR_444, "2026-11-21T05:16:55Z PR #444")):
            with self.subTest(pr=number):
                self.assert_cutoff({"comments": [[comment(number, body)]], "merged": [number]},
                                   expected)

    def test_the_greatest_cutoff_wins_across_record_forms(self):
        comments = [comment(n, body) for n, body in ((355, PR_355), (444, PR_444), (424, PR_424))]
        self.assert_cutoff({"comments": [comments], "merged": [355, 424, 444]},
                           "2026-11-21T05:16:55Z PR #444")
        calls = self.gh_calls()
        self.assertEqual(calls[0], ["api", "--paginate", COMMENTS])
        self.assertEqual(calls[1][:2], ["pr", "list"])
        self.assertEqual(calls[1][calls[1].index("--state") + 1], "merged")

    def test_compares_cutoffs_as_times_not_as_text(self):
        # As text, "...:08Z" sorts after "...:08.234+00:00"; as a time, it is earlier.
        comments = [comment(500, record("2026-11-18T16:26:08Z")), comment(424, PR_424)]
        self.assert_cutoff({"comments": [comments], "merged": [424, 500]},
                           "2026-11-18T16:26:08.234Z PR #424")

    def test_a_time_that_does_not_exist_does_not_count(self):
        comments = [comment(501, record("2026-11-31T00:00:00Z")), comment(444, PR_444)]
        self.assert_cutoff({"comments": [comments], "merged": [444, 501]},
                           "2026-11-21T05:16:55Z PR #444")

    def test_only_records_on_merged_prs_count(self):
        issue = comment(294, "Navigation retrospective of the #314 run.\n\n"
                             "**Reviewed through:** 2026-11-22T00:00:00Z\n")
        unmerged = comment(600, record("2026-11-22T01:00:00Z"))
        self.assert_cutoff({"comments": [[issue, unmerged, comment(444, PR_444)]], "merged": [444]},
                           "2026-11-21T05:16:55Z PR #444")

    def test_a_cutoff_outside_a_record_field_does_not_count(self):
        comments = [
            comment(498, "Reviewed through 2026-11-18T06:30:00Z, outside a record.\n"),
            comment(499, "Quoted from a draft:\n\n**Reviewed through:** 2026-11-19T00:00:00Z\n"),
            comment(497, "## Navigation retrospective\n\nReviewed through 2026-11-20T00:00:00Z.\n"),
            comment(446, "Write `**Reviewed through:** YYYY-MM-DDTHH:MM:SSZ` in the "
                         "Navigation retrospective record.\n"),
            comment(512, record("2026-11-18T06:04:17Z, before PR #600's 2026-11-23T00:00:00Z")),
        ]
        self.assert_cutoff({"comments": [comments], "merged": [446, 497, 498, 499, 512]},
                           "2026-11-18T06:04:17Z PR #512")

    def test_reads_every_comment_page(self):
        pages = [[comment(393, PR_393)], [comment(444, PR_444)]]
        self.assert_cutoff({"comments": pages, "merged": [393, 444]},
                           "2026-11-21T05:16:55Z PR #444")

    def test_no_record_on_a_merged_pr_exits_1(self):
        issue = comment(294, record("2026-11-22T00:00:00Z"))
        result = self.find({"comments": [[comment(444, "Looks good."), issue]], "merged": [444]})
        self.assertEqual((result.returncode, result.stdout), (1, ""))
        self.assertIn("No Navigation retrospective record", result.stderr)

    def test_a_failed_gh_call_exits_1_with_the_gh_error(self):
        result = self.find({"fail": "error connecting to api.github.com"})
        self.assertEqual((result.returncode, result.stdout), (1, ""))
        self.assertIn("FAIL: gh api failed:", result.stderr)
        self.assertIn("error connecting to api.github.com", result.stderr)


if __name__ == "__main__":
    unittest.main()
