"""Contract checks for the review (phase 5) and PR (phase 6) phases of matt-automode.

Issue #409: before the merge, phase 6 posts the phase 5 review record on the
PR for the full head SHA, then merges with `--match-head-commit` on that SHA.
After a push changes the head, the run posts a new record before the merge.
Issue #475: phase 5 runs one full review and one focused check of the fixes,
only blocking findings block, and a blocking finding in a focused check stops
the ticket. A fix for a failing check gets a focused check, not a full review.
Issue #446: the retrospective runs the cutoff script that dev-skills ships, in
every repository.
Issue #458: phase 4 runs the phase gate and the glossary term scripts, and a
full test suite runs through the suite lock script.
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
    "the focused checks",
    "the test results",
)
REVIEW_BOUND = (
    "Run one full review against the ticket spec and a recorded comparison commit.",
    "Only these findings block: a regression that a failing run or a reproducible case shows "
    "at the head, a missed ticket requirement, a broken cited rule, and shipped text that the "
    "change makes false.",
    "A problem present at the comparison commit blocks only when the ticket requires its fix.",
    "List other findings with a reason in the review record.",
    "Open or reuse an issue only for a defect that a user can hit.",
    "give one fresh reviewer only the fix diff and the findings that it closes.",
    "Run no second full review.",
    "If this focused check finds a blocking finding, stop the ticket without a merge, keep the "
    "work, report the finding, and continue independent tickets.",
)
OLD_FIX_RULE = "code changes need review against the same comparison commit"
FIX_RULE = "Give each fix one focused check of its diff and the failure that it fixes"
PLUGIN_ROOT_PATHS = {"skills": "${CLAUDE_PLUGIN_ROOT}", "codex-skills": "<plugin-root>",
                     "antigravity-skills": "<plugin-root>"}
SAFETY_RULE = ("For a change to a safety check, such as a command hook, the spec states what the "
               "check must block. Where the check cannot decide, it blocks: it fails closed.")


def automode(host: str) -> str:
    """Return the text of one host copy of matt-automode."""
    return (PLUGIN_ROOT / host / "matt-automode" / "SKILL.md").read_text(encoding="utf-8")


def flat(text: str) -> str:
    """Join wrapped lines so that a phrase can cross a line break."""
    return " ".join(text.split())


def between(host: str, start: str, end: str) -> str:
    """Return the joined text of one host copy from `start` up to `end`."""
    text = flat(automode(host))
    return text[text.index(start):text.index(end)]


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
                self.assertIn("Record the head SHA that the review covers. 6. **PR",
                              flat(automode(host)))

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


class ReviewLoopIsBoundedTest(unittest.TestCase):
    def test_phase_five_runs_one_full_review_and_one_focused_check(self) -> None:
        for host in HOSTS:
            phase = between(host, "5. **Review", "6. **PR")
            for rule in REVIEW_BOUND:
                with self.subTest(host=host, rule=rule):
                    self.assertIn(rule, phase)

    def test_a_fix_for_a_failing_check_gets_a_focused_check(self) -> None:
        for host in HOSTS:
            paragraph = between(host, "Fix failures on the PR branch", "For a rebase")
            with self.subTest(host=host):
                self.assertNotIn(OLD_FIX_RULE, flat(automode(host)))
                self.assertIn(FIX_RULE, paragraph)

    def test_the_spec_of_a_safety_check_change_fails_closed(self) -> None:
        for host in HOSTS:
            phase = between(host, "2. **Spec", "3. **Tickets")
            with self.subTest(host=host):
                self.assertIn(SAFETY_RULE, phase)


class RetrospectiveRunsTheShippedCutoffScriptTest(unittest.TestCase):
    def test_steps_one_and_four_run_the_shipped_script(self) -> None:
        for host in HOSTS:
            steps = between(host, "## Navigation retrospective", "A leader is a session")
            run = (f'Run `python3 "{PLUGIN_ROOT_PATHS[host]}/scripts/find_retrospective_cutoff.py"` '
                   "from the checkout root")
            with self.subTest(host=host):
                self.assertIn(run, steps)
                self.assertIn("4. When step 1 found a record, run the script again.", steps)
                self.assertNotIn("scripts/find-retrospective-cutoff.py", steps)
                self.assertNotIn("When the repository has", steps)



class ScriptsReplaceProseRulesTest(unittest.TestCase):
    """Issue #458: each host copy runs the script that replaces a prose rule."""

    def test_phase_four_runs_the_phase_gate_and_the_glossary_term_scan(self) -> None:
        for host in HOSTS:
            phase = between(host, "4. **Implement", "5. **Review")
            root = PLUGIN_ROOT_PATHS[host]
            with self.subTest(host=host):
                self.assertIn(f'`python3 "{root}/scripts/phase_gate.py" --ticket <N>`', phase)
                self.assertIn(f'`python3 "{root}/scripts/avoid_terms.py" --base <comparison commit>`',
                              phase)
                self.assertNotIn("search new prose", phase)

    def test_full_suites_run_through_the_suite_lock(self) -> None:
        for host in HOSTS:
            briefs = between(host, "## Sub-agent briefs", "## Finish")
            root = PLUGIN_ROOT_PATHS[host]
            with self.subTest(host=host):
                self.assertIn(f'`python3 "{root}/scripts/run_suite.py" -- <suite command>`', briefs)
                self.assertNotIn("Allow only one full test suite at a time", briefs)


if __name__ == "__main__":
    unittest.main()
