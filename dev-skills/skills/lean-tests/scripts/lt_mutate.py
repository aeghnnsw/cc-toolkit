"""mutate: the full kill matrix of a prune scope, and the killed-set check after a removal batch.

Imported by lean_tests.py; never run directly. A standard-library AST
mutator puts one small fault at a time into the product modules that the
in-scope tests cover. Each mutant runs against every in-scope test in one
pytest run, in a temporary copy of the project, so the project never
changes. Coverage contexts only choose the modules and lines and label the
unmeasured tests; the kill matrix is the evidence.
"""

from __future__ import annotations

import ast
import bisect
import codecs
import hashlib
import io
import itertools
import math
import os
import queue
import shutil
import time
import tokenize
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import NamedTuple

from lt_common import EXAMPLES, PARSE_ERRORS, UsageError, load_json, node_file, parse_failure, rel, suite_node_ids, tail
from lt_coverage import lines_by_test, product_files, ran_tests, unmeasured_tests
from lt_suite import (
    failure, interpreter, load_suite, probe, pytest_env, read_records, run_pytest, test_entries, version_tuple,
)

DEFAULT_BUDGET = 1800.0
DEFAULT_WORKERS = max(1, (os.cpu_count() or 2) - 1)
TIMEOUT_FLOOR = 10.0
TIMEOUT_FACTOR = 3.0
PER_LINE = 3
LOG_TAIL = 30
SANITY = b'\nraise RuntimeError("lean-tests sanity mutant")\n'
SKIP_NAMES = frozenset({
    ".git", ".hg", ".svn", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".tox", ".nox",
    "node_modules",
})
# Failures of a check: assert, unittest and mock assert methods, pytest.fail, and pytest.raises without a raise.
CHECK_FAILURES = frozenset({"AssertionError", "Failed"})
CLASSES = ("unique", "subsumed", "union-only", "empty", "unmeasured", "incomplete")
# A test of these classes can be deleted, so a demotion does not count on it.
DELETION_CLASSES = frozenset({"empty", "subsumed"})

# The order of OPERATORS decides which mutants a line keeps when it has more than PER_LINE.
OPERATORS = ("comparison", "boolean", "arithmetic", "condition", "return-none", "raise-removal", "constant", "stub")
COMPARE = {
    ast.Lt: ("<=", ">="), ast.LtE: ("<", ">"), ast.Gt: (">=", "<="), ast.GtE: (">", "<"),
    ast.Eq: ("!=",), ast.NotEq: ("==",), ast.Is: ("is not",), ast.IsNot: ("is",),
    ast.In: ("not in",), ast.NotIn: ("in",),
}
BOOLEAN = {ast.And: "or", ast.Or: "and"}
ARITHMETIC = {
    ast.Add: "-", ast.Sub: "+", ast.Mult: "/", ast.Div: "*", ast.FloorDiv: "/", ast.Mod: "//",
    ast.Pow: "*", ast.LShift: ">>", ast.RShift: "<<", ast.BitAnd: "|", ast.BitOr: "&", ast.BitXor: "&",
}
LOG_OWNERS = frozenset({"logging", "logger", "log", "_logger", "_log", "LOGGER", "LOG"})
LOG_METHODS = frozenset({"debug", "info", "warning", "warn", "error", "exception", "critical", "fatal", "log"})


class Token(NamedTuple):
    """The text offsets of an operator or keyword token."""

    start: int
    end: int


class Module(NamedTuple):
    """A product module as read from disk."""

    raw: bytes
    bom: bytes
    text: str


class Source:
    """A module's text, with AST and token positions turned into text offsets."""

    def __init__(self, text: str) -> None:
        self.text = text
        self.lines = text.split("\n")
        self.starts = []
        offset = 0
        for line in self.lines:
            self.starts.append(offset)
            offset += len(line) + 1
        self.tokens = [
            Token(self.at(*token.start), self.at(*token.end))
            for token in tokenize.generate_tokens(io.StringIO(text).readline)
            if token.type in (tokenize.OP, tokenize.NAME) and token.string not in ("(", ")")
        ]
        self.token_starts = [token.start for token in self.tokens]

    def at(self, lineno: int, column: int) -> int:
        """The offset of a token position: a line and a character column."""
        return self.starts[lineno - 1] + column

    def offset(self, lineno: int, column: int) -> int:
        """The offset of an AST position: a line and a UTF-8 byte column."""
        line = self.lines[lineno - 1].encode("utf-8")
        return self.starts[lineno - 1] + len(line[:column].decode("utf-8", errors="replace"))

    def span(self, node: ast.AST) -> tuple[int, int]:
        return self.offset(node.lineno, node.col_offset), self.offset(node.end_lineno, node.end_col_offset)

    def operator_span(self, start: int, end: int) -> tuple[int, int] | None:
        """The span from the first to the last operator or keyword token between two offsets, or None."""
        index = bisect.bisect_left(self.token_starts, start)
        inside = list(itertools.takewhile(lambda token: token.end <= end, itertools.islice(self.tokens, index, None)))
        return (inside[0].start, inside[-1].end) if inside else None

    def check_field(self, node: ast.expr) -> bool:
        """Whether an f-string field's expression is at its position; add its tokens when it has none.

        Before Python 3.12, an f-string is one string token, and the positions
        of the expressions inside it can be wrong.
        """
        start, end = self.span(node)
        wrapped = "(" + self.text[start:end] + "\n)"
        try:
            if ast.dump(ast.parse(wrapped, mode="eval").body) != ast.dump(node):
                return False
        except SyntaxError:
            return False
        if self.operator_span(start, end) is None:
            found = [Token(start + token.start - 1, start + token.end - 1) for token in Source(wrapped).tokens]
            self.tokens = sorted(self.tokens + found)
            self.token_starts = [token.start for token in self.tokens]
        return True

    def line_of(self, offset: int) -> int:
        return bisect.bisect_right(self.starts, offset)


def is_string_statement(node: ast.AST) -> bool:
    return isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str)


def is_logging_call(node: ast.AST) -> bool:
    if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute) or node.func.attr not in LOG_METHODS:
        return False
    owner = node.func.value
    name = owner.attr if isinstance(owner, ast.Attribute) else owner.id if isinstance(owner, ast.Name) else ""
    return name in LOG_OWNERS or name.lower().endswith("logger")


def is_arid(stmt: ast.stmt) -> bool:
    """A docstring, `pass`, or a logging call: a statement that gets no mutant."""
    if isinstance(stmt, ast.Expr) and is_logging_call(stmt.value):
        return True
    return is_string_statement(stmt) or isinstance(stmt, ast.Pass)


class Finder:
    """Find the mutants of one module on the lines that coverage saw run.

    Arid code gets no mutant: docstrings, annotations, logging calls, `pass`, and `__repr__`.
    """

    def __init__(self, source: Source, executed: set) -> None:
        self.source = source
        self.executed = executed
        self.found: list[dict] = []

    def visit(self, node: ast.AST, stmt: ast.AST) -> None:
        if isinstance(node, ast.stmt):
            stmt = node
            if is_string_statement(node):
                return
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name == "__repr__":
                return
            self.stub(node)
            args = node.args
            for child in [*node.decorator_list, *args.defaults, *(d for d in args.kw_defaults if d is not None)]:
                self.visit(child, stmt)
            for child in node.body:
                self.visit(child, child)
            return
        if isinstance(node, ast.AnnAssign):
            if node.value is not None:
                self.visit(node.value, stmt)
            return
        if is_logging_call(node):
            return
        if isinstance(node, ast.JoinedStr):
            self.fstring(node, stmt)
            return
        if self.ran(stmt):
            self.mutate(node)
        for child in ast.iter_child_nodes(node):
            self.visit(child, stmt)

    def ran(self, stmt: ast.AST) -> bool:
        """Whether coverage saw the header lines of `stmt` run, decorators included."""
        first = min([stmt.lineno, *(d.lineno for d in getattr(stmt, "decorator_list", []))])
        body = getattr(stmt, "body", None)
        if isinstance(body, list) and body:
            last = max(stmt.lineno, body[0].lineno - 1)
        else:
            last = stmt.end_lineno
        return any(line in self.executed for line in range(first, last + 1))

    def add(self, operator: str, splices: list) -> None:
        position = min(start for start, _, _ in splices)
        self.found.append({
            "operator": operator, "line": self.source.line_of(position), "position": position,
            "order": len(self.found), "splices": sorted(splices),
        })

    def replace(self, node: ast.AST, text: str) -> tuple[int, int, str]:
        """Replace an expression; parentheses keep the line count when it spans lines."""
        start, end = self.source.span(node)
        if node.end_lineno > node.lineno:
            text = "(" + text + "\n" * (node.end_lineno - node.lineno) + ")"
        return start, end, text

    def token_span(self, left: ast.AST, right: ast.AST) -> tuple[int, int] | None:
        """The span of the operator tokens between two operands, or None."""
        _, start = self.source.span(left)
        end, _ = self.source.span(right)
        return self.source.operator_span(start, end)

    def mutate(self, node: ast.AST) -> None:
        if isinstance(node, ast.Compare):
            left = node.left
            for op, right in zip(node.ops, node.comparators):
                found = self.token_span(left, right)
                if found:
                    for text in COMPARE[type(op)]:
                        self.add("comparison", [(*found, text)])
                left = right
        elif isinstance(node, ast.BoolOp):
            spans = [self.token_span(a, b) for a, b in zip(node.values, node.values[1:])]
            if all(spans):
                self.add("boolean", [(*span, BOOLEAN[type(node.op)]) for span in spans])
        elif isinstance(node, ast.BinOp) and type(node.op) in ARITHMETIC:
            formatting = isinstance(node.op, ast.Mod) and isinstance(node.left, ast.Constant) and isinstance(
                node.left.value, (str, bytes)
            )
            found = None if formatting else self.token_span(node.left, node.right)
            if found:
                self.add("arithmetic", [(*found, ARITHMETIC[type(node.op)])])
        elif isinstance(node, ast.AugAssign) and type(node.op) in ARITHMETIC:
            found = self.token_span(node.target, node.value)
            if found:
                self.add("arithmetic", [(*found, ARITHMETIC[type(node.op)] + "=")])
        elif isinstance(node, ast.Constant):
            self.constant(node)
        elif isinstance(node, (ast.If, ast.While, ast.IfExp)):
            test = node.test
            if not (isinstance(test, ast.Compare) and len(test.ops) == 1):  # a comparison swap covers it
                start, end = self.source.span(test)
                self.add("condition", [(start, start, "not ("), (end, end, ")")])
        elif isinstance(node, ast.Return):
            if node.value is not None and not (isinstance(node.value, ast.Constant) and node.value.value is None):
                self.add("return-none", [self.replace(node.value, "None")])
        elif isinstance(node, ast.Raise):
            start, end = self.source.span(node)
            self.add("raise-removal", [(start, end, "pass" + "\n" * (node.end_lineno - node.lineno))])

    def constant(self, node: ast.Constant) -> None:
        value = node.value
        if isinstance(value, bool):
            new = not value
        elif isinstance(value, int):
            new = value + 1
        elif isinstance(value, float) and math.isfinite(value):
            new = value + 1.0
        elif isinstance(value, str):
            new = "XX" + value + "XX"
        elif isinstance(value, bytes):
            new = b"XX" + value + b"XX"
        else:
            return
        self.add("constant", [self.replace(node, repr(new))])

    def fstring(self, node: ast.JoinedStr, stmt: ast.AST) -> None:
        """An f-string: a constant change of its text, as for a string, and the mutants of each replacement field."""
        if self.ran(stmt):
            start, end = self.source.span(node)
            self.add("constant", [(start, start, '("XX" + '), (end, end, ' + "XX")')])
        for value in node.values:
            if isinstance(value, ast.FormattedValue) and self.source.check_field(value.value):
                self.visit(value.value, stmt)

    def stub(self, node: ast.AST) -> None:
        """Replace a function body, without its docstring, by `return None`."""
        body = node.body[1:] if node.body and is_string_statement(node.body[0]) else node.body
        if not body or not any(line in self.executed for line in range(body[0].lineno, body[-1].end_lineno + 1)):
            return
        only = body[0] if len(body) == 1 else None
        ellipsis = isinstance(only, ast.Expr) and isinstance(only.value, ast.Constant) and only.value.value is Ellipsis
        if ellipsis or isinstance(only, (ast.Return, ast.Raise)) or all(is_arid(statement) for statement in body):
            return  # the body does nothing, is arid, or return-none or raise-removal covers it
        start = self.source.offset(body[0].lineno, body[0].col_offset)
        end = self.source.offset(body[-1].end_lineno, body[-1].end_col_offset)
        self.add("stub", [(start, end, "return None" + "\n" * (body[-1].end_lineno - body[0].lineno))])


def apply(text: str, splices: list) -> str:
    for start, end, new in sorted(splices, reverse=True):
        text = text[:start] + new + text[end:]
    return text


def by_operator(mutant: dict) -> tuple:
    return OPERATORS.index(mutant["operator"]), mutant["position"], mutant["order"]


def capped(found: list[dict]) -> list[dict]:
    """At most PER_LINE mutants per reported line.

    A line keeps the first mutant of each operator in OPERATORS order, then the second of each.
    """
    lines: dict[int, list[dict]] = {}
    for mutant in sorted(found, key=by_operator):
        group = lines.setdefault(mutant["line"], [])
        mutant["rank"] = sum(1 for other in group if other["operator"] == mutant["operator"])
        group.append(mutant)
    return [
        mutant
        for group in lines.values()
        for mutant in sorted(group, key=lambda m: (m["rank"], *by_operator(m)))[:PER_LINE]
    ]


def read_module(path: Path) -> Module:
    """Read a product module, with its byte-order mark apart from its text. Raises PARSE_ERRORS."""
    raw = path.read_bytes()
    bom = codecs.BOM_UTF8 if raw.startswith(codecs.BOM_UTF8) else b""
    return Module(raw, bom, raw[len(bom):].decode("utf-8"))


def module_mutants(path: str, text: str, executed: set) -> list[dict]:
    """The mutants of one module, ordered by line. Raises PARSE_ERRORS."""
    tree = ast.parse(text)
    finder = Finder(Source(text), executed)
    for node in tree.body:
        finder.visit(node, node)
    lines = text.split("\n")
    seen = {hashlib.sha256(text.encode("utf-8")).digest()}
    mutants = []
    for found in sorted(capped(finder.found), key=lambda m: (m["line"], *by_operator(m))):
        mutated = apply(text, found["splices"])
        digest = hashlib.sha256(mutated.encode("utf-8")).digest()
        if digest in seen or mutated.count("\n") != text.count("\n"):
            continue
        try:
            ast.parse(mutated)
        except SyntaxError:
            continue
        seen.add(digest)
        mutants.append({
            "path": path,
            "line": found["line"],
            "operator": found["operator"],
            "before": lines[found["line"] - 1].strip(),
            "after": mutated.split("\n")[found["line"] - 1].strip(),
            "splices": [list(splice) for splice in found["splices"]],
        })
    return mutants


def import_root(project: Path, path: str) -> str:
    """The directory above the outermost package of a module, relative to the project."""
    folder = (project / path).parent
    while folder != project and (folder / "__init__.py").is_file():
        folder = folder.parent
    return rel(folder, project)


def scope(project: Path, coverage: dict, nodeids: list[str]) -> tuple[dict, dict, list]:
    """The product modules of the prune scope.

    Returns the modules that an in-scope test covers, with their executed
    lines; the modules where the run phase of each test ran a line; and the
    covered modules that a copy cannot change.
    """
    files = product_files(coverage, project, {(project / node_file(n)).resolve() for n in nodeids})
    lines, run_modules = lines_by_test(files, project)
    covered = {name for nodeid in nodeids for name in lines.get(nodeid, {})}
    modules: dict[str, set] = {}
    skipped = []
    for path, entry in sorted(files.items()):
        name = rel(path, project)
        if name not in covered:
            continue
        if name.startswith("../") or Path(name).is_absolute():
            skipped.append({"path": name, "reason": "outside the project, so a copy cannot change it"})
        else:
            modules[name] = set(entry.get("executed_lines") or [])
    return modules, run_modules, skipped


def skip_copy(directory: str, names: list) -> set:
    """Leave caches, bytecode, coverage data, version control, and virtual environments out of a copy."""
    skipped = set()
    for name in names:
        path = os.path.join(directory, name)
        coverage_data = name == ".coverage" or name.startswith(".coverage.")
        if name in SKIP_NAMES or coverage_data or name.endswith((".pyc", ".pyo")):
            skipped.add(name)
        elif not os.path.islink(path) and os.path.isfile(os.path.join(path, "pyvenv.cfg")):
            skipped.add(name)
    return skipped


def copy_env(project: Path, records: Path, data_file: Path, roots: tuple[str, ...] = ()) -> dict:
    """The pytest environment of a run in a copy; `uv run` in a copy uses the project's environment."""
    env = pytest_env(records, data_file, roots)
    env.setdefault("UV_PROJECT", str(project))
    return env


class ProjectCopy:
    """One worker's copy of the project, with its own outcome records and log."""

    def __init__(self, index: int, work: Path, project: Path, roots: list[str]) -> None:
        self.dir = work / f"copy{index}"
        if self.dir.exists():
            shutil.rmtree(self.dir)
        self.dir.mkdir(parents=True)
        self.root = self.dir / project.name
        shutil.copytree(project, self.root, symlinks=True, ignore=skip_copy)
        self.records = self.dir / "records.jsonl"
        self.log = self.dir / "pytest.log"
        # The copy's import roots come first: an editable install would otherwise import the project.
        roots_in_copy = tuple(str((self.root / root).resolve()) for root in roots)
        self.env = copy_env(project, self.records, self.dir / "coverage.data", roots_in_copy)

    def run(self, cmd: list[str], limit: float) -> dict:
        self.records.write_text("", encoding="utf-8")
        start = time.monotonic()
        exit_code, timed_out = run_pytest(cmd, self.root, self.env, self.log, limit)
        return {
            "exit_code": exit_code, "timed_out": timed_out, "seconds": time.monotonic() - start,
            "found": read_records(self.records),
        }

    def run_mutant(self, path: str, original: bytes, mutated: bytes, cmd: list[str], limit: float) -> dict:
        target = self.root / path
        target.write_bytes(mutated)
        try:
            return self.run(cmd, limit)
        finally:
            target.write_bytes(original)

    def remove(self) -> None:
        shutil.rmtree(self.root, ignore_errors=True)


def kill_type(test: dict) -> str | None:
    """`assertion` when a check failed, `exception` for any other failure, None when the test did not fail."""
    if test["outcome"] not in ("failed", "error"):
        return None
    return "assertion" if failure(test) in CHECK_FAILURES else "exception"


def verdict(run: dict, nodeids: list[str]) -> tuple[dict, list, str | None]:
    """The kill of each test, the tests the run did not reach, and a kill that no test gets.

    When the run stops early, the first test without a complete record gets
    the timeout or crash; the tests after it were not reached.
    """
    found = run["found"]
    if found["collected"] is None:
        if run["timed_out"]:
            return {}, list(nodeids), "timeout"
        return {n: "collection" for n in nodeids}, [], None
    collected = set(found["collected"])
    tests = {test["nodeid"]: test for test in test_entries(found)}
    stopped = run["timed_out"] or run["exit_code"] not in (0, 1)
    stop_kill: str | None = "timeout" if run["timed_out"] else "crash"
    killed_by: dict[str, str] = {}
    not_reached = []
    for nodeid in nodeids:
        test = tests.get(nodeid)
        if nodeid not in collected:
            killed_by[nodeid] = "collection"
        elif test is not None and "teardown" in test["phases"]:
            kind = kill_type(test)
            if kind:
                killed_by[nodeid] = kind
        elif stopped and stop_kill is not None:
            killed_by[nodeid] = stop_kill
            stop_kill = None
        else:
            not_reached.append(nodeid)
    return killed_by, not_reached, "timeout" if run["timed_out"] and stop_kill is not None else None


class Runner:
    """The copies, the pytest command, and the budget of one mutate call."""

    def __init__(self, args, extra: list[str], project: Path, roots: list[str], workers: int) -> None:
        self.budget = args.budget
        self.deadline = time.monotonic() + args.budget
        self.python = interpreter(args.python)
        self.extra = extra
        self.work = Path(args.work_dir).resolve() / ("recheck" if args.recheck else "mutate")
        if self.work == project or project in self.work.parents:
            raise UsageError(f"the work directory {self.work} is inside the project; use one outside it")
        self.work.mkdir(parents=True, exist_ok=True)
        probe_env = copy_env(project, self.work / "probe.jsonl", self.work / "probe.data")
        self.versions = probe(self.python, project, probe_env)
        if not self.versions.get("pytest"):
            raise UsageError("the target interpreter cannot import pytest", package="pytest")
        self.idle: queue.Queue = queue.Queue()
        self.copies: list[ProjectCopy] = []
        try:
            for index in range(workers):
                copy = ProjectCopy(index, self.work, project, roots)
                self.copies.append(copy)
                self.idle.put(copy)
        except OSError as error:
            self.close()
            raise UsageError(f"cannot copy the project to {self.work}: {error}") from error
        self.timeout = TIMEOUT_FLOOR

    def remaining(self) -> float:
        return self.deadline - time.monotonic()

    def command(self, name: str, files: list[str], deselect: list[str]) -> list[str]:
        cmd = [
            *self.python, "-m", "pytest", "-p", "no:cacheprovider", "-p", "no:randomly", "-p", "lean_tests_report",
            # Every test runs: a failing module or test does not stop the run.
            "--continue-on-collection-errors", "--maxfail=0",
        ]
        if self.versions.get("pytest_cov"):
            cmd.append("--no-cov")
        targets = [*files, *(f"--deselect={n}" for n in deselect)]
        if version_tuple(self.versions["pytest"]) >= (8, 2):
            argfile = self.work / f"{name}-args.txt"
            argfile.write_text("".join(f"{t}\n" for t in targets), encoding="utf-8")
            cmd.append(f"@{argfile}")
        else:
            cmd += targets
        return cmd + self.extra

    def baseline(self, cmd: list[str]) -> dict | None:
        """Run the scope once on the unchanged copy; None when the budget runs out."""
        copy = self.idle.get()
        try:
            run = copy.run(cmd, max(self.remaining(), 0.0))
        finally:
            self.idle.put(copy)
        if run["timed_out"]:
            return None
        if run["found"]["collected"] is None or run["exit_code"] in (3, 4):
            raise UsageError(
                f"pytest exited with {run['exit_code']} in the unchanged copy; see log_tail",
                log_tail=tail(copy.log.read_text(encoding="utf-8", errors="replace"), LOG_TAIL),
            )
        self.timeout = max(TIMEOUT_FLOOR, TIMEOUT_FACTOR * run["seconds"])
        return run

    def run_all(self, jobs: list[tuple[str, bytes, bytes]], cmd: list[str]) -> list[dict | None]:
        """Run each (path, original, mutated) job in a copy; None for a job the budget did not let finish."""

        def job(item: tuple[str, bytes, bytes]) -> dict | None:
            copy = self.idle.get()
            try:
                remaining = self.remaining()
                if remaining <= 0:
                    return None
                limit = min(self.timeout, remaining)
                run = copy.run_mutant(*item, cmd, limit)
                return None if run["timed_out"] and limit < self.timeout else run
            finally:
                self.idle.put(copy)

        with ThreadPoolExecutor(max_workers=len(self.copies)) as pool:
            return list(pool.map(job, jobs))

    def timing(self, started: float) -> dict:
        return {
            "workers": len(self.copies),
            "budget_seconds": self.budget,
            "mutant_timeout_seconds": round(self.timeout, 3),
            "wall_seconds": round(time.monotonic() - started, 3),
        }

    def close(self) -> None:
        for copy in self.copies:
            copy.remove()


def check_sanity(runner: Runner, modules: dict, cmd: list[str], nodeids: list[str]) -> tuple[list, str | None]:
    """Run one module-level raise per mutated module; each must be killed.

    Returns the sanity entries and an incomplete-evidence reason. A sanity
    mutant that survives is a usage or environment error.
    """
    jobs = [(path, module.raw, module.raw + SANITY) for path, module in modules.items()]
    entries = []
    for (path, _, _), run in zip(jobs, runner.run_all(jobs, cmd)):
        if run is None:
            return entries, "the budget ran out before the sanity mutants finished"
        killed_by, _, lost_kill = verdict(run, nodeids)
        entries.append({"path": path, "killed": bool(killed_by or lost_kill)})
    survived = [entry["path"] for entry in entries if not entry["killed"]]
    if survived:
        raise UsageError(
            "incomplete evidence: the sanity mutant of " + ", ".join(survived) + " survived, so the tests do "
            "not run the copied module; check the import path, for example an installed copy of the package",
            sanity=entries,
        )
    return entries, None


def run_mutants(runner: Runner, mutants: list[dict], texts: dict, cmd: list[str], nodeids: list[str]) -> None:
    """Run each mutant against every in-scope test and record its status and kills in place."""
    jobs = []
    for mutant in mutants:
        module = texts[mutant["path"]]
        mutated = apply(module.text, [tuple(s) for s in mutant["splices"]])
        jobs.append((mutant["path"], module.raw, module.bom + mutated.encode("utf-8")))
    for mutant, run in zip(mutants, runner.run_all(jobs, cmd)):
        if run is None:
            continue
        killed_by, not_reached, lost_kill = verdict(run, nodeids)
        mutant.update(
            status="killed" if killed_by or lost_kill else "survived",
            killed_by=killed_by,
            not_reached=not_reached,
            timed_out=run["timed_out"],
        )


def prepare(runner: Runner, suite: dict, nodeids: list[str], files: list[str]) -> tuple[dict | None, list, list, list]:
    """The baseline run: the in-scope tests, the excluded tests, and the run command.

    An in-scope test passed in the suite output and in the unchanged copy.
    """
    run = runner.baseline(runner.command("baseline", files, []))
    if run is None:
        return None, [], [], []
    in_suite = {test["nodeid"]: test["outcome"] for test in suite["tests"]}
    in_copy = {test["nodeid"]: test["outcome"] for test in test_entries(run["found"])}
    passed, excluded = [], []
    for nodeid in nodeids:
        if in_suite.get(nodeid) != "passed":
            excluded.append({"nodeid": nodeid, "run": "suite", "outcome": in_suite.get(nodeid, "not run")})
        elif in_copy.get(nodeid) != "passed":
            excluded.append({"nodeid": nodeid, "run": "copy", "outcome": in_copy.get(nodeid, "not run")})
        else:
            passed.append(nodeid)
    if not passed:
        raise UsageError(
            "no in-scope test passed in the suite run and the unchanged copy", excluded=excluded[:EXAMPLES]
        )
    keep = set(passed)
    deselect = [n for n in run["found"]["collected"] if n not in keep]
    return run, passed, excluded, runner.command("mutants", files, deselect)


def not_run() -> dict:
    return {"status": "not-run", "killed_by": {}, "not_reached": [], "timed_out": False}


def gather(runner: Runner, suite: dict, files: list[str], texts: dict, mutants: list[dict]) -> tuple:
    """Run the baseline, the sanity mutants, and every mutant, then remove the copies.

    Returns the incomplete-evidence reason (None for complete evidence), the
    in-scope tests, the excluded tests, and the sanity entries.
    """
    nodeids = suite_node_ids(suite)
    try:
        run, in_scope, excluded, cmd = prepare(runner, suite, nodeids, files)
        if run is None:
            return "the budget ran out before the baseline run finished", list(nodeids), [], []
        mutated = {path: texts[path] for path in dict.fromkeys(m["path"] for m in mutants)}
        sanity, reason = check_sanity(runner, mutated, cmd, in_scope)
        if reason is None:
            run_mutants(runner, mutants, texts, cmd, in_scope)
            if any(m["status"] == "not-run" for m in mutants):
                reason = "the budget ran out before every mutant ran"
        return reason, in_scope, excluded, sanity
    finally:
        runner.close()


def test_files(project: Path, nodeids: list[str]) -> list[str]:
    files = list(dict.fromkeys(node_file(nodeid) for nodeid in nodeids))
    for name in files:
        if rel((project / name).resolve(), project).startswith("../"):
            raise UsageError(f"the test file {name} is outside the project")
    return files


def load_scope_suite(path: str) -> tuple[dict, Path, list[str]]:
    """A suite output of the prune scope, its project, and its collected tests."""
    suite = load_suite(path)
    project = Path(suite.get("project") or ".").resolve()
    rootdir = Path(suite.get("rootdir") or project).resolve()
    if rootdir != project:
        raise UsageError(
            f"pytest's rootdir {rootdir} is not the project directory {project}; run suite with --project {rootdir}"
        )
    nodeids = suite_node_ids(suite)
    if not nodeids:
        raise UsageError(f"the suite output {path} collected no test")
    return suite, project, nodeids


def mutate_command(args, extra: list[str]) -> dict:
    if args.budget <= 0:
        raise UsageError("--budget must be more than 0 seconds")
    if args.workers < 1:
        raise UsageError("--workers must be 1 or more")
    if args.recheck:
        return recheck(args, extra)
    return matrix(args, extra)


def matrix(args, extra: list[str]) -> dict:
    started = time.monotonic()
    suite, project, nodeids = load_scope_suite(args.suite)
    contexts = (suite.get("files") or {}).get("coverage_json")
    if not contexts:
        raise UsageError(
            "the suite output has no coverage contexts; run suite with --coverage-source for each product package"
        )
    executed, run_modules, skipped = scope(project, load_json(contexts, "coverage JSON"), nodeids)
    texts = {}
    mutants = []
    for path, lines in executed.items():
        try:
            module = read_module(project / path)
            found = module_mutants(path, module.text, lines)
        except (*PARSE_ERRORS, tokenize.TokenError) as error:
            skipped.append({"path": path, "reason": parse_failure(error)})
            continue
        if not found:
            skipped.append({"path": path, "reason": "no mutant on the lines that the tests ran"})
            continue
        texts[path] = module
        mutants += found
    if not mutants:
        raise UsageError("the covered product modules have no mutant", skipped=skipped)
    mutants = [{"id": f"m{number}", **mutant, **not_run()} for number, mutant in enumerate(mutants, start=1)]
    # Only the mutated modules count as measured: a test that reaches only skipped modules is unmeasured.
    mutated = set(texts)
    measured_in = {nodeid: modules & mutated for nodeid, modules in run_modules.items()}
    files = test_files(project, nodeids)
    roots = list(dict.fromkeys(import_root(project, path) for path in texts))
    runner = Runner(args, extra, project, roots, min(args.workers, len(mutants)))
    reason, in_scope, excluded, sanity = gather(runner, suite, files, texts, mutants)
    unmeasured = set(unmeasured_tests(in_scope, ran_tests(suite), measured_in))
    tests, groups = classify(in_scope, unmeasured, mutants, complete=reason is None)
    modules = [
        {
            "path": path,
            "sha256": hashlib.sha256(module.raw).hexdigest(),
            "mutants": sum(1 for m in mutants if m["path"] == path),
        }
        for path, module in texts.items()
    ]
    statuses = [m["status"] for m in mutants]
    summary = {
        "mode": "matrix",
        "complete": reason is None,
        "incomplete_reason": reason,
        "tests": len(in_scope),
        "excluded": len(excluded),
        "unmeasured": len(unmeasured),
        "modules": len(modules),
        "skipped_modules": len(skipped),
        "mutants": len(mutants),
        "killed": statuses.count("killed"),
        "survived": statuses.count("survived"),
        "not_run": statuses.count("not-run"),
        "timeouts": sum(1 for m in mutants if m.get("timed_out")),
        "classes": {c: sum(1 for t in tests if t["class"] == c) for c in CLASSES} if reason is None else None,
        "demote": sum(1 for t in tests if t["demote"]),
        **runner.timing(started),
        "examples": {
            **{c: [t["nodeid"] for t in tests if t["class"] == c][:EXAMPLES] for c in CLASSES},
            "survived": [label(m) for m in mutants if m["status"] == "survived"][:EXAMPLES],
        },
    }
    return {
        "summary": summary,
        "project": str(project),
        "suite": str(Path(args.suite).resolve()),
        "modules": modules,
        "skipped_modules": skipped,
        "sanity": sanity,
        "excluded": excluded,
        "unmeasured": [n for n in in_scope if n in unmeasured],
        "tests": tests,
        "equal_groups": groups,
        "mutants": mutants,
    }


def label(mutant: dict) -> str:
    return f"{mutant['id']} {mutant['path']}:{mutant['line']} {mutant['operator']}: {mutant['after']}"


def classify(in_scope: list[str], unmeasured: set, mutants: list[dict], complete: bool) -> tuple[list, list]:
    """One entry per in-scope test with its kill set and, for complete evidence, its class; equal kill sets.

    A run that stops early leaves the later tests unknown for that mutant.
    An unknown counts as a kill of the test under review and as no kill of
    the test that would cover it, so each class errs toward keeping tests.
    """
    kills: dict[str, list[str]] = {n: [] for n in in_scope}
    unknown: dict[str, list[str]] = {n: [] for n in in_scope}
    killers: dict[str, set] = {}
    for mutant in mutants:
        killers[mutant["id"]] = set(mutant["killed_by"])
        for nodeid in mutant["killed_by"]:
            if nodeid in kills:
                kills[nodeid].append(mutant["id"])
        for nodeid in mutant["not_reached"]:
            if nodeid in unknown:
                unknown[nodeid].append(mutant["id"])
    known = {n: frozenset(kills[n]) for n in in_scope}
    tests = []
    for nodeid in in_scope:
        entry = {
            "nodeid": nodeid,
            "class": None,
            "measured": nodeid not in unmeasured,
            "kills": kills[nodeid],
            "unknown": unknown[nodeid],
            "unique": [],
            "subsumed_by": [],
            "demote": False,
        }
        tests.append(entry)
        if not complete:
            continue
        entry["unique"] = [m for m in kills[nodeid] if killers[m] == {nodeid}]
        possible = known[nodeid] | set(unknown[nodeid])
        if nodeid in unmeasured:
            entry["class"] = "unmeasured"
        elif not possible:
            entry["class"] = "empty"
        elif entry["unique"]:
            entry["class"] = "unique"
        else:
            entry["subsumed_by"] = [o for o in in_scope if o != nodeid and possible <= known[o]]
            others = set().union(*(known[o] for o in in_scope if o != nodeid))
            if entry["subsumed_by"]:
                entry["class"] = "subsumed"
            else:
                entry["class"] = "union-only" if possible <= others else "incomplete"
    demoted = set(demotions(tests))
    for entry in tests:
        entry["demote"] = entry["nodeid"] in demoted
    groups: dict[frozenset, list[str]] = {}
    for nodeid in in_scope:
        if known[nodeid] and not unknown[nodeid]:
            groups.setdefault(known[nodeid], []).append(nodeid)
    return tests, [members for members in groups.values() if len(members) > 1]


def demotions(tests: list[dict]) -> list[str]:
    """The `union-only` tests that can leave the fast tiers, in test order.

    The tests that stay in the fast tiers are the tests of no deletion class
    that are not demoted. Each demoted test's kills, unknowns included, stay
    known kills of these tests. A deletion of a test of a deletion class, or
    a demotion that is left out, keeps this true.
    """
    stay = {t["nodeid"]: set(t["kills"]) for t in tests if t["class"] not in DELETION_CLASSES}
    demoted = []
    for test in tests:
        if test["class"] != "union-only":
            continue
        others = set().union(*(kills for nodeid, kills in stay.items() if nodeid != test["nodeid"]))
        if set(test["kills"]) | set(test["unknown"]) <= others:
            demoted.append(test["nodeid"])
            del stay[test["nodeid"]]
    return demoted


def recheck(args, extra: list[str]) -> dict:
    started = time.monotonic()
    before = load_json(args.recheck, "mutate output")
    summary = before.get("summary") or {}
    if summary.get("mode") != "matrix":
        raise UsageError(f"{args.recheck} is not the output of a mutate matrix run")
    if not summary.get("complete"):
        raise UsageError(f"the matrix {args.recheck} is incomplete evidence; it cannot back a removal")
    suite, project, nodeids = load_scope_suite(args.suite)
    texts = {}
    for module in before.get("modules", []):
        path = module["path"]
        try:
            texts[path] = read_module(project / path)
        except PARSE_ERRORS as error:
            raise UsageError(f"cannot read the product module {path}: {parse_failure(error)}") from error
        if hashlib.sha256(texts[path].raw).hexdigest() != module["sha256"]:
            raise UsageError(f"the product module {path} changed after the matrix run; run mutate again")
    keys = ("id", "path", "line", "operator", "before", "after", "splices")
    killed = [m for m in before.get("mutants", []) if m.get("status") == "killed"]
    mutants = [{**{k: m[k] for k in keys}, **not_run()} for m in killed]
    killed_before = {m["id"]: sorted(m["killed_by"]) for m in killed}
    if not mutants:
        raise UsageError(f"the matrix {args.recheck} has no killed mutant to check")
    files = test_files(project, nodeids)
    roots = list(dict.fromkeys(import_root(project, path) for path in texts))
    runner = Runner(args, extra, project, roots, min(args.workers, len(mutants)))
    reason, in_scope, excluded, sanity = gather(runner, suite, files, texts, mutants)
    in_matrix = {t["nodeid"] for t in before.get("tests", [])}
    broken = [e for e in excluded if e["nodeid"] in in_matrix]
    lost = [
        {**{k: m[k] for k in keys if k != "splices"}, "killed_before_by": killed_before[m["id"]]}
        for m in mutants if m["status"] == "survived"
    ]
    statuses = [m["status"] for m in mutants]
    result_summary = {
        "mode": "recheck",
        "complete": reason is None,
        "incomplete_reason": reason,
        "passed": reason is None and not lost and not broken,
        "tests": len(in_scope),
        "killed_set": len(mutants),
        "still_killed": statuses.count("killed"),
        "lost": len(lost),
        "not_run": statuses.count("not-run"),
        "broken": len(broken),
        **runner.timing(started),
        "examples": {
            "lost": [label(m) for m in mutants if m["status"] == "survived"][:EXAMPLES],
            "broken": [e["nodeid"] for e in broken][:EXAMPLES],
        },
    }
    return {
        "summary": result_summary,
        "project": str(project),
        "matrix": str(Path(args.recheck).resolve()),
        "sanity": sanity,
        "excluded": excluded,
        "broken": broken,
        "lost": lost,
        "mutants": mutants,
    }
