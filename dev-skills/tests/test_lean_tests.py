"""Checks for the lean-tests command-line entry, scripts/lean_tests.py.

Each check runs the script in a child process against a small fixture
project in a temporary directory and compares its JSON output with values
that follow from the fixture design. The suite, compare, and coverage checks
need pytest and pytest-cov in the running interpreter. Without them they skip,
and the skip reason, which `-v` shows, names the command that supplies both.
The scan checks need only Python.
"""

from __future__ import annotations

import ast
import hashlib
import importlib
import importlib.util
import json
import os
import shutil
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
    ".gitignore": "*.log\n",
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
            target.with_suffix(".log").write_text("ok")  # .gitignore lists *.log.
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


def run_cli(*args: str, cwd: Path | None = None, env: dict | None = None) -> tuple[int, dict, str]:
    """Run lean_tests.py; return the exit code, the parsed stdout JSON, and stderr."""
    result = subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        cwd=cwd,
        env=env,
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

    def test_syntax_error_names_the_line_and_the_python_version(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "tests").mkdir()
            (root / "tests" / "test_broken.py").write_text("x = 1\ndef test_x(:\n    pass\n", encoding="utf-8")
            nodeids = root / "nodeids.txt"
            nodeids.write_text("tests/test_broken.py::test_x\n", encoding="utf-8")
            code, data, stderr = run_cli("scan", "--project", str(root), "--node-ids", str(nodeids))
        self.assertEqual(code, 0, stderr)
        [entry] = data["unresolved"]
        version = f"{sys.version_info[0]}.{sys.version_info[1]}"
        self.assertTrue(entry["reason"].startswith(f"syntax error at line 2 under Python {version}: "), entry)

    def test_node_ids_are_relative_to_the_working_directory_by_default(self) -> None:
        code, data, stderr = run_cli("scan", "--node-ids", str(self.nodeids), cwd=self.root)
        self.assertEqual(code, 0, stderr)
        self.assertEqual(data, self.data)


def git(root: Path, env: dict, *args: str) -> str:
    result = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, env=env)
    assert result.returncode == 0, result.stderr
    return result.stdout


def git_env(tmp: Path) -> dict:
    """The environment without the user's Git configuration, for a repository under `tmp`."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(
        GIT_CONFIG_GLOBAL=str(tmp / "gitconfig"),
        GIT_CONFIG_NOSYSTEM="1",
        GIT_CEILING_DIRECTORIES=str(tmp),
        GIT_AUTHOR_NAME="Test",
        GIT_AUTHOR_EMAIL="test@example.com",
        GIT_COMMITTER_NAME="Test",
        GIT_COMMITTER_EMAIL="test@example.com",
    )
    return env


def import_script(name: str):
    """Import a module of the scripts directory without writing bytecode beside it."""
    scripts = str(SCRIPT.parent)
    sys.path.insert(0, scripts)
    previous, sys.dont_write_bytecode = sys.dont_write_bytecode, True
    try:
        return importlib.import_module(name)
    finally:
        sys.dont_write_bytecode = previous
        sys.path.remove(scripts)


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
        self.env = git_env(tmp)
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
        # The ignored file counts too; run2 rewrites both files, which then exist already.
        self.assertEqual(self.runs.run1[1]["summary"]["files_written"], ["!! tests/report.log", "?? tests/report.txt"])
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


SPEED_BEFORE = """\
def test_kept():
    assert 2 + 2 == 4


def test_old_name():
    assert "a".upper() == "A"


def test_outcome():
    assert sorted([2, 1]) == [1, 2]
"""

# The after run renames test_old_name to test_new_name, and test_outcome fails.
SPEED_AFTER = SPEED_BEFORE.replace("test_old_name", "test_new_name").replace("== [1, 2]", "== [2, 1]")
SPEED_NODE_PREFIX = "tests/test_speed.py::"


@needs_pytest
class NoLossTest(unittest.TestCase):
    """compare checks the speed mode's no-loss invariant: no node ID missing and no outcome changed."""

    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = tempfile.TemporaryDirectory()
        tmp = Path(cls._tmp.name)
        root = tmp / "proj"
        (root / "tests").mkdir(parents=True)
        (root / "pyproject.toml").write_text('[tool.pytest.ini_options]\ntestpaths = ["tests"]\n', encoding="utf-8")
        cls.out = {label: str(tmp / f"{label}.json") for label in ("before", "after")}
        cls.runs = {}
        for label, text in (("before", SPEED_BEFORE), ("after", SPEED_AFTER)):
            (root / "tests" / "test_speed.py").write_text(text, encoding="utf-8")
            cls.runs[label] = run_cli(
                "suite", "--python", sys.executable, "--project", str(root), "--work-dir", str(tmp / "work"),
                "--label", label, "--out", cls.out[label],
            )

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tmp.cleanup()

    def test_both_runs_pass_or_fail_as_designed(self) -> None:
        for label, passed, failed in (("before", 3, 0), ("after", 2, 1)):
            code, printed, stderr = self.runs[label]
            self.assertEqual(code, 0, stderr)
            self.assertEqual((printed["summary"]["counts"]["passed"], printed["summary"]["counts"]["failed"]), (passed, failed))

    def test_renamed_test_and_changed_outcome_fail_the_invariant(self) -> None:
        code, data, stderr = run_cli("compare", self.out["before"], self.out["after"])
        self.assertEqual(code, 0, stderr)
        self.assertEqual(data["missing"], [SPEED_NODE_PREFIX + "test_old_name"])
        self.assertEqual(data["added"], [SPEED_NODE_PREFIX + "test_new_name"])
        self.assertEqual(
            [(c["nodeid"], c["first"], c["second"], c["second_exception"]) for c in data["changed"]],
            [(SPEED_NODE_PREFIX + "test_outcome", "passed", "failed", "AssertionError")],
        )
        self.assertIs(data["summary"]["no_loss"], False)

    def test_same_tests_and_outcomes_keep_the_invariant(self) -> None:
        code, data, stderr = run_cli("compare", self.out["before"], self.out["before"])
        self.assertEqual(code, 0, stderr)
        self.assertEqual((data["missing"], data["added"], data["changed"]), ([], [], []))
        self.assertIs(data["summary"]["no_loss"], True)


class IncompleteRunTest(unittest.TestCase):
    """A run that did not finish cannot prove the no-loss invariant."""

    def test_timed_out_run_fails_the_invariant(self) -> None:
        ids = [SPEED_NODE_PREFIX + "test_kept", SPEED_NODE_PREFIX + "test_outcome"]

        def suite(timed_out: bool, ran: list[str]) -> dict:
            return {
                "summary": {"timed_out": timed_out, "pytest_exit_code": None if timed_out else 0, "wall_seconds": 1.0},
                "collected": ids,
                "tests": [{"nodeid": n, "outcome": "passed", "phases": {}} for n in ran],
            }

        with tempfile.TemporaryDirectory() as tmp:
            paths = []
            for name, data in (("complete", suite(False, ids)), ("cut", suite(True, ids[:1]))):
                path = Path(tmp) / f"{name}.json"
                path.write_text(json.dumps(data), encoding="utf-8")
                paths.append(str(path))
            code, data, stderr = run_cli("compare", *paths)
        self.assertEqual(code, 0, stderr)
        self.assertEqual((data["missing"], data["changed"]), ([], []))
        self.assertEqual(data["not_run"]["second"], [SPEED_NODE_PREFIX + "test_outcome"])
        self.assertIs(data["summary"]["no_loss"], False)


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


ADDOPTS_FILES = {
    ".gitignore": ".coverage\ncoverage.xml\nhtmlcov/\n",
    "pyproject.toml": """\
        [tool.pytest.ini_options]
        addopts = "--cov=pkg --cov-report=xml"
        testpaths = ["tests"]
        pythonpath = ["src"]
        """,
    "src/pkg/__init__.py": """\
        def f(x):
            return x + 1
        """,
    "tests/test_f.py": """\
        from pkg import f


        def test_f():
            assert f(1) == 2
        """,
}


@needs_pytest
class ProjectCoverageOptionsTest(unittest.TestCase):
    """The project's own pytest-cov options write no coverage file into the project.

    The project's addopts ask for coverage with an XML report, and
    PYTEST_ADDOPTS asks for an HTML report. .gitignore lists all three files.
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = tempfile.TemporaryDirectory()
        tmp = Path(cls._tmp.name)
        cls.root = tmp / "proj"
        env = git_env(tmp)
        for name, text in ADDOPTS_FILES.items():
            path = cls.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(textwrap.dedent(text), encoding="utf-8")
        git(cls.root, env, "init", "-q")
        git(cls.root, env, "add", *ADDOPTS_FILES)
        git(cls.root, env, "commit", "-q", "-m", "base")
        env["PYTEST_ADDOPTS"] = "--cov-report=html"
        common = ("suite", "--python", sys.executable, "--project", str(cls.root), "--work-dir", str(tmp / "work"))
        cls.plain = run_cli(*common, "--label", "plain", env=env)
        cls.covered = run_cli(*common, "--label", "covered", "--coverage-source", "pkg", env=env)

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tmp.cleanup()

    def test_runs_write_no_coverage_file_into_the_project(self) -> None:
        for code, data, stderr in (self.plain, self.covered):
            self.assertEqual(code, 0, stderr)
            self.assertEqual(data["summary"]["counts"]["passed"], 1, data["log_tail"])
            self.assertEqual(data["summary"]["files_written"], [])
        for name in (".coverage", "coverage.xml", "htmlcov"):
            self.assertFalse((self.root / name).exists(), name)

    def test_coverage_run_still_records_per_test_contexts(self) -> None:
        report = json.loads(Path(self.covered[1]["files"]["coverage_json"]).read_text(encoding="utf-8"))
        contexts = report["files"]["src/pkg/__init__.py"]["contexts"]
        self.assertIn("tests/test_f.py::test_f|run", {c for found in contexts.values() for c in found})


class CoverageParseTest(unittest.TestCase):
    """Diff coverage names a changed product file that it cannot parse."""

    def test_changed_file_with_a_syntax_error_is_unparsed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            root = tmp / "proj"
            module = root / "src" / "pkg" / "mod.py"
            module.parent.mkdir(parents=True)
            module.write_text("x = 1\n", encoding="utf-8")
            env = git_env(tmp)
            git(root, env, "init", "-q")
            git(root, env, "add", "src/pkg/mod.py")
            git(root, env, "commit", "-q", "-m", "base")
            module.write_text("x = 1\ndef f(:\n    pass\n", encoding="utf-8")
            contexts = tmp / "contexts.json"
            contexts.write_text(json.dumps({
                "meta": {"show_contexts": True},
                "files": {"src/pkg/mod.py": {"executed_lines": [1], "missing_lines": [2], "contexts": {"1": [""]}}},
            }), encoding="utf-8")
            suite = tmp / "suite.json"
            suite.write_text(json.dumps({
                "summary": {}, "project": str(root), "rootdir": str(root),
                "collected": ["tests/test_mod.py::test_x"], "tests": [],
            }), encoding="utf-8")
            code, data, stderr = run_cli(
                "coverage", "--contexts", str(contexts), "--suite", str(suite), "--base", "HEAD", env=env
            )
        self.assertEqual(code, 0, stderr)
        [entry] = data["diff"]["unparsed"]
        self.assertEqual(entry["file"], "src/pkg/mod.py")
        version = f"{sys.version_info[0]}.{sys.version_info[1]}"
        self.assertTrue(entry["reason"].startswith(f"syntax error at line 2 under Python {version}: "), entry)
        self.assertEqual(data["summary"]["diff"]["unparsed"], 1)
        self.assertEqual(data["diff"]["files"][0]["missed"], [2])


class WithoutCovTest(unittest.TestCase):
    """A coverage run removes the project's pytest-cov options from addopts."""

    def test_drops_each_option_shape_and_keeps_cov_config(self) -> None:
        without_cov = import_script("lt_suite").without_cov
        cases = [
            (["--cov=pkg", "--cov-report=xml", "-q"], ["-q"]),
            (["--cov", "pkg", "-q"], ["-q"]),
            (["--cov", "-q"], ["-q"]),
            (["-q", "--cov"], ["-q"]),
            (["--cov-report", "xml", "--cov-fail-under", "90", "-x"], ["-x"]),
            (["--cov-context", "test", "--cov-precision", "2", "-x"], ["-x"]),
            (["--cov-fail-under=90", "--cov-context=test", "--cov-precision=2"], []),
            (["--cov-branch", "--cov-append", "--cov-reset", "--no-cov", "--no-cov-on-fail", "tests"], ["tests"]),
            (["--cov-config", "setup.cfg", "--cov-config=.coveragerc", "--cov=pkg"], ["--cov-config", "setup.cfg", "--cov-config=.coveragerc"]),
            (["-p", "xdist", "--cov-report"], ["-p", "xdist"]),
        ]
        for args, kept in cases:
            self.assertEqual(without_cov(args), kept, args)


class UsageTest(unittest.TestCase):
    """Usage and environment errors exit with status 2."""

    def test_unknown_subcommand(self) -> None:
        code, _, _ = run_cli("bogus")
        self.assertEqual(code, 2)

    def test_scan_without_node_ids(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            code, _, _ = run_cli("scan", "--project", tmp)
        self.assertEqual(code, 2)

    def test_scan_of_a_suite_output_takes_no_project(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            code, data, _ = run_cli("scan", "--suite", str(Path(tmp) / "run1.json"), "--project", tmp)
        self.assertEqual(code, 2)
        self.assertIn("--project", data["error"])

    def test_python_older_than_3_9_stops_with_one_line(self) -> None:
        code = (
            "import runpy, sys; sys.argv = [sys.argv[1], 'scan']; sys.version_info = (3, 8, 0); "
            "runpy.run_path(sys.argv[0], run_name='__main__')"
        )
        result = subprocess.run([sys.executable, "-c", code, str(SCRIPT)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stderr, "lean_tests.py: needs Python 3.9 or newer, not Python 3.8\n")
        self.assertEqual(json.loads(result.stdout), {"error": "needs Python 3.9 or newer, not Python 3.8"})

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


MUTATE_CORE = """\
import functools

LIMIT = 5


def classify(n):
    if n < 0:  # sign check
        return "negative"
    return "non-negative"


def total(qty, unit):
    return qty * unit


@functools.lru_cache(maxsize=None)
def rate(code):
    if code == "gold":
        return 3
    return 1


def discount(code, price):
    return price - rate(code)


class Cart:
    def __repr__(self):
        return "Cart()"
"""

MUTATE_TESTS = """\
from shop.core import LIMIT, Cart, classify, discount, rate, total


def test_limit():
    assert LIMIT == 5


def test_classify_negative():
    assert classify(-1) == "negative"


def test_classify_negative_copy():
    assert classify(-1) == "negative"


def test_classify_zero():
    assert classify(0) == "non-negative"


def test_total():
    assert total(3, 4) == 12


def test_total_tautology():
    assert total(2, 3) == total(2, 3)


def test_rate_gold():
    assert rate("gold") == 3


def test_discount_gold():
    assert discount("gold", 10) == 7


def test_cart_repr():
    assert repr(Cart()) == "Cart()"
"""

# The mutator finds no mutant in this module: a docstring and `pass` are arid code.
MUTATE_HOOKS = """\
def on_sale(item):
    \"\"\"Run after each sale; the default hook does nothing.\"\"\"
    pass
"""

MUTATE_HOOK_TESTS = """\
from shop.hooks import on_sale


def test_on_sale_hook():
    assert on_sale("pen") is None
"""

# No pytest `pythonpath`: PYTHONPATH names src/, as an editable install of the project would.
MUTATE_FILES = {
    "pyproject.toml": '[tool.pytest.ini_options]\ntestpaths = ["tests"]\n',
    "src/shop/__init__.py": "",
    "src/shop/core.py": MUTATE_CORE,
    "src/shop/hooks.py": MUTATE_HOOKS,
    "tests/test_hooks.py": MUTATE_HOOK_TESTS,
    "tests/test_shop.py": MUTATE_TESTS,
}
SHOP = "tests/test_shop.py::"
HOOK_TEST = "tests/test_hooks.py::test_on_sale_hook"


def tree_state(root: Path) -> dict[str, tuple]:
    """Each path under `root` with its SHA-256 and modification time; a directory has neither."""
    state = {}
    for path in sorted(root.rglob("*")):
        if path.is_file():
            state[path.relative_to(root).as_posix()] = (hashlib.sha256(path.read_bytes()).hexdigest(), path.stat().st_mtime_ns)
        else:
            state[path.relative_to(root).as_posix()] = ()
    return state


def shop_env(root: Path) -> dict:
    return {**os.environ, "PYTHONPATH": str(root / "src")}


def without_test(text: str, name: str) -> str:
    blocks = text.split("\n\n\n")
    kept = [block for block in blocks if not block.startswith(f"def {name}(")]
    assert len(kept) == len(blocks) - 1, name
    return "\n\n\n".join(kept)


class Mutation:
    """The shop project, its coverage run, and its kill matrix, shared by the mutate checks.

    The expected kill sets follow from MUTATE_CORE and MUTATE_TESTS. Each
    mutant runs in a fresh pytest process, so rate() computes its value in
    test_rate_gold, and test_discount_gold gets the cached value. The hook
    test reaches only MUTATE_HOOKS, which has no mutant. test_cart_repr runs
    only `__repr__`, which gets no mutant.
    """

    _instance: Mutation | None = None

    @classmethod
    def get(cls) -> Mutation:
        if cls._instance is None:
            cls._instance = cls()
            unittest.addModuleCleanup(cls._instance._tmp.cleanup)
        return cls._instance

    def __init__(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.root = self.tmp / "shop"
        for name, text in MUTATE_FILES.items():
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        self.env = shop_env(self.root)
        self.work = self.tmp / "work"
        self.scope = self.work / "scope.json"
        self.matrix = self.work / "matrix.json"
        code, _, stderr = run_cli(
            "suite", "--python", sys.executable, "--project", str(self.root), "--work-dir", str(self.work),
            "--label", "scope", "--coverage-source", "shop", "--out", str(self.scope), env=self.env,
        )
        assert code == 0, stderr
        self.before = tree_state(self.root)
        self.code, self.printed, self.stderr = self.mutate("--out", str(self.matrix))
        self.after = tree_state(self.root)
        self.data = json.loads(self.matrix.read_text(encoding="utf-8")) if self.matrix.is_file() else {}
        self.tests = {test["nodeid"]: test for test in self.data.get("tests", [])}

    def mutate(self, *args: str, suite: Path | None = None, env: dict | None = None) -> tuple[int, dict, str]:
        return run_cli(
            "mutate", "--python", sys.executable, "--suite", str(suite or self.scope),
            "--work-dir", str(self.work), "--workers", "3", *args, env=env or self.env,
        )

    def mutant(self, snippet: str, after: str) -> dict:
        """The one mutant whose changed line contains `snippet` and reads `after` once mutated."""
        line = line_of(MUTATE_CORE, snippet)
        found = [m for m in self.data["mutants"] if m["line"] == line and m["after"] == after]
        assert len(found) == 1, (snippet, after, [(m["line"], m["after"]) for m in self.data["mutants"]])
        return found[0]


@needs_pytest
class MutateMatrixTest(unittest.TestCase):
    """mutate runs every mutant of the covered modules against every in-scope test."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.m = Mutation.get()

    def entry(self, name: str) -> dict:
        return self.m.tests[SHOP + name]

    def test_matrix_is_complete_after_the_sanity_mutant_is_killed(self) -> None:
        self.assertEqual(self.m.code, 0, self.m.stderr)
        summary = self.m.data["summary"]
        self.assertTrue(summary["complete"], summary["incomplete_reason"])
        self.assertEqual(self.m.printed, {"summary": summary, "output": str(self.m.matrix)})
        self.assertEqual((summary["tests"], summary["modules"], summary["survived"]), (10, 1, 0))
        self.assertEqual(summary["killed"], summary["mutants"])
        [sanity] = self.m.data["sanity"]
        self.assertEqual(sanity["path"], "src/shop/core.py")
        self.assertTrue(sanity["killed"])

    def test_duplicate_tests_are_subsumed_by_each_other(self) -> None:
        negative, copy = SHOP + "test_classify_negative", SHOP + "test_classify_negative_copy"
        for test, other in ((negative, copy), (copy, negative)):
            entry = self.m.tests[test]
            self.assertEqual((entry["class"], entry["subsumed_by"]), ("subsumed", [other]), test)
        self.assertEqual(self.m.data["equal_groups"], [[negative, copy]])

    def test_tautological_test_has_an_empty_kill_set(self) -> None:
        tautology = self.entry("test_total_tautology")
        self.assertEqual((tautology["class"], tautology["kills"]), ("empty", []))

    def test_kill_set_within_another_tests_kill_set_is_subsumed(self) -> None:
        rate = self.entry("test_rate_gold")
        self.assertEqual((rate["class"], rate["subsumed_by"]), ("subsumed", [SHOP + "test_discount_gold"]))

    def test_branch_specific_test_has_a_unique_kill(self) -> None:
        zero = self.entry("test_classify_zero")
        boundary = self.m.mutant("if n < 0", "if n <= 0:  # sign check")
        self.assertEqual(zero["class"], "unique")
        self.assertIn(boundary["id"], zero["unique"])
        self.assertEqual(boundary["killed_by"], {SHOP + "test_classify_zero": "assertion"})
        self.assertEqual(boundary["operator"], "comparison")

    def test_kill_through_a_memoized_value_counts(self) -> None:
        mutant = self.m.mutant("return 3", "return 4")
        self.assertEqual(
            mutant["killed_by"], {SHOP + "test_rate_gold": "assertion", SHOP + "test_discount_gold": "assertion"}
        )
        # Coverage gives the line only to test_rate_gold: test_discount_gold gets the cached value.
        scope = json.loads(self.m.scope.read_text(encoding="utf-8"))
        report = json.loads(Path(scope["files"]["coverage_json"]).read_text(encoding="utf-8"))
        contexts = report["files"]["src/shop/core.py"]["contexts"][str(mutant["line"])]
        self.assertEqual(contexts, [SHOP + "test_rate_gold|run"])

    def test_kills_record_the_failure_type(self) -> None:
        mutant = self.m.mutant("return 3", "return None")
        self.assertEqual(
            mutant["killed_by"], {SHOP + "test_rate_gold": "assertion", SHOP + "test_discount_gold": "exception"}
        )
        self.assertEqual(mutant["operator"], "return-none")

    def test_unmeasured_test_is_labeled_and_keeps_its_kill(self) -> None:
        limit = self.entry("test_limit")
        mutant = self.m.mutant("LIMIT = 5", "LIMIT = 6")
        self.assertEqual(limit["class"], "unmeasured")
        self.assertEqual(limit["kills"], [mutant["id"]])
        self.assertEqual(mutant["killed_by"], {SHOP + "test_limit": "assertion"})

    def test_test_that_reaches_only_a_skipped_module_is_unmeasured(self) -> None:
        hook = self.m.tests[HOOK_TEST]
        self.assertEqual((hook["class"], hook["measured"], hook["kills"]), ("unmeasured", False, []))
        [skipped] = self.m.data["skipped_modules"]
        self.assertEqual(skipped["path"], "src/shop/hooks.py")
        self.assertIn("no mutant", skipped["reason"])
        self.assertEqual(self.m.data["unmeasured"], [HOOK_TEST, SHOP + "test_limit", SHOP + "test_cart_repr"])

    def test_test_that_runs_only_lines_without_a_mutant_is_unmeasured(self) -> None:
        cart = self.entry("test_cart_repr")
        self.assertEqual((cart["class"], cart["measured"], cart["kills"]), ("unmeasured", False, []))
        repr_line = line_of(MUTATE_CORE, 'return "Cart()"')
        self.assertNotIn(repr_line, {m["line"] for m in self.m.data["mutants"]})

    def test_summary_counts_each_class(self) -> None:
        classes = self.m.data["summary"]["classes"]
        self.assertEqual(classes, {"unique": 3, "subsumed": 3, "union-only": 0, "empty": 1, "unmeasured": 3, "incomplete": 0})

    def test_no_reported_line_has_more_than_three_mutants(self) -> None:
        lines = [(m["path"], m["line"]) for m in self.m.data["mutants"]]
        self.assertLessEqual(max(lines.count(line) for line in lines), 3)

    def test_mutated_text_is_spliced_into_the_original_line(self) -> None:
        # The comment stays, so only the operator changed. Unparsing the whole file drops comments.
        boundary = self.m.mutant("if n < 0", "if n <= 0:  # sign check")
        self.assertEqual(boundary["before"], "if n < 0:  # sign check")
        stub = self.m.mutant("if n < 0", "return None")
        self.assertEqual(stub["operator"], "stub")

    def test_a_line_that_no_test_runs_gets_no_mutant(self) -> None:
        self.assertNotIn(line_of(MUTATE_CORE, "return 1"), {m["line"] for m in self.m.data["mutants"]})

    def test_mutants_never_change_the_project(self) -> None:
        self.assertEqual(self.m.after, self.m.before)


@needs_pytest
class MutateBudgetTest(unittest.TestCase):
    """mutate gives incomplete evidence and no deletion classes when the budget runs out."""

    def test_budget_overrun_is_incomplete_evidence(self) -> None:
        m = Mutation.get()
        with tempfile.TemporaryDirectory() as tmp:
            code, data, stderr = run_cli(
                "mutate", "--python", sys.executable, "--suite", str(m.scope), "--work-dir", tmp,
                "--workers", "1", "--budget", "1", env=m.env,
            )
        self.assertEqual(code, 0, stderr)
        summary = data["summary"]
        self.assertFalse(summary["complete"])
        self.assertIn("budget", summary["incomplete_reason"])
        self.assertGreater(summary["not_run"], 0)
        self.assertIsNone(summary["classes"])
        self.assertEqual([t["class"] for t in data["tests"] if t["class"] is not None], [])
        self.assertEqual(tree_state(m.root), m.before)


@needs_pytest
class MutateRecheckTest(unittest.TestCase):
    """The killed-set check reruns the killed set against the tests that remain after a removal batch."""

    def recheck(self, removed: str) -> dict:
        m = Mutation.get()
        tmp = Path(tempfile.mkdtemp(dir=m.tmp))
        root = tmp / "shop"
        shutil.copytree(m.root, root)
        (root / "tests" / "test_shop.py").write_text(without_test(MUTATE_TESTS, removed), encoding="utf-8")
        env = shop_env(root)
        after = tmp / "after.json"
        code, _, stderr = run_cli(
            "suite", "--python", sys.executable, "--project", str(root), "--work-dir", str(tmp / "work"),
            "--label", "after", "--out", str(after), env=env,
        )
        self.assertEqual(code, 0, stderr)
        before = tree_state(root)
        code, data, stderr = m.mutate("--recheck", str(m.matrix), suite=after, env=env)
        self.assertEqual(code, 0, stderr)
        self.assertEqual(tree_state(root), before)
        return data

    def test_removing_a_test_with_a_unique_kill_fails(self) -> None:
        m = Mutation.get()
        data = self.recheck("test_classify_zero")
        summary = data["summary"]
        self.assertTrue(summary["complete"], summary["incomplete_reason"])
        self.assertFalse(summary["passed"])
        lost = [mutant["id"] for mutant in data["lost"]]
        self.assertEqual(sorted(lost), sorted(m.tests[SHOP + "test_classify_zero"]["unique"]))
        self.assertIn(m.mutant("if n < 0", "if n <= 0:  # sign check")["id"], lost)
        self.assertEqual(summary["lost"], len(lost))
        self.assertEqual(data["lost"][0]["killed_before_by"], [SHOP + "test_classify_zero"])

    def test_removing_a_true_duplicate_passes(self) -> None:
        m = Mutation.get()
        data = self.recheck("test_classify_negative_copy")
        summary = data["summary"]
        self.assertTrue(summary["complete"], summary["incomplete_reason"])
        self.assertTrue(summary["passed"])
        self.assertEqual(data["lost"], [])
        self.assertEqual(summary["tests"], 9)
        self.assertEqual(summary["still_killed"], summary["killed_set"])
        self.assertEqual(summary["killed_set"], m.data["summary"]["killed"])


class MutantFinderTest(unittest.TestCase):
    """The mutator chooses the mutants of a module from its text and executed lines, without a pytest run."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.module_mutants = staticmethod(import_script("lt_mutate").module_mutants)

    def mutants(self, text: str) -> list[dict]:
        text = textwrap.dedent(text)
        return self.module_mutants("m.py", text, set(range(1, text.count("\n") + 1)))

    def test_a_stub_counts_toward_the_cap_of_the_line_that_reports_it(self) -> None:
        found = self.mutants("""\
            def shipping(weight):
                return weight * 2 + 5
            """)
        self.assertEqual([(m["line"], m["operator"]) for m in found], [(2, "arithmetic"), (2, "return-none"), (2, "constant")])

    def test_f_string_gets_mutants_like_other_code(self) -> None:
        found = self.mutants("""\
            def label(count):
                prefix = "n"
                text = f"{prefix}: {count + 1} items"
                return text
            """)
        self.assertEqual({m["after"] for m in found if m["line"] == 3}, {
            'text = ("XX" + f"{prefix}: {count + 1} items" + "XX")',
            'text = f"{prefix}: {count - 1} items"',
            'text = f"{prefix}: {count + 2} items"',
        })

    def test_arid_code_gets_no_mutant(self) -> None:
        found = self.mutants('''\
            import logging

            log = logging.getLogger(__name__)


            def audit(event: str) -> None:
                """Log the event."""
                log.info("event %s", event)


            class Box:
                size: int = 3

                def __repr__(self):
                    return "Box(" + str(self.size) + ")"
            ''')
        self.assertEqual([(m["line"], m["after"]) for m in found], [(12, "size: int = 4")])


class DemotionTest(unittest.TestCase):
    """Every mutant that a demoted test kills stays killed by a staying test, assuming that each staying test runs and passes, with the same kills, in the hand-off tier."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.classify = staticmethod(import_script("lt_mutate").classify)

    def matrix(self, tests: list[str], killers: dict[str, list[str]], not_reached: dict | None = None) -> dict:
        """The test entries of a complete matrix with these killers of each mutant."""
        mutants = [
            {"id": mutant, "killed_by": dict.fromkeys(names, "assertion"), "not_reached": (not_reached or {}).get(mutant, [])}
            for mutant, names in killers.items()
        ]
        entries, _ = self.classify(tests, set(), mutants, complete=True)
        return {entry["nodeid"]: entry for entry in entries}

    def assert_demoted_kills_stay(self, entries: dict) -> None:
        stay = [e for e in entries.values() if not e["demote"] and e["class"] not in ("empty", "subsumed")]
        kept = set().union(*(e["kills"] for e in stay))
        for entry in entries.values():
            if entry["demote"]:
                self.assertLessEqual(set(entry["kills"]) | set(entry["unknown"]), kept, entry["nodeid"])

    def test_one_of_two_union_only_duplicates_stays(self) -> None:
        # The run of m3 timed out in z, so m3 is unknown for x and y, and neither subsumes the other.
        entries = self.matrix(["z", "x", "y"], {"m1": ["x", "y"], "m2": ["x", "y"], "m3": ["z"]}, {"m3": ["x", "y"]})
        self.assertEqual({n: e["class"] for n, e in entries.items()}, {"z": "unique", "x": "union-only", "y": "union-only"})
        self.assertEqual([n for n, e in entries.items() if e["demote"]], ["x"])
        self.assert_demoted_kills_stay(entries)

    def test_union_only_tests_whose_other_killers_can_be_deleted_stay(self) -> None:
        entries = self.matrix(["a", "b", "c", "d"], {"m1": ["a", "c"], "m2": ["a", "b"], "m3": ["b", "d"]})
        self.assertEqual(
            {n: e["class"] for n, e in entries.items()},
            {"a": "union-only", "b": "union-only", "c": "subsumed", "d": "subsumed"},
        )
        self.assertEqual([n for n, e in entries.items() if e["demote"]], [])
        self.assert_demoted_kills_stay(entries)

    def test_a_demotion_relies_on_no_test_of_a_deletion_class(self) -> None:
        # x and y are subsumed by each other; the decision step keeps one of them, so m1 stays killed.
        killers = {"m1": ["x", "y"], "m2": ["a", "w"], "m3": ["b", "w"], "m4": ["a"], "m5": ["b"]}
        entries = self.matrix(["x", "y", "a", "b", "w"], killers)
        self.assertEqual(
            {n: e["class"] for n, e in entries.items()},
            {"x": "subsumed", "y": "subsumed", "a": "unique", "b": "unique", "w": "union-only"},
        )
        self.assertEqual([n for n, e in entries.items() if e["demote"]], ["w"])
        self.assert_demoted_kills_stay(entries)


def write_suite(tmp: Path, project: Path) -> Path:
    """A suite output with one collected test of `project` and no coverage contexts."""
    suite = tmp / "suite.json"
    suite.write_text(json.dumps({
        "summary": {}, "project": str(project), "rootdir": str(project),
        "collected": ["tests/test_x.py::test_x"], "tests": [], "files": {},
    }), encoding="utf-8")
    return suite


class MutateUsageTest(unittest.TestCase):
    """mutate stops with exit status 2 before it runs a test when its inputs cannot give evidence."""

    def test_matrix_needs_coverage_contexts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "proj"
            project.mkdir()
            suite = write_suite(Path(tmp), project)
            code, data, _ = run_cli(
                "mutate", "--python", sys.executable, "--suite", str(suite), "--work-dir", str(Path(tmp) / "work")
            )
        self.assertEqual(code, 2)
        self.assertIn("--coverage-source", data["error"])

    def test_recheck_refuses_changed_product_code(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "proj"
            (project / "src").mkdir(parents=True)
            (project / "src" / "m.py").write_text("X = 2\n", encoding="utf-8")
            matrix = Path(tmp) / "matrix.json"
            matrix.write_text(json.dumps({
                "summary": {"mode": "matrix", "complete": True},
                "modules": [{"path": "src/m.py", "sha256": hashlib.sha256(b"X = 1\n").hexdigest()}],
                "tests": [], "mutants": [],
            }), encoding="utf-8")
            suite = write_suite(Path(tmp), project)
            code, data, _ = run_cli(
                "mutate", "--python", sys.executable, "--suite", str(suite), "--recheck", str(matrix),
                "--work-dir", str(Path(tmp) / "work"),
            )
        self.assertEqual(code, 2)
        self.assertIn("src/m.py", data["error"])


GATE_CORE = """\
def classify(n):
    if n < 0:
        return "negative"
    return "non-negative"


def total(qty, unit):
    return qty * unit


def discount(price, code):
    if code == "gold":
        return price - 3
    return price
"""

GATE_TESTS = """\
import pytest

from calc.core import classify, discount, total
from shared import SharedChecks

try:
    from math import isqrt
except ImportError:  # before Python 3.8
    isqrt = None


def test_classify_negative():
    assert classify(-1) == "negative"


def test_classify_zero():
    assert classify(0) == "non-negative"


@pytest.mark.parametrize("n, expected", [(-2, "negative"), (5, "non-negative")])
def test_classify_cases(n, expected):
    assert classify(n) == expected


@pytest.mark.parametrize("n", [1, 2])
def test_double(n):
    assert total(n, 2) == 2 * n


def test_total():
    assert total(3, 4) == 12


def test_total_bound():
    assert total(2, 2) <= 4


def test_discount_plain():
    assert discount(10, "none") == 10


class TestShared:
    def expected(self):
        return "non-negative"

    def test_shared(self):
        assert classify(3) == self.expected()


class TestChild(TestShared):
    "Runs the shared tests again."


class TestImported(SharedChecks):
    "Runs the checks of tests/shared.py."
"""

# A helper module: the gate cannot read the names that TestImported inherits from it.
GATE_SHARED = """\
from calc.core import classify


class SharedChecks:
    def test_classify_shared(self):
        assert classify(4) == "non-negative"
"""

GATE_FILES = {
    "pyproject.toml": '[tool.pytest.ini_options]\ntestpaths = ["tests"]\npythonpath = ["src"]\n',
    "src/calc/__init__.py": "",
    "src/calc/core.py": GATE_CORE,
    "tests/shared.py": GATE_SHARED,
    "tests/test_core.py": GATE_TESTS,
}
GATE = "tests/test_core.py::"


def edited(text: str, *pairs: str) -> str:
    """`text` with each (old, new) pair of `pairs` replaced once."""
    for old, new in zip(pairs[0::2], pairs[1::2]):
        assert text.count(old) == 1, old
        text = text.replace(old, new)
    return text


# A product change that keeps every base test passing, so the gate unit is a mixed change.
PRODUCT_EDIT = {"src/calc/core.py": GATE_CORE + "\n\ndef double(n):\n    return 2 * n\n"}
# Each case is one branch from the base commit with PRODUCT_EDIT and this version of tests/test_core.py.
GATE_CASES = {
    "self-comparison": edited(GATE_TESTS, "    assert total(3, 4) == 12", "    actual = total(3, 4)\n    assert actual == actual"),
    "autouse": GATE_TESTS + "\n\n@pytest.fixture(autouse=True)\ndef reset_state():\n    yield\n",
    "walrus": edited(GATE_TESTS, "    assert total(n, 2) == 2 * n", "    assert (n := 0) == 0\n    assert total(n, 2) == 2 * n"),
    "rebinding": GATE_TESTS + "\n\ndef test_total():\n    assert total(0, 4) == 0\n",
    "removed": edited(GATE_TESTS, 'def test_classify_negative():\n    assert classify(-1) == "negative"\n\n\n', ""),
    "skip": edited(GATE_TESTS, "def test_total():", '@pytest.mark.skip(reason="slow")\ndef test_total():'),
    "expected-literal": edited(GATE_TESTS, '== "negative"\n\n\ndef test_classify_zero', '== "neg"\n\n\ndef test_classify_zero'),
    "two-literals": edited(GATE_TESTS, 'classify(-1) == "negative"', 'classify(-5) == "neg"'),
    "bound": edited(GATE_TESTS, "total(2, 2) <= 4", "total(2, 2) <= 5"),
    "appended": edited(GATE_TESTS, '(5, "non-negative")])', '(5, "non-negative"), (7, "non-negative")])'),
    "new-tests": GATE_TESTS + "\n\ndef test_total_zero():\n    assert total(0, 4) == 0\n",
    "guarded": GATE_TESTS + "\n\ndef isqrt(n):\n    return int(n ** 0.5)\n",
    "override": edited(GATE_TESTS, "again.\"\n", "again.\"\n\n    def test_shared(self):\n        assert True\n"),
    "imported-override": edited(
        GATE_TESTS, "shared.py.\"\n", "shared.py.\"\n\n    def test_classify_shared(self):\n        assert True\n",
    ),
    "inherited-helper": edited(GATE_TESTS, "again.\"\n", "again.\"\n\n    def expected(self):\n        return classify(3)\n"),
    "builtin": GATE_TESTS + "\n\ndef sum(values):\n    return 0\n",
    "alias-autouse": edited(GATE_TESTS, "import pytest\n", "import pytest\nfrom pytest import fixture as fx\n")
    + '\n\n@fx(autouse=True)\ndef skip_all():\n    pytest.skip("off")\n',
    "computed-name": GATE_TESTS + '\n\nNAME = "tmp_path"\n\n\n@pytest.fixture(name=NAME)\ndef scratch():\n    return None\n',
    "plugin-fixture": GATE_TESTS + "\n\n@pytest.fixture\ndef linecomp():\n    return None\n",
    "xunit": GATE_TESTS + '\n\ndef setup_function():\n    pytest.skip("off")\n',
    "xunit-method": edited(
        GATE_TESTS, "    def test_shared(self):\n", '    def setup_method(self):\n        pytest.skip("off")\n\n    def test_shared(self):\n',
    ),
    "skip-helper": GATE_TESTS + '\n\ndef offline():\n    pytest.skip("offline")\n',
    "import-alias-write": GATE_TESTS + (
        "\n\ndef test_patched():\n    import calc.core as core\n    core.discount = lambda price, code: price\n"
        '    assert core.discount(5, "gold") == 5\n'
    ),
    "dunder-test": edited(GATE_TESTS, "class TestShared:\n", "class TestShared:\n    __test__ = False\n\n"),
}


# The product code of g1: a guard in total, and parse_qty.
G1_CORE = edited(
    GATE_CORE, "def total(qty, unit):\n", 'def total(qty, unit):\n    if qty < 0:\n        raise ValueError("qty must not be negative")\n',
) + "\n\ndef parse_qty(text):\n    return int(text)\n"


class GateRepo:
    """A Git project with a base commit and one branch per gate case.

    `g1` adds a guard and parse_qty to the product code, appends a literal
    case that keeps the existing node IDs, and adds four new tests: one that
    fails on base with an assertion (catching), one in a module that cannot
    import at base (new-API), and two that pass on base (hardening).
    test_discount_gold reaches a branch that no base test covers;
    test_total_large covers only lines that test_total covers. `g2` makes
    classify(0) return "zero", changes the expected value of
    test_classify_zero to match, and appends a duplicate case to
    test_double, which renames its node ID test_double[2]. The work tree
    ends on g1.
    """

    _instance: GateRepo | None = None

    @classmethod
    def get(cls) -> GateRepo:
        if cls._instance is None:
            cls._instance = cls()
            unittest.addModuleCleanup(cls._instance._tmp.cleanup)
        return cls._instance

    def __init__(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.root = self.tmp / "proj"
        self.work = self.tmp / "work"
        self.env = git_env(self.tmp)
        self.commit("base", GATE_FILES, new=True)
        git(self.root, self.env, "tag", "base")
        for name, tests in GATE_CASES.items():
            self.branch(name, {**PRODUCT_EDIT, "tests/test_core.py": tests})
        self.branch("test-only", {"tests/test_core.py": GATE_CASES["expected-literal"]})
        self.branch("test-only-new", {"tests/test_core.py": GATE_CASES["new-tests"]})
        self.branch("package-doc", {
            "tests/test_core.py": GATE_CASES["removed"], "README.md": "# calc\n", "src/calc/template.md": "Total: {}\n",
        })
        self.branch("per-commit", {"tests/test_core.py": GATE_CASES["expected-literal"]}, stay=True)
        self.commit("product", PRODUCT_EDIT)
        git(self.root, self.env, "checkout", "-q", "base")
        self.branch("conftest", {**PRODUCT_EDIT, "tests/conftest.py": "import pytest\n"})
        self.branch("config", {
            **PRODUCT_EDIT,
            "pyproject.toml": GATE_FILES["pyproject.toml"] + "addopts = [\"-k\", \"not total\"]\n",
        })
        self.branch("g2", {
            "src/calc/core.py": edited(GATE_CORE, '        return "negative"\n', '        return "negative"\n    if n == 0:\n        return "zero"\n'),
            "tests/test_core.py": edited(GATE_TESTS, 'classify(0) == "non-negative"', 'classify(0) == "zero"', "[1, 2])", "[1, 2, 2])"),
        })
        self.branch("g1", {
            "src/calc/core.py": G1_CORE,
            "tests/test_core.py": GATE_CASES["appended"] + (
                "\n\ndef test_total_rejects_negative():\n    with pytest.raises(ValueError):\n        total(-1, 2)\n"
                "\n\ndef test_total_large():\n    assert total(1000, 3) == 3000\n"
                '\n\ndef test_discount_gold():\n    assert discount(10, "gold") == 7\n'
            ),
            "tests/test_parse.py": 'from calc.core import parse_qty\n\n\ndef test_parse_qty():\n    assert parse_qty("3") == 3\n',
        }, stay=True)

    def commit(self, message: str, files: dict[str, str], new: bool = False) -> None:
        if new:
            git(self.tmp, self.env, "init", "-q", str(self.root))
        for name, text in files.items():
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        git(self.root, self.env, "add", *files)
        git(self.root, self.env, "commit", "-q", "-m", message)

    def branch(self, name: str, files: dict[str, str], stay: bool = False) -> None:
        git(self.root, self.env, "checkout", "-q", "-b", name, "base")
        self.commit(name, files)
        if not stay:
            git(self.root, self.env, "checkout", "-q", "base")

    def gate(self, head: str, *args: str) -> tuple[int, dict, str]:
        return run_cli("gate", "--project", str(self.root), "--base", "base", "--head", head, *args, env=self.env)

    def run_gate(self, head: str, *extra: str) -> tuple[int, dict, str]:
        """The gate with pytest runs; `extra` holds pytest arguments for each run."""
        tail = ["--", *extra] if extra else []
        return self.gate(head, "--python", sys.executable, "--work-dir", str(self.work / head), *tail)


def gate_items(data: dict) -> list[tuple]:
    return [(i["class"], i["subtype"], i["nodeid"]) for unit in data["units"] for i in unit["items"]]


class GateStaticTest(unittest.TestCase):
    """Layer 2 of the gate classifies each test-side change of a unit from the syntax trees."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.repo = GateRepo.get()

    def static(self, head: str, *args: str) -> tuple[int, dict]:
        code, data, stderr = self.repo.gate(head, "--static-only", *args)
        self.assertIn(code, (0, 1), stderr)
        return code, data

    def assert_fails_with(self, head: str, cls: str, subtype: str, name: str | None, status: str = "fail") -> dict:
        """Assert that the gate fails the mixed change `head` with one item other than SAFE, and return that item."""
        code, data = self.static(head)
        self.assertEqual(code, 1)
        self.assertFalse(data["summary"]["passed"])
        unit = data["units"][0]
        self.assertTrue(unit["mixed"])
        self.assertEqual(unit["status"], status)
        found = [i for i in unit["items"] if i["class"] != "SAFE"]
        nodeid = GATE + name if name else None
        self.assertEqual([(i["class"], i["subtype"], i["nodeid"]) for i in found], [(cls, subtype, nodeid)])
        return found[0]

    def test_self_comparison_in_an_existing_test_is_weakening(self) -> None:
        self.assert_fails_with("self-comparison", "WEAKENING", "self-comparison", "test_total")

    def test_new_autouse_fixture_is_unclassified(self) -> None:
        found = self.assert_fails_with("autouse", "UNCLASSIFIED", "signal", "reset_state")
        self.assertIn("autouse fixture reset_state", found["detail"])

    def test_walrus_assertion_added_inside_an_existing_test_is_unclassified(self) -> None:
        self.assert_fails_with("walrus", "UNCLASSIFIED", "changed-definition", "test_double")

    def test_same_name_rebinding_is_unclassified(self) -> None:
        found = self.assert_fails_with("rebinding", "UNCLASSIFIED", "rebinding", "test_total")
        self.assertIn("assert total(0, 4) == 0", found["diff"])

    def test_removed_test_is_weakening(self) -> None:
        self.assert_fails_with("removed", "WEAKENING", "removed-test", "test_classify_negative")

    def test_new_skip_marker_is_weakening(self) -> None:
        self.assert_fails_with("skip", "WEAKENING", "skip", "test_total")

    def test_one_changed_literal_operand_of_an_equality_is_expected_literal(self) -> None:
        found = self.assert_fails_with("expected-literal", "WEAKENING", "expected-literal", "test_classify_negative")
        self.assertEqual((found["old"], found["new"]), ('"negative"', '"neg"'))

    def test_a_second_changed_literal_is_not_expected_literal(self) -> None:
        self.assert_fails_with("two-literals", "WEAKENING", "changed-assert", "test_classify_negative")

    def test_inequality_bound_change_is_not_expected_literal(self) -> None:
        self.assert_fails_with("bound", "WEAKENING", "changed-assert", "test_total_bound")

    def test_appended_cases_without_collection_evidence_need_evidence(self) -> None:
        self.assert_fails_with(
            "appended", "UNCLASSIFIED", "no-collection-evidence", "test_classify_cases", status="needs evidence",
        )

    def test_binding_inside_a_try_block_counts_for_the_binding_rule(self) -> None:
        self.assert_fails_with("guarded", "UNCLASSIFIED", "rebinding", "isqrt")

    def test_new_test_that_replaces_an_inherited_test_of_the_module_is_rebinding(self) -> None:
        found = self.assert_fails_with("override", "UNCLASSIFIED", "rebinding", "TestChild::test_shared")
        self.assertIn("from a base class", found["detail"])

    def test_new_test_in_a_subclass_of_an_imported_class_needs_collection_evidence(self) -> None:
        self.assert_fails_with(
            "imported-override", "UNCLASSIFIED", "no-collection-evidence", "TestImported::test_classify_shared",
            status="needs evidence",
        )

    def test_new_method_that_replaces_an_inherited_helper_is_rebinding(self) -> None:
        found = self.assert_fails_with("inherited-helper", "UNCLASSIFIED", "rebinding", "TestChild::expected")
        self.assertIn("binds expected", found["detail"])

    def test_new_definition_that_replaces_a_builtin_is_rebinding(self) -> None:
        found = self.assert_fails_with("builtin", "UNCLASSIFIED", "rebinding", "sum")
        self.assertIn("from the builtins", found["detail"])

    def test_fixture_decorator_through_an_import_alias_is_a_signal(self) -> None:
        found = self.assert_fails_with("alias-autouse", "UNCLASSIFIED", "signal", "skip_all")
        self.assertIn("autouse fixture skip_all", found["detail"])

    def test_fixture_name_from_an_expression_is_a_signal(self) -> None:
        found = self.assert_fails_with("computed-name", "UNCLASSIFIED", "signal", "scratch")
        self.assertIn("takes its name from an expression", found["detail"])

    def test_new_fixture_needs_collection_evidence_without_a_run(self) -> None:
        found = self.assert_fails_with(
            "plugin-fixture", "UNCLASSIFIED", "no-collection-evidence", "linecomp", status="needs evidence",
        )
        self.assertEqual(found["fixtures"], ["linecomp"])

    def test_new_xunit_function_or_method_is_a_signal(self) -> None:
        found = self.assert_fails_with("xunit", "UNCLASSIFIED", "signal", "setup_function")
        self.assertIn("xunit setup or teardown function setup_function", found["detail"])
        self.assert_fails_with("xunit-method", "UNCLASSIFIED", "signal", "TestShared::setup_method")

    def test_skip_call_in_a_new_definition_is_weakening(self) -> None:
        self.assert_fails_with("skip-helper", "WEAKENING", "skip", "offline")

    def test_attribute_write_through_an_import_alias_is_a_signal(self) -> None:
        found = self.assert_fails_with("import-alias-write", "UNCLASSIFIED", "signal", "test_patched")
        self.assertIn("non-local name core", found["detail"])

    def test_new_dunder_test_binding_is_a_skip(self) -> None:
        found = self.assert_fails_with("dunder-test", "WEAKENING", "skip", None)
        self.assertIn("__test__", found["detail"])

    def test_documentation_inside_a_product_package_is_product_code(self) -> None:
        code, data = self.static("package-doc")
        self.assertEqual(code, 1)
        self.assertEqual(data["units"][0]["product_files"], ["src/calc/template.md"])
        self.assertEqual(gate_items(data), [("WEAKENING", "removed-test", GATE + "test_classify_negative")])

    def test_conftest_and_configuration_edits(self) -> None:
        self.assertEqual(gate_items(self.static("conftest")[1]), [("UNCLASSIFIED", "conftest", None)])
        code, data = self.static("config")
        self.assertEqual(code, 1)
        self.assertEqual(gate_items(data), [("WEAKENING", "config-deselect", None)])
        self.assertEqual(data["units"][0]["product_files"], ["src/calc/core.py"])

    def test_mixed_change_that_only_adds_test_functions_passes(self) -> None:
        code, data = self.static("new-tests")
        self.assertEqual(code, 0)
        self.assertTrue(data["summary"]["passed"])
        self.assertEqual(data["units"][0]["status"], "pass")
        self.assertEqual(gate_items(data), [("SAFE", "new-test", GATE + "test_total_zero")])

    def test_test_only_change_with_only_new_tests_needs_evidence(self) -> None:
        code, data = self.static("test-only-new")
        self.assertEqual(code, 0)
        self.assertEqual(data["units"][0]["status"], "needs evidence")
        self.assertEqual(gate_items(data), [("SAFE", "new-test", GATE + "test_total_zero")])

    def test_test_only_change_needs_evidence(self) -> None:
        code, data = self.static("test-only")
        self.assertEqual(code, 0)
        unit = data["units"][0]
        self.assertFalse(unit["mixed"])
        self.assertEqual(unit["status"], "needs evidence")
        self.assertEqual(data["summary"]["needs_evidence_units"], 1)
        self.assertEqual(gate_items(data), [("WEAKENING", "expected-literal", GATE + "test_classify_negative")])

    def test_whole_range_is_one_unit_unless_per_commit(self) -> None:
        code, data = self.static("per-commit")
        self.assertEqual(code, 1)
        self.assertEqual([u["status"] for u in data["units"]], ["fail"])
        code, data = self.static("per-commit", "--per-commit")
        self.assertEqual(code, 0)
        self.assertEqual([(u["subject"], u["status"]) for u in data["units"]], [
            ("per-commit", "needs evidence"), ("product", "pass"),
        ])

    def test_item_ids_and_the_unit_diff_hash(self) -> None:
        _, data = self.static("skip")
        unit = data["units"][0]
        self.assertEqual([i["id"] for i in unit["items"]], ["u1-i1"])
        diff = git(self.repo.root, self.repo.env, "diff", "--no-color", "--no-ext-diff", "--no-renames", "--full-index",
                   "--binary", data["summary"]["merge_base"], data["summary"]["head_sha"])
        self.assertEqual(unit["diff_sha256"], hashlib.sha256(diff.encode("utf-8")).hexdigest())

    def test_gate_without_python_needs_static_only(self) -> None:
        code, data, _ = self.repo.gate("skip")
        self.assertEqual(code, 2)
        self.assertIn("--static-only", data["error"])


@needs_pytest
class GateRunTest(unittest.TestCase):
    """The gate's pytest runs in a temporary worktree: replay, collection evidence, and the new-test labels."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.repo = GateRepo.get()
        cls.before = {k: v for k, v in tree_state(cls.repo.root).items() if not k.startswith(".git")}
        cls.passing = cls.repo.run_gate("g1")
        cls.failing = cls.repo.run_gate("g2")
        cls.override = cls.repo.run_gate("imported-override")
        # -p pytester adds plugin fixtures, linecomp among them, that no test-side file defines.
        cls.plugin = cls.repo.run_gate("plugin-fixture", "-p", "pytester")
        cls.after = {k: v for k, v in tree_state(cls.repo.root).items() if not k.startswith(".git")}

    def test_mixed_change_with_new_tests_and_appended_cases_that_keep_ids_passes(self) -> None:
        code, data, stderr = self.passing
        self.assertEqual(code, 0, stderr)
        self.assertEqual(data["units"][0]["status"], "pass")
        self.assertEqual(sorted(gate_items(data)), sorted([
            ("SAFE", "appended-cases", GATE + "test_classify_cases"),
            ("SAFE", "new-test", GATE + "test_total_rejects_negative"),
            ("SAFE", "new-test", GATE + "test_total_large"),
            ("SAFE", "new-test", GATE + "test_discount_gold"),
            ("SAFE", "new-import", None),
            ("SAFE", "new-test", "tests/test_parse.py::test_parse_qty"),
        ]))

    def test_new_tests_are_labeled_by_a_run_against_the_base_product_code(self) -> None:
        labels = {entry["nodeid"]: entry["label"] for entry in self.passing[1]["new_tests"]}
        self.assertEqual(labels, {
            GATE + "test_classify_cases[7-non-negative]": "hardening",
            GATE + "test_total_rejects_negative": "catching",
            GATE + "test_total_large": "hardening",
            GATE + "test_discount_gold": "hardening",
            "tests/test_parse.py::test_parse_qty": "new-API",
        })
        listed = Path(self.passing[1]["files"]["new_tests"]).read_text(encoding="utf-8").split()
        self.assertEqual(sorted(listed), sorted(labels))

    def test_layer_1_lists_a_base_test_that_fails_against_the_head_product_code(self) -> None:
        code, data, stderr = self.failing
        self.assertEqual(code, 1, stderr)
        changed = [i for i in data["units"][0]["items"] if i["class"] == "BEHAVIOR CHANGE"]
        self.assertEqual([(i["nodeid"], i["outcome"], i["exception"]) for i in changed], [
            (GATE + "test_classify_zero", "failed", "AssertionError"),
        ])

    def test_appended_case_that_renames_an_existing_id_is_weakening(self) -> None:
        items = {i["subtype"]: i for i in self.failing[1]["units"][0]["items"]}
        self.assertEqual(items["missing-node-id"]["nodeid"], GATE + "test_double")
        self.assertEqual(items["missing-node-id"]["missing"], [GATE + "test_double[2]"])
        self.assertEqual(items["expected-literal"]["class"], "WEAKENING")
        self.assertEqual(sorted(i["class"] for i in items.values()), ["BEHAVIOR CHANGE", "WEAKENING", "WEAKENING"])

    def test_renamed_cases_are_no_new_tests(self) -> None:
        self.assertEqual(self.failing[1]["new_tests"], [])
        self.assertEqual(Path(self.failing[1]["files"]["new_tests"]).read_text(encoding="utf-8"), "")

    def test_new_test_with_a_node_id_that_the_base_collected_is_not_safe(self) -> None:
        code, data, stderr = self.override
        self.assertEqual(code, 1, stderr)
        self.assertEqual(gate_items(data), [
            ("UNCLASSIFIED", "existing-node-id", GATE + "TestImported::test_classify_shared"),
        ])
        self.assertEqual(data["new_tests"], [])

    def test_new_fixture_with_the_name_of_a_plugin_fixture_is_a_signal(self) -> None:
        code, data, stderr = self.plugin
        self.assertEqual(code, 1, stderr)
        self.assertEqual(data["units"][0]["status"], "fail")
        self.assertEqual(gate_items(data), [("UNCLASSIFIED", "signal", GATE + "linecomp")])
        self.assertIn("pytest reports at base", data["units"][0]["items"][0]["detail"])

    def test_gate_leaves_the_project_unchanged_and_removes_its_worktree(self) -> None:
        self.assertEqual(self.after, self.before)
        listing = git(self.repo.root, self.repo.env, "worktree", "list", "--porcelain")
        self.assertEqual(listing.count("worktree "), 1)
        self.assertFalse((self.repo.work / "g1" / "gate" / "worktree").exists())


# The node IDs of the new tests of g1, from the design of GateRepo.
G1_NEW_TESTS = [
    GATE + "test_classify_cases[7-non-negative]",
    GATE + "test_total_rejects_negative",
    GATE + "test_total_large",
    GATE + "test_discount_gold",
    "tests/test_parse.py::test_parse_qty",
]


@needs_pytest
class MutateReviewTest(unittest.TestCase):
    """mutate with --base and --new-tests mutates the review lines and gives each new test its admission verdict."""

    @classmethod
    def setUpClass(cls) -> None:
        repo = GateRepo.get()
        work = repo.work / "review"
        scope = work / "scope.json"
        code, _, stderr = run_cli(
            "suite", "--python", sys.executable, "--project", str(repo.root), "--work-dir", str(work),
            "--label", "scope", "--coverage-source", "calc", "--out", str(scope), env=repo.env,
        )
        assert code == 0, stderr
        new_tests = work / "new-tests.txt"
        new_tests.write_text("".join(f"{n}\n" for n in G1_NEW_TESTS), encoding="utf-8")
        output = work / "review.json"
        cls.code, _, cls.stderr = run_cli(
            "mutate", "--python", sys.executable, "--suite", str(scope), "--work-dir", str(work), "--workers", "3",
            "--base", "base", "--new-tests", str(new_tests), "--out", str(output), env=repo.env,
        )
        cls.data = json.loads(output.read_text(encoding="utf-8")) if output.is_file() else {}

    def test_mutants_stay_on_changed_lines_and_lines_only_new_tests_cover(self) -> None:
        self.assertEqual(self.code, 0, self.stderr)
        lines = {line_of(G1_CORE, s) for s in ("if qty < 0", "raise ValueError", "return price - 3", "return int(text)")}
        self.assertTrue({m["line"] for m in self.data["mutants"]} <= set(self.data["review_lines"]["src/calc/core.py"]))
        self.assertEqual({m["line"] for m in self.data["mutants"]}, lines)

    def test_admission_accepts_a_new_test_only_with_a_kill_no_existing_test_makes(self) -> None:
        verdicts = {entry["nodeid"]: entry["verdict"] for entry in self.data["admission"]}
        self.assertEqual(verdicts, {
            GATE + "test_classify_cases[7-non-negative]": "no unique kill",
            GATE + "test_total_rejects_negative": "accept",
            GATE + "test_total_large": "no unique kill",
            GATE + "test_discount_gold": "accept",
            "tests/test_parse.py::test_parse_qty": "accept",
        })
        self.assertEqual(self.data["summary"]["review"]["verdicts"], {"accept": 3, "no unique kill": 2})


class PinTest(unittest.TestCase):
    """pin records SHA-256 hashes of the requirement sources, and checks them and a quote later."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self.request = self.tmp / "request.txt"
        self.request.write_text("Make classify(0) return zero.\nKeep the other\nlabels.\n", encoding="utf-8")
        self.issue = self.tmp / "issue.txt"
        self.issue.write_text("Issue 7: zero is its own class.\n", encoding="utf-8")
        self.record = self.tmp / "pins.json"
        self.code, self.data, self.stderr = run_cli(
            "pin", "--record", str(self.record), "--source", f"request={self.request}", "--source", f"issue={self.issue}"
        )

    def test_records_the_sha256_of_each_source(self) -> None:
        self.assertEqual(self.code, 0, self.stderr)
        expected = {
            "request": hashlib.sha256(self.request.read_bytes()).hexdigest(),
            "issue": hashlib.sha256(self.issue.read_bytes()).hexdigest(),
        }
        self.assertEqual(self.data["summary"]["sha256"], expected)
        record = json.loads(self.record.read_text(encoding="utf-8"))
        self.assertEqual({s["name"]: s["text"] for s in record["sources"]}["request"], self.request.read_text())

    def test_never_overwrites_a_record(self) -> None:
        code, data, _ = run_cli("pin", "--record", str(self.record), "--source", f"request={self.request}")
        self.assertEqual(code, 2)
        self.assertIn("exists", data["error"])

    def test_check_finds_a_quote_across_line_breaks(self) -> None:
        code, data, _ = run_cli("pin", "--check", str(self.record), "--quote", "Keep the other labels.")
        self.assertEqual(code, 0)
        self.assertEqual(data["summary"]["quote_found_in"], ["request"])
        code, data, _ = run_cli("pin", "--check", str(self.record), "--quote", "Make classify(0) return None.")
        self.assertEqual(code, 1)
        self.assertEqual(data["summary"]["quote_found_in"], [])

    def test_check_fails_when_a_pinned_text_changed(self) -> None:
        record = json.loads(self.record.read_text(encoding="utf-8"))
        record["sources"][1]["text"] = "Issue 7: zero is negative.\n"
        self.record.write_text(json.dumps(record), encoding="utf-8")
        code, data, _ = run_cli("pin", "--check", str(self.record))
        self.assertEqual(code, 1)
        self.assertEqual(data["summary"]["changed"], ["issue"])


def runtime_unions(tree: ast.Module) -> list[int]:
    """Lines where `X | Y` of types is evaluated when the code runs, which needs Python 3.10."""
    postponed = any(
        isinstance(node, ast.ImportFrom) and node.module == "__future__" and any(a.name == "annotations" for a in node.names)
        for node in tree.body
    )
    evaluated = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in ("isinstance", "issubclass"):
            evaluated += node.args[1:]
        elif not postponed and isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            args = node.args
            params = [*args.posonlyargs, *args.args, *args.kwonlyargs, args.vararg, args.kwarg]
            evaluated += [p.annotation for p in params if p is not None and p.annotation is not None]
            evaluated += [node.returns] if node.returns is not None else []
        elif not postponed and isinstance(node, ast.AnnAssign):
            evaluated.append(node.annotation)
    return [
        sub.lineno for node in evaluated for sub in ast.walk(node)
        if isinstance(sub, ast.BinOp) and isinstance(sub.op, ast.BitOr)
    ]


class ScriptSyntaxTest(unittest.TestCase):
    """The scripts run on Python 3.9. Python 3.9 is not installed, so its grammar stands in."""

    def test_scripts_parse_with_the_python_3_9_grammar_and_evaluate_no_type_union(self) -> None:
        paths = sorted(SCRIPT.parent.rglob("*.py"))
        self.assertIn(SCRIPT, paths)
        for path in paths:
            with self.subTest(path=path.name):
                tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path), feature_version=(3, 9))
                self.assertEqual(runtime_unions(tree), [])


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
        self.assertEqual(fields["claude"]["version"], "1.4.0")
        self.assertEqual({k: v for k, v in fields["claude"].items() if k != "version"}, fields["codex"])

    def test_references_and_scripts_match(self) -> None:
        claude = supporting_files(HOST_SKILLS["claude"])
        codex = supporting_files(HOST_SKILLS["codex"])
        self.assertIn("references/check.md", sorted(claude))
        self.assertIn("references/speed.md", sorted(claude))
        self.assertIn("references/review.md", sorted(claude))
        self.assertIn("scripts/lt_gate.py", sorted(claude))
        self.assertIn("scripts/lt_pin.py", sorted(claude))
        self.assertIn("scripts/lean_tests.py", sorted(claude))
        self.assertEqual(sorted(claude), sorted(codex))
        for name in claude:
            self.assertEqual(claude[name], codex[name], f"{name} differs between hosts")


if __name__ == "__main__":
    unittest.main()
