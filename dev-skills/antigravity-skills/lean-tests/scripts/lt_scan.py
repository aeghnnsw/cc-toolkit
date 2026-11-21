"""scan: find weak, duplicate, and protected tests by their syntax tree.

Imported by lean_tests.py; never run directly. Every finding is a
candidate for review, not a verdict: the scan reads only the test source.
"""

from __future__ import annotations

import ast
import copy
import io
import re
import tokenize
from pathlib import Path

from lt_common import EXAMPLES, PARSE_ERRORS, UsageError, load_json, parse_failure, read_node_ids, suite_node_ids

MOCK_ASSERTS = frozenset({
    "assert_called", "assert_called_once", "assert_called_with", "assert_called_once_with",
    "assert_any_call", "assert_has_calls", "assert_not_called", "assert_awaited",
    "assert_awaited_once", "assert_awaited_with", "assert_awaited_once_with", "assert_any_await",
    "assert_has_awaits", "assert_not_awaited",
})
MOCK_ATTRS = frozenset({
    "call_args", "call_args_list", "call_count", "mock_calls", "method_calls", "called",
    "await_args", "await_args_list", "await_count",
})
PYTEST_CHECKS = frozenset({"raises", "warns", "deprecated_call", "fail"})
WEAK_CALLS = frozenset({"isinstance", "hasattr", "callable", "len", "bool"})
CONSTANT_NAME = re.compile(r"^[A-Z][A-Z0-9_]+$")
COMPUTING = (ast.BinOp, ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp, ast.JoinedStr)

PROTECTION_WORDS = re.compile(
    r"\b(regression|characteri[sz]ation|security|compat(?:ibility)?|perf(?:ormance)?)\b", re.IGNORECASE
)
ISSUE_TEXT = re.compile(
    r"(?:\b(?:issue|bug|gh|ticket)\s*[#-]?\s*\d+|(?<![\w&])#\d+\b|/(?:issues|pull)/\d+)", re.IGNORECASE
)
ISSUE_NAME = re.compile(r"(?:^|_)(?:issue|bug|gh|ticket)_?\d+", re.IGNORECASE)
NAME_PROTECTION = {
    "regression": "regression", "regressions": "regression", "characterization": "characterization",
    "characterisation": "characterization", "security": "security", "compat": "compat",
    "compatibility": "compat", "perf": "perf", "performance": "perf",
}

INPUT_CLASS_WORDS = {
    "boundary": {"boundary", "boundaries", "edge", "limit", "limits", "empty", "zero", "min", "max",
                 "minimum", "maximum", "overflow", "underflow", "threshold"},
    "types": {"type", "types", "int", "integer", "float", "str", "string", "bytes", "bool", "boolean", "decimal"},
    "unicode": {"unicode", "utf", "utf8", "encoding", "encode", "decode", "emoji", "ascii", "nonascii"},
    "timezone": {"timezone", "timezones", "tz", "dst", "utc"},
    "large-size": {"large", "big", "huge", "many", "bulk", "stress"},
    "error-path": {"error", "errors", "invalid", "fail", "fails", "failure", "raise", "raises", "exception",
                   "exceptions", "bad", "reject", "rejects", "rejected", "wrong", "malformed"},
    "concurrency": {"concurrent", "concurrency", "thread", "threads", "threaded", "threading", "race",
                    "parallel", "async", "lock", "locks", "deadlock"},
    "locale": {"locale", "locales", "i18n", "l10n", "translation", "translations"},
    "platform": {"windows", "win32", "linux", "macos", "darwin", "posix", "platform"},
}
INPUT_CLASS_NAMES = {
    "unicode": {"encode", "decode"},
    "timezone": {"timezone", "tzinfo", "zoneinfo", "ZoneInfo", "pytz", "utc", "UTC", "astimezone", "dst"},
    "concurrency": {"threading", "Thread", "asyncio", "multiprocessing", "concurrent", "ThreadPoolExecutor",
                    "ProcessPoolExecutor", "Lock", "RLock", "Barrier"},
    "locale": {"locale", "setlocale", "gettext", "babel"},
    "platform": {"platform", "win32"},
}
LARGE_NUMBER = 100_000


def scan_command(args) -> dict:
    if args.suite:
        if args.project is not None:
            raise UsageError("--project goes only with --node-ids; the suite output names its project")
        data = load_json(args.suite, "suite output")
        nodeids = suite_node_ids(data)
        root = Path(data.get("rootdir") or data.get("project") or ".").resolve()
    else:
        nodeids = read_node_ids(args.node_ids)
        root = Path(args.project or ".").resolve()
    if not root.is_dir():
        raise UsageError(f"project directory {root} does not exist")
    return scan(root, nodeids)


def function_id(nodeid: str) -> tuple[str, list[str]]:
    """Split a node ID into its file and the names of its class and function, without parameters."""
    path, _, rest = nodeid.partition("::")
    rest = rest.partition("[")[0]
    parts = [part for part in rest.split("::") if part and part != "()"]
    return path, parts


def scan(root: Path, nodeids: list[str]) -> dict:
    functions: dict[str, tuple[str, list[str]]] = {}
    for nodeid in nodeids:
        path, parts = function_id(nodeid)
        key = "::".join([path, *parts])
        functions.setdefault(key, (path, parts))

    modules: dict[str, Module | str] = {}
    findings: list[dict] = []
    unresolved: list[dict] = []
    shapes: dict[str, list[tuple[str, str, int]]] = {}
    for key, (path, parts) in functions.items():
        if path not in modules:
            modules[path] = load_module(root / path)
        module = modules[path]
        if isinstance(module, str):
            unresolved.append({"nodeid": key, "reason": module})
            continue
        found = module.find(parts)
        if found is None:
            unresolved.append({"nodeid": key, "reason": "test function not found in the file"})
            continue
        func, classes = found
        test = TestFunction(module, func, classes)
        for code, line, detail in test.findings():
            findings.append(finding(code, key, path, line, detail))
        shapes.setdefault(test.shape(), []).append((key, path, func.lineno))

    groups = []
    for members in shapes.values():
        if len(members) < 2:
            continue
        number = len(groups) + 1
        groups.append({"group": number, "nodeids": [key for key, _, _ in members]})
        for key, path, line in members:
            findings.append(finding("duplicate-shape", key, path, line, f"group {number}"))

    findings.sort(key=lambda f: (f["file"], f["line"], f["code"], f["nodeid"]))
    counts: dict[str, int] = {}
    examples: dict[str, list[str]] = {}
    for entry in findings:
        counts[entry["code"]] = counts.get(entry["code"], 0) + 1
        shown = examples.setdefault(entry["code"], [])
        if len(shown) < EXAMPLES and entry["nodeid"] not in shown:
            shown.append(entry["nodeid"])
    return {
        "summary": {
            "nodeids": len(nodeids),
            "tests": len(functions),
            "files": len(modules),
            "counts": dict(sorted(counts.items())),
            "duplicate_groups": len(groups),
            "unresolved": len(unresolved),
            "examples": dict(sorted(examples.items())),
        },
        "findings": findings,
        "duplicate_groups": groups,
        "unresolved": unresolved,
    }


def finding(code: str, nodeid: str, path: str, line: int, detail: str) -> dict:
    return {"code": code, "nodeid": nodeid, "file": path, "line": line, "detail": detail}


def load_module(path: Path):
    """The parsed module, or the reason it could not be parsed."""
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
    except PARSE_ERRORS as error:
        return parse_failure(error)
    return Module(source, tree)


class Module:
    def __init__(self, source: str, tree: ast.Module) -> None:
        self.tree = tree
        self.comments: dict[int, str] = {}
        try:
            for token in tokenize.generate_tokens(io.StringIO(source).readline):
                if token.type == tokenize.COMMENT:
                    self.comments[token.start[0]] = token.string
        except (tokenize.TokenError, IndentationError):
            pass
        self.lines = source.splitlines()
        self.imported = set()
        self.time_sleep_names = set()
        for node in tree.body:
            if isinstance(node, ast.Import):
                self.imported.update((a.asname or a.name).split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom):
                self.imported.update(a.asname or a.name for a in node.names)
                if node.module == "time":
                    self.time_sleep_names.update(a.asname or a.name for a in node.names if a.name == "sleep")
        self.classes = {n.name: n for n in tree.body if isinstance(n, ast.ClassDef)}
        functions = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
        self.helpers = checking_functions(functions, set())

    def find(self, parts: list[str]):
        """Find the test function for the class and function names of a node ID."""
        if not parts:
            return None
        body = self.tree.body
        classes: list[ast.ClassDef] = []
        for name in parts[:-1]:
            cls = next((n for n in body if isinstance(n, ast.ClassDef) and n.name == name), None)
            if cls is None:
                return None
            classes.append(cls)
            body = cls.body
        if not classes:
            func = defined_function(body, parts[-1])
            return None if func is None else (func, classes)
        func = self.method(classes[-1], parts[-1], set())
        return None if func is None else (func, classes)

    def method(self, cls: ast.ClassDef, name: str, seen: set):
        func = defined_function(cls.body, name)
        if func is not None or cls.name in seen:
            return func
        seen.add(cls.name)
        for base in cls.bases:
            if isinstance(base, ast.Name) and base.id in self.classes:
                func = self.method(self.classes[base.id], name, seen)
                if func is not None:
                    return func
        return None


def defined_function(body: list, name: str):
    return next(
        (n for n in body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name), None
    )


def checking_functions(functions: list, methods: set) -> set:
    """Names of the functions that make a check, directly or through another such function."""
    helpers: set = set()
    changed = True
    while changed:
        changed = False
        for func in functions:
            if func.name not in helpers and any(check_kind(n, helpers, methods) for n in ast.walk(func)):
                helpers.add(func.name)
                changed = True
    return helpers


def call_name(call: ast.Call) -> tuple[str | None, str | None]:
    """The dotted base and the final name of a call, for example ("pytest", "raises")."""
    func = call.func
    if isinstance(func, ast.Name):
        return None, func.id
    if isinstance(func, ast.Attribute):
        return dotted(func.value), func.attr
    return None, None


def dotted(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = dotted(node.value)
        return None if base is None else f"{base}.{node.attr}"
    return None


def check_kind(node: ast.AST, helpers: set, methods: set) -> str | None:
    """The kind of check a node makes, or None when it makes no check."""
    if isinstance(node, ast.Assert):
        return "assert"
    if isinstance(node, ast.Raise):
        return "raise"
    if not isinstance(node, ast.Call):
        return None
    base, name = call_name(node)
    if name is None:
        return None
    if base == "pytest" and name in PYTEST_CHECKS:
        return "pytest"
    if name in MOCK_ASSERTS:
        return "mock"
    if name.startswith("assert") or (base == "self" and name == "fail"):
        return "call-assert"
    if base is None and name in helpers:
        return "helper"
    if base == "self" and name in methods:
        return "helper"
    return None


def is_literal(node: ast.AST) -> bool:
    if isinstance(node, ast.Constant):
        return True
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
        return isinstance(node.operand, ast.Constant)
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        return all(is_literal(e) for e in node.elts)
    if isinstance(node, ast.Dict):
        return all(k is not None and is_literal(k) for k in node.keys) and all(is_literal(v) for v in node.values)
    return False


def is_none(node: ast.AST) -> bool:
    return isinstance(node, ast.Constant) and node.value is None


def same(a: ast.AST, b: ast.AST) -> bool:
    return ast.dump(a) == ast.dump(b)


def input_names(nodes: list) -> set:
    """Names read in `nodes`, without the names of called functions."""
    called = set()
    names = set()
    for node in nodes:
        for sub in ast.walk(node):
            if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Name):
                called.add(id(sub.func))
            if isinstance(sub, ast.Name) and isinstance(sub.ctx, ast.Load):
                names.add((id(sub), sub.id))
    return {name for ident, name in names if ident not in called}


def recomputed(actual: ast.AST, expected: ast.AST) -> bool:
    """True when `expected` recomputes the result of the call `actual` from its inputs."""
    if not isinstance(actual, ast.Call):
        return False
    inputs = input_names(list(actual.args) + [k.value for k in actual.keywords])
    if not inputs:
        return False
    computes = any(isinstance(n, COMPUTING) for n in ast.walk(expected))
    same_call = isinstance(expected, ast.Call) and same(expected.func, actual.func)
    return (computes or same_call) and bool(inputs & input_names([expected]))


def is_weak(test: ast.AST) -> bool:
    """True for a truthiness, non-None, type, or non-empty check."""
    if isinstance(test, (ast.Name, ast.Attribute, ast.Subscript)):
        return True
    if isinstance(test, ast.Call) and isinstance(test.func, ast.Name) and test.func.id in WEAK_CALLS:
        return True
    if isinstance(test, ast.Compare) and len(test.ops) == 1:
        op, right = test.ops[0], test.comparators[0]
        if isinstance(op, (ast.IsNot, ast.NotEq)) and is_none(right):
            return True
        left = test.left
        if isinstance(left, ast.Call) and isinstance(left.func, ast.Name) and left.func.id == "len":
            if isinstance(right, ast.Constant) and (
                (isinstance(op, ast.Gt) and right.value == 0)
                or (isinstance(op, ast.GtE) and right.value == 1)
                or (isinstance(op, ast.NotEq) and right.value == 0)
            ):
                return True
    return False


def uses_mock_attrs(test: ast.AST) -> bool:
    return any(isinstance(n, ast.Attribute) and n.attr in MOCK_ATTRS for n in ast.walk(test))


class ShapeNormalizer(ast.NodeTransformer):
    """Replace literals with one placeholder, so tests that differ only in literals match."""

    def visit_Constant(self, node: ast.Constant) -> ast.AST:
        return ast.Constant(value="<literal>")

    def visit_UnaryOp(self, node: ast.UnaryOp) -> ast.AST:
        if isinstance(node.op, (ast.USub, ast.UAdd)) and isinstance(node.operand, ast.Constant):
            return ast.Constant(value="<literal>")
        return self.generic_visit(node)


def words_of(name: str) -> set:
    return set(re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", name).lower().split("_")) - {""}


class TestFunction:
    def __init__(self, module: Module, func, classes: list) -> None:
        self.module = module
        self.func = func
        self.classes = classes
        methods: set = set()
        for cls in classes:
            members = [n for n in cls.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
            methods |= checking_functions(members, methods)
        self.checks = []
        for node in ast.walk(func):
            kind = check_kind(node, module.helpers, methods)
            if kind is not None:
                self.checks.append((kind, node))
        self.assigned = {}
        for stmt in func.body:
            if isinstance(stmt, ast.Assign) and len(stmt.targets) == 1:
                target, value = stmt.targets[0], stmt.value
                if isinstance(target, ast.Name):
                    self.assigned[target.id] = value
                elif (
                    isinstance(target, ast.Tuple) and isinstance(value, ast.Tuple)
                    and len(target.elts) == len(value.elts)
                ):
                    for t, v in zip(target.elts, value.elts):
                        if isinstance(t, ast.Name):
                            self.assigned[t.id] = v

    def resolve(self, node: ast.AST) -> ast.AST:
        if isinstance(node, ast.Name) and node.id in self.assigned:
            return self.assigned[node.id]
        return node

    def findings(self):
        yield from self.check_findings()
        yield from self.protection()
        yield from self.input_classes()
        yield from self.sleeps()

    def check_findings(self):
        func = self.func
        if not self.checks:
            yield "no-assertion", func.lineno, "no assert, pytest.raises, pytest.fail, assert method, or raise"
            return
        asserts = [node for kind, node in self.checks if kind == "assert"]
        for node in asserts:
            verdict = self.assert_verdict(node.test)
            if verdict is not None:
                yield verdict[0], node.lineno, verdict[1]
        only_asserts = len(asserts) == len(self.checks)
        if only_asserts and all(is_weak(n.test) for n in asserts):
            yield "weak-oracle", func.lineno, "only truthiness, non-None, type, or non-empty checks"
        if all(kind == "mock" or (kind == "assert" and uses_mock_attrs(node.test)) for kind, node in self.checks):
            yield "change-detector", func.lineno, "checks only mock calls, their order, or their arguments"
        if only_asserts and all(self.is_trivial(n.test) for n in asserts):
            yield "trivial-code", func.lineno, "compares an imported constant with a literal"

    def assert_verdict(self, test: ast.AST):
        if isinstance(test, ast.Constant) and test.value:
            return "tautology", "asserts a constant"
        if not (isinstance(test, ast.Compare) and len(test.ops) == 1):
            return None
        left, right, op = test.left, test.comparators[0], test.ops[0]
        if same(left, right):
            if is_literal(left):
                if isinstance(op, (ast.Eq, ast.Is, ast.LtE, ast.GtE)):
                    return "tautology", "compares a constant with itself"
                return None
            return "self-comparison", "compares an expression with itself"
        if not isinstance(op, (ast.Eq, ast.Is)):
            return None
        left, right = self.resolve(left), self.resolve(right)
        if same(left, right):
            return "tautology", "computes the expected value with the same call"
        if recomputed(left, right) or recomputed(right, left):
            return "tautology", "recomputes the expected value from the inputs"
        return None

    def is_trivial(self, test: ast.AST) -> bool:
        if not (isinstance(test, ast.Compare) and len(test.ops) == 1 and isinstance(test.ops[0], ast.Eq)):
            return False
        sides = (test.left, test.comparators[0])
        return any(self.is_constant_name(a) and is_literal(b) for a, b in (sides, sides[::-1]))

    def is_constant_name(self, node: ast.AST) -> bool:
        if isinstance(node, ast.Name):
            return bool(CONSTANT_NAME.match(node.id)) and node.id in self.module.imported
        if isinstance(node, ast.Attribute):
            base = dotted(node.value)
            return (
                bool(CONSTANT_NAME.match(node.attr))
                and base is not None
                and base.split(".")[0] in self.module.imported
            )
        return False

    def shape(self) -> str:
        node = copy.deepcopy(self.func)
        node.name = ""
        body = node.body
        if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
            if isinstance(body[0].value.value, str):
                node.body = body[1:] or [ast.Pass()]
        return ast.dump(ShapeNormalizer().visit(node))

    def names(self) -> list[str]:
        return [cls.name for cls in self.classes] + [self.func.name]

    def texts(self):
        """Yield (source, text) pairs: the docstring and the comments in and above the test."""
        docstring = ast.get_docstring(self.func)
        if docstring:
            yield "docstring", docstring
        start = min([d.lineno for d in self.func.decorator_list] + [self.func.lineno])
        first = start
        while first - 1 in self.module.comments and self.module.lines[first - 2].lstrip().startswith("#"):
            first -= 1
        end = getattr(self.func, "end_lineno", None) or self.func.lineno
        for line in range(first, end + 1):
            if line in self.module.comments:
                yield "comment", self.module.comments[line]

    def markers(self) -> list[str]:
        found = []
        for decorator in self.func.decorator_list:
            node = decorator.func if isinstance(decorator, ast.Call) else decorator
            name = dotted(node) or ""
            if ".mark." in f".{name}":
                found.append(name.rsplit(".", 1)[-1])
        return found

    def protection(self):
        details = []
        for name in self.names():
            match = ISSUE_NAME.search(name)
            if match:
                details.append(f"name: {match.group(0).strip('_')}")
            for word in sorted(words_of(name)):
                if word in NAME_PROTECTION:
                    details.append(f"name: {NAME_PROTECTION[word]}")
        for marker in self.markers():
            for word in sorted(words_of(marker)):
                if word in NAME_PROTECTION:
                    details.append(f"marker: {marker}")
        for source, text in self.texts():
            for match in ISSUE_TEXT.finditer(text):
                details.append(f"{source}: {match.group(0)}")
            for match in PROTECTION_WORDS.finditer(text):
                details.append(f"{source}: {match.group(0).lower()}")
        seen = set()
        for detail in details:
            if detail not in seen:
                seen.add(detail)
                yield "protected", self.func.lineno, detail

    def input_classes(self):
        words = set()
        for name in self.names():
            words |= words_of(name)
        names = set()
        for node in ast.walk(self.func):
            if isinstance(node, ast.Name):
                names.add(node.id)
            elif isinstance(node, ast.Attribute):
                names.add(node.attr)
                base = dotted(node)
                if base in ("sys.platform", "os.name", "os.sep"):
                    names.add("platform")
        found = {label for label, vocabulary in INPUT_CLASS_WORDS.items() if words & vocabulary}
        found |= {label for label, vocabulary in INPUT_CLASS_NAMES.items() if names & vocabulary}
        body = [n for stmt in self.func.body for n in ast.walk(stmt)]
        for node in body:
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and not node.value.isascii():
                found.add("unicode")
            elif isinstance(node, ast.Constant) and type(node.value) is int and abs(node.value) >= LARGE_NUMBER:
                found.add("large-size")
            elif isinstance(node, ast.Call):
                base, name = call_name(node)
                if (base == "pytest" and name == "raises") or (name or "").startswith("assertRaises"):
                    found.add("error-path")
                for arg in list(node.args) + [k.value for k in node.keywords]:
                    if is_empty_or_zero(arg):
                        found.add("boundary")
                    elif isinstance(arg, ast.Constant) and isinstance(arg.value, bytes):
                        found.add("types")
                if name == "float" and node.args and isinstance(node.args[0], ast.Constant):
                    if str(node.args[0].value).lower().lstrip("+-") in ("inf", "infinity", "nan"):
                        found.add("boundary")
            elif isinstance(node, ast.Attribute) and node.attr in ("inf", "nan", "maxsize"):
                found.add("boundary")
        for label in sorted(found):
            yield "input-class", self.func.lineno, label

    def sleeps(self):
        for node in ast.walk(self.func):
            if not isinstance(node, ast.Call):
                continue
            base, name = call_name(node)
            if (base == "time" and name == "sleep") or (base is None and name in self.module.time_sleep_names):
                seconds = None
                if node.args and isinstance(node.args[0], ast.Constant):
                    seconds = node.args[0].value
                yield "sleep", node.lineno, f"time.sleep({seconds})" if seconds is not None else "time.sleep"


def is_empty_or_zero(node: ast.AST) -> bool:
    if isinstance(node, ast.Constant):
        return node.value in ("", b"") or (type(node.value) in (int, float) and node.value == 0)
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        return not node.elts
    if isinstance(node, ast.Dict):
        return not node.keys
    return False
