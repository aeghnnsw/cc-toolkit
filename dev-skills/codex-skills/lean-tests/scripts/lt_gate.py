"""gate: the weakening gate of review.

Imported by lean_tests.py; never run directly. The gate checks gate units:
by default one unit, the whole range from the merge base of a base ref and
a head ref to the head ref; with --per-commit, one unit per commit. A gate
unit that changes product code is a mixed change; documentation outside the
product packages is no product code. Layer 1 runs the changed base test
modules against the head product code in a temporary detached worktree.
Layer 2 classifies each test-side change of a unit from the syntax trees of
its two versions. The same worktree collects the head tests, which gives
the collection evidence, and runs each new test against the base product
code, which gives its label. A BEHAVIOR CHANGE, WEAKENING, or UNCLASSIFIED
item fails a mixed change; when each of its failing items lacks collection
evidence, the mixed change needs evidence, which also fails the gate. A
test-only gate unit needs evidence and does not fail the gate.
"""

from __future__ import annotations

import ast
import builtins
import copy
import difflib
import re
import shutil
import subprocess
from collections import Counter
from pathlib import Path, PurePosixPath
from typing import Callable, NamedTuple

from lt_common import (
    EXAMPLES, PARSE_ERRORS, UsageError, git, import_root, is_string_statement, node_file, parse_failure, rel, sha256,
    tail,
)
from lt_coverage import is_test_path
from lt_scan import Module, TestFunction, dotted, function_id, is_literal
from lt_suite import (
    copy_env, failure, interpreter, kill_type, probe, pytest_command, read_records, run_pytest, test_entries,
)

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
# Base classes that define no test, so a test method of a subclass with only these bases overrides nothing.
PLAIN_BASES = frozenset({
    "object", "TestCase", "unittest.TestCase", "IsolatedAsyncioTestCase", "unittest.IsolatedAsyncioTestCase",
})
# xunit setup and teardown functions and methods: a new one runs around existing tests.
XUNIT = frozenset({
    "setup_module", "teardown_module", "setup_function", "teardown_function", "setup_class", "teardown_class",
    "setup_method", "teardown_method", "setup", "teardown", "setUp", "tearDown", "setUpClass", "tearDownClass",
    "setUpModule", "tearDownModule",
})
# Calls that change a module, an object, or a class of the tests or the product.
CALL_SIGNALS = frozenset({"setattr", "delattr", "reload", "importlib.reload", "builtins.setattr", "builtins.delattr"})
BUILTIN_NAMES = frozenset(dir(builtins))
# fixture_name returns it for a fixture whose name argument is not a literal.
COMPUTED = "\0computed fixture name\0"
# Statements whose blocks bind names in the enclosing scope.
BLOCKS = (ast.If, ast.Try, ast.With, ast.AsyncWith, ast.For, ast.AsyncFor, ast.While)
# Nodes that open a scope of their own.
SCOPES = (
    ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda, ast.ListComp, ast.SetComp, ast.DictComp,
    ast.GeneratorExp,
)
BUILTIN_FIXTURES = frozenset({
    "cache", "capfd", "capfdbinary", "caplog", "capsys", "capsysbinary", "doctest_namespace", "monkeypatch",
    "pytestconfig", "pytester", "record_property", "record_testsuite_property", "record_xml_attribute", "recwarn",
    "request", "testdir", "tmp_path", "tmp_path_factory", "tmpdir", "tmpdir_factory",
})
# Replaces the expected value of an `assert x == literal`; no test source contains it.
EXPECTED = "\0lean-tests expected value\0"


class Unit(NamedTuple):
    """One gate unit: the change from `base` to `head`. `subject` is the commit subject of a per-commit unit."""

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
    """One side of a changed test-side Python file: its text, syntax tree, scan module, and import aliases."""

    text: str
    tree: ast.Module
    module: Module
    aliases: dict


class Static(NamedTuple):
    """The layer 2 result of a unit or a file: its items, and the function keys of its new and changed tests.

    `subclass_tests` are the new tests in an existing test class with a base
    class outside the module: such a test can replace an inherited test with
    the same node ID.
    """

    items: list
    new_tests: list
    changed_tests: list
    subclass_tests: list

    @classmethod
    def empty(cls) -> Static:
        return cls([], [], [], [])

    def extend(self, other: Static) -> None:
        for mine, theirs in zip(self, other):
            mine.extend(theirs)


class Overlay(NamedTuple):
    """The test-side files of another commit `rev`: the paths that it has, and the paths that it lacks."""

    rev: str
    present: list
    absent: list


class Run(NamedTuple):
    """One pytest run in the worktree."""

    exit_code: int | None
    timed_out: bool
    found: dict
    log: Path

    def complete(self) -> bool:
        return not self.timed_out and self.found["collected"] is not None

    def broken(self) -> bool:
        """True when pytest stopped before it collected the tests, but not on the time limit."""
        return not self.timed_out and (self.found["collected"] is None or self.exit_code in (3, 4))

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


def item(
    cls: str, subtype: str | None, path: str | None, detail: str, nodeid: str | None = None, line: int | None = None,
    **extra,
) -> dict:
    return {"class": cls, "subtype": subtype, "path": path, "nodeid": nodeid, "line": line, "detail": detail, **extra}


def new_test(nodeid: str, outcome: str, label: str | None = None, exception: str | None = None) -> dict:
    """One entry of the new tests of a unit."""
    return {"nodeid": nodeid, "label": label, "outcome": outcome, "exception": exception}


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
        self.fixture_names: dict[str, frozenset] = {}
        self.packages: dict[str, frozenset] = {}

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
        if rev not in self.fixture_names:
            names = set(BUILTIN_FIXTURES)
            paths = [path for path in self.files(rev) if path.endswith(".py") and self.is_test_side(path)]
            for data in self.blobs(rev, paths).values():
                try:
                    tree = ast.parse(data.decode("utf-8"))
                except PARSE_ERRORS:
                    continue
                names.update(defined_fixtures(tree, import_aliases(tree)))
            self.fixture_names[rev] = frozenset(names)
        return self.fixture_names[rev]

    def package_dirs(self, rev: str) -> frozenset:
        """The repository paths of the directories with an `__init__.py` at `rev`."""
        if rev not in self.packages:
            listing = self.git("ls-tree", "-r", "-z", "--name-only", rev)
            names = (PurePosixPath(name) for name in listing.split("\0") if name)
            self.packages[rev] = frozenset(str(name.parent) for name in names if name.name == "__init__.py")
        return self.packages[rev]

    def documentation(self, unit: Unit, name: str) -> bool:
        """True for a documentation file outside the product packages at both ends of the unit."""
        path = PurePosixPath(name)
        if path.suffix not in DOCUMENTATION:
            return False
        packages = self.package_dirs(unit.base) | self.package_dirs(unit.head)
        return not any(str(parent) in packages for parent in path.parents)

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
                if not self.documentation(unit, name):
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
            elif not self.documentation(unit, name):
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


def import_aliases(tree: ast.AST) -> dict:
    """The full dotted name of each name that an import binds with another name, for example fx for pytest.fixture."""
    found = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update((alias.asname, alias.name) for alias in node.names if alias.asname)
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            found.update(
                (alias.asname or alias.name, f"{node.module}.{alias.name}") for alias in node.names if alias.name != "*"
            )
    return found


def resolved(node: ast.AST, aliases: dict) -> str | None:
    """The dotted name of an expression, with its first part resolved through the import aliases."""
    name = dotted(node)
    if not name:
        return name
    first, dot, rest = name.partition(".")
    return aliases.get(first, first) + dot + rest


def fixture_decorator(decorator: ast.AST, aliases: dict) -> ast.Call | bool:
    """The call of a fixture decorator, True for a fixture decorator without a call, else False."""
    call = decorator if isinstance(decorator, ast.Call) else None
    if resolved(call.func if call else decorator, aliases) not in FIXTURE_DECORATORS:
        return False
    return call or True


def fixture_name(func: ast.AST, aliases: dict) -> str | None:
    """The name of the fixture that a function defines, COMPUTED for a name that is no literal, or None."""
    for decorator in func.decorator_list:
        call = fixture_decorator(decorator, aliases)
        if not call:
            continue
        for keyword in call.keywords if isinstance(call, ast.Call) else []:
            if keyword.arg == "name":
                return str(keyword.value.value) if isinstance(keyword.value, ast.Constant) else COMPUTED
        return func.name
    return None


def autouse(func: ast.AST, aliases: dict) -> bool:
    for decorator in func.decorator_list:
        call = fixture_decorator(decorator, aliases)
        for keyword in call.keywords if isinstance(call, ast.Call) else []:
            if keyword.arg == "autouse":
                return not (isinstance(keyword.value, ast.Constant) and keyword.value.value is False)
    return False


def defined_fixtures(stmt: ast.AST, aliases: dict) -> list[str]:
    """The literal names of the fixtures that a statement defines."""
    names = []
    for sub in ast.walk(stmt):
        if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
            name = fixture_name(sub, aliases)
            if name and name != COMPUTED:
                names.append(name)
    return names


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


def scope_bindings(stmt: ast.stmt) -> list[str]:
    """Every name that a statement binds in its scope, also inside its if, try, with, for, and while blocks."""
    names = bound_names(stmt)
    if names is not None:
        return names
    found = []
    pending = [stmt]
    while pending:
        node = pending.pop()
        if node is not stmt and isinstance(node, SCOPES):
            if not isinstance(node, (ast.Lambda, ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)):
                found.append(node.name)
            continue
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            found += bound_names(node) or []
        elif isinstance(node, ast.Name) and not isinstance(node.ctx, ast.Load):
            found.append(node.id)
        elif isinstance(node, ast.ExceptHandler) and node.name:
            found.append(node.name)
        pending += ast.iter_child_nodes(node)
    return found


def level(chain: list) -> str:
    return "class-level" if chain else "module-level"


def without(node: ast.AST, field: str) -> ast.AST:
    """A shallow copy of a definition with an empty `field`, for example its body."""
    bare = copy.copy(node)
    setattr(bare, field, [])
    return bare


def same_except(before: ast.AST, after: ast.AST, field: str) -> bool:
    """True when two definitions are equal apart from `field`."""
    return ast.dump(without(before, field)) == ast.dump(without(after, field))


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


def skip_markers(node: ast.AST, aliases: dict) -> Counter:
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
            name = aliases.get(target.id, target.id).rsplit(".", 1)[-1]
        else:
            continue
        if name in SKIP_NAMES:
            found[ast.dump(sub)] += 1
    return found


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
    if len(before.decorator_list) != len(after.decorator_list) or not same_except(before, after, "decorator_list"):
        return False
    pairs = [(b, a) for b, a in zip(before.decorator_list, after.decorator_list) if ast.dump(b) != ast.dump(a)]
    if len(pairs) != 1 or not all(isinstance(node, ast.Call) for node in pairs[0]):
        return False
    old, new = pairs[0]
    if not (dotted(old.func) or "").endswith("parametrize") or ast.dump(old.func) != ast.dump(new.func):
        return False
    (old_values, old_rest), (new_values, new_rest) = parametrize_values(old), parametrize_values(new)
    if old_rest != new_rest or not isinstance(old_values, (ast.List, ast.Tuple)):
        return False
    if type(new_values) is not type(old_values):
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

    def __init__(
        self, path: str, base: Version | None, head: Version | None, base_fixtures: Callable[[], frozenset]
    ) -> None:
        self.path = path
        self.base = base
        self.head = head
        self.base_fixtures = base_fixtures
        self.found = Static.empty()

    def classify(self) -> Static:
        self.diff_scope(
            expand_imports(self.base.tree.body if self.base else []),
            expand_imports(self.head.tree.body if self.head else []),
            [],
            BUILTIN_NAMES if self.base is not None else frozenset(),
        )
        reasons = sorted({r for v in (self.base, self.head) if v is not None for r in unresolvable(v.tree)})
        if reasons:
            self.found.items[:] = [i for i in self.found.items if i["class"] != "SAFE"]
            self.found.items.insert(0, item(
                "UNCLASSIFIED", "unresolvable-binding", self.path,
                "the module binds names that the binding rule cannot see: " + ", ".join(reasons),
            ))
        return self.found

    def key(self, chain: list, stmt: ast.AST) -> str:
        names = [(head or base).name for base, head in chain]
        return "::".join([self.path, *names, stmt.name]) if hasattr(stmt, "name") else self.path

    def add(self, cls: str, subtype: str, chain: list, before: ast.AST | None, after: ast.AST | None, detail: str,
            **extra) -> None:
        stmt = after or before
        self.found.items.append(item(
            cls, subtype, self.path, detail,
            nodeid=self.key(chain, stmt) if hasattr(stmt, "name") else None,
            line=stmt.lineno,
            **extra,
            diff=unified(
                self.path,
                self.segment(self.base, before) if before is not None else "",
                self.segment(self.head, after) if after is not None else "",
            ),
        ))

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

    def skip_added(self, before: ast.AST, after: ast.AST) -> bool:
        """True when `after` has a skip or xfail marker or call that `before` does not have."""
        return bool(skip_markers(after, self.head.aliases) - skip_markers(before, self.base.aliases))

    def inherited(self, cls: ast.ClassDef, seen: frozenset) -> frozenset | None:
        """The names that a class inherits from its base classes at base; None for a base class outside the module."""
        classes = {node.name: node for node in self.base.tree.body if isinstance(node, ast.ClassDef)}
        names: set = set()
        for base in cls.bases:
            name = dotted(base) or ""
            if name in PLAIN_BASES:
                continue
            parent = classes.get(name)
            further = None if parent is None or name in seen else self.inherited(parent, seen | {name})
            if further is None:
                return None
            names |= further
            names.update(n for stmt in parent.body for n in scope_bindings(stmt))
        return frozenset(names)

    def diff_scope(self, before: list, after: list, chain: list, outer: frozenset | None) -> None:
        """Classify the changes between the statements of one scope at base and at head.

        `outer` holds the names that the scope gets from outside its own
        statements at base: the builtin names of an existing module, or the
        names that a class inherits. None means a base class outside the module.
        """
        base_count = Counter(name for stmt in before for name in scope_bindings(stmt))
        head_count = Counter(name for stmt in after for name in scope_bindings(stmt))
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
            shadowed = sorted(set(names or []) & (outer or frozenset()))
            if names is None:
                self.scope_statement(None, stmt, chain)
            elif not all(base_count[n] == 0 and head_count[n] == 1 for n in names):
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
            elif shadowed:
                source = "a base class" if chain else "the builtins"
                self.add(
                    "UNCLASSIFIED", "rebinding", chain, None, stmt,
                    f"binds {', '.join(shadowed)}, which replaces a name from {source}",
                )
            elif outer is None and not self.test_keys(stmt, chain):
                self.add(
                    "UNCLASSIFIED", "rebinding", chain, None, stmt,
                    f"binds {', '.join(names)} in a class with a base class outside the module, so it can replace "
                    "an inherited name",
                )
            else:
                if outer is None:
                    self.found.subclass_tests.extend(self.test_keys(stmt, chain))
                self.new_binding(stmt, chain)
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
        if after is not None and self.base is not None and skip_markers(after, self.head.aliases):
            self.add("WEAKENING", "skip", chain, before, after, f"adds a {level(chain)} skip or xfail")
        else:
            verb = "adds" if before is None else "removes"
            self.add("UNCLASSIFIED", "scope-statement", chain, before, after, f"{verb} a {level(chain)} statement")

    def new_binding(self, stmt: ast.AST, chain: list) -> None:
        names = bound_names(stmt)
        existing = self.base is not None
        if isinstance(stmt, (ast.Import, ast.ImportFrom)):
            hooks = [n for n in names if n in XUNIT or n in self.base_fixtures()]
            if hooks:
                detail = f"imports {', '.join(hooks)}, the name of an xunit function or an existing fixture"
                self.add("UNCLASSIFIED", "signal", chain, None, stmt, detail)
            else:
                self.add("SAFE", "new-import", chain, None, stmt, f"imports {', '.join(names)}")
        elif isinstance(stmt, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
            if existing and "__test__" in names:
                detail = f"binds a {level(chain)} __test__, which can turn off the collection of existing tests"
                self.add("WEAKENING", "skip", chain, None, stmt, detail)
            elif existing and skip_markers(stmt, self.head.aliases):
                self.add("WEAKENING", "skip", chain, None, stmt, f"adds a {level(chain)} skip or xfail marker")
            elif "pytest_plugins" in names:
                self.add("UNCLASSIFIED", "signal", chain, None, stmt, "binds pytest_plugins")
            elif not isinstance(stmt, ast.AugAssign) and stmt.value is not None and is_literal(stmt.value):
                self.add("SAFE", "new-constant", chain, None, stmt, f"binds the constant {', '.join(names)}")
            else:
                self.add(
                    "UNCLASSIFIED", "signal", chain, None, stmt,
                    f"a {level(chain)} statement other than an import, a constant, a def, or a class",
                )
        else:
            found = self.signals(stmt)
            tests = self.test_keys(stmt, chain)
            self.found.new_tests.extend(tests)
            fixtures = defined_fixtures(stmt, self.head.aliases)
            extra = {"fixtures": fixtures} if fixtures else {}
            if found:
                self.add("UNCLASSIFIED", "signal", chain, None, stmt, "; ".join(found))
            elif existing and not tests and skip_markers(stmt, self.head.aliases):
                detail = f"adds a skip or xfail in the new definition {stmt.name}"
                self.add("WEAKENING", "skip", chain, None, stmt, detail)
            elif tests:
                self.add("SAFE", "new-test", chain, None, stmt, f"adds {len(tests)} test function(s)", **extra)
            else:
                self.add("SAFE", "new-definition", chain, None, stmt, f"defines {stmt.name}", **extra)

    def signals(self, stmt: ast.AST) -> list[str]:
        """The infrastructure signals of a new definition: changes it can make to the tests around it.

        A name that an import binds counts as non-local: it can name a module of the product or of the tests.
        """
        aliases = self.head.aliases
        local = set()
        patchers = set()
        for sub in ast.walk(stmt):
            if isinstance(sub, ast.arg):
                local.add(sub.arg)
            elif isinstance(sub, ast.Name) and not isinstance(sub.ctx, ast.Load):
                local.add(sub.id)
            elif isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                local.add(sub.name)
            elif isinstance(sub, ast.ExceptHandler) and sub.name:
                local.add(sub.name)
            patcher = isinstance(sub, ast.Assign) and isinstance(sub.value, ast.Call)
            if patcher and "patch" in (resolved(sub.value.func, aliases) or ""):
                patchers.update(t.id for t in targets_of(sub) if isinstance(t, ast.Name))
        found = []
        if self.base is not None and isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)) and stmt.name in XUNIT:
            found.append(f"xunit setup or teardown function {stmt.name}")
        for sub in ast.walk(stmt):
            if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if autouse(sub, aliases):
                    found.append(f"autouse fixture {sub.name}")
                name = fixture_name(sub, aliases)
                if name == COMPUTED:
                    found.append(f"fixture {sub.name} takes its name from an expression")
                elif name and name in self.base_fixtures():
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
                name = resolved(sub.func, aliases) or ""
                receiver = sub.func.value if isinstance(sub.func, ast.Attribute) else None
                if name in CALL_SIGNALS:
                    found.append(f"{name}()")
                elif receiver is not None and sub.func.attr == "start" and (
                    (isinstance(receiver, ast.Call) and "patch" in (resolved(receiver.func, aliases) or ""))
                    or (isinstance(receiver, ast.Name) and receiver.id in patchers)
                ):
                    found.append("patcher .start()")
            elif isinstance(sub, (ast.Attribute, ast.Name)):
                name = resolved(sub, aliases) or ""
                if name == "sys.modules":
                    found.append("sys.modules")
                elif isinstance(sub, ast.Name) and name.split(".")[0] in ("builtins", "__builtins__"):
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
            if not same_except(before, after, "body"):
                if self.skip_added(without(before, "body"), without(after, "body")):
                    self.add("WEAKENING", "skip", chain, before, after, "adds or changes a skip or xfail marker")
                else:
                    self.add("UNCLASSIFIED", "changed-definition", chain, before, after, "changes the class header")
            self.diff_scope(
                expand_imports(before.body), expand_imports(after.body), [*chain, (before, after)],
                self.inherited(before, frozenset()),
            )
        elif isinstance(after, (ast.FunctionDef, ast.AsyncFunctionDef)):
            self.modified_function(before, after, chain)
        elif self.skip_added(before, after):
            self.add("WEAKENING", "skip", chain, before, after, "adds or changes a skip or xfail marker")
        else:
            detail = f"changes {', '.join(bound_names(after))}"
            self.add("UNCLASSIFIED", "changed-definition", chain, before, after, detail)

    def modified_function(self, before: ast.AST, after: ast.AST, chain: list) -> None:
        test = self.is_test(after, chain)
        if test and appended_cases(before, after):
            self.add("SAFE", "appended-cases", chain, before, after, "appends literal parametrize cases")
            return
        if test:
            self.found.changed_tests.append(self.key(chain, after))
            values = self.expected_literal(before, after)
            if values:
                self.add(
                    "WEAKENING", "expected-literal", chain, before, after,
                    f"changes the expected value of one == assertion from {values[0]} to {values[1]}",
                    old=values[0], new=values[1],
                )
                return
        what = "test" if test else "fixture" if fixture_name(after, self.head.aliases) else "function"
        if self.skip_added(before, after):
            detail = f"adds or changes a skip or xfail in an existing {what}"
            self.add("WEAKENING", "skip", chain, before, after, detail)
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
        base_checks = TestFunction(self.base.module, before, [base for base, _ in chain]).checks
        head_test = TestFunction(self.head.module, after, [head for _, head in chain])
        old = Counter(ast.dump(node) for _, node in base_checks)
        new = Counter(ast.dump(node) for _, node in head_test.checks)
        missing = old - new
        if not missing:
            return None
        added = new - old
        for _, node in head_test.checks:
            if isinstance(node, ast.Assert) and added[ast.dump(node)]:
                verdict = head_test.assert_verdict(node.test)
                if verdict:
                    return verdict[0]
        gone = [node for _, node in base_checks if missing[ast.dump(node)]]
        calls = [sub for node in gone for sub in ast.walk(node) if isinstance(sub, ast.Call)]
        names = {(dotted(sub.func) or "").rsplit(".", 1)[-1] for sub in calls}
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
    return Version(text, tree, Module(text, tree), import_aliases(tree))


def static_layer(project: Project, unit: Unit, changes: list[Change]) -> Static:
    """Layer 2: classify each test-side change of a unit."""
    python = [c.path for c in changes if c.kind in ("test-module", "helper")]
    base_blobs = project.blobs(unit.base, python)
    head_blobs = project.blobs(unit.head, python)
    result = Static.empty()
    items = result.items
    for change in changes:
        path = change.path
        verb = {"A": "adds", "D": "removes", "M": "changes"}[change.status]
        if change.kind == "conftest":
            diff = project.file_diff(unit, path)
            items.append(item("UNCLASSIFIED", "conftest", path, f"{verb} a conftest.py", diff=diff))
        elif change.kind == "data":
            diff = project.file_diff(unit, path)
            items.append(item("UNCLASSIFIED", "test-data", path, f"{verb} a test-side file", diff=diff))
        elif change.kind == "config":
            header = CONFIG_SECTIONS[path]
            before = split_config(header, project.text(unit.base, path) or "")[0]
            after = split_config(header, project.text(unit.head, path) or "")[0]
            ndiff = difflib.ndiff(before.splitlines(), after.splitlines())
            added = [line[2:] for line in ndiff if line.startswith("+ ")]
            diff = unified(path, before, after)
            if any(DESELECTION.search(line) for line in added):
                detail = "adds a deselect, ignore, -k, or -m option"
                items.append(item("WEAKENING", "config-deselect", path, detail, diff=diff))
            else:
                detail = f"{verb} the pytest configuration"
                items.append(item("UNCLASSIFIED", "configuration", path, detail, diff=diff))
        else:
            base, head = parse_version(base_blobs.get(path)), parse_version(head_blobs.get(path))
            broken = [reason for reason in (base, head) if isinstance(reason, str)]
            if broken:
                diff = project.file_diff(unit, path)
                items.append(item("UNCLASSIFIED", "parse-error", path, "; ".join(broken), diff=diff))
                continue
            result.extend(FileDiff(path, base, head, lambda: project.base_fixtures(unit.base)).classify())
    return result


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

    def checkout(self, rev: str, overlay: Overlay | None) -> None:
        """Check out `rev`; an overlay puts the test-side files of another commit in place."""
        self.git_tree("checkout", "--force", "--detach", "--quiet", rev)
        self.git_tree("clean", "-f", "-d", "-x", "-q")
        if overlay:
            if overlay.present:
                self.git_tree("checkout", overlay.rev, "--", *(self.project.outer(p) for p in overlay.present))
            for path in overlay.absent:
                (self.dir / path).unlink(missing_ok=True)

    def roots(self, rev: str) -> tuple[str, ...]:
        """The import roots of the product packages at `rev`, in the worktree."""
        found = []
        for path in self.project.files(rev):
            if not path.endswith(".py") or self.project.is_test_side(path):
                continue
            if (self.dir / path).parent.joinpath("__init__.py").is_file():
                found.append(str((self.dir / import_root(self.dir, path)).resolve()))
        return tuple(dict.fromkeys(found))

    def run(
        self, name: str, rev: str, overlay: Overlay | None, selection: list | None, collect_only: bool = False
    ) -> Run:
        self.checkout(rev, overlay)
        records = self.work / f"{name}.jsonl"
        records.write_text("", encoding="utf-8")
        log = self.work / f"{name}.log"
        env = copy_env(self.project.dir, records, self.work / f"{name}.data", self.roots(rev))
        targets = (["--collect-only"] if collect_only else []) + (selection or [])
        argfile = self.work / f"{name}-args.txt"
        cmd = pytest_command(self.python, self.versions, targets, argfile, every_test=True) + self.extra
        exit_code, timed_out = run_pytest(cmd, self.dir, env, log, self.timeout)
        found = read_records(records)
        if found["rootdir"] and Path(found["rootdir"]).resolve() != self.dir.resolve():
            inner = rel(Path(found["rootdir"]).resolve(), self.dir.resolve())
            raise UsageError(f"pytest's rootdir is {inner} under the project directory; run gate with that --project")
        return Run(exit_code, timed_out, found, log)


def label_entry(nodeid: str, run: Run, tests: dict) -> dict:
    """The label of a new test from its run against the base product code.

    catching: an assertion failure in the call phase. new-API: a collection
    error, a setup error, or an exception other than an assertion failure.
    hardening: a pass.
    """
    test = tests.get(nodeid)
    if test is None:
        if run.timed_out:
            return new_test(nodeid, "not run")
        return new_test(nodeid, "not collected", label="new-API")
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
    return new_test(nodeid, outcome, label=label, exception=failure(test))


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


def item_keys(entry: dict, keys: list[str]) -> list[str]:
    """The function keys among `keys` of the tests that a new-test item adds."""
    node = entry["nodeid"]
    return [key for key in keys if key == node or key.startswith(node + "::")]


def run_layers(session: Session, unit: Unit, changes: list[Change], mixed: bool, static: Static) -> tuple:
    """Layer 1, the collection evidence, and the new-test labels of a unit; returns (items, new tests, run reports).

    The items are the layer 2 items, revised with the evidence of the runs, and then the items of the runs.
    """
    items: list[dict] = []
    reports: dict = {}
    modules = [c for c in changes if c.kind == "test-module"]
    whole = any(c.kind != "test-module" for c in changes)
    base_files = None if whole else [c.path for c in modules if c.status != "A"]
    head_files = None if whole else [c.path for c in modules if c.status != "D"]
    added = [c.path for c in changes if c.status == "A"]
    deleted = [c.path for c in changes if c.status == "D"]
    base_side = Overlay(unit.base, [c.path for c in changes if c.status != "A"], added)
    head_side = Overlay(unit.head, [c.path for c in changes if c.status != "D"], deleted)

    def run(label: str, rev: str, overlay: Overlay | None, selection: list | None, collect_only: bool = False) -> Run:
        found = session.run(f"{unit.id}-{label}", rev, overlay, selection, collect_only)
        reports[label] = found.report(selection)
        if found.timed_out:
            items.append(item(
                "UNCLASSIFIED", "incomplete-run", None, f"the {label} run stopped after {session.timeout:g} seconds"
            ))
        return found

    head = run("head", unit.head, None, head_files, collect_only=True) if whole or head_files else None
    if head is not None and head.broken():
        items.append(item(
            "UNCLASSIFIED", "collection-error", None,
            f"pytest exited with {head.exit_code} before it collected the head tests; see {head.log}",
        ))
    replay = base = None
    if whole or base_files:
        if mixed:
            replay = run("replay", unit.head, base_side, base_files)
        base = run("base", unit.base, None, base_files)
        if base.broken():
            raise UsageError(
                f"pytest exited with {base.exit_code} on the base tests at {unit.base}; see log_tail",
                log_tail=tail(base.log.read_text(encoding="utf-8", errors="replace"), LOG_TAIL),
            )
    for found, side in ((base, "base"), (head, "head")):
        for nodeid in found.found["collect_errors"] if found else []:
            detail = f"collection fails at {side}"
            items.append(item("UNCLASSIFIED", "collection-error", node_file(nodeid), detail, nodeid=nodeid))
    if replay is not None:
        items += behavior_changes(base, replay)

    evidence = base is not None and base.complete() and (head is None or head.complete())
    base_ids = set(base.collected()) if evidence else set()
    head_ids = set(head.collected()) if head is not None else set()
    if evidence:
        revised, existing = confirmed(static, base.collected(), head_ids, items)
    else:
        revised, existing = unconfirmed(static), set()
    if base is None and any(entry.get("fixtures") for entry in revised):
        fixtures = run("fixtures", unit.base, None, None, collect_only=True)
    else:
        fixtures = base
    revised = fixture_evidence(revised, fixtures.found["fixtures"] if fixtures and fixtures.complete() else None)

    new_ids = []
    if head is not None and head.complete():
        keys = set(static.new_tests) - existing
        kept = {e["nodeid"] for e in revised if e["subtype"] == "appended-cases" and e["class"] == "SAFE"}
        for nodeid in head.collected():
            key = function_key(nodeid)
            if key in keys or (key in kept and nodeid not in base_ids):
                new_ids.append(nodeid)
    entries = []
    if new_ids:
        label = run("label", unit.base, head_side, sorted({node_file(n) for n in new_ids}))
        tests = label.tests()
        entries = [label_entry(nodeid, label, tests) for nodeid in new_ids]
    seen = {function_key(n) for n in new_ids} | existing
    entries += [new_test(key, "not collected at head") for key in static.new_tests if key not in seen]
    return revised + items, entries, reports


def confirmed(static: Static, base_ids: list, head_ids: set, items: list) -> tuple[list, set]:
    """The layer 2 items revised with the collection evidence, and the function keys of the existing node IDs.

    Each base node ID that head does not collect, outside a removed test or
    a test with appended cases, goes to `items`.
    """
    appended = {i["nodeid"] for i in static.items if i["subtype"] == "appended-cases"}
    removed = [i["nodeid"] for i in static.items if i["subtype"] == "removed-test"]
    missing: dict = {}
    for nodeid in base_ids:
        if nodeid in head_ids:
            continue
        key = function_key(nodeid)
        if any(key == k or key.startswith(k + "::") for k in removed):
            continue
        if key in appended:
            missing.setdefault(key, []).append(nodeid)
        else:
            items.append(item(
                "WEAKENING", "missing-node-id", node_file(nodeid), "a base node ID is not collected at head",
                nodeid=nodeid,
            ))
    base_keys = {function_key(nodeid) for nodeid in base_ids}
    revised, existing = [], set()
    for entry in static.items:
        new = entry["subtype"] == "new-test"
        taken = [key for key in item_keys(entry, static.new_tests) if key in base_keys] if new else []
        if entry["subtype"] == "appended-cases" and entry["nodeid"] in missing:
            lost = missing[entry["nodeid"]]
            entry = {
                **entry, "class": "WEAKENING", "subtype": "missing-node-id",
                "detail": "the appended cases change base node IDs: " + ", ".join(lost), "missing": lost,
            }
        elif taken:
            existing.update(taken)
            entry = {
                **entry, "class": "UNCLASSIFIED", "subtype": "existing-node-id",
                "detail": "adds a test with a node ID that the base collected, so it replaces an inherited test: "
                + ", ".join(taken),
            }
        revised.append(entry)
    return revised, existing


def unconfirmed(static: Static) -> list:
    """The layer 2 items, with the items that need collection evidence as UNCLASSIFIED, when the gate has none.

    Without it, appended parametrize cases can rename base node IDs, and a new
    test in a subclass can replace an inherited test.
    """
    revised = []
    for entry in static.items:
        if entry["subtype"] == "appended-cases":
            detail = "appends literal parametrize cases, but no collection shows that each base node ID stays"
        elif entry["subtype"] == "new-test" and item_keys(entry, static.subclass_tests):
            detail = "adds a test to a subclass, but no collection shows that the base had no test with its node ID"
        else:
            detail = None
        if detail:
            entry = {**entry, "class": "UNCLASSIFIED", "subtype": "no-collection-evidence", "detail": detail}
        revised.append(entry)
    return revised


def fixture_evidence(items: list, known: list | None) -> list:
    """The items, with each SAFE item that defines a fixture checked against the fixture names of a base run.

    pytest reports these names, plugin fixtures included. `known` is None when no complete base run reported them.
    """
    revised = []
    for entry in items:
        names = entry.get("fixtures") if entry["class"] == "SAFE" else None
        clash = sorted(set(names or []) & set(known or []))
        if names and known is None:
            entry = {
                **entry, "class": "UNCLASSIFIED", "subtype": "no-collection-evidence",
                "detail": f"defines the fixture {', '.join(names)}, but no base run shows the fixture names of pytest",
            }
        elif clash:
            entry = {
                **entry, "class": "UNCLASSIFIED", "subtype": "signal",
                "detail": f"fixture {', '.join(clash)} has the name of a fixture that pytest reports at base",
            }
        revised.append(entry)
    return revised


def check_unit(project: Project, session: Session | None, unit: Unit) -> dict:
    changes, product = project.changes(unit)
    mixed = bool(product)
    static = static_layer(project, unit, changes)
    reports: dict = {}
    if session is not None and changes:
        items, new_tests, reports = run_layers(session, unit, changes, mixed, static)
    else:
        items = fixture_evidence(unconfirmed(static), None)
        new_tests = [new_test(key, "not run") for key in static.new_tests]
    items = [{"id": f"{unit.id}-i{n}", **entry} for n, entry in enumerate(items, start=1)]
    if not mixed:
        status = "needs evidence" if changes else "pass"
    elif any(i["class"] in FAILING and i["subtype"] != "no-collection-evidence" for i in items):
        status = "fail"
    elif any(i["subtype"] == "no-collection-evidence" for i in items):
        status = "needs evidence"
    else:
        status = "pass"
    diff = project.git(
        "diff", "--no-color", "--no-ext-diff", "--no-renames", "--full-index", "--binary", unit.base, unit.head
    )
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
            "passed": all(unit["status"] == "pass" for unit in results if unit["mixed"]),
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
