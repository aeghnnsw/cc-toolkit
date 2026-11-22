"""Command-line checks for phase_gate.py, which matt-automode runs before coding.

Each check runs the script with a fake gh (fake_gh.py) that answers GraphQL
queries from fixed issue data. No check reads or changes GitHub. The ticket
bodies follow the to-tickets issue template.
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
SCRIPT = TESTS.parent / "scripts" / "phase_gate.py"
REPO = "o/r"


def issue(number: int, body: str = "", parent: int | None = None,
          blocked_by: tuple[dict, ...] = (), prs: tuple[tuple[int, str], ...] = ()) -> dict:
    """Return an issue in the shape of the GraphQL answer."""
    return {"number": number, "body": body, "repository": {"nameWithOwner": REPO},
            "parent": {"number": parent, "repository": {"nameWithOwner": REPO}} if parent else None,
            "blockedBy": {"totalCount": len(blocked_by), "nodes": list(blocked_by)},
            "closedByPullRequestsReferences": {"totalCount": len(prs), "nodes": [
                {"number": n, "merged": state == "MERGED", "state": state} for n, state in prs]}}


class PhaseGateTests(unittest.TestCase):
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
        self.merged = issue(11, prs=((20, "MERGED"),))
        self.unmerged = issue(13, prs=((21, "OPEN"),))
        self.issues = {10: issue(10), 11: self.merged, 13: self.unmerged}

    def gate(self, ticket: dict | None, data: dict | None = None) -> subprocess.CompletedProcess[str]:
        issues = {**self.issues, **({12: ticket} if ticket else {})}
        data = data or {"graphql": {"nameWithOwner": REPO,
                                    "issues": {str(n): i for n, i in issues.items()}}}
        (self.tmp / "gh.json").write_text(json.dumps(data))
        return subprocess.run([sys.executable, str(SCRIPT), "--ticket", "12"], env=self.env,
                              capture_output=True, text=True, timeout=60)

    def gh_calls(self) -> list[list[str]]:
        return [json.loads(line) for line in (self.tmp / "gh.log").read_text().splitlines()]

    def assert_gate(self, result: subprocess.CompletedProcess[str], code: int,
                    lines: list[str]) -> None:
        self.assertEqual((result.returncode, result.stdout.splitlines()), (code, lines),
                         result.stderr)

    def test_passes_with_a_native_parent_and_a_merged_native_blocker(self):
        body = "## What to build\n\nA thing.\n\n## Blocked by\n\n- None (can start immediately)\n"

        result = self.gate(issue(12, body, parent=10, blocked_by=(self.merged,)))

        self.assert_gate(result, 0, [
            "PASS ticket: issue #12 exists in o/r",
            "PASS spec: native parent issue #10 exists",
            "PASS blocker #11: merged PR #20 closes it",
            "PASS: ticket #12 can start coding; all 3 checks passed",
        ])
        calls = self.gh_calls()
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][:8], ["api", "graphql", "-F", "owner={owner}",
                                        "-F", "name={repo}", "-F", "number=12"])

    def test_fails_when_a_blocker_has_no_merged_pr(self):
        result = self.gate(issue(12, blocked_by=(self.merged, self.unmerged)))

        self.assert_gate(result, 1, [
            "PASS ticket: issue #12 exists in o/r",
            "PASS spec: ticket #12 names no parent issue, so it is its own spec",
            "PASS blocker #11: merged PR #20 closes it",
            "FAIL blocker #13: no merged PR closes it; closing PRs: #21 (OPEN)",
            "FAIL: do not start coding ticket #12; 1 of 4 checks failed",
        ])

    def test_reads_the_parent_and_blockers_from_the_body_sections(self):
        body = ("## Parent\n\n#10\n\n## What to build\n\nA thing.\n\n## Blocked by\n\n"
                "- #11 (adds the parser)\n- https://github.com/o/r/issues/13\n")

        result = self.gate(issue(12, body, blocked_by=(self.merged,)))

        self.assert_gate(result, 1, [
            "PASS ticket: issue #12 exists in o/r",
            "PASS spec: parent issue #10 from the ## Parent section exists",
            "PASS blocker #11: merged PR #20 closes it",
            "FAIL blocker #13: no merged PR closes it; closing PRs: #21 (OPEN)",
            "FAIL: do not start coding ticket #12; 1 of 4 checks failed",
        ])
        calls = self.gh_calls()
        self.assertEqual(len(calls), 2)
        query = calls[1][-1]
        self.assertIn("i10: issue(number: 10)", query)
        self.assertIn("i13: issue(number: 13)", query)
        self.assertNotIn("i11:", query)

    def test_fails_when_the_ticket_or_its_parent_does_not_exist(self):
        for ticket, lines in (
                (issue(12, "## Parent\n\n#9\n"), [
                    "PASS ticket: issue #12 exists in o/r",
                    "FAIL spec: parent issue #9 from the ## Parent section does not exist in o/r",
                    "PASS blockers: ticket #12 has no blockers",
                    "FAIL: do not start coding ticket #12; 1 of 3 checks failed"]),
                (None, [
                    "FAIL ticket: issue #12 does not exist in o/r",
                    "FAIL: do not start coding ticket #12; 1 of 1 checks failed"])):
            with self.subTest(ticket=ticket and ticket["body"]):
                self.assert_gate(self.gate(ticket), 1, lines)

    def test_fails_closed_on_a_reference_that_it_cannot_check(self):
        body = ("## Parent\n\nhttps://github.com/x/y/issues/10\n\n"
                "## Blocked by\n\n- x/y#11\n- The parser ticket\n")

        result = self.gate(issue(12, body))

        self.assert_gate(result, 1, [
            "PASS ticket: issue #12 exists in o/r",
            "FAIL spec: ## Parent section: https://github.com/x/y/issues/10 is in another "
            "repository",
            "FAIL blockers: ## Blocked by section: x/y#11 is in another repository",
            "FAIL blockers: ## Blocked by section: cannot read an issue reference in "
            "'The parser ticket'",
            "FAIL: do not start coding ticket #12; 3 of 4 checks failed",
        ])

    def test_exits_1_when_gh_fails(self):
        result = self.gate(None, {"fail": "HTTP 401: Bad credentials "
                                          "(https://api.github.com/graphql)"})

        self.assert_gate(result, 1, [
            "FAIL cannot decide: gh api graphql failed: HTTP 401: Bad credentials "
            "(https://api.github.com/graphql)",
            "FAIL: do not start coding ticket #12; 1 of 1 checks failed",
        ])


if __name__ == "__main__":
    unittest.main()
