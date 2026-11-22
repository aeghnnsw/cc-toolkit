"""Contract checks for phase 6 (PR) of matt-automode.

Issue #409: before the merge, phase 6 posts the phase 5 review record on the
PR for the full head SHA, then merges with `--match-head-commit` on that SHA.
After a push changes the head, the run posts a new record before the merge.
Agent behavior is checked by the scenario review in
matt-automode-scenarios.md.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
HOSTS = ("skills", "codex-skills", "antigravity-skills")
GET_HEAD_COMMAND = "gh pr view <PR> --json headRefOid --jq .headRefOid"
POST_REVIEW_COMMAND = "gh pr review <PR> --comment --body-file <file>"
MERGE_COMMAND = "gh pr merge <PR> --match-head-commit <head SHA>"
RECORD_ITEMS = (
    "the comparison commit",
    "the head SHA",
    "the Standards and Spec results",
    "the fixes",
    "the test results",
)


def automode(host: str) -> str:
    """Return the text of one host copy of matt-automode."""
    return (PLUGIN_ROOT / host / "matt-automode" / "SKILL.md").read_text(encoding="utf-8")


def flat(text: str) -> str:
    """Join wrapped lines so that a phrase can cross a line break."""
    return " ".join(text.split())


def phase_six(host: str) -> str:
    match = re.search(r"^6\. \*\*PR .*?(?=^7\. \*\*Cleanup)", automode(host), flags=re.M | re.S)
    if match is None:
        raise AssertionError(f"{host}: phase 6 not found")
    return match.group(0)


class PhaseSixPinsTheReviewedHeadTest(unittest.TestCase):
    def test_phase_six_is_the_same_in_every_copy(self) -> None:
        for host in HOSTS[1:]:
            with self.subTest(host=host):
                self.assertEqual(phase_six(host), phase_six("skills"))

    def test_the_record_for_the_full_head_sha_comes_before_the_merge(self) -> None:
        text = flat(phase_six("skills"))
        self.assertIn("full 40-character head SHA", text)
        self.assertLess(text.index(GET_HEAD_COMMAND), text.index(POST_REVIEW_COMMAND))
        self.assertLess(text.index(POST_REVIEW_COMMAND), text.index(MERGE_COMMAND))
        self.assertLess(text.index(MERGE_COMMAND), text.index("4. Record the merged PR link."))
        record = text[text.index(POST_REVIEW_COMMAND):text.index(MERGE_COMMAND)]
        for item in RECORD_ITEMS:
            with self.subTest(item=item):
                self.assertIn(item, record)
        self.assertIn("When the head is not the commit that phase 5 reviewed, name that commit "
                      "and state what changed since it.", record)

    def test_phase_five_records_the_head_that_it_reviewed(self) -> None:
        for host in HOSTS:
            with self.subTest(host=host):
                self.assertIn("pass affected checks. Record the head SHA that the review covers. "
                              "6. **PR", flat(automode(host)))

    def test_every_merge_command_pins_the_head(self) -> None:
        for host in HOSTS:
            tails = re.findall(r"gh\s+pr\s+merge([^`]*)", automode(host))
            with self.subTest(host=host):
                self.assertTrue(tails)
                for tail in tails:
                    self.assertIn("--match-head-commit <head SHA>", tail)

    def test_a_new_head_needs_a_new_record_before_the_merge(self) -> None:
        text = flat(phase_six("skills"))
        self.assertIn("When the head changes after step 1, such as after a fix, a rebase, or a "
                      "conflict resolution, or when step 3 fails because the head changed, wait for "
                      "the required checks on the new head. Then do steps 1 and 2 again before "
                      "step 3.", text)
        self.assertIn("what changed since the last reviewed head", text)


if __name__ == "__main__":
    unittest.main()
