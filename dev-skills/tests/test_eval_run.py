"""Checks for scripts/eval_run.py of the project-eval skill.

check reads a run folder of evaluator results (E<N>.md) and verifier results
(V-E<N>-<b>.md). path prints the default report path. lint checks a report
against references/report-format.md. Each check runs the script on fixture
files in a temporary folder.
"""

from __future__ import annotations

import importlib.util
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1] / "skills" / "project-eval"
SCRIPT = SKILL / "scripts" / "eval_run.py"

E1 = """\
1. **Findings**:

### E1-1. SQL injection in the login query (Critical)
- **Dimension**: Security: injection
- **Location**: `src/auth.py:10-12`
- **Evidence**:
  ```
  ## A heading in a quoted file is not a finding (Major)
  ```
- **Why it matters**: An attacker can log in as any user.
- **Suggested fix**: Use a bound parameter.

### E1-2. No index on the session table (Minor)
- **Dimension**: Data & API: queries

2. **Angles covered**: injection, queries
5. **Stop reason**: deadline
6. **Browser checks**: not needed
"""
E2 = "### E2-1. The cache has no limit (Major)\n\n**Stop reason**: two angles with nothing new\n"
V_E1_1 = ("```text\n"
          "E1-1 | Confirmed | Major (was Critical: only admins reach it) | The query joins the input.\n"
          "E1-2 | Plausible | **Minor** | No load data.\n"
          "```\n")
V_E2_1 = "| E2-1 | Rejected | Major | A guard handles it. |\n"
VALID_CHECK = """\
E1.md: 2 findings; stop reason: deadline
E2.md: 1 finding; stop reason: two angles with nothing new
No verdict: none

Summary by finding ID, before you merge duplicates:

| Severity | Confirmed | Plausible |
|----------|-----------|-----------|
| Critical | 0 | 0 |
| Major | 1 | 0 |
| Minor | 0 | 1 |

Rejected: 1. Not verified: 0.

Status: Complete
"""

REPORT = "2026-11-24-1530-auth-module.md"
EARLIER = ("2026-11-20-0900-auth-module.md", "2026-11-20-0900-auth-module-2.md")
OTHERS = ("2026-11-21-0900-other.md", "2026-11-25-0900-auth-module.md")
VALID_REPORT = """\
# Project Evaluation: the auth module

- **Date**: 2026-11-24 15:30 CET
- **Scope**: src/auth/
- **Criteria**: none
- **App**: none
- **Evaluators**: E1 Security, Code (deadline); E2 Architecture (partial: turn limit)
- **Status**: Incomplete (1 finding not verified; E2 partial)
- **Browser checks**: not needed
- **Earlier reports**: docs/eval/2026-11-20-0900-auth-module.md, docs/eval/2026-11-20-0900-auth-module-2.md
- **Run results**: {run}

## Summary

| Severity | Confirmed | Plausible |
|----------|-----------|-----------|
| Critical | 0 | 0 |
| Major | 1 | 0 |
| Minor | 0 | 1 |

Rejected: 1. Not verified: 1.

## Findings

### F1. SQL injection in the login query (Major, Confirmed)
- **IDs**: E1-1
- **Evidence**:
  ```
  ### A heading in a quoted file is not a finding
  ```
- **Verifier**: The query joins the input.

### F2. No index on the session table (Minor, Plausible)
- **IDs**: E1-2

## Rejected Findings

| ID | Title | Reason |
|----|-------|--------|
| E2-1 | The cache has no limit | A guard handles it. |

## Not Verified Findings

| ID | Title | Why not verified |
|----|-------|------------------|
| E2-2 | The token never expires | No verdict after the retry. |

## Coverage

| Area | Dimensions and angles covered |
|------|-------------------------------|
| src/auth/ | Security: injection; Code: errors |

- **Not covered**: rate limits
- **Other areas**: none
"""


def load_script():
    """Import eval_run.py without writing bytecode beside it."""
    spec = importlib.util.spec_from_file_location("eval_run", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    previous, sys.dont_write_bytecode = sys.dont_write_bytecode, True
    try:
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = previous
    return module


class EvalRunTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.run_dir = self.tmp / "run"
        self.run_dir.mkdir()

    def script(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run([sys.executable, str(SCRIPT), *args], cwd=self.tmp, capture_output=True,
                              text=True, timeout=60)

    def write_run(self, **files: str) -> None:
        for name, text in files.items():
            (self.run_dir / f"{name.replace('_', '-')}.md").write_text(text)

    def check(self, **files: str) -> tuple[int, list[str], list[str]]:
        """Run check on the files; return the exit status, the PROBLEM lines, and the other lines."""
        self.write_run(**files)
        result = self.script("check", str(self.run_dir))
        self.assertEqual(result.stderr, "")
        lines = result.stdout.splitlines()
        return (result.returncode, [line for line in lines if line.startswith("PROBLEM ")],
                [line for line in lines if not line.startswith("PROBLEM ")])

    def test_check_passes_a_valid_run_and_prints_the_summary_and_status(self):
        self.write_run(E1=E1, E2=E2, V_E1_1=V_E1_1, V_E2_1=V_E2_1)

        result = self.script("check", str(self.run_dir))

        self.assertEqual((result.returncode, result.stdout, result.stderr), (0, VALID_CHECK, ""))

    def test_check_names_a_free_id_for_each_finding_with_a_bad_id(self):
        e1 = ("### E1-1. A (Major)\n### Without an ID (Minor)\n### E1-1. A again (Major)\n"
              "### E2-4. Wrong evaluator (Minor)\n### E1-3: Colon after the ID (Minor)\n"
              "**Stop reason**: deadline\n")

        code, problems, lines = self.check(E1=e1)

        malformed = 'write "E1-<k>. <Title> (<Severity>)"'
        self.assertEqual((code, problems), (1, [
            "PROBLEM E1.md:2: finding has no ID; use the free ID E1-2",
            "PROBLEM E1.md:3: duplicate ID E1-1 (first at line 1); use the free ID E1-3",
            f'PROBLEM E1.md:4: malformed ID "E2-4": {malformed}; use the free ID E1-4',
            f'PROBLEM E1.md:5: malformed ID "E1-3": {malformed}; use the free ID E1-5',
        ]))
        self.assertIn("E1.md: 1 finding; stop reason: deadline", lines)

    def test_check_reports_a_missing_or_unknown_stop_reason_and_counts_it_as_partial(self):
        code, problems, lines = self.check(
            E1="### E1-1. A (Major)\n",
            E2="### E2-1. B (Major)\n**Stop reason**: out of time\n",
            E3="### E3-1. C (Major)\n\n## Stop reason\n\npartial: turn limit\n",
        )

        self.assertEqual((code, problems), (1, [
            'PROBLEM E1.md: no stop reason; append the line "**Stop reason**: partial: <reason>"',
            'PROBLEM E2.md:2: unknown stop reason "out of time"; use deadline, two angles with nothing new, '
            "or partial: <reason>",
        ]))
        self.assertIn("E3.md: 1 finding; stop reason: partial: turn limit", lines)
        self.assertEqual(lines[-1], "Status: Incomplete (3 findings not verified; E1, E2, E3 partial)")

    def test_check_reports_bad_verdict_lines_and_findings_with_no_verdict(self):
        e1 = "".join(f"### E1-{k}. Finding {k} (Major)\n" for k in range(1, 6)) + "**Stop reason**: deadline\n"
        verdicts = ("E1-1 | Confirmed | Major\n"
                    "E1-2 | Probably | Major | Not sure.\n"
                    "E1-3 | Plausible | High | No app.\n"
                    "E1-9 | Confirmed | Minor | A typo in the ID.\n"
                    "E1-4 | Confirmed | Minor | It holds.\n"
                    "E1-4 | Rejected | Minor | It does not hold.\n"
                    "| E1-5 | **confirmed** | **Critical** | It holds. |\n")

        code, problems, lines = self.check(E1=e1, V_E1_1=verdicts)

        self.assertEqual((code, problems), (1, [
            'PROBLEM V-E1-1.md:1: malformed verdict line; write "<ID> | <Verdict> | <Severity> | <Reason>"',
            'PROBLEM V-E1-1.md:2: bad verdict "Probably" for E1-2; use Confirmed, Plausible, or Rejected',
            'PROBLEM V-E1-1.md:3: bad severity "High" for E1-3; start it with Critical, Major, or Minor',
            "PROBLEM V-E1-1.md:4: verdict for E1-9, which no E<N>.md has",
            "PROBLEM V-E1-1.md:6: E1-4 has a second verdict, Rejected, which differs from Confirmed Minor "
            "at V-E1-1.md:5",
        ]))
        self.assertIn("No verdict: E1-1, E1-2, E1-3", lines)
        self.assertIn("| Critical | 1 | 0 |", lines)
        self.assertIn("Rejected: 1. Not verified: 3.", lines)
        self.assertEqual(lines[-1], "Status: Incomplete (3 findings not verified)")

    def test_check_needs_a_run_folder_with_an_evaluator_result(self):
        result = self.script("check", str(self.run_dir))

        self.assertEqual((result.returncode, result.stdout), (2, ""))
        self.assertIn("has no E<N>.md file", result.stderr)

    # path

    def test_path_adds_a_suffix_to_a_taken_name_and_lists_the_same_slug(self):
        eval_run = load_script()
        folder = self.tmp / "docs" / "eval"
        folder.mkdir(parents=True)
        for name in (*EARLIER, *OTHERS, "2026-11-24-1530-auth-module.md"):
            (folder / name).write_text("")
        now = datetime(2026, 11, 24, 15, 30)

        self.assertEqual(eval_run.default_path(folder, "auth-module", now).name,
                         "2026-11-24-1530-auth-module-2.md")
        self.assertEqual(eval_run.default_path(folder, "other", now).name, "2026-11-24-1530-other.md")
        self.assertEqual(eval_run.same_slug(folder, "auth-module"),
                         [*EARLIER, "2026-11-24-1530-auth-module.md", "2026-11-25-0900-auth-module.md"])

        result = self.script("path", "other")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertRegex(result.stdout, r"^Report path: docs/eval/\d{4}-\d\d-\d\d-\d{4}-other\.md\n"
                                        r"Earlier reports: docs/eval/2026-11-21-0900-other\.md\n$")

    def test_path_rejects_a_slug_that_is_not_lowercase_words_or_ends_in_a_number(self):
        for slug in ("Auth-Module", "auth_module", "phase-2"):
            with self.subTest(slug=slug):
                result = self.script("path", slug)
                self.assertEqual((result.returncode, result.stdout), (2, ""))

    # lint

    def write_report(self, text: str, path: str = f"docs/eval/{REPORT}") -> str:
        folder = self.tmp / "docs" / "eval"
        folder.mkdir(parents=True, exist_ok=True)
        for name in (*EARLIER, *OTHERS):
            (folder / name).write_text("")
        (self.tmp / path).parent.mkdir(parents=True, exist_ok=True)
        (self.tmp / path).write_text(text)
        return path

    def lint(self, text: str, path: str = f"docs/eval/{REPORT}", *args: str) -> tuple[int, list[str]]:
        path = self.write_report(text, path)
        result = self.script("lint", path, *args)
        self.assertEqual(result.stderr, "")
        return result.returncode, [line for line in result.stdout.splitlines() if line.startswith("PROBLEM ")]

    def test_lint_passes_a_valid_report(self):
        path = self.write_report(VALID_REPORT.format(run=self.run_dir))

        result = self.script("lint", path)

        self.assertEqual((result.returncode, result.stdout, result.stderr),
                         (0, f"{path}: 0 problems\n", ""))

    def test_lint_reports_each_planted_violation(self):
        valid = VALID_REPORT.format(run=self.run_dir)
        report = f"docs/eval/{REPORT}"
        heading = f'{report}:33: the finding heading is not "### F<k>. <Title> (<Severity>, <Confirmed or Plausible>)"'
        cases = (
            ("title", "# Project Evaluation: the auth module", "# Evaluation",
             f'{report}: the first line is not "# Project Evaluation: <target>"'),
            ("no Run results field", f"- **Run results**: {self.run_dir}\n", "",
             f'{report}: no "- **Run results**:" header field'),
            ("empty field", "- **Scope**: src/auth/", "- **Scope**:", f"{report}:4: the Scope field is empty"),
            ("Date with no time zone", "15:30 CET", "15:30",
             f'{report}:3: the Date field is not "<YYYY-MM-DD HH:MM time zone>"'),
            ("Status", "Incomplete (1 finding not verified; E2 partial)", "Partial",
             f'{report}:8: the Status field is not "Complete | Incomplete (<causes>)"'),
            ("Browser checks", "**Browser checks**: not needed", "**Browser checks**: some",
             f'{report}:9: the Browser checks field is not "done | not needed | skipped: <reason>"'),
            ("Earlier reports misses one", "docs/eval/2026-11-20-0900-auth-module.md, ", "",
             f"{report}:10: Earlier reports does not name 2026-11-20-0900-auth-module.md"),
            ("Earlier reports names a later one", "auth-module-2.md", "auth-module-2.md, 2026-11-25-0900-auth-module.md",
             f"{report}:10: Earlier reports names 2026-11-25-0900-auth-module.md, which is not an earlier "
             "report with the slug auth-module in docs/eval"),
            ("Run results folder", f"**Run results**: {self.run_dir}", f"**Run results**: {self.run_dir}-gone",
             f"{report}:11: the Run results field does not name a folder that exists"),
            ("no Coverage section", valid[valid.index("## Coverage"):], "",
             f'{report}: no "## Coverage" section'),
            ("a second section", "- **Other areas**: none\n", "- **Other areas**: none\n\n## Coverage\n",
             f'{report}:57: a second "## Coverage" section'),
            ("Summary count", "| Major | 1 | 0 |", "| Major | 2 | 0 |",
             f"{report}: the Summary counts 2 Major Confirmed, and the Findings section has 1"),
            ("Summary row", "| Minor | 0 | 1 |\n", "",
             f'{report}: the Summary has no "| Minor | <n> | <n> |" row'),
            ("Summary count line", "Rejected: 1. Not verified: 1.", "Rejected: one.",
             f'{report}: the Summary has no "Rejected: <n>. Not verified: <n>." line'),
            ("finding heading", "(Minor, Plausible)", "(Minor, Rejected)",
             heading, f"{report}: the Summary counts 1 Minor Plausible, and the Findings section has 0"),
            ("Rejected rows", "Rejected: 1.", "Rejected: 2.",
             f"{report}: the Summary counts 2 Rejected, and the Rejected Findings table has 1 rows"),
            ("Not verified rows", "Not verified: 1.", "Not verified: 2.",
             f"{report}: the Summary counts 2 Not verified, and the Not Verified Findings table has 1 rows"),
            ("Coverage field", "- **Other areas**: none\n", "",
             f'{report}: the Coverage section has no "- **Other areas**:" line'),
        )
        for name, old, new, *problems in cases:
            with self.subTest(name):
                self.assertIn(old, valid)
                self.assertEqual(self.lint(valid.replace(old, new, 1)),
                                 (1, [f"PROBLEM {problem}" for problem in problems]))

    def test_lint_checks_the_sections_and_the_not_verified_section(self):
        valid = VALID_REPORT.format(run=self.run_dir)
        report = f"docs/eval/{REPORT}"
        coverage = valid[valid.index("## Coverage"):]
        out_of_order = valid.replace(coverage, "").replace("## Summary", coverage + "\n## Summary")
        all_verified = valid.replace("Not verified: 1.", "Not verified: 0.")
        no_section = valid[:valid.index("## Not Verified")] + coverage

        self.assertEqual(self.lint(out_of_order), (1, [
            f"PROBLEM {report}: the sections are not in the order Summary, Findings, Rejected Findings, "
            "Not Verified Findings, Coverage"]))
        self.assertEqual(self.lint(all_verified), (1, [
            f"PROBLEM {report}: every finding has a verdict, so omit the Not Verified Findings section"]))
        self.assertEqual(self.lint(no_section), (1, [
            f'PROBLEM {report}: the Summary counts 1 Not verified, and there is no "## Not Verified Findings" '
            "section"]))
        self.assertEqual(self.lint(no_section.replace("Not verified: 1.", "Not verified: 0.")), (0, []))

    def test_lint_checks_the_default_name_unless_the_path_is_custom(self):
        valid = VALID_REPORT.format(run=self.run_dir)
        cases = (
            ("reports/2026-11-24-1530-auth-module.md",
             "the default path is in docs/eval/; pass --custom-path for a path that the user or a calling "
             "skill named"),
            ("docs/eval/auth-module.md",
             "the name is not YYYY-MM-DD-HHMM-<slug>.md or YYYY-MM-DD-HHMM-<slug>-<N>.md"),
            ("docs/eval/2026-13-01-1530-auth-module.md", "2026-13-01-1530 is not a valid date and time"),
            ("docs/eval/2026-11-24-1530-auth-module-1.md",
             "the -N suffix starts at -2, and a slug does not end in a number"),
        )
        for path, problem in cases:
            with self.subTest(path=path):
                code, problems = self.lint(valid, path)
                self.assertEqual(code, 1)
                self.assertIn(f"PROBLEM {path}: {problem}", problems)

        self.assertEqual(self.lint(valid, "reports/auth-eval.md", "--custom-path"), (0, []))

    def test_lint_fields_and_sections_match_report_format(self):
        """The script checks the header fields and sections of the report template in report-format.md."""
        eval_run = load_script()
        text = (SKILL / "references" / "report-format.md").read_text()
        template = re.search(r"^````markdown\n(# Project Evaluation.*?)^````$", text, re.M | re.S).group(1)
        header, _, body = template.partition("\n## ")
        coverage = body[body.index("Coverage\n"):]

        self.assertEqual(tuple(re.findall(r"^- \*\*(.+?)\*\*:", header, re.M)), eval_run.HEADER_FIELDS)
        self.assertEqual(tuple(re.findall(r"^## (.+)$", "## " + body, re.M)), eval_run.SECTIONS)
        self.assertEqual(tuple(re.findall(r"^- \*\*(.+?)\*\*:", coverage, re.M)), eval_run.COVERAGE_FIELDS)
        self.assertIn("- **Run results**: <RUN path>", header)


if __name__ == "__main__":
    unittest.main()
