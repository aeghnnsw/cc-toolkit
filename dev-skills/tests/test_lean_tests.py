"""Checks for the lean-tests command-line entry, scripts/lean_tests.py.

Each check runs the script in a child process against a small fixture
project in a temporary directory and compares its JSON output with values
that follow from the fixture design. The suite, compare, and coverage checks
need pytest and pytest-cov in the running interpreter. Without them they skip
and name the command that supplies both. The scan checks need only Python.
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
HOST_SKILLS = {
    "claude": PLUGIN_ROOT / "skills" / "lean-tests",
    "codex": PLUGIN_ROOT / "codex-skills" / "lean-tests",
}
SCRIPT = HOST_SKILLS["claude"] / "scripts" / "lean_tests.py"
UV_COMMAND = (
    "uv run --no-project --python '>=3.11' --with pytest --with pytest-cov "
    "python -m unittest discover -s dev-skills/tests -p 'test_lean_tests*.py'"
)
HAS_PYTEST = all(importlib.util.find_spec(name) for name in ("pytest", "pytest_cov"))
needs_pytest = unittest.skipUnless(HAS_PYTEST, f"needs pytest and pytest-cov; run: {UV_COMMAND}")

CORE_BASE = """\
MAX_QTY = 100


def classify(n):
    if n < 0:
        return "negative"
    return "non-negative"


def total_price(qty, unit, discount=0):
    return qty * unit - discount


def notify(sender, message):
    sender.send(message)
    return True
"""

CORE_HEAD = """\
MAX_QTY = 100


def classify(n):
    if n < 0:
        return "negative"
    return "non-negative"


def total_price(qty, unit, discount=0):
    if discount < 0:
        raise ValueError("discount must not be negative")
    return qty * unit - discount


def parse_qty(text):
    try:
        return int(text)
    except ValueError:
        raise ValueError(f"bad quantity: {text}")


def notify(sender, message):
    sender.send(message)
    return True
"""

FILES = {
    "pyproject.toml": """\
        [tool.pytest.ini_options]
        testpaths = ["tests"]
        pythonpath = ["src"]
        """,
    "src/calc/__init__.py": "",
    "tests/conftest.py": """\
        import time

        import pytest


        @pytest.fixture
        def slow_resource():
            time.sleep(0.15)
            return "ready"
        """,
    "tests/test_cli.py": """\
        import subprocess
        import sys
        from pathlib import Path

        SRC = Path(__file__).resolve().parents[1] / "src"


        def test_classify_in_subprocess():
            code = "from calc.core import classify; print(classify(-2))"
            out = subprocess.run([sys.executable, "-c", code], cwd=SRC, capture_output=True, text=True, check=True)
            assert out.stdout.strip() == "negative"


        def test_writes_report_file():
            target = Path(__file__).resolve().parent / "report.txt"
            target.write_text("ok")  # Write UTF-8 text.
            assert target.read_text() == "ok"
        """,
    "tests/test_core.py": """\
        import time
        import unittest
        from unittest import mock

        import pytest

        from calc.core import MAX_QTY, classify, notify, parse_qty, total_price


        def check_label(value, expected):
            assert value == expected


        def test_classify_negative():
            assert classify(-1) == "negative"


        def test_classify_negative_copy():
            assert classify(-7) == "negative"


        def test_classify_zero_boundary():
            assert classify(0) == "non-negative"


        def test_classify_both_signs():
            assert [classify(-1), classify(1)] == ["negative", "non-negative"]


        def test_classify_with_helper():
            check_label(classify(5), "non-negative")


        def test_classify_not_none():
            assert classify(3) is not None


        def test_total_price_tautology():
            qty, unit = 3, 4
            assert total_price(qty, unit) == qty * unit


        def test_total_price_no_assert():
            # Covers bug 7.
            total_price(2, 5)


        def test_total_price_self():
            result = total_price(1, 1)
            assert result == result


        def test_total_price_slow():
            time.sleep(0.15)
            assert total_price(2, 3) == 6


        def test_total_price_with_slow_fixture(slow_resource):
            assert total_price(1, 2, discount=1) == 1


        def test_negative_discount_is_rejected():
            \"\"\"Regression test for issue #12.\"\"\"
            with pytest.raises(ValueError):
                total_price(1, 1, discount=-1)


        def test_parse_qty():
            assert parse_qty("3") == 3


        @pytest.mark.parametrize("text, expected", [("1", 1), ("42", 42)])
        def test_parse_qty_values(text, expected):
            assert parse_qty(text) == expected


        def test_quantity_cap():
            assert MAX_QTY == 100


        def test_notify_calls_send():
            sender = mock.Mock()
            notify(sender, "hi")
            sender.send.assert_called_once_with("hi")


        class TestClassify(unittest.TestCase):
            def test_positive(self):
                self.assertEqual(classify(2), "non-negative")
        """,
    "tests/test_order.py": """\
        SEEN = []


        def test_order_first_writes():
            SEEN.append("first")
            assert SEEN == ["first"]


        def test_order_second_reads():
            assert SEEN == ["first"]
        """,
}

CORE = "tests/test_core.py::"
NODEIDS = [
    "tests/test_cli.py::test_classify_in_subprocess",
    "tests/test_cli.py::test_writes_report_file",
    CORE + "test_classify_negative",
    CORE + "test_classify_negative_copy",
    CORE + "test_classify_zero_boundary",
    CORE + "test_classify_both_signs",
    CORE + "test_classify_with_helper",
    CORE + "test_classify_not_none",
    CORE + "test_total_price_tautology",
    CORE + "test_total_price_no_assert",
    CORE + "test_total_price_self",
    CORE + "test_total_price_slow",
    CORE + "test_total_price_with_slow_fixture",
    CORE + "test_negative_discount_is_rejected",
    CORE + "test_parse_qty",
    CORE + "test_parse_qty_values[1-1]",
    CORE + "test_parse_qty_values[42-42]",
    CORE + "test_quantity_cap",
    CORE + "test_notify_calls_send",
    CORE + "TestClassify::test_positive",
    "tests/test_order.py::test_order_first_writes",
    "tests/test_order.py::test_order_second_reads",
]


def write_project(root: Path, core: str = CORE_HEAD) -> None:
    for name, text in FILES.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(textwrap.dedent(text), encoding="utf-8")
    (root / "src" / "calc" / "core.py").write_text(core, encoding="utf-8")


def line_of(text: str, snippet: str) -> int:
    """Return the 1-based number of the one line of `text` that contains `snippet`."""
    lines = [n for n, line in enumerate(textwrap.dedent(text).splitlines(), start=1) if snippet in line]
    assert len(lines) == 1, f"{snippet!r} matches lines {lines}"
    return lines[0]


def run_cli(*args: str, cwd: Path | None = None) -> tuple[int, dict, str]:
    """Run lean_tests.py; return the exit code, the parsed stdout JSON, and stderr."""
    result = subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        cwd=cwd,
    )
    try:
        data = json.loads(result.stdout) if result.stdout.strip() else {}
    except json.JSONDecodeError as error:
        raise AssertionError(f"stdout is not JSON: {error}\n{result.stdout}\n{result.stderr}") from error
    return result.returncode, data, result.stderr


def findings_by_test(data: dict) -> dict[str, set[str]]:
    found: dict[str, set[str]] = {}
    for finding in data["findings"]:
        found.setdefault(finding["nodeid"], set()).add(finding["code"])
    return found


class ScanTest(unittest.TestCase):
    """The AST scan reads the test files of the collected node IDs."""

    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls._tmp.name) / "proj"
        write_project(cls.root)
        cls.nodeids = Path(cls._tmp.name) / "nodeids.txt"
        cls.nodeids.write_text("\n".join(NODEIDS) + "\n", encoding="utf-8")
        cls.code, cls.data, cls.stderr = run_cli("scan", "--project", str(cls.root), "--node-ids", str(cls.nodeids))
        cls.found = findings_by_test(cls.data)

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tmp.cleanup()

    def codes(self, name: str) -> set[str]:
        return self.found.get(CORE + name, set())

    def test_scan_succeeds_and_counts_function_level_tests(self) -> None:
        self.assertEqual(self.code, 0, self.stderr)
        self.assertEqual(self.data["summary"]["nodeids"], len(NODEIDS))
        # The two parametrized instances share one function.
        self.assertEqual(self.data["summary"]["tests"], len(NODEIDS) - 1)
        self.assertEqual(self.data["unresolved"], [])

    def test_no_assertion_keeps_other_signals(self) -> None:
        self.assertEqual(self.codes("test_total_price_no_assert"), {"no-assertion", "protected"})
        details = {f["detail"] for f in self.data["findings"] if f["nodeid"] == CORE + "test_total_price_no_assert"}
        self.assertIn("comment: bug 7", details)

    def test_checks_through_a_helper_or_unittest_method_are_assertions(self) -> None:
        self.assertEqual(self.codes("test_classify_with_helper"), set())
        self.assertEqual(self.codes("TestClassify::test_positive"), set())

    def test_tautology_recomputes_the_expected_value(self) -> None:
        self.assertEqual(self.codes("test_total_price_tautology"), {"tautology"})

    def test_self_comparison(self) -> None:
        self.assertEqual(self.codes("test_total_price_self"), {"self-comparison"})

    def test_non_none_only_check_is_a_weak_oracle(self) -> None:
        self.assertEqual(self.codes("test_classify_not_none"), {"weak-oracle"})

    def test_mock_call_assertions_only_is_a_change_detector(self) -> None:
        self.assertEqual(self.codes("test_notify_calls_send"), {"change-detector"})

    def test_constant_check_is_a_trivial_code_test(self) -> None:
        self.assertEqual(self.codes("test_quantity_cap"), {"trivial-code"})

    def test_tests_equal_except_for_literals_form_one_duplicate_group(self) -> None:
        group = {CORE + n for n in ("test_classify_negative", "test_classify_negative_copy", "test_classify_zero_boundary")}
        self.assertEqual([set(g["nodeids"]) for g in self.data["duplicate_groups"]], [group])
        self.assertEqual(self.codes("test_classify_negative"), {"duplicate-shape"})

    def test_protection_signals_and_input_class_markers(self) -> None:
        name = "test_negative_discount_is_rejected"
        self.assertEqual(self.codes(name), {"protected", "input-class"})
        details = {(f["code"], f["detail"]) for f in self.data["findings"] if f["nodeid"] == CORE + name}
        self.assertIn(("input-class", "error-path"), details)
        protected = " ".join(d for c, d in details if c == "protected")
        self.assertIn("#12", protected)
        self.assertIn("regression", protected.lower())
        self.assertIn(("input-class", "boundary"), {
            (f["code"], f["detail"]) for f in self.data["findings"] if f["nodeid"] == CORE + "test_classify_zero_boundary"
        })

    def test_sleep_call(self) -> None:
        self.assertEqual(self.codes("test_total_price_slow"), {"sleep"})

    def test_findings_name_the_file_and_line(self) -> None:
        test_core = FILES["tests/test_core.py"]
        [finding] = [f for f in self.data["findings"] if f["nodeid"] == CORE + "test_total_price_self"]
        self.assertEqual(finding["file"], "tests/test_core.py")
        self.assertEqual(finding["line"], line_of(test_core, "assert result == result"))
        [finding] = [
            f for f in self.data["findings"]
            if f["nodeid"] == CORE + "test_total_price_no_assert" and f["code"] == "no-assertion"
        ]
        self.assertEqual(finding["line"], line_of(test_core, "def test_total_price_no_assert"))

    def test_clean_tests_have_no_finding(self) -> None:
        clean = ["test_classify_both_signs", "test_parse_qty", "test_parse_qty_values", "test_total_price_with_slow_fixture"]
        for name in clean:
            self.assertEqual(self.codes(name), set(), name)
        for nodeid in NODEIDS[:2] + NODEIDS[-2:]:
            self.assertNotIn(nodeid, self.found)

    def test_summary_names_examples_of_each_finding(self) -> None:
        examples = self.data["summary"]["examples"]
        self.assertEqual(examples["no-assertion"], [CORE + "test_total_price_no_assert"])
        self.assertEqual(len(examples["duplicate-shape"]), 3)

    def test_out_writes_the_full_result_and_prints_the_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "scan.json"
            code, printed, stderr = run_cli(
                "scan", "--project", str(self.root), "--node-ids", str(self.nodeids), "--out", str(out)
            )
            self.assertEqual(code, 0, stderr)
            self.assertEqual(json.loads(out.read_text(encoding="utf-8")), self.data)
        self.assertEqual(printed, {"summary": self.data["summary"], "output": str(out)})

    def test_unknown_node_id_is_unresolved(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            nodeids = Path(tmp) / "nodeids.txt"
            nodeids.write_text(CORE + "test_missing\ntests/test_gone.py::test_x\n", encoding="utf-8")
            code, data, stderr = run_cli("scan", "--project", str(self.root), "--node-ids", str(nodeids))
        self.assertEqual(code, 0, stderr)
        self.assertEqual({u["nodeid"] for u in data["unresolved"]}, {CORE + "test_missing", "tests/test_gone.py::test_x"})


def git(root: Path, env: dict, *args: str) -> str:
    result = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, env=env)
    assert result.returncode == 0, result.stderr
    return result.stdout


class Runs:
    """A fixture Git project with two commits and the suite runs that the checks read.

    Commit 1 has CORE_BASE; commit 2 adds the discount check and parse_qty.
    run1 is in file order, run2 is reversed with coverage contexts, and run3
    runs two node IDs from a file.
    """

    _instance: Runs | None = None

    @classmethod
    def get(cls) -> Runs:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        tmp = Path(self._tmp.name)
        self.root = tmp / "proj"
        self.work = tmp / "work"
        self.env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
        self.env.update(
            GIT_CONFIG_GLOBAL=str(tmp / "gitconfig"),
            GIT_CONFIG_NOSYSTEM="1",
            GIT_CEILING_DIRECTORIES=str(tmp),
            GIT_AUTHOR_NAME="Test",
            GIT_AUTHOR_EMAIL="test@example.com",
            GIT_COMMITTER_NAME="Test",
            GIT_COMMITTER_EMAIL="test@example.com",
        )
        write_project(self.root, core=CORE_BASE)
        git(self.root, self.env, "init", "-q")
        names = [*FILES, "src/calc/core.py"]
        git(self.root, self.env, "add", *names)
        git(self.root, self.env, "commit", "-q", "-m", "base")
        (self.root / "src" / "calc" / "core.py").write_text(CORE_HEAD, encoding="utf-8")
        git(self.root, self.env, "add", "src/calc/core.py")
        git(self.root, self.env, "commit", "-q", "-m", "head")
        self.status_before = git(self.root, self.env, "status", "--porcelain", "--untracked-files=all")
        self.subset = [CORE + "test_parse_qty", "tests/test_order.py::test_order_first_writes"]
        ids = tmp / "subset.txt"
        ids.write_text("\n".join(self.subset) + "\n", encoding="utf-8")
        self.run1 = self.suite("run1")
        self.run2 = self.suite("run2", "--reverse", "--coverage-source", "calc")
        self.run3 = self.suite("run3", "--node-ids", str(ids))
        self.status_after = git(self.root, self.env, "status", "--porcelain", "--untracked-files=all")

    def suite(self, label: str, *args: str) -> tuple[int, dict, str]:
        result = run_cli(
            "suite", "--python", sys.executable, "--project", str(self.root),
            "--work-dir", str(self.work), "--label", label, *args,
        )
        path = self.work / f"{label}.json"
        path.write_text(json.dumps(result[1]), encoding="utf-8")
        return result

    def output(self, label: str) -> str:
        return str(self.work / f"{label}.json")


def tearDownModule() -> None:
    if Runs._instance is not None:
        Runs._instance._tmp.cleanup()


def by_nodeid(data: dict) -> dict[str, dict]:
    return {test["nodeid"]: test for test in data["tests"]}


@needs_pytest
class SuiteTest(unittest.TestCase):
    """suite runs pytest and reports counts, times, and per-test phases."""

    def setUp(self) -> None:
        self.runs = Runs.get()

    def test_file_order_run_counts_every_test(self) -> None:
        code, data, stderr = self.runs.run1
        self.assertEqual(code, 0, stderr)
        summary = data["summary"]
        self.assertEqual(summary["pytest_exit_code"], 0)
        self.assertFalse(summary["timed_out"])
        self.assertEqual(summary["collected"], len(NODEIDS))
        self.assertEqual(summary["counts"]["passed"], len(NODEIDS))
        self.assertEqual(sum(summary["counts"].values()), len(NODEIDS))
        self.assertEqual(data["collected"], NODEIDS)
        self.assertGreater(summary["wall_seconds"], 0)
        self.assertGreaterEqual(summary["collection_seconds"], 0)

    def test_phase_durations_separate_slow_calls_from_slow_setup(self) -> None:
        data = self.runs.run1[1]
        tests = by_nodeid(data)
        slow = tests[CORE + "test_total_price_slow"]
        self.assertGreaterEqual(slow["phases"]["call"]["seconds"], 0.15)
        self.assertEqual(slow["outcome"], "passed")
        slowest = data["summary"]["slowest"]
        self.assertEqual(slowest["call"][0]["nodeid"], CORE + "test_total_price_slow")
        self.assertEqual(slowest["setup"][0]["nodeid"], CORE + "test_total_price_with_slow_fixture")
        self.assertGreaterEqual(slowest["setup"][0]["seconds"], 0.15)

    def test_reports_files_the_tests_wrote_and_writes_none_itself(self) -> None:
        self.assertEqual(self.runs.run1[1]["summary"]["files_written"], ["?? tests/report.txt"])
        self.assertEqual(self.runs.run2[1]["summary"]["files_written"], [])
        added = set(self.runs.status_after.splitlines()) - set(self.runs.status_before.splitlines())
        self.assertEqual(added, {"?? tests/report.txt"})

    def test_reversed_run_reverses_the_collected_order(self) -> None:
        code, data, stderr = self.runs.run2
        self.assertEqual(code, 0, stderr)
        self.assertEqual(data["collected"], NODEIDS[::-1])
        self.assertEqual(data["summary"]["counts"]["failed"], 1)
        failed = by_nodeid(data)["tests/test_order.py::test_order_second_reads"]
        self.assertEqual(failed["outcome"], "failed")
        self.assertEqual(failed["phases"]["call"]["exception"], "AssertionError")

    def test_node_id_file_runs_only_those_tests(self) -> None:
        code, data, stderr = self.runs.run3
        self.assertEqual(code, 0, stderr)
        self.assertEqual(data["collected"], self.runs.subset)
        self.assertEqual(data["summary"]["counts"]["passed"], 2)

    def test_timeout_stops_pytest_and_marks_the_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            code, data, stderr = run_cli(
                "suite", "--python", sys.executable, "--project", str(self.runs.root),
                "--work-dir", tmp, "--timeout", "0.01",
            )
        self.assertEqual(code, 0, stderr)
        self.assertTrue(data["summary"]["timed_out"])
        self.assertIsNone(data["summary"]["pytest_exit_code"])


@needs_pytest
class CompareTest(unittest.TestCase):
    """compare reports outcome changes and node IDs added or missing."""

    def setUp(self) -> None:
        self.runs = Runs.get()

    def test_order_dependent_test_changes_outcome(self) -> None:
        code, data, stderr = run_cli("compare", self.runs.output("run1"), self.runs.output("run2"))
        self.assertEqual(code, 0, stderr)
        self.assertEqual(
            [(c["nodeid"], c["first"], c["second"]) for c in data["changed"]],
            [("tests/test_order.py::test_order_second_reads", "passed", "failed")],
        )
        self.assertEqual(data["missing"], [])
        self.assertEqual(data["added"], [])
        self.assertEqual(data["summary"]["changed"], 1)
        self.assertEqual(data["summary"]["examples"]["changed"], ["tests/test_order.py::test_order_second_reads"])

    def test_node_ids_missing_from_the_second_run(self) -> None:
        code, data, stderr = run_cli("compare", self.runs.output("run1"), self.runs.output("run3"))
        self.assertEqual(code, 0, stderr)
        self.assertEqual(data["missing"], [n for n in NODEIDS if n not in self.runs.subset])
        self.assertEqual(data["added"], [])
        code, data, stderr = run_cli("compare", self.runs.output("run3"), self.runs.output("run1"))
        self.assertEqual(data["added"], [n for n in NODEIDS if n not in self.runs.subset])


@needs_pytest
class CoverageTest(unittest.TestCase):
    """coverage reads the contexts of the reversed run and diffs against commit 1."""

    @classmethod
    def setUpClass(cls) -> None:
        runs = Runs.get()
        contexts = runs.run2[1]["files"]["coverage_json"]
        cls.code, cls.data, cls.stderr = run_cli(
            "coverage", "--contexts", contexts, "--suite", runs.output("run2"), "--base", "HEAD~1"
        )

    def lines(self, *snippets: str) -> list[int]:
        return sorted(line_of(CORE_HEAD, s) for s in snippets)

    def test_per_test_lines_strip_the_phase_and_skip_import_time(self) -> None:
        self.assertEqual(self.code, 0, self.stderr)
        negative = self.data["tests"][CORE + "test_classify_negative"]
        self.assertEqual(negative["files"], {"src/calc/core.py": self.lines("if n < 0", 'return "negative"')})
        # Test files are not product code.
        for test in self.data["tests"].values():
            self.assertEqual(set(test["files"]), {"src/calc/core.py"})

    def test_equal_and_strict_subset_candidates(self) -> None:
        groups = [set(group) for group in self.data["equal_groups"]]
        self.assertIn({CORE + "test_classify_negative", CORE + "test_classify_negative_copy"}, groups)
        subsets = {entry["test"]: entry["supersets"] for entry in self.data["strict_subsets"]}
        self.assertIn(CORE + "test_classify_both_signs", subsets[CORE + "test_classify_negative"])
        self.assertNotIn(CORE + "test_classify_both_signs", subsets)

    def test_unmeasured_tests_ran_no_measured_line(self) -> None:
        expected = {
            "tests/test_cli.py::test_classify_in_subprocess",
            "tests/test_cli.py::test_writes_report_file",
            CORE + "test_quantity_cap",
            "tests/test_order.py::test_order_first_writes",
            "tests/test_order.py::test_order_second_reads",
        }
        self.assertEqual(set(self.data["unmeasured"]), expected)
        self.assertEqual(set(self.data["summary"]["examples"]["unmeasured"]), expected)
        self.assertEqual(self.data["summary"]["unmeasured"], len(expected))
        self.assertEqual(self.data["summary"]["measured"], len(NODEIDS) - len(expected))

    def test_diff_coverage_of_changed_lines_with_raise_and_except_lines(self) -> None:
        diff = self.data["diff"]
        [entry] = diff["files"]
        self.assertEqual(entry["path"], "src/calc/core.py")
        self.assertEqual(entry["missed"], self.lines("except ValueError:", 'raise ValueError(f"bad'))
        for snippet in ("if discount < 0", 'raise ValueError("discount', "return int(text)"):
            self.assertIn(line_of(CORE_HEAD, snippet), entry["executed"])
        self.assertEqual(entry["raise"], {
            "executed": self.lines('raise ValueError("discount'), "missed": self.lines('raise ValueError(f"bad'),
        })
        self.assertEqual(entry["except"], {"executed": [], "missed": self.lines("except ValueError:")})
        self.assertEqual(diff["missed"], 2)
        self.assertEqual(diff["executed"], len(entry["executed"]))
        summary = self.data["summary"]["diff"]
        self.assertEqual((summary["missed"], summary["raise_missed"], summary["except_missed"]), (2, 1, 1))
        self.assertEqual(
            self.data["summary"]["examples"]["missed_lines"],
            [f"src/calc/core.py:{n}" for n in self.lines("except ValueError:", 'raise ValueError(f"bad')],
        )

    def test_contexts_without_show_contexts_is_an_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            plain = Path(tmp) / "plain.json"
            plain.write_text(json.dumps({"meta": {"show_contexts": False}, "files": {}}), encoding="utf-8")
            code, data, _ = run_cli("coverage", "--contexts", str(plain), "--suite", Runs.get().output("run2"))
        self.assertEqual(code, 2)
        self.assertIn("--show-contexts", data["error"])


class UsageTest(unittest.TestCase):
    """Usage and environment errors exit with status 2."""

    def test_unknown_subcommand(self) -> None:
        code, _, _ = run_cli("bogus")
        self.assertEqual(code, 2)

    def test_scan_without_node_ids(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            code, _, _ = run_cli("scan", "--project", tmp)
        self.assertEqual(code, 2)

    def test_suite_with_an_interpreter_that_cannot_import_pytest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "proj"
            write_project(root)
            # -S skips site-packages, so pytest cannot be imported.
            python = f'"{sys.executable}" -S'
            code, data, _ = run_cli(
                "suite", "--python", python, "--project", str(root), "--work-dir", str(Path(tmp) / "work")
            )
        self.assertEqual(code, 2)
        self.assertEqual(data["package"], "pytest")

    def test_suite_with_a_missing_interpreter(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            code, data, _ = run_cli(
                "suite", "--python", str(Path(tmp) / "no-python"), "--project", tmp, "--work-dir", tmp
            )
        self.assertEqual(code, 2)
        self.assertIn("error", data)


def split_skill(path: Path) -> tuple[dict[str, str], str]:
    _, header, body = path.read_text(encoding="utf-8").split("---\n", 2)
    fields = {}
    for line in header.splitlines():
        key, sep, value = line.partition(":")
        if sep:
            fields[key.strip()] = value.strip()
    return fields, body


def supporting_files(skill_dir: Path) -> dict[str, bytes]:
    return {
        path.relative_to(skill_dir).as_posix(): path.read_bytes()
        for path in sorted(skill_dir.rglob("*"))
        if path.is_file()
        and path.name != "SKILL.md"
        and not path.name.startswith(".")
        and "__pycache__" not in path.parts
        and "logs" not in path.relative_to(skill_dir).parts
    }


class HostParityTest(unittest.TestCase):
    def test_bodies_match(self) -> None:
        bodies = {host: split_skill(d / "SKILL.md")[1] for host, d in HOST_SKILLS.items()}
        self.assertEqual(bodies["claude"], bodies["codex"])

    def test_frontmatter_differs_only_by_version(self) -> None:
        fields = {host: split_skill(d / "SKILL.md")[0] for host, d in HOST_SKILLS.items()}
        self.assertEqual(fields["codex"]["name"], "lean-tests")
        self.assertEqual(set(fields["codex"]), {"name", "description"})
        self.assertEqual(fields["claude"]["version"], "1.0.0")
        self.assertEqual({k: v for k, v in fields["claude"].items() if k != "version"}, fields["codex"])

    def test_references_and_scripts_match(self) -> None:
        claude = supporting_files(HOST_SKILLS["claude"])
        codex = supporting_files(HOST_SKILLS["codex"])
        self.assertIn("references/check.md", sorted(claude))
        self.assertIn("scripts/lean_tests.py", sorted(claude))
        self.assertEqual(sorted(claude), sorted(codex))
        for name in claude:
            self.assertEqual(claude[name], codex[name], f"{name} differs between hosts")


if __name__ == "__main__":
    unittest.main()
