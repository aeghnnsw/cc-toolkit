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
import re
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PLUGIN_ROOT / "skills" / "lean-tests" / "scripts" / "lean_tests.py"
UV_COMMAND = (
    "uv run --no-project --python '>=3.11' --with pytest --with pytest-cov "
    "python -m unittest discover -s dev-skills/tests -p 'test_lean_tests*.py'"
)
HAS_PYTEST = all(importlib.util.find_spec(name) for name in ("pytest", "pytest_cov"))
needs_pytest = unittest.skipUnless(HAS_PYTEST, f"needs pytest and pytest-cov; run: {UV_COMMAND}")
HAS_XDIST = importlib.util.find_spec("xdist") is not None
needs_xdist = unittest.skipUnless(
    HAS_PYTEST and HAS_XDIST, f"needs pytest, pytest-cov, and pytest-xdist; add --with pytest-xdist to: {UV_COMMAND}"
)

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


HISTORY_FILE = "tests/test_history.py"
HISTORY_PLAIN = "def test_plain():\n    assert 1 + 1 == 2\n"
HISTORY_NEGATIVE = "\n\ndef test_negative():\n    assert -1 < 0\n"


class ScanGitHistoryTest(unittest.TestCase):
    """scan --git-history reads the subject of the commit that added each test.

    Commit "add tests" adds test_plain, commit "fix #12" adds test_negative,
    and a later commit with a protection word changes the def line of
    test_plain: the oldest commit decides.
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = tempfile.TemporaryDirectory()
        tmp = Path(cls._tmp.name)
        cls.root = tmp / "proj"
        cls.env = git_env(tmp)
        test_file = cls.root / HISTORY_FILE
        test_file.parent.mkdir(parents=True)
        git(cls.root, cls.env, "init", "-q")
        steps = (
            ("add tests", HISTORY_PLAIN),
            ("fix #12", HISTORY_PLAIN + HISTORY_NEGATIVE),
            ("fix a typing regression", (HISTORY_PLAIN + HISTORY_NEGATIVE).replace("test_plain()", "test_plain() -> None")),
        )
        for subject, text in steps:
            test_file.write_text(text, encoding="utf-8")
            git(cls.root, cls.env, "add", HISTORY_FILE)
            git(cls.root, cls.env, "commit", "-q", "-m", subject)
        cls.nodeids = tmp / "nodeids.txt"
        cls.nodeids.write_text(f"{HISTORY_FILE}::test_plain\n{HISTORY_FILE}::test_negative\n", encoding="utf-8")
        cls.scan = ("scan", "--project", str(cls.root), "--node-ids", str(cls.nodeids))

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tmp.cleanup()

    def test_subject_of_the_commit_that_added_a_test_protects_it(self) -> None:
        code, data, stderr = run_cli(*self.scan, "--git-history", env=self.env)
        self.assertEqual(code, 0, stderr)
        commit = [f for f in data["findings"] if f["detail"].startswith("commit: ")]
        self.assertEqual(
            {(f["nodeid"], f["code"], f["detail"], f["subject"]) for f in commit},
            {
                (f"{HISTORY_FILE}::test_negative", "protected", "commit: #12", "fix #12"),
                (f"{HISTORY_FILE}::test_negative", "protected", "commit: fix", "fix #12"),
            },
        )
        self.assertEqual(data["summary"]["git_history"], {"files": 1, "tests_not_in_history": 0})

    def test_without_the_flag_the_scan_reads_no_history(self) -> None:
        code, data, stderr = run_cli(*self.scan, env=self.env)
        self.assertEqual(code, 0, stderr)
        self.assertEqual([f for f in data["findings"] if f["detail"].startswith("commit: ")], [])
        self.assertIsNone(data["summary"]["git_history"])

    def test_project_outside_a_git_work_tree_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "proj"
            shutil.copytree(self.root / "tests", root / "tests")
            code, data, _ = run_cli(
                "scan", "--project", str(root), "--node-ids", str(self.nodeids), "--git-history", env=git_env(Path(tmp))
            )
        self.assertEqual(code, 2)
        self.assertIn("Git work tree", data["error"])

    def test_missing_git_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as empty:
            code, data, _ = run_cli(*self.scan, "--git-history", env={**self.env, "PATH": empty})
        self.assertEqual(code, 2)
        self.assertIn("cannot run git", data["error"])


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


class XdistOptionTest(unittest.TestCase):
    """suite and mutate find the pytest-xdist options that can start workers."""

    def test_finds_each_option_shape_and_skips_options_that_start_no_worker(self) -> None:
        has_xdist_option = import_script("lt_suite").has_xdist_option
        cases = [
            (["-n", "2"], True), (["-n4"], True), (["-n=auto"], True), (["--numprocesses", "auto"], True),
            (["--numprocesses=2"], True), (["--dist", "loadscope"], True), (["-d", "--tx", "popen"], True),
            (["--tx=2*popen"], True), (["-p", "xdist"], True), (["-pxdist"], True),
            (["-n", "0"], False), (["-n0"], False), (["--numprocesses=0"], False), (["--dist=no"], False),
            (["-p", "no:xdist"], False), (["-p", "no:randomly", "-q", "--strict-markers"], False), ([], False),
        ]
        for args, found in cases:
            self.assertEqual(has_xdist_option(args), found, args)


XDIST_FILES = {
    "pyproject.toml": """\
        [tool.pytest.ini_options]
        addopts = "-n 2"
        pythonpath = ["src"]
        """,
    "src/pkg/__init__.py": """\
        def f(x):
            return x + 1
        """,
    "tests/test_f.py": """\
        import os

        from pkg import f


        def test_f():
            assert f(1) == 2


        def test_in_one_process():
            assert "PYTEST_XDIST_WORKER" not in os.environ
        """,
}
XDIST_TESTS = ["tests/test_f.py::test_f", "tests/test_f.py::test_in_one_process"]


@needs_xdist
class XdistTest(unittest.TestCase):
    """A run whose order matters adds -n 0 when the project's pytest options start pytest-xdist workers.

    The project's addopts set -n 2. test_in_one_process fails in a
    pytest-xdist worker.
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = tempfile.TemporaryDirectory()
        tmp = Path(cls._tmp.name)
        cls.root = tmp / "proj"
        cls.work = tmp / "work"
        for name, text in XDIST_FILES.items():
            path = cls.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(textwrap.dedent(text), encoding="utf-8")
        cls.common = ("suite", "--python", sys.executable, "--project", str(cls.root), "--work-dir", str(cls.work))
        cls.scope = cls.work / "scope.json"
        cls.reversed = run_cli(
            *cls.common, "--label", "scope", "--reverse", "--coverage-source", "pkg", "--out", str(cls.scope)
        )

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tmp.cleanup()

    def test_reversed_run_adds_n_0_and_names_the_source(self) -> None:
        code, printed, stderr = self.reversed
        self.assertEqual(code, 0, stderr)
        data = json.loads(self.scope.read_text(encoding="utf-8"))
        self.assertEqual(data["command"][-2:], ["-n", "0"])
        self.assertEqual(printed["summary"]["xdist_off"], ["addopts"])
        self.assertEqual(data["collected"], XDIST_TESTS[::-1])
        self.assertEqual(data["summary"]["counts"]["passed"], 2, data["log_tail"])

    def test_pytest_addopts_is_a_source_too(self) -> None:
        env = {**os.environ, "PYTEST_ADDOPTS": "--dist load"}
        code, data, stderr = run_cli(*self.common, "--label", "env", "--reverse", env=env)
        self.assertEqual(code, 0, stderr)
        self.assertEqual(data["summary"]["xdist_off"], ["addopts", "PYTEST_ADDOPTS"])
        self.assertEqual(data["summary"]["counts"]["passed"], 2, data["log_tail"])

    def test_file_order_run_keeps_the_project_workers(self) -> None:
        code, data, stderr = run_cli(*self.common, "--label", "plain")
        self.assertEqual(code, 0, stderr)
        self.assertEqual(data["summary"]["xdist_off"], [])
        self.assertNotEqual(data["command"][-2:], ["-n", "0"])
        self.assertEqual(by_nodeid(data)["tests/test_f.py::test_in_one_process"]["outcome"], "failed")

    def test_mutate_runs_each_copy_in_one_process(self) -> None:
        code, data, stderr = run_cli(
            "mutate", "--python", sys.executable, "--suite", str(self.scope), "--work-dir", str(self.work),
            "--workers", "1",
        )
        self.assertEqual(code, 0, stderr)
        summary = data["summary"]
        self.assertEqual(summary["xdist_off"], ["addopts"])
        # In a pytest-xdist worker, test_in_one_process would fail in the unchanged copy and be excluded.
        self.assertEqual((summary["tests"], summary["excluded"]), (2, 0), data["excluded"])
        self.assertTrue(summary["complete"], summary["incomplete_reason"])


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
    """The killed-set check reruns the killed set against the tests that remain after a removal batch.

    It also checks the prune limits of the batch: the batch size, the class of
    each removed test, and the excluded and protected tests.
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.m = Mutation.get()
        cls.scan = cls.m.tmp / "scope-scan.json"
        if not cls.scan.is_file():
            code, _, stderr = run_cli("scan", "--suite", str(cls.m.scope), "--out", str(cls.scan))
            assert code == 0, stderr

    def recheck(self, text: str, matrix: Path | None = None, scan: Path | None = None) -> dict:
        """Run the scope with `text` as tests/test_shop.py, then the killed-set check of the matrix."""
        m = self.m
        tmp = Path(tempfile.mkdtemp(dir=m.tmp))
        root = tmp / "shop"
        shutil.copytree(m.root, root)
        (root / "tests" / "test_shop.py").write_text(text, encoding="utf-8")
        env = shop_env(root)
        after = tmp / "after.json"
        code, _, stderr = run_cli(
            "suite", "--python", sys.executable, "--project", str(root), "--work-dir", str(tmp / "work"),
            "--label", "after", "--out", str(after), env=env,
        )
        self.assertEqual(code, 0, stderr)
        before = tree_state(root)
        code, data, stderr = m.mutate(
            "--recheck", str(matrix or m.matrix), "--scan", str(scan or self.scan), suite=after, env=env
        )
        self.assertEqual(code, 0, stderr)
        self.assertEqual(tree_state(root), before)
        return data

    def edited(self, name: str, data: dict) -> Path:
        path = Path(tempfile.mkdtemp(dir=self.m.tmp)) / name
        path.write_text(json.dumps(data), encoding="utf-8")
        return path

    def test_removing_a_test_with_a_unique_kill_fails(self) -> None:
        m = self.m
        data = self.recheck(without_test(MUTATE_TESTS, "test_classify_zero"))
        summary = data["summary"]
        self.assertTrue(summary["complete"], summary["incomplete_reason"])
        self.assertFalse(summary["passed"])
        lost = [mutant["id"] for mutant in data["lost"]]
        self.assertEqual(sorted(lost), sorted(m.tests[SHOP + "test_classify_zero"]["unique"]))
        self.assertIn(m.mutant("if n < 0", "if n <= 0:  # sign check")["id"], lost)
        self.assertEqual(summary["lost"], len(lost))
        self.assertEqual(data["lost"][0]["killed_before_by"], [SHOP + "test_classify_zero"])

    def test_removing_a_true_duplicate_passes(self) -> None:
        m = self.m
        data = self.recheck(without_test(MUTATE_TESTS, "test_classify_negative_copy"))
        summary = data["summary"]
        self.assertTrue(summary["complete"], summary["incomplete_reason"])
        self.assertTrue(summary["passed"])
        self.assertEqual((data["lost"], summary["reasons"]), ([], []))
        self.assertEqual((summary["tests"], summary["removed"]), (9, 1))
        self.assertEqual(summary["still_killed"], summary["killed_set"])
        self.assertEqual(summary["killed_set"], m.data["summary"]["killed"])
        count = summary["killed_set"]
        self.assertEqual(summary["commit_line"], f"Killed-set check: {count} of {count} mutants still killed.")

    def test_removing_a_test_of_a_keep_class_fails(self) -> None:
        # test_cart_repr kills no mutant, so no mutant is lost, but it is unmeasured.
        data = self.recheck(without_test(MUTATE_TESTS, "test_cart_repr"))
        summary = data["summary"]
        self.assertEqual(summary["lost"], 0)
        self.assertFalse(summary["passed"])
        self.assertIsNone(summary["commit_line"])
        self.assertEqual(summary["reasons"], ["1 removed tests have a class other than empty or subsumed"])
        self.assertEqual(summary["examples"]["keep_class"], [SHOP + "test_cart_repr (unmeasured)"])

    def test_removing_an_excluded_test_fails(self) -> None:
        tautology = SHOP + "test_total_tautology"
        matrix = json.loads(self.m.matrix.read_text(encoding="utf-8"))
        matrix["tests"] = [test for test in matrix["tests"] if test["nodeid"] != tautology]
        matrix["excluded"].append({"nodeid": tautology, "run": "suite", "outcome": "failed"})
        data = self.recheck(without_test(MUTATE_TESTS, "test_total_tautology"), matrix=self.edited("matrix.json", matrix))
        summary = data["summary"]
        self.assertFalse(summary["passed"])
        self.assertEqual(summary["reasons"], ["1 removed or merged tests are in the excluded list of the matrix"])
        self.assertEqual(summary["examples"]["excluded"], [tautology])

    def test_removing_a_protected_test_fails(self) -> None:
        tautology = SHOP + "test_total_tautology"
        scan = json.loads(self.scan.read_text(encoding="utf-8"))
        scan["findings"].append(
            {"code": "protected", "nodeid": tautology, "file": "tests/test_shop.py", "line": 1, "detail": "fix #12"}
        )
        data = self.recheck(without_test(MUTATE_TESTS, "test_total_tautology"), scan=self.edited("scan.json", scan))
        summary = data["summary"]
        self.assertEqual(summary["lost"], 0)
        self.assertFalse(summary["passed"])
        self.assertEqual(summary["reasons"], ["1 removed or merged tests have a protected scan finding"])
        self.assertEqual(summary["examples"]["protected"], [f"{tautology}: fix #12"])

    def test_merging_a_test_into_its_retained_test_passes(self) -> None:
        # The merged test keeps the name of the retained test, test_classify_zero, whose class is unique.
        text = "import pytest\n" + without_test(MUTATE_TESTS, "test_classify_negative_copy").replace(
            'def test_classify_zero():\n    assert classify(0) == "non-negative"',
            '@pytest.mark.parametrize("n, expected", [(0, "non-negative"), (-1, "negative")])\n'
            "def test_classify_zero(n, expected):\n    assert classify(n) == expected",
        )
        data = self.recheck(text)
        summary = data["summary"]
        self.assertTrue(summary["passed"], summary["reasons"])
        self.assertEqual((summary["removed"], summary["merged"]), (1, 1))
        [merged] = data["merged"]
        self.assertEqual((merged["nodeid"], len(merged["into"])), (SHOP + "test_classify_zero", 2))
        self.assertEqual([entry["nodeid"] for entry in data["removed"]], [SHOP + "test_classify_negative_copy"])

    def test_recheck_needs_the_scan_of_the_prune_scope(self) -> None:
        code, data, _ = self.m.mutate("--recheck", str(self.m.matrix))
        self.assertEqual(code, 2)
        self.assertIn("--scan", data["error"])
        scan = json.loads(self.scan.read_text(encoding="utf-8"))
        scan["summary"]["nodeids"] = 3
        code, data, _ = self.m.mutate("--recheck", str(self.m.matrix), "--scan", str(self.edited("scan.json", scan)))
        self.assertEqual(code, 2)
        self.assertIn("scan the suite output of the prune scope", data["error"])


class RemovalCheckTest(unittest.TestCase):
    """The prune limits of a removal batch, from the matrix, the collected tests, and the scan of the scope."""

    @classmethod
    def setUpClass(cls) -> None:
        module = import_script("lt_mutate")
        cls.check = staticmethod(module.removal_check)
        cls.load_previous = staticmethod(module.load_previous)
        cls.usage_error = import_script("lt_common").UsageError

    def matrix(self, classes: dict, excluded: tuple = ()) -> dict:
        return {
            "tests": [{"nodeid": nodeid, "class": name} for nodeid, name in classes.items()],
            "excluded": [{"nodeid": nodeid, "run": "suite", "outcome": "failed"} for nodeid in excluded],
        }

    def scan(self, protected: tuple = (), unresolved: tuple = ()) -> dict:
        return {
            "findings": [
                {"code": "protected", "nodeid": n, "file": "tests/test_x.py", "line": 1, "detail": "issue #7"}
                for n in protected
            ],
            "unresolved": [{"nodeid": n, "reason": "syntax error"} for n in unresolved],
        }

    def test_more_than_twenty_removed_tests_fail_and_a_committed_batch_does_not_count(self) -> None:
        tests = [f"tests/test_x.py::test_{number}" for number in range(22)]
        matrix = self.matrix(dict.fromkeys(tests, "empty"))
        within = self.check(matrix, tests[20:], self.scan(), set())
        self.assertEqual((len(within["batch"]), within["reasons"]), (20, []))
        over = self.check(matrix, tests[21:], self.scan(), set())
        self.assertEqual(over["reasons"], ["21 tests removed in this batch, more than the batch size of 20"])
        self.assertEqual(over["examples"]["removed"], tests[:5])
        # A committed batch of the same matrix removed the first 15 tests, so this batch removes 6.
        later = self.check(matrix, tests[21:], self.scan(), set(tests[:15]))
        self.assertEqual((later["batch"], later["reasons"]), (tests[15:21], []))

    def test_a_merge_keeps_its_retained_test_and_each_other_missing_test_is_removed(self) -> None:
        u, v, t = "tests/test_x.py::test_u", "tests/test_x.py::test_v", "tests/test_x.py::test_t"
        matrix = self.matrix({u: "unique", v: "subsumed", f"{t}[1]": "union-only", f"{t}[2]": "union-only"})
        merge = self.check(matrix, [f"{u}[a]", f"{u}[b]", f"{t}[1]", f"{t}[2]"], self.scan(), set())
        self.assertEqual(([e["nodeid"] for e in merge["merged"]], merge["batch"], merge["reasons"]), ([u], [v], []))
        cases = {
            "a renamed test with no new case": ([f"{u}[a]", v, f"{t}[1]", f"{t}[2]"], [f"{u} (unique)"]),
            "a removed case": ([u, v, f"{t}[1]"], [f"{t}[2] (union-only)"]),
            "fewer cases with new IDs": ([u, v, f"{t}[x]"], [f"{t}[1] (union-only)", f"{t}[2] (union-only)"]),
        }
        for name, (collected, keep) in cases.items():
            with self.subTest(name):
                result = self.check(matrix, collected, self.scan(), set())
                self.assertEqual(result["merged"], [])
                self.assertEqual(result["examples"]["keep_class"], keep)

    def test_excluded_protected_and_unresolved_tests_fail_also_when_merged(self) -> None:
        a, b, c, d = (f"tests/test_x.py::test_{name}" for name in "abcd")
        matrix = self.matrix({b: "empty", c: "empty", d: "unique"}, excluded=(a,))
        result = self.check(matrix, [f"{d}[1]", f"{d}[2]"], self.scan(protected=(b, d), unresolved=(c,)), set())
        self.assertEqual([e["nodeid"] for e in result["merged"]], [d])
        self.assertEqual(result["examples"]["excluded"], [a])
        self.assertEqual(result["examples"]["protected"], [f"{b}: issue #7", f"{d}: issue #7"])
        self.assertEqual(result["examples"]["protection_unknown"], [f"{c}: syntax error"])
        self.assertEqual((len(result["reasons"]), result["examples"]["keep_class"]), (3, []))

    def test_previous_check_must_be_a_passed_check_of_the_same_matrix(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "recheck-1.json"

            def write(passed: bool, matrix: str) -> None:
                path.write_text(json.dumps({
                    "summary": {"mode": "recheck", "passed": passed}, "matrix": matrix, "removed": [{"nodeid": "t1"}],
                }), encoding="utf-8")

            write(True, "/w/matrix.json")
            self.assertEqual(self.load_previous(str(path), "/w/matrix.json"), {"t1"})
            for passed, matrix in ((False, "/w/matrix.json"), (True, "/w/other.json")):
                write(passed, matrix)
                with self.subTest(passed=passed, matrix=matrix), self.assertRaises(self.usage_error):
                    self.load_previous(str(path), "/w/matrix.json")


SCORE_A1, SCORE_A2 = "tests/test_a.py::test_a1", "tests/test_a.py::test_a2"
SCORE_B1, SCORE_B2 = "tests/test_b.py::test_b1", "tests/test_b.py::test_b2"
IMPORT_TIMES = """\
import time: self [us] | cumulative | imported package
import time:       100 |        100 |   _io
import time:      2000 |       5000 | site
import time:      3000 |       3000 |     pkg.util
import time:      4000 |       9000 |   pkg.core
import time:      1000 |       1000 |   json
import time:      2000 |      12000 | pkg
"""


def score_finding(code: str, nodeid: str) -> dict:
    return {"code": code, "nodeid": nodeid, "file": nodeid.split("::")[0], "line": 1, "detail": ""}


def score_inputs() -> dict:
    """The check outputs of a fast, passing suite. tests/test_b.py has more candidates, but they are protected."""
    run = {
        "pytest_exit_code": 0, "timed_out": False, "wall_seconds": 3.5, "collection_seconds": 0.4, "collected": 4,
        "counts": {"passed": 4, "failed": 0}, "files_written": [],
        "slowest": {"call": [{"nodeid": SCORE_A1, "seconds": 1.5}], "setup": [], "teardown": []},
    }
    return {
        "run1.json": {"summary": {**run, "label": "run1", "coverage": False}, "tests": []},
        "run2.json": {"summary": {**run, "label": "run2", "coverage": True, "files_written": ["?? report.txt"]}},
        "compare.json": {
            "summary": {"missing": 0, "added": 0}, "changed": [], "missing": [], "added": [],
            "not_run": {"first": [], "second": []},
        },
        "scan.json": {
            "summary": {}, "duplicate_groups": [], "unresolved": [],
            "findings": [
                score_finding("no-assertion", SCORE_A1), score_finding("no-assertion", SCORE_B1),
                score_finding("protected", SCORE_B1), score_finding("tautology", SCORE_B2),
                score_finding("protected", SCORE_B2),
            ],
        },
        "coverage.json": {
            "summary": {}, "equal_groups": [], "unmeasured": [],
            "strict_subsets": [{"test": SCORE_A2 + "[1]", "supersets": [SCORE_A1]}],
            "diff": {
                "base": "main", "executed": 4, "executable": 4, "missed": 0, "percent": 100.0, "files": [],
                "unmeasured_files": [], "unparsed": [],
            },
        },
        "growth.txt": "",
        "end-state.txt": "0a1\n> ?? report.txt\n",
    }


class ScorecardTest(unittest.TestCase):
    """scorecard builds the check scorecard and its one next mode from the files in a check work directory."""

    def scorecard(self, inputs: dict, *args: str) -> tuple[dict, dict]:
        """The scorecard output and its rows by name."""
        with tempfile.TemporaryDirectory() as tmp:
            for name, content in inputs.items():
                text = content if isinstance(content, str) else json.dumps(content)
                (Path(tmp) / name).write_text(text, encoding="utf-8")
            code, data, stderr = run_cli("scorecard", "--work-dir", tmp, *args)
        self.assertEqual(code, 0, stderr)
        return data, {row["row"]: row["value"] for row in data["rows"]}

    def test_missing_inputs_are_not_measured_and_no_rule_claims_a_clean_suite(self) -> None:
        data, rows = self.scorecard({})
        self.assertEqual(len(rows), 18)
        self.assertEqual([name for name, value in rows.items() if not value.startswith("not measured")], [])
        self.assertEqual(data["summary"]["not_measured"], list(rows))
        mode = data["summary"]["next_mode"]
        self.assertEqual(mode["mode"], "check")
        self.assertIn("not measured: run 1, diff coverage, the scan", mode["reason"])
        markdown = data["summary"]["markdown"]
        self.assertEqual(markdown[:2], ["| Row | Value |", "| --- | --- |"])
        self.assertEqual(markdown[-1], f"Next mode: check again after the next change. {mode['reason']}")

    def test_next_mode_is_the_first_rule_that_applies(self) -> None:
        def changed(**edits) -> dict:
            inputs = json.loads(json.dumps(score_inputs()))
            for path, value in edits.items():
                name, *keys = path.split("__")
                target = inputs[name + ".json"]
                for key in keys[:-1]:
                    target = target[key]
                target[keys[-1]] = value
            return inputs

        missed = [{"path": "src/m.py", "missed": [3, 7], "raise": {"missed": [7]}, "except": {"missed": []}}]
        cases = {
            "unprotected candidates": (changed(), (), "prune", "tests/test_a.py has the most unprotected candidates: 2"),
            "missed changed lines": (
                changed(coverage__diff__missed=2, coverage__diff__files=missed), (), "review", "src/m.py:3, src/m.py:7",
            ),
            "a changed outcome": (
                changed(compare__changed=[{"nodeid": SCORE_B1, "first": "passed", "second": "failed"}], **{
                    "coverage__diff__missed": 2, "coverage__diff__files": missed,
                }), (), "speed", f"1 tests changed their outcome between the runs: {SCORE_B1}",
            ),
            "a slow run 1": (changed(run1__summary__wall_seconds=200.0), (), "speed", "hand-off budget of 120 s"),
            "a slow run 1 within a larger budget": (
                changed(run1__summary__wall_seconds=200.0), ("--hand-off-budget", "300"), "prune", "tests/test_a.py",
            ),
            "only protected tests": (
                changed(scan__findings=score_inputs()["scan.json"]["findings"][1:], coverage__strict_subsets=[]),
                (), "check", "the suite needs no lean-tests work now",
            ),
        }
        for name, (inputs, args, mode, reason) in cases.items():
            with self.subTest(name):
                data, _ = self.scorecard(inputs, *args)
                found = data["summary"]["next_mode"]
                self.assertEqual(found["mode"], mode, found["reason"])
                self.assertIn(reason, found["reason"])
        data, _ = self.scorecard(changed())
        self.assertEqual(data["summary"]["next_mode"]["request"], "prune the tests in tests/test_a.py")
        self.assertIn('ask, for example, "prune the tests in tests/test_a.py"', data["summary"]["markdown"][-1])

    def test_a_timed_out_run_1_leaves_the_later_rows_not_measured(self) -> None:
        inputs = score_inputs()
        inputs["run1.json"]["summary"]["timed_out"] = True
        for name in ("run2.json", "compare.json", "coverage.json"):
            del inputs[name]
        data, rows = self.scorecard(inputs)
        self.assertEqual(data["summary"]["next_mode"]["mode"], "speed")
        for name in ("Flaky or order-dependent", "Coverage-subset candidates", "Diff coverage against `<base>`"):
            self.assertEqual(rows[name], "not measured: run 1 exceeded the check budget", name)

    def test_rows_give_values_examples_and_missing_packages(self) -> None:
        inputs = score_inputs()
        inputs["run2.json"]["summary"]["coverage"] = False
        del inputs["coverage.json"]
        inputs["importtime-pkg.txt"] = IMPORT_TIMES
        inputs["importtime-broken.txt"] = "Traceback (most recent call last):\nModuleNotFoundError: No module named 'broken'\n"
        _, rows = self.scorecard(inputs)
        self.assertEqual(rows["Tests collected"], "4")
        self.assertEqual(rows["Import cost"], (
            "broken not measured: the import failed: ModuleNotFoundError: No module named 'broken'; "
            "pkg 12 ms; largest imports: pkg.core 9 ms, pkg.util 3 ms, json 1 ms"
        ))
        self.assertEqual(rows["No assertion"], f"2 tests: {SCORE_A1}, {SCORE_B1}")
        self.assertEqual(rows["Unmeasured tests"], "not measured: run 2 has no coverage contexts; needs pytest-cov")
        self.assertEqual(rows["Instructions that force test growth"], "none")
        self.assertEqual(rows["Files the tests wrote"], "1 lines: > ?? report.txt (run2)")


@needs_pytest
class ScorecardRunTest(unittest.TestCase):
    """scorecard reads the outputs that suite, compare, scan, and coverage write."""

    def test_scorecard_of_the_fixture_runs_recommends_speed_for_the_order_dependent_test(self) -> None:
        runs = Runs.get()
        contexts = runs.run2[1]["files"]["coverage_json"]
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            for label in ("run1", "run2"):
                shutil.copy(runs.output(label), work / f"{label}.json")
            for args in (
                ("compare", runs.output("run1"), runs.output("run2")),
                ("scan", "--suite", runs.output("run1")),
                ("coverage", "--contexts", contexts, "--suite", runs.output("run2"), "--base", "HEAD~1"),
            ):
                code, _, stderr = run_cli(*args, "--out", str(work / f"{args[0]}.json"))
                self.assertEqual(code, 0, stderr)
            code, data, stderr = run_cli("scorecard", "--work-dir", tmp)
        self.assertEqual(code, 0, stderr)
        rows = {row["row"]: row["value"] for row in data["rows"]}
        order = "tests/test_order.py::test_order_second_reads"
        self.assertEqual(rows["Tests collected"], str(len(NODEIDS)))
        self.assertIn(f"{order} (passed -> failed)", rows["Flaky or order-dependent"])
        self.assertIn("2 missed, 1 raise and 1 except lines among them", rows["Diff coverage against `<base>`"])
        self.assertEqual(
            data["summary"]["not_measured"], ["Import cost", "Instructions that force test growth", "Files the tests wrote"]
        )
        mode = data["summary"]["next_mode"]
        self.assertEqual(mode["mode"], "speed")
        self.assertIn(order, mode["reason"])


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
    """Every mutant that a candidate kills stays killed by a staying test.

    This assumes that each staying test runs and passes, with the same kills,
    in the hand-off tier.
    """

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
            scan = Path(tmp) / "scan.json"
            scan.write_text(json.dumps({"summary": {"nodeids": 0}, "findings": [], "unresolved": []}), encoding="utf-8")
            code, data, _ = run_cli(
                "mutate", "--python", sys.executable, "--suite", str(suite), "--recheck", str(matrix),
                "--scan", str(scan), "--work-dir", str(Path(tmp) / "work"),
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


CHANGED_PYPROJECT = """\
[project]
name = "pkg"
version = "1.0"

[dependency-groups]
dev = ["pytest"]

[tool.pytest.ini_options]
testpaths = ["tests"]
"""
CHANGED_BASE = {
    "pyproject.toml": CHANGED_PYPROJECT,
    "uv.lock": "version = 1\n",
    "CLAUDE.md": "# Project\n",
    "tox.ini": "[tox]\nenv_list = py\n",
    "README.md": "# pkg\n",
    ".github/workflows/tests.yml": "on: push\n",
    "src/pkg/__init__.py": "def f(x):\n    return x + 1\n",
    "tests/test_f.py": "from pkg import f\n\n\ndef test_f():\n    assert f(1) == 2\n",
    "tests/test_g.py": "def test_g():\n    assert True\n",
}
# Each step is one commit: the changes that speed may make, then changes that it may not make.
CHANGED_STEPS = {
    "speed": {
        "tests/test_f.py": CHANGED_BASE["tests/test_f.py"] + "\n\ndef test_f_zero():\n    assert f(0) == 1\n",
        "tests/conftest.py": "import pytest\n",
        "pyproject.toml": CHANGED_PYPROJECT.replace('["pytest"]', '["pytest", "pytest-xdist"]')
        + 'addopts = "--strict-markers"\n\n[tool.uv]\npackage = false\n',
        "uv.lock": "version = 1\n# pytest-xdist\n",
        "CLAUDE.md": "# Project\n\n## Tests\n\nRun `uv run pytest -n auto`.\n",
        "tox.ini": "[tox]\nenv_list = py\n\n[testenv]\nset_env = COVERAGE_CORE=sysmon\n",
    },
    "workflow": {
        ".github/workflows/tests.yml": "on: [push, pull_request]\n",
        ".github/workflows/test_matrix.yml": "on: push\n",
    },
    # setUpClass also changes the version in pyproject.toml.
    "product": {"src/pkg/__init__.py": "def f(x):\n    return x + 2\n", "README.md": "# pkg\n\nMore text.\n"},
    "other-test": {"tests/test_g.py": "def test_g():\n    assert 1\n"},
}


class ChangedFilesTest(unittest.TestCase):
    """changed-files fails on a changed file that a speed or prune run may not change."""

    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = tempfile.TemporaryDirectory()
        tmp = Path(cls._tmp.name)
        cls.root = tmp / "proj"
        cls.env = git_env(tmp)
        git(cls.root.parent, cls.env, "init", "-q", str(cls.root))
        cls.commits = {"base": cls.commit("base", CHANGED_BASE)}
        for step, files in CHANGED_STEPS.items():
            if step == "product":
                pyproject = (cls.root / "pyproject.toml").read_text(encoding="utf-8")
                files = {**files, "pyproject.toml": pyproject.replace('version = "1.0"', 'version = "1.1"')}
            cls.commits[step] = cls.commit(step, files)

    @classmethod
    def commit(cls, subject: str, files: dict) -> str:
        for name, text in files.items():
            path = cls.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        git(cls.root, cls.env, "add", *files)
        git(cls.root, cls.env, "commit", "-q", "-m", subject)
        return git(cls.root, cls.env, "rev-parse", "HEAD").strip()

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tmp.cleanup()

    def check(self, base: str, head: str, *args: str) -> tuple[int, dict, dict]:
        code, data, stderr = run_cli(
            "changed-files", "--project", str(self.root), "--base", self.commits[base], "--head", self.commits[head],
            *args, env=self.env,
        )
        self.assertIn(code, (0, 1), stderr)
        return code, data, {entry["path"]: entry["class"] for entry in data["files"]}

    def test_changes_that_speed_may_make_pass(self) -> None:
        code, data, classes = self.check("base", "speed")
        self.assertEqual(code, 0, data["failures"])
        self.assertTrue(data["summary"]["passed"])
        self.assertEqual(classes, {
            "tests/test_f.py": "test", "tests/conftest.py": "test", "pyproject.toml": "allowed",
            "uv.lock": "allowed", "CLAUDE.md": "allowed", "tox.ini": "allowed",
        })

    def test_workflow_files_fail_also_with_a_test_file_name(self) -> None:
        code, data, classes = self.check("speed", "workflow")
        self.assertEqual(code, 1)
        self.assertFalse(data["summary"]["passed"])
        self.assertEqual(classes, {".github/workflows/tests.yml": "ci", ".github/workflows/test_matrix.yml": "ci"})

    def test_product_changes_fail_with_the_changed_section_of_a_mixed_file(self) -> None:
        code, data, classes = self.check("workflow", "product")
        self.assertEqual(code, 1)
        self.assertEqual(classes, {"src/pkg/__init__.py": "product", "pyproject.toml": "product", "README.md": "product"})
        [pyproject] = [entry for entry in data["failures"] if entry["path"] == "pyproject.toml"]
        self.assertEqual(pyproject["detail"], "changed sections: [project]")

    def test_path_fails_on_a_changed_file_outside_it(self) -> None:
        code, data, classes = self.check("product", "other-test", "--path", "tests/test_f.py")
        self.assertEqual(code, 1)
        self.assertEqual(classes, {"tests/test_g.py": "outside-path"})
        code, data, _ = self.check("product", "other-test", "--path", "tests")
        self.assertEqual(code, 0, data["failures"])

    def test_project_outside_a_git_work_tree_is_an_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            code, data, _ = run_cli("changed-files", "--project", tmp, "--base", "HEAD", env=git_env(Path(tmp)))
        self.assertEqual(code, 2)
        self.assertIn("Git work tree", data["error"])


class CiWordTest(unittest.TestCase):
    """lean-tests names CI only in safety rule 7, so that no mode suggests a change to it."""

    def test_ci_appears_only_in_safety_rule_7(self) -> None:
        for host in ("skills", "codex-skills", "antigravity-skills"):
            skill = PLUGIN_ROOT / host / "lean-tests"
            text = (skill / "SKILL.md").read_text(encoding="utf-8")
            rule = re.search(r"^7\. Leave the CI .*?(?=\n\n)", text, re.MULTILINE | re.DOTALL)
            self.assertIsNotNone(rule, host)
            self.assertNotRegex(text[:rule.start()] + text[rule.end():], r"\bCI\b", host)
            for reference in sorted((skill / "references").glob("*.md")):
                self.assertNotRegex(reference.read_text(encoding="utf-8"), r"\bCI\b", str(reference))


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


if __name__ == "__main__":
    unittest.main()
