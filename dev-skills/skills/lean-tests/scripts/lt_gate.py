"""gate and pin: the weakening gate of review, and pinned requirement sources.

Imported by lean_tests.py; never run directly. The gate splits the commits
from the merge base of a base ref and a head ref into units: the whole
range by default, or one unit per commit. A unit is mixed when it changes a
file outside the test side, documentation aside. Layer 2 classifies each
test-side change of a unit from the syntax trees of its two versions.
Layer 1 runs the changed base test modules against the head product code in
a temporary detached worktree. The same worktree collects the head tests,
which gives the collection evidence, and runs each new test against the base
product code, which gives its label. A BEHAVIOR CHANGE, WEAKENING, or
UNCLASSIFIED item fails a mixed unit. pin records requirement sources with
SHA-256 hashes before implementation starts.
"""

from __future__ import annotations

import ast
import copy
import datetime
import difflib
import hashlib
import json
import re
import shutil
import subprocess
from collections import Counter
from pathlib import Path, PurePosixPath
from typing import NamedTuple

from lt_common import EXAMPLES, PARSE_ERRORS, UsageError, git, load_json, node_file, parse_failure, rel, tail
from lt_coverage import is_test_path
from lt_mutate import copy_env, import_root, is_string_statement, kill_type, scope_command
from lt_scan import Module, TestFunction, dotted, function_id, is_literal
from lt_suite import failure, interpreter, probe, read_records, run_pytest, test_entries

DEFAULT_TIMEOUT = 1800.0
FAILING = ("BEHAVIOR CHANGE", "WEAKENING", "UNCLASSIFIED")
CLASSES = (*FAILING, "SAFE")
LABELS = ("catching", "new-API", "hardening")
LOG_TAIL = 30
# The pytest section of each configuration file at the project root; None means the whole file.
CONFIG_SECTIONS = {
    "pytest.ini": None, ".pytest.ini": None, "pyproject.toml": "[tool.pytest.ini_options]",
    "tox.ini": "[pytest]", "setup.cfg": "[tool:pytest]",
}
DOCUMENTATION = frozenset({".md", ".rst"})
DESELECTION = re.compile(r"(?<![\w-])(?:--deselect|--ignore|--ignore-glob|-k|-m)(?![\w-])")
SKIP_NAMES = frozenset({
    "skip", "skipif", "xfail", "importorskip", "skipTest", "SkipTest", "skipIf", "skipUnless", "expectedFailure",
})
FIXTURE_DECORATORS = frozenset({"pytest.fixture", "fixture", "pytest_asyncio.fixture"})
BUILTIN_FIXTURES = frozenset({
    "cache", "capfd", "capfdbinary", "caplog", "capsys", "capsysbinary", "doctest_namespace", "monkeypatch",
    "pytestconfig", "pytester", "record_property", "record_testsuite_property", "record_xml_attribute", "recwarn",
    "request", "testdir", "tmp_path", "tmp_path_factory", "tmpdir", "tmpdir_factory",
})
# Replaces the expected value of an `assert x == literal`; no test source contains it.
EXPECTED = "\0lean-tests expected value\0"


class Unit(NamedTuple):
    """One unit of the gate: the change from `base` to `head`. `subject` is the commit subject of a per-commit unit."""

    id: str
    base: str
    head: str
    subject: str | None


class Change(NamedTuple):
    """A changed test-side file of a unit.

    `path` is relative to the project. `status` is A (added), D (deleted), or
    M (modified). `kind` is test-module, helper, conftest, config, or data.
    """

    path: str
    status: str
    kind: str


class Version(NamedTuple):
    """One side of a changed test-side Python file: its text, syntax tree, and scan module."""

    text: str
    tree: ast.Module
    module: Module


class Static(NamedTuple):
    """The layer 2 result of a unit: its items, and the function keys of its new, appended, and changed tests."""

    items: list
    new_tests: list
    appended: list
    changed_tests: list


class Run(NamedTuple):
    """One pytest run in the worktree."""

    exit_code: int | None
    timed_out: bool
    found: dict
    log: Path

    def complete(self) -> bool:
        return not self.timed_out and self.found["collected"] is not None

    def collected(self) -> list:
        return self.found["collected"] or []

    def tests(self) -> dict:
        return {test["nodeid"]: test for test in test_entries(self.found)}

    def report(self, selection: list | None) -> dict:
        return {
            "selection": "suite" if selection is None else selection,
            "exit_code": self.exit_code,
            "timed_out": self.timed_out,
            "collected": len(self.collected()),
            "collect_errors": self.found["collect_errors"],
            "log": str(self.log),
        }


def item(cls: str, subtype: str | None, path: str | None, detail: str, nodeid: str | None = None, line: int | None = None,
         **extra) -> dict:
    return {"class": cls, "subtype": subtype, "path": path, "nodeid": nodeid, "line": line, "detail": detail, **extra}


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def unified(path: str, before: str, after: str) -> str:
    def lines(text: str) -> list[str]:
        return (text if not text or text.endswith("\n") else text + "\n").splitlines(keepends=True)

    return "".join(difflib.unified_diff(lines(before), lines(after), f"a/{path}", f"b/{path}"))


def function_key(nodeid: str) -> str:
    """The node ID of a test function without its parameters, for example tests/test_a.py::TestA::test_b."""
    path, parts = function_id(nodeid)
    return "::".join([path, *parts])


class Project:
    """The project directory, its Git work tree, and the Git reads of the gate."""

    def __init__(self, path: str) -> None:
        self.dir = Path(path).resolve()
        if not self.dir.is_dir():
            raise UsageError(f"project directory {self.dir} does not exist")
        top = git(self.dir, "rev-parse", "--show-toplevel")
        if top.returncode != 0:
            raise UsageError("the gate needs a Git work tree", log_tail=tail(top.stderr, 5))
        self.root = Path(top.stdout.strip()).resolve()
        self.prefix = rel(self.dir, self.root)
        self.fixtures: dict[str, frozenset] = {}

    def git(self, *args: str) -> str:
        result = git(self.root, *args)
        if result.returncode != 0:
            raise UsageError(f"git {args[0]} failed", log_tail=tail(result.stderr, 5))
        return result.stdout

    def commit(self, ref: str) -> str:
        found = git(self.root, "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}")
        if found.returncode != 0:
            raise UsageError(f"{ref} is not a commit")
        return found.stdout.strip()

    def inner(self, path: str) -> str | None:
        """A repository path relative to the project, or None outside it."""
        if self.prefix == ".":
            return path
        return path[len(self.prefix) + 1:] if path.startswith(self.prefix + "/") else None

    def outer(self, path: str) -> str:
        """A project path relative to the repository."""
        return path if self.prefix == "." else f"{self.prefix}/{path}"

    def blobs(self, rev: str, paths: list[str]) -> dict:
        """The bytes of each project path at `rev`, or None when it does not exist there."""
        if not paths:
            return {}
        request = "".join(f"{rev}:{self.outer(path)}\n" for path in paths).encode("utf-8")
        try:
            result = subprocess.run(
                ["git", "-C", str(self.root), "cat-file", "--batch"], input=request, capture_output=True, check=True
            )
        except (OSError, subprocess.CalledProcessError) as error:
            raise UsageError(f"git cat-file failed: {error}") from error
        out, position, found = result.stdout, 0, {}
        for path in paths:
            end = out.index(b"\n", position)
            header = out[position:end].split()
            position = end + 1
            if len(header) != 3 or header[1] != b"blob":
                found[path] = None
                continue
            size = int(header[2])
            found[path] = out[position:position + size]
            position += size + 1
        return found

    def text(self, rev: str, path: str) -> str | None:
        data = self.blobs(rev, [path])[path]
        return None if data is None else data.decode("utf-8", errors="replace")

    def files(self, rev: str) -> list[str]:
        """The project paths of the files at `rev`."""
        spec = [] if self.prefix == "." else ["--", self.prefix]
        listing = self.git("ls-tree", "-r", "-z", "--name-only", rev, *spec)
        return [inner for name in listing.split("\0") if name for inner in [self.inner(name)] if inner is not None]

    def is_test_side(self, path: str) -> bool:
        return is_test_path(self.dir / path, set(), self.dir)

    def base_fixtures(self, rev: str) -> frozenset:
        """The fixture names that the test side defines at `rev`, and the built-in fixture names of pytest."""
        if rev not in self.fixtures:
            names = set(BUILTIN_FIXTURES)
            paths = [path for path in self.files(rev) if path.endswith(".py") and self.is_test_side(path)]
            for data in self.blobs(rev, paths).values():
                try:
                    tree = ast.parse(data.decode("utf-8"))
                except PARSE_ERRORS:
                    continue
                for node in ast.walk(tree):
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        name = fixture_name(node)
                        if name:
                            names.add(name)
            self.fixtures[rev] = frozenset(names)
        return self.fixtures[rev]

    def units(self, merge_base: str, head: str, per_commit: bool) -> list[Unit]:
        if not per_commit:
            return [Unit("u1", merge_base, head, None)]
        log = self.git("log", "--reverse", "--first-parent", "--format=%H%x00%P%x00%s", f"{merge_base}..{head}")
        units = []
        for line in log.splitlines():
            commit, parents, subject = line.split("\0", 2)
            if not parents:
                raise UsageError(f"commit {commit} has no parent")
            units.append(Unit(f"u{len(units) + 1}", parents.split()[0], commit, subject))
        return units

    def changes(self, unit: Unit) -> tuple[list[Change], list[str]]:
        """The changed test-side files of a unit, and its changed product files."""
        listing = self.git("diff", "--name-status", "-z", "--no-renames", "--no-ext-diff", unit.base, unit.head)
        fields = listing.split("\0")
        changes, product = [], []
        for status, name in zip(fields[0::2], fields[1::2]):
            status = status[:1] if status[:1] in ("A", "D") else "M"
            path = self.inner(name)
            if path is None:
                if PurePosixPath(name).suffix not in DOCUMENTATION:
                    product.append(rel(self.root / name, self.dir))
            elif path in CONFIG_SECTIONS:
                header = CONFIG_SECTIONS[path]
                before = split_config(header, self.text(unit.base, path) or "")
                after = split_config(header, self.text(unit.head, path) or "")
                if before[0] != after[0]:
                    changes.append(Change(path, status, "config"))
                if before[1] != after[1]:
                    product.append(path)
            elif self.is_test_side(path):
                changes.append(Change(path, status, test_kind(path)))
            elif PurePosixPath(path).suffix not in DOCUMENTATION:
                product.append(path)
        return changes, product

    def file_diff(self, unit: Unit, path: str) -> str:
        return self.git("diff", "--no-color", "--no-ext-diff", unit.base, unit.head, "--", self.outer(path))


def test_kind(path: str) -> str:
    name = PurePosixPath(path).name
    if name == "conftest.py":
        return "conftest"
    if name.endswith(".py"):
        return "test-module" if name.startswith("test_") or name[:-3].endswith("_test") else "helper"
    return "data"


def split_config(header: str | None, text: str) -> tuple[str, str]:
    """The pytest section of a configuration file, and the rest of it."""
    if header is None:
        return text, ""
    inside, outside = [], []
    current = False
    for line in text.splitlines():
        if line.strip().startswith("["):
            current = line.strip() == header
        (inside if current else outside).append(line)
    return "\n".join(inside), "\n".join(outside)


def fixture_name(func: ast.AST) -> str | None:
    """The name of the fixture that a function defines, or None when it is no fixture."""
    for decorator in func.decorator_list:
        call = decorator if isinstance(decorator, ast.Call) else None
        if dotted(call.func if call else decorator) not in FIXTURE_DECORATORS:
            continue
        for keyword in call.keywords if call else []:
            if keyword.arg == "name" and isinstance(keyword.value, ast.Constant):
                return str(keyword.value.value)
        return func.name
    return None


def autouse(func: ast.AST) -> bool:
    for decorator in func.decorator_list:
        if isinstance(decorator, ast.Call) and dotted(decorator.func) in FIXTURE_DECORATORS:
            for keyword in decorator.keywords:
                if keyword.arg == "autouse":
                    return not (isinstance(keyword.value, ast.Constant) and keyword.value.value is False)
    return False


def expand_imports(body: list) -> list:
    """The statements of a scope, with one import statement per imported name and without docstrings."""
    found = []
    for stmt in body:
        if is_string_statement(stmt):
            continue
        if isinstance(stmt, (ast.Import, ast.ImportFrom)) and len(stmt.names) > 1:
            for alias in stmt.names:
                single = copy.copy(stmt)
                single.names = [alias]
                found.append(single)
        else:
            found.append(stmt)
    return found


def bound_names(stmt: ast.stmt) -> list[str] | None:
    """The names that a statement binds in its scope, or None for a statement that the binding rule does not track."""
    if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return [stmt.name]
    if isinstance(stmt, ast.Import):
        return [(alias.asname or alias.name).split(".")[0] for alias in stmt.names]
    if isinstance(stmt, ast.ImportFrom):
        return [alias.asname or alias.name for alias in stmt.names]
    if isinstance(stmt, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
        names = []
        for target in stmt.targets if isinstance(stmt, ast.Assign) else [stmt.target]:
            for node in target.elts if isinstance(target, (ast.Tuple, ast.List)) else [target]:
                if not isinstance(node, ast.Name):
                    return None
                names.append(node.id)
        return names
    return None


def unresolvable(tree: ast.Module) -> list[str]:
    """The constructs of a module that bind names the binding rule cannot see."""
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and any(alias.name == "*" for alias in node.names):
            found.append("star import")
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            name = node.func.id
            if name in ("globals", "locals", "exec") or (name == "vars" and not node.args):
                found.append(f"{name}()")
    if any(isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == "__getattr__" for n in tree.body):
        found.append("module __getattr__")
    return list(dict.fromkeys(found))


def skip_markers(node: ast.AST) -> Counter:
    """The skip and xfail markers and calls in `node`, as syntax-tree dumps."""
    called = {id(sub.func) for sub in ast.walk(node) if isinstance(sub, ast.Call)}
    found: Counter = Counter()
    for sub in ast.walk(node):
        if id(sub) in called:
            continue
        target = sub.func if isinstance(sub, ast.Call) else sub
        if isinstance(target, ast.Attribute):
            name = target.attr
        elif isinstance(target, ast.Name) and isinstance(target.ctx, ast.Load):
            name = target.id
        else:
            continue
        if name in SKIP_NAMES:
            found[ast.dump(sub)] += 1
    return found


def skip_added(before: ast.AST, after: ast.AST) -> bool:
    return bool(skip_markers(after) - skip_markers(before))


def is_test_class(cls: ast.ClassDef | None) -> bool:
    if cls is None:
        return False
    return cls.name.startswith("Test") or any((dotted(base) or "").endswith("TestCase") for base in cls.bases)


def root_name(target: ast.AST) -> str | None:
    while isinstance(target, (ast.Attribute, ast.Subscript)):
        target = target.value
    return target.id if isinstance(target, ast.Name) else None


def targets_of(stmt: ast.AST) -> list:
    found = []
    pending = list(stmt.targets) if isinstance(stmt, (ast.Assign, ast.Delete)) else [stmt.target]
    while pending:
        target = pending.pop()
        if isinstance(target, (ast.Tuple, ast.List)):
            pending += target.elts
        elif isinstance(target, ast.Starred):
            pending.append(target.value)
        else:
            found.append(target)
    return found


class ExpectedValues(ast.NodeTransformer):
    """Replace the single literal operand of each `assert x == literal` by one placeholder, and keep the operands."""

    def __init__(self) -> None:
        self.operands: list = []

    def visit_Assert(self, node: ast.Assert) -> ast.Assert:
        test = node.test
        if isinstance(test, ast.Compare) and len(test.ops) == 1 and isinstance(test.ops[0], ast.Eq):
            left, right = test.left, test.comparators[0]
            if is_literal(left) != is_literal(right):
                if is_literal(left):
                    self.operands.append(left)
                    test.left = ast.Constant(value=EXPECTED)
                else:
                    self.operands.append(right)
                    test.comparators[0] = ast.Constant(value=EXPECTED)
        return node


def parametrize_values(call: ast.Call) -> tuple:
    """The argvalues of a parametrize call, and its other arguments as dumps."""
    keywords = [k for k in call.keywords if k.arg != "argvalues"]
    if len(call.args) >= 2:
        values, others = call.args[1], [call.args[0], *call.args[2:]]
    else:
        found = [k.value for k in call.keywords if k.arg == "argvalues"]
        values, others = (found[0] if found else None), list(call.args)
    return values, [ast.dump(n) for n in [*others, *keywords]]


def appended_cases(before: ast.AST, after: ast.AST) -> bool:
    """True when `after` equals `before` except for literal cases appended to the argvalues of one parametrize."""
    if len(before.decorator_list) != len(after.decorator_list):
        return False
    bare_before, bare_after = copy.copy(before), copy.copy(after)
    bare_before.decorator_list = bare_after.decorator_list = []
    if ast.dump(bare_before) != ast.dump(bare_after):
        return False
    pairs = [(b, a) for b, a in zip(before.decorator_list, after.decorator_list) if ast.dump(b) != ast.dump(a)]
    if len(pairs) != 1 or not all(isinstance(node, ast.Call) for node in pairs[0]):
        return False
    old, new = pairs[0]
    if not (dotted(old.func) or "").endswith("parametrize") or ast.dump(old.func) != ast.dump(new.func):
        return False
    (old_values, old_rest), (new_values, new_rest) = parametrize_values(old), parametrize_values(new)
    if old_rest != new_rest or not isinstance(old_values, (ast.List, ast.Tuple)) or type(new_values) is not type(old_values):
        return False
    count = len(old_values.elts)
    return (
        len(new_values.elts) > count
        and [ast.dump(e) for e in new_values.elts[:count]] == [ast.dump(e) for e in old_values.elts]
        and all(is_literal(e) for e in new_values.elts[count:])
    )


class FileDiff:
    """Layer 2 for one test-side Python file: one item for each change between its base and head versions.

    A chain is the list of (base class, head class) pairs that enclose a scope.
    """

    def __init__(self, path: str, base: Version | None, head: Version | None, fixtures) -> None:
        self.path = path
        self.base = base
        self.head = head
        self.fixtures = fixtures
        self.items: list[dict] = []
        self.new_tests: list[str] = []
        self.appended: list[str] = []
        self.changed_tests: list[str] = []

    def classify(self) -> None:
        self.diff_scope(
            expand_imports(self.base.tree.body if self.base else []),
            expand_imports(self.head.tree.body if self.head else []),
            [],
        )
        reasons = sorted({r for v in (self.base, self.head) if v is not None for r in unresolvable(v.tree)})
        if reasons:
            self.items = [i for i in self.items if i["class"] != "SAFE"]
            self.items.insert(0, item(
                "UNCLASSIFIED", "unresolvable-binding", self.path,
                "the module binds names that the binding rule cannot see: " + ", ".join(reasons),
            ))

    def key(self, chain: list, stmt: ast.AST) -> str:
        names = [(head or base).name for base, head in chain]
        return "::".join([self.path, *names, stmt.name]) if hasattr(stmt, "name") else self.path

    def add(self, cls: str, subtype: str, chain: list, before: ast.AST | None, after: ast.AST | None, detail: str,
            **extra) -> dict:
        stmt = after or before
        found = item(
            cls, subtype, self.path, detail,
            nodeid=self.key(chain, stmt) if hasattr(stmt, "name") else None,
            line=stmt.lineno,
            **extra,
            diff=unified(
                self.path,
                self.segment(self.base, before) if before is not None else "",
                self.segment(self.head, after) if after is not None else "",
            ),
        )
        self.items.append(found)
        return found

    @staticmethod
    def segment(version: Version, stmt: ast.AST) -> str:
        first = min([stmt.lineno, *(d.lineno for d in getattr(stmt, "decorator_list", []))])
        return "".join(version.text.splitlines(keepends=True)[first - 1:stmt.end_lineno])

    def is_test(self, stmt: ast.AST, chain: list) -> bool:
        inside = not chain or is_test_class(chain[-1][1] or chain[-1][0])
        if isinstance(stmt, ast.ClassDef):
            return inside and is_test_class(stmt)
        return inside and isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)) and stmt.name.startswith("test")

    def test_keys(self, stmt: ast.AST, chain: list) -> list[str]:
        """The function keys of the tests that a test function or test class defines."""
        if not self.is_test(stmt, chain):
            return []
        if not isinstance(stmt, ast.ClassDef):
            return [self.key(chain, stmt)]
        inner = [*chain, (None, stmt)]
        return [key for child in stmt.body for key in self.test_keys(child, inner)]

    def diff_scope(self, before: list, after: list, chain: list) -> None:
        """Classify the changes between the statements of one scope at base and at head."""
        base_count = Counter(name for stmt in before for name in bound_names(stmt) or [])
        head_count = Counter(name for stmt in after for name in bound_names(stmt) or [])
        unmatched = Counter(ast.dump(stmt) for stmt in before)
        added = []
        for stmt in after:
            dump = ast.dump(stmt)
            if unmatched[dump] > 0:
                unmatched[dump] -= 1
            else:
                added.append(stmt)
        removed = []
        for stmt in before:
            dump = ast.dump(stmt)
            if unmatched[dump] > 0:
                unmatched[dump] -= 1
                removed.append(stmt)
        by_name: dict[str, list] = {}
        for stmt in removed:
            for name in bound_names(stmt) or []:
                by_name.setdefault(name, []).append(stmt)
        consumed: set = set()
        for stmt in added:
            names = bound_names(stmt)
            if names is None:
                self.scope_statement(None, stmt, chain)
            elif all(base_count[n] == 0 and head_count[n] == 1 for n in names):
                self.new_binding(stmt, chain)
            else:
                old = by_name.get(names[0], [])
                if (
                    len(names) == 1 and base_count[names[0]] == 1 and head_count[names[0]] == 1
                    and len(old) == 1 and type(old[0]) is type(stmt)
                ):
                    consumed.add(id(old[0]))
                    self.modified(old[0], stmt, chain)
                else:
                    consumed.update(id(b) for n in names for b in by_name.get(n, []))
                    self.add(
                        "UNCLASSIFIED", "rebinding", chain, None, stmt,
                        f"binds {', '.join(names)} again; a rebinding of an existing name modifies its definition",
                    )
        for stmt in removed:
            if id(stmt) in consumed:
                continue
            names = bound_names(stmt)
            if names is None:
                self.scope_statement(stmt, None, chain)
            elif any(head_count[n] for n in names):
                self.add("UNCLASSIFIED", "rebinding", chain, stmt, None, f"removes one binding of {', '.join(names)}")
            else:
                self.removed(stmt, chain)

    def scope_statement(self, before: ast.AST | None, after: ast.AST | None, chain: list) -> None:
        where = "class-level" if chain else "module-level"
        if after is not None and self.base is not None and skip_markers(after):
            self.add("WEAKENING", "skip", chain, before, after, f"adds a {where} skip or xfail")
        else:
            verb = "adds" if before is None else "removes"
            self.add("UNCLASSIFIED", "scope-statement", chain, before, after, f"{verb} a {where} statement")

    def new_binding(self, stmt: ast.AST, chain: list) -> None:
        names = bound_names(stmt)
        if isinstance(stmt, (ast.Import, ast.ImportFrom)):
            self.add("SAFE", "new-import", chain, None, stmt, f"imports {', '.join(names)}")
        elif isinstance(stmt, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
            where = "class-level" if chain else "module-level"
            if self.base is not None and skip_markers(stmt):
                self.add("WEAKENING", "skip", chain, None, stmt, f"adds a {where} skip or xfail marker")
            elif "pytest_plugins" in names:
                self.add("UNCLASSIFIED", "signal", chain, None, stmt, "binds pytest_plugins")
            elif not isinstance(stmt, ast.AugAssign) and stmt.value is not None and is_literal(stmt.value):
                self.add("SAFE", "new-constant", chain, None, stmt, f"binds the constant {', '.join(names)}")
            else:
                self.add(
                    "UNCLASSIFIED", "signal", chain, None, stmt,
                    f"a {where} statement other than an import, a constant, a def, or a class",
                )
        else:
            found = self.signals(stmt)
            tests = self.test_keys(stmt, chain)
            self.new_tests += tests
            if found:
                self.add("UNCLASSIFIED", "signal", chain, None, stmt, "; ".join(found))
            elif tests:
                self.add("SAFE", "new-test", chain, None, stmt, f"adds {len(tests)} test function(s)")
            else:
                self.add("SAFE", "new-definition", chain, None, stmt, f"defines {stmt.name}")

    def signals(self, stmt: ast.AST) -> list[str]:
        """The infrastructure signals of a new definition: changes it can make to the tests around it."""
        local = set()
        patchers = set()
        for sub in ast.walk(stmt):
            if isinstance(sub, ast.arg):
                local.add(sub.arg)
            elif isinstance(sub, ast.Name) and not isinstance(sub.ctx, ast.Load):
                local.add(sub.id)
            elif isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                local.add(sub.name)
            elif isinstance(sub, (ast.Import, ast.ImportFrom)):
                local.update((alias.asname or alias.name).split(".")[0] for alias in sub.names)
            elif isinstance(sub, ast.ExceptHandler) and sub.name:
                local.add(sub.name)
            if isinstance(sub, ast.Assign) and isinstance(sub.value, ast.Call) and "patch" in (dotted(sub.value.func) or ""):
                patchers.update(t.id for t in targets_of(sub) if isinstance(t, ast.Name))
        found = []
        for sub in ast.walk(stmt):
            if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if autouse(sub):
                    found.append(f"autouse fixture {sub.name}")
                name = fixture_name(sub)
                if name and name in self.fixtures():
                    found.append(f"fixture {name} has the name of an existing fixture")
                if sub.name.startswith("pytest_"):
                    found.append(f"pytest hook {sub.name}")
            elif isinstance(sub, (ast.Global, ast.Nonlocal)):
                found.append(("global " if isinstance(sub, ast.Global) else "nonlocal ") + ", ".join(sub.names))
            elif isinstance(sub, (ast.Assign, ast.AugAssign, ast.AnnAssign, ast.Delete)):
                for target in targets_of(sub):
                    root = root_name(target)
                    if isinstance(target, (ast.Attribute, ast.Subscript)) and root not in local:
                        found.append(f"changes an attribute or item of the non-local name {root or 'expression'}")
            elif isinstance(sub, ast.Call):
                name = dotted(sub.func) or ""
                receiver = sub.func.value if isinstance(sub.func, ast.Attribute) else None
                if name in ("setattr", "delattr", "importlib.reload", "reload"):
                    found.append(f"{name}()")
                elif receiver is not None and sub.func.attr == "start" and (
                    (isinstance(receiver, ast.Call) and "patch" in (dotted(receiver.func) or ""))
                    or (isinstance(receiver, ast.Name) and receiver.id in patchers)
                ):
                    found.append("patcher .start()")
            elif isinstance(sub, ast.Attribute) and dotted(sub) == "sys.modules":
                found.append("sys.modules")
            elif isinstance(sub, ast.Name) and sub.id in ("builtins", "__builtins__"):
                found.append("builtins")
        return list(dict.fromkeys(found))

    def removed(self, stmt: ast.AST, chain: list) -> None:
        tests = self.test_keys(stmt, chain)
        if tests:
            self.add("WEAKENING", "removed-test", chain, stmt, None, f"removes {len(tests)} test function(s)")
        else:
            names = ", ".join(bound_names(stmt) or [])
            self.add("UNCLASSIFIED", "removed-definition", chain, stmt, None, f"removes {names}")

    def modified(self, before: ast.AST, after: ast.AST, chain: list) -> None:
        if isinstance(after, ast.ClassDef):
            bare_before, bare_after = copy.copy(before), copy.copy(after)
            bare_before.body = bare_after.body = []
            if ast.dump(bare_before) != ast.dump(bare_after):
                if skip_added(bare_before, bare_after):
                    self.add("WEAKENING", "skip", chain, before, after, "adds or changes a skip or xfail marker")
                else:
                    self.add("UNCLASSIFIED", "changed-definition", chain, before, after, "changes the class header")
            self.diff_scope(expand_imports(before.body), expand_imports(after.body), [*chain, (before, after)])
        elif isinstance(after, (ast.FunctionDef, ast.AsyncFunctionDef)):
            self.modified_function(before, after, chain)
        elif skip_added(before, after):
            self.add("WEAKENING", "skip", chain, before, after, "adds or changes a skip or xfail marker")
        else:
            self.add("UNCLASSIFIED", "changed-definition", chain, before, after, f"changes {', '.join(bound_names(after))}")

    def modified_function(self, before: ast.AST, after: ast.AST, chain: list) -> None:
        test = self.is_test(after, chain)
        if test and appended_cases(before, after):
            self.appended.append(self.key(chain, after))
            self.add("SAFE", "appended-cases", chain, before, after, "appends literal parametrize cases")
            return
        if test:
            self.changed_tests.append(self.key(chain, after))
            values = self.expected_literal(before, after)
            if values:
                self.add(
                    "WEAKENING", "expected-literal", chain, before, after,
                    f"changes the expected value of one == assertion from {values[0]} to {values[1]}",
                    old=values[0], new=values[1],
                )
                return
        what = "test" if test else "fixture" if fixture_name(after) else "function"
        if skip_added(before, after):
            self.add("WEAKENING", "skip", chain, before, after, f"adds or changes a skip or xfail in an existing {what}")
            return
        subtype = self.weakening(before, after, chain)
        if subtype:
            self.add("WEAKENING", subtype, chain, before, after, f"removes or changes a check of an existing {what}")
        else:
            self.add(
                "UNCLASSIFIED", "changed-definition", chain, before, after,
                f"adds or changes a statement inside an existing {what}",
            )

    def expected_literal(self, before: ast.AST, after: ast.AST) -> tuple[str, str] | None:
        """The old and new value when only the single literal operand of one == assertion changed."""
        old_tree, new_tree = copy.deepcopy(before), copy.deepcopy(after)
        old, new = ExpectedValues(), ExpectedValues()
        old.visit(old_tree)
        new.visit(new_tree)
        if ast.dump(old_tree) != ast.dump(new_tree) or len(old.operands) != len(new.operands):
            return None
        changed = [(a, b) for a, b in zip(old.operands, new.operands) if ast.dump(a) != ast.dump(b)]
        if len(changed) != 1:
            return None
        a, b = changed[0]
        return ast.get_source_segment(self.base.text, a), ast.get_source_segment(self.head.text, b)

    def weakening(self, before: ast.AST, after: ast.AST, chain: list) -> str | None:
        """The WEAKENING subtype when a check of the base version is missing at head, else None."""
        old = TestFunction(self.base.module, before, [base for base, _ in chain]).checks
        new_test = TestFunction(self.head.module, after, [head for _, head in chain])
        missing = Counter(ast.dump(node) for _, node in old) - Counter(ast.dump(node) for _, node in new_test.checks)
        if not missing:
            return None
        added = Counter(ast.dump(node) for _, node in new_test.checks) - Counter(ast.dump(node) for _, node in old)
        for _, node in new_test.checks:
            if isinstance(node, ast.Assert) and added[ast.dump(node)]:
                verdict = new_test.assert_verdict(node.test)
                if verdict:
                    return verdict[0]
        gone = [node for _, node in old if missing[ast.dump(node)]]
        names = {(dotted(sub.func) or "").rsplit(".", 1)[-1] for node in gone for sub in ast.walk(node) if isinstance(sub, ast.Call)}
        if "approx" in names:
            return "approx"
        if names & {"raises", "assertRaises", "assertRaisesRegex"}:
            return "raises"
        return "changed-assert"


def parse_version(data: bytes | None) -> Version | str | None:
    """The parsed version of a file, the reason it does not parse, or None when the file does not exist."""
    if data is None:
        return None
    try:
        text = data.decode("utf-8")
        tree = ast.parse(text)
    except PARSE_ERRORS as error:
        return parse_failure(error)
    return Version(text, tree, Module(text, tree))


def static_layer(project: Project, unit: Unit, changes: list[Change]) -> Static:
    """Layer 2: classify each test-side change of a unit."""
    python = [c.path for c in changes if c.kind in ("test-module", "helper")]
    base_blobs = project.blobs(unit.base, python)
    head_blobs = project.blobs(unit.head, python)
    items, new_tests, appended, changed_tests = [], [], [], []
    for change in changes:
        path = change.path
        verb = {"A": "adds", "D": "removes", "M": "changes"}[change.status]
        if change.kind == "conftest":
            items.append(item("UNCLASSIFIED", "conftest", path, f"{verb} a conftest.py", diff=project.file_diff(unit, path)))
        elif change.kind == "data":
            items.append(item("UNCLASSIFIED", "test-data", path, f"{verb} a test-side file", diff=project.file_diff(unit, path)))
        elif change.kind == "config":
            header = CONFIG_SECTIONS[path]
            before = split_config(header, project.text(unit.base, path) or "")[0]
            after = split_config(header, project.text(unit.head, path) or "")[0]
            added = [line[1:] for line in difflib.ndiff(before.splitlines(), after.splitlines()) if line.startswith("+ ")]
            diff = unified(path, before, after)
            if any(DESELECTION.search(line) for line in added):
                items.append(item("WEAKENING", "config-deselect", path, "adds a deselect, ignore, -k, or -m option", diff=diff))
            else:
                items.append(item("UNCLASSIFIED", "configuration", path, f"{verb} the pytest configuration", diff=diff))
        else:
            base, head = parse_version(base_blobs.get(path)), parse_version(head_blobs.get(path))
            broken = [found for found in (base, head) if isinstance(found, str)]
            if broken:
                items.append(item(
                    "UNCLASSIFIED", "parse-error", path, "; ".join(broken), diff=project.file_diff(unit, path)
                ))
                continue
            diff = FileDiff(path, base, head, lambda: project.base_fixtures(unit.base))
            diff.classify()
            items += diff.items
            new_tests += diff.new_tests
            appended += diff.appended
            changed_tests += diff.changed_tests
    return Static(items, new_tests, appended, changed_tests)


class Session:
    """The temporary detached worktree of the gate's pytest runs, removed by its path at the end."""

    def __init__(self, project: Project, args, extra: list[str], start: str) -> None:
        self.project = project
        self.python = interpreter(args.python)
        self.extra = extra
        self.timeout = args.timeout
        self.work = Path(args.work_dir).resolve() / "gate"
        if self.work == project.root or project.root in self.work.parents:
            raise UsageError(f"the work directory {self.work} is inside the repository; use one outside it")
        self.work.mkdir(parents=True, exist_ok=True)
        self.hooks = self.work / "no-hooks"
        self.hooks.mkdir(exist_ok=True)
        self.tree = self.work / "worktree"
        self.dir = self.tree if project.prefix == "." else self.tree / project.prefix
        env = copy_env(project.dir, self.work / "probe.jsonl", self.work / "probe.data")
        self.versions = probe(self.python, project.dir, env)
        if not self.versions.get("pytest"):
            raise UsageError("the target interpreter cannot import pytest", package="pytest")
        self.remove()
        self.added = False
        self.git_tree("worktree", "add", "--detach", "--no-checkout", str(self.tree), start, top=True)
        self.added = True

    def git_tree(self, *args: str, top: bool = False) -> None:
        """Run git without hooks, in the worktree, or in the repository when `top` is true."""
        where = self.project.root if top else self.tree
        result = git(where, "-c", f"core.hooksPath={self.hooks}", *args)
        if result.returncode != 0:
            raise UsageError(f"git {args[0]} failed in the gate worktree", log_tail=tail(result.stderr, 5))

    def remove(self) -> None:
        if self.tree.exists():
            git(self.project.root, "worktree", "remove", "--force", str(self.tree))
            shutil.rmtree(self.tree, ignore_errors=True)
        git(self.project.root, "worktree", "prune")

    def close(self) -> None:
        if self.added:
            self.remove()

    def checkout(self, rev: str, overlay: tuple | None) -> None:
        """Check out `rev`; an overlay (other rev, paths there, paths absent there) puts other test-side files in place."""
        self.git_tree("checkout", "--force", "--detach", "--quiet", rev)
        self.git_tree("clean", "-f", "-d", "-x", "-q")
        if overlay:
            other, present, absent = overlay
            if present:
                self.git_tree("checkout", other, "--", *(self.project.outer(p) for p in present))
            for path in absent:
                (self.dir / path).unlink(missing_ok=True)

    def roots(self, rev: str) -> tuple[str, ...]:
        """The import roots of the product packages at `rev`, in the worktree."""
        found = []
        for path in self.project.files(rev):
            if path.endswith(".py") and not self.project.is_test_side(path) and (self.dir / path).parent.joinpath(
                "__init__.py"
            ).is_file():
                found.append(str((self.dir / import_root(self.dir, path)).resolve()))
        return tuple(dict.fromkeys(found))

    def run(self, name: str, rev: str, overlay: tuple | None, selection: list | None, collect_only: bool = False) -> Run:
        self.checkout(rev, overlay)
        records = self.work / f"{name}.jsonl"
        records.write_text("", encoding="utf-8")
        log = self.work / f"{name}.log"
        env = copy_env(self.project.dir, records, self.work / f"{name}.data", self.roots(rev))
        targets = (["--collect-only"] if collect_only else []) + (selection or [])
        cmd = scope_command(self.python, self.versions, targets, self.work / f"{name}-args.txt", self.extra)
        exit_code, timed_out = run_pytest(cmd, self.dir, env, log, self.timeout)
        found = read_records(records)
        if found["rootdir"] and Path(found["rootdir"]).resolve() != self.dir.resolve():
            inner = rel(Path(found["rootdir"]).resolve(), self.dir.resolve())
            raise UsageError(f"pytest's rootdir is {inner} under the project directory; run gate with that --project")
        return Run(exit_code, timed_out, found, log)


def label_entry(nodeid: str, run: Run, tests: dict) -> dict:
    """The label of a new test from its run against the base product code."""
    test = tests.get(nodeid)
    if test is None:
        if run.timed_out:
            return {"nodeid": nodeid, "label": None, "outcome": "not run", "exception": None}
        return {"nodeid": nodeid, "label": "new-API", "outcome": "not collected", "exception": None}
    setup = test["phases"].get("setup") or {}
    outcome = test["outcome"]
    if setup.get("outcome") == "failed":
        label = "new-API"
    elif outcome == "failed":
        label = "catching" if kill_type(test) == "assertion" else "new-API"
    elif outcome in ("passed", "error"):
        label = "hardening"  # an error here is a teardown failure after a passing call
    else:
        label = None
    return {"nodeid": nodeid, "label": label, "outcome": outcome, "exception": failure(test)}


def behavior_changes(base: Run, replay: Run) -> list[dict]:
    """Layer 1: the base tests that pass against the base product code and not against the head product code."""
    found = []
    before, after = base.tests(), replay.tests()
    for nodeid in base.collected():
        if (before.get(nodeid) or {}).get("outcome") != "passed":
            continue
        test = after.get(nodeid)
        if test is not None and test["outcome"] == "passed":
            continue
        if test is None and replay.timed_out:
            continue  # the incomplete-run item covers it
        outcome = test["outcome"] if test else "not collected" if nodeid not in replay.collected() else "not run"
        found.append(item(
            "BEHAVIOR CHANGE", None, node_file(nodeid),
            f"passes against the base product code, and is {outcome} against the head product code",
            nodeid=nodeid, outcome=outcome, exception=failure(test) if test else None,
        ))
    return found


def run_layers(session: Session, unit: Unit, changes: list[Change], mixed: bool, static: Static) -> tuple:
    """Layer 1, the collection evidence, and the new-test labels of a unit; returns (items, new tests, run reports)."""
    items: list[dict] = []
    reports: dict = {}
    modules = [c for c in changes if c.kind == "test-module"]
    whole = any(c.kind != "test-module" for c in changes)
    base_files = None if whole else [c.path for c in modules if c.status != "A"]
    head_files = None if whole else [c.path for c in modules if c.status != "D"]
    base_side = (unit.base, [c.path for c in changes if c.status != "A"], [c.path for c in changes if c.status == "A"])
    head_side = (unit.head, [c.path for c in changes if c.status != "D"], [c.path for c in changes if c.status == "D"])

    def run(label: str, rev: str, overlay: tuple | None, selection: list | None, collect_only: bool = False) -> Run:
        found = session.run(f"{unit.id}-{label}", rev, overlay, selection, collect_only)
        reports[label] = found.report(selection)
        if found.timed_out:
            items.append(item(
                "UNCLASSIFIED", "incomplete-run", None, f"the {label} run stopped after {session.timeout:g} seconds"
            ))
        return found

    head = run("head", unit.head, None, head_files, collect_only=True) if whole or head_files else None
    if head is not None and not head.timed_out and (head.found["collected"] is None or head.exit_code in (3, 4)):
        items.append(item(
            "UNCLASSIFIED", "collection-error", None,
            f"pytest exited with {head.exit_code} before it collected the head tests; see {head.log}",
        ))
    replay = base = None
    if whole or base_files:
        if mixed:
            replay = run("replay", unit.head, base_side, base_files)
        base = run("base", unit.base, None, base_files)
        if not base.timed_out and (base.found["collected"] is None or base.exit_code in (3, 4)):
            raise UsageError(
                f"pytest exited with {base.exit_code} on the base tests at {unit.base}; see log_tail",
                log_tail=tail(base.log.read_text(encoding="utf-8", errors="replace"), LOG_TAIL),
            )
    for found, side in ((base, "base"), (head, "head")):
        for nodeid in found.found["collect_errors"] if found else []:
            items.append(item("UNCLASSIFIED", "collection-error", node_file(nodeid), f"collection fails at {side}", nodeid=nodeid))
    if replay is not None:
        items += behavior_changes(base, replay)

    evidence = base is not None and base.complete() and (head is None or head.complete())
    base_ids = set(base.collected()) if evidence else set()
    head_ids = set(head.collected()) if head is not None else set()
    appended = {i["nodeid"]: i for i in static.items if i["subtype"] == "appended-cases"}
    removed = [i["nodeid"] for i in static.items if i["subtype"] == "removed-test"]
    if evidence:
        for nodeid in base.collected():
            if nodeid in head_ids:
                continue
            key = function_key(nodeid)
            if any(key == k or key.startswith(k + "::") for k in removed):
                continue
            if key in appended:
                entry = appended[key]
                entry.update({"class": "WEAKENING", "subtype": "missing-node-id"})
                entry.setdefault("missing", []).append(nodeid)
                entry["detail"] = "the appended cases change base node IDs: " + ", ".join(entry["missing"])
            else:
                items.append(item(
                    "WEAKENING", "missing-node-id", node_file(nodeid), "a base node ID is not collected at head",
                    nodeid=nodeid,
                ))
    else:
        unconfirmed(appended.values())

    new_ids = []
    if head is not None and head.complete():
        keys = set(static.new_tests)
        for nodeid in head.collected():
            key = function_key(nodeid)
            if key in keys or (evidence and key in appended and nodeid not in base_ids):
                new_ids.append(nodeid)
    entries = []
    if new_ids:
        label = run("label", unit.base, head_side, sorted({node_file(n) for n in new_ids}))
        tests = label.tests()
        entries = [label_entry(nodeid, label, tests) for nodeid in new_ids]
    seen = {function_key(n) for n in new_ids}
    entries += [
        {"nodeid": key, "label": None, "outcome": "not collected at head", "exception": None}
        for key in static.new_tests if key not in seen
    ]
    return items, entries, reports


def unconfirmed(appended) -> None:
    """Mark appended parametrize cases without collection evidence as UNCLASSIFIED."""
    for entry in appended:
        entry.update({
            "class": "UNCLASSIFIED", "subtype": "no-collection-evidence",
            "detail": "appends literal parametrize cases, but no collection shows that each base node ID stays",
        })


def check_unit(project: Project, session: Session | None, unit: Unit) -> dict:
    changes, product = project.changes(unit)
    mixed = bool(product)
    static = static_layer(project, unit, changes)
    items = list(static.items)
    reports: dict = {}
    if session is not None and changes:
        found, new_tests, reports = run_layers(session, unit, changes, mixed, static)
        items += found
    else:
        unconfirmed(i for i in items if i["subtype"] == "appended-cases")
        new_tests = [
            {"nodeid": key, "label": None, "outcome": "not run", "exception": None} for key in static.new_tests
        ]
    items = [{"id": f"{unit.id}-i{n}", **entry} for n, entry in enumerate(items, start=1)]
    failing = [i for i in items if i["class"] in FAILING]
    if mixed and failing:
        status = "fail"
    elif not mixed and changes and failing:
        status = "needs evidence"
    else:
        status = "pass"
    diff = project.git("diff", "--no-color", "--no-ext-diff", "--no-renames", "--full-index", "--binary", unit.base, unit.head)
    return {
        "id": unit.id,
        "base": unit.base,
        "head": unit.head,
        "subject": unit.subject,
        "mixed": mixed,
        "status": status,
        "diff_sha256": sha256(diff.encode("utf-8")),
        "product_files": product,
        "test_files": [c._asdict() for c in changes],
        "runs": reports,
        "items": items,
        "new_tests": new_tests,
        "changed_tests": static.changed_tests,
    }


def gate_command(args, extra: list[str]) -> dict:
    if not args.static_only and not (args.python and args.work_dir):
        raise UsageError("gate needs --python and --work-dir, or --static-only")
    if args.timeout <= 0:
        raise UsageError("--timeout must be more than 0 seconds")
    project = Project(args.project)
    head = project.commit(args.head)
    base = project.commit(args.base)
    merge_base = project.git("merge-base", base, head).strip()
    units = project.units(merge_base, head, args.per_commit)
    uncommitted = []
    if head == project.commit("HEAD"):
        status = git(project.dir, "status", "--porcelain", "--untracked-files=normal", "--", ".")
        uncommitted = status.stdout.splitlines()
    session = None if args.static_only else Session(project, args, extra, head)
    try:
        results = [check_unit(project, session, unit) for unit in units]
    finally:
        if session is not None:
            session.close()

    every = [i for unit in results for i in unit["items"]]
    new_tests = [entry for unit in results for entry in unit["new_tests"]]
    files = {}
    if args.work_dir:
        folder = Path(args.work_dir).resolve() / "gate"
        folder.mkdir(parents=True, exist_ok=True)
        lists = {
            "new_tests": [e["nodeid"] for e in new_tests if e["outcome"] != "not collected at head"],
            "changed_tests": [key for unit in results for key in unit["changed_tests"]],
        }
        for name, nodeids in lists.items():
            path = folder / f"{name.replace('_', '-')}.txt"
            path.write_text("".join(f"{n}\n" for n in dict.fromkeys(nodeids)), encoding="utf-8")
            files[name] = str(path)
    counts = Counter(i["class"] for i in every)
    labels = Counter(entry["label"] or "unlabeled" for entry in new_tests)
    return {
        "summary": {
            "passed": not any(unit["status"] == "fail" for unit in results),
            "base": args.base,
            "head": args.head,
            "merge_base": merge_base,
            "head_sha": head,
            "per_commit": args.per_commit,
            "static_only": args.static_only,
            "units": len(results),
            "failed_units": sum(1 for unit in results if unit["status"] == "fail"),
            "needs_evidence_units": sum(1 for unit in results if unit["status"] == "needs evidence"),
            "items": {cls: counts[cls] for cls in CLASSES},
            "new_tests": {label: labels[label] for label in (*LABELS, "unlabeled")},
            "uncommitted": len(uncommitted),
            "examples": {
                "failing": [
                    " ".join(str(x) for x in (i["id"], i["class"], i["subtype"], i["nodeid"] or i["path"]) if x)
                    for i in every if i["class"] in FAILING
                ][:EXAMPLES],
                "uncommitted": uncommitted[:EXAMPLES],
            },
        },
        "project": str(project.dir),
        "units": results,
        "new_tests": new_tests,
        "files": files,
    }


def pin_command(args) -> dict:
    if args.record:
        if args.quote is not None:
            raise UsageError("--quote goes with --check")
        return pin_sources(Path(args.record).resolve(), args.source)
    if args.source:
        raise UsageError("--source goes with --record")
    return check_pins(Path(args.check).resolve(), args.quote)


def pin_sources(record: Path, specs: list[str]) -> dict:
    """Write each source's text and SHA-256 hash to a new pin record."""
    if not specs:
        raise UsageError("pin --record needs at least one --source NAME=PATH")
    sources = []
    for spec in specs:
        name, sep, path = spec.partition("=")
        if not (sep and name and path):
            raise UsageError(f"--source {spec!r} is not NAME=PATH")
        if any(source["name"] == name for source in sources):
            raise UsageError(f"the source name {name} appears twice")
        try:
            data = Path(path).read_bytes()
        except OSError as error:
            raise UsageError(f"cannot read the source {path}: {error.strerror}") from error
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError as error:
            raise UsageError(f"the source {path} is not UTF-8 text") from error
        sources.append({
            "name": name, "path": str(Path(path).resolve()), "sha256": sha256(data), "bytes": len(data), "text": text,
        })
    pinned_at = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        with open(record, "x", encoding="utf-8") as handle:
            json.dump({"pinned_at": pinned_at, "sources": sources}, handle, indent=1)
    except FileExistsError as error:
        raise UsageError(f"the pin record {record} exists; pin writes a new record and never changes one") from error
    except OSError as error:
        raise UsageError(f"cannot write the pin record {record}: {error.strerror}") from error
    return {
        "summary": {
            "record": str(record),
            "pinned_at": pinned_at,
            "sources": len(sources),
            "sha256": {source["name"]: source["sha256"] for source in sources},
        },
        "sources": [{k: v for k, v in source.items() if k != "text"} for source in sources],
    }


def check_pins(record: Path, quote: str | None) -> dict:
    """Recompute the hash of each pinned text, and find the pinned sources that contain a quote."""
    data = load_json(str(record), "pin record")
    sources = data.get("sources")
    if not isinstance(sources, list) or not all(
        isinstance(s, dict) and isinstance(s.get("text"), str) and "name" in s and "sha256" in s for s in sources
    ):
        raise UsageError(f"{record} is not a pin record")
    entries = [
        {"name": s["name"], "sha256": s["sha256"], "intact": sha256(s["text"].encode("utf-8")) == s["sha256"]}
        for s in sources
    ]
    changed = [entry["name"] for entry in entries if not entry["intact"]]
    found = None
    if quote is not None:
        needle = " ".join(quote.split())
        if not needle:
            raise UsageError("--quote is empty")
        found = [{"name": s["name"], "sha256": s["sha256"]} for s in sources if needle in " ".join(s["text"].split())]
    return {
        "summary": {
            "passed": not changed and (found is None or bool(found)),
            "record": str(record),
            "pinned_at": data.get("pinned_at"),
            "sources": len(entries),
            "changed": changed,
            "quote_found_in": None if found is None else [entry["name"] for entry in found],
        },
        "sources": entries,
        "quote": None if quote is None else {"text": quote, "found_in": found},
    }
