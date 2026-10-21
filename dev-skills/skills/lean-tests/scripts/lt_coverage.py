"""coverage: per-test lines, coverage-subset candidates, unmeasured tests, diff coverage.

Imported by lean_tests.py; never run directly. Reads the output of
`coverage json --show-contexts` from a run with pytest-cov's
`--cov-context=test`, so it never imports coverage.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

from lt_common import (
    EXAMPLES, PARSE_ERRORS, UsageError, git, load_json, node_file, parse_failure, rel, suite_node_ids, tail,
)

PHASE = re.compile(r"\|(setup|run|teardown)$")
HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")
TEST_DIRS = frozenset({"tests", "test", "testing"})
SUPERSETS_SHOWN = 5
GIT_TAIL = 5


def coverage_command(args) -> dict:
    data = load_json(args.contexts, "coverage JSON")
    if not (data.get("meta") or {}).get("show_contexts"):
        raise UsageError("the coverage JSON has no contexts; write it with `coverage json --show-contexts`")
    suite = load_json(args.suite, "suite output")
    project = Path(suite.get("project") or ".").resolve()
    rootdir = Path(suite.get("rootdir") or project).resolve()
    nodeids = suite_node_ids(suite)
    ran = ran_tests(suite)
    test_files = {(rootdir / node_file(n)).resolve() for n in nodeids}

    measured_files = product_files(data, project, test_files)
    lines, run_files = lines_by_test(measured_files, project)

    measured = [n for n in nodeids if n in run_files]
    unmeasured = unmeasured_tests(nodeids, ran, run_files)
    not_run = [n for n in nodeids if n not in ran]
    equal_groups, strict_subsets = subsets(measured, lines)
    diff = diff_coverage(project, args.base, measured_files, test_files) if args.base else None

    tests = {}
    for nodeid in sorted(lines):
        files = {name: sorted(found) for name, found in sorted(lines[nodeid].items())}
        tests[nodeid] = {"lines": sum(len(found) for found in files.values()), "files": files}
    return {
        "summary": {
            "tests": len(nodeids),
            "measured": len(measured),
            "unmeasured": len(unmeasured),
            "not_run": len(not_run),
            "equal_groups": len(equal_groups),
            "strict_subsets": len(strict_subsets),
            "diff": diff_summary(diff),
            "examples": {
                "equal_groups": equal_groups[:EXAMPLES],
                "strict_subsets": [{"test": e["test"], "superset": e["supersets"][0]} for e in strict_subsets[:EXAMPLES]],
                "unmeasured": unmeasured[:EXAMPLES],
                "missed_lines": [] if diff is None else [
                    f"{f['path']}:{line}" for f in diff["files"] for line in f["missed"]
                ][: 2 * EXAMPLES],
            },
        },
        "tests": tests,
        "equal_groups": equal_groups,
        "strict_subsets": strict_subsets,
        "unmeasured": unmeasured,
        "not_run": not_run,
        "diff": diff,
    }


def diff_summary(diff: dict | None) -> dict | None:
    if diff is None:
        return None
    summary = {k: v for k, v in diff.items() if k not in ("files", "unmeasured_files", "unparsed")}
    summary["raise_missed"] = sum(len(f["raise"]["missed"]) for f in diff["files"])
    summary["except_missed"] = sum(len(f["except"]["missed"]) for f in diff["files"])
    summary["unmeasured_files"] = len(diff["unmeasured_files"])
    summary["unparsed"] = len(diff["unparsed"])
    return summary


def ran_tests(suite: dict) -> set:
    """The tests of a suite output whose call phase ran."""
    return {t["nodeid"] for t in suite.get("tests", []) if "call" in t.get("phases", {})}


def product_files(data: dict, project: Path, test_files: set) -> dict:
    """The coverage entry of each measured file that is not a test file, by resolved path."""
    files = {}
    for name, entry in (data.get("files") or {}).items():
        path = (project / name).resolve()
        if not is_test_path(path, test_files, project):
            files[path] = entry
    return files


def lines_by_test(files: dict, project: Path) -> tuple[dict, dict]:
    """The lines that each test ran in each product file, in any phase; and the files where its run phase ran a line.

    Both are keyed by node ID, with file paths relative to the project.
    """
    lines: dict[str, dict[str, set]] = {}
    run_files: dict[str, set] = {}
    for path, entry in files.items():
        name = rel(path, project)
        for lineno, contexts in (entry.get("contexts") or {}).items():
            for context in contexts:
                match = PHASE.search(context)
                if not match:
                    continue  # "" is import time
                nodeid = context[: match.start()]
                lines.setdefault(nodeid, {}).setdefault(name, set()).add(int(lineno))
                if match.group(1) == "run":
                    run_files.setdefault(nodeid, set()).add(name)
    return lines, run_files


def unmeasured_tests(nodeids: list[str], ran: set, run_files: dict) -> list[str]:
    """The unmeasured tests: tests that ran, but whose run phase ran no line of a file in `run_files`."""
    return [n for n in nodeids if n in ran and not run_files.get(n)]


def is_test_path(path: Path, test_files: set, project: Path) -> bool:
    if path in test_files or path.name == "conftest.py" or path.name.startswith("test_"):
        return True
    if path.stem.endswith("_test"):
        return True
    return any(part in TEST_DIRS for part in Path(rel(path, project)).parts[:-1])


def subsets(measured: list[str], lines: dict) -> tuple[list, list]:
    """Group tests with equal line sets; list each test whose lines are a strict subset of others'."""
    keys: dict = {}
    sets = {}
    for nodeid in measured:
        sets[nodeid] = frozenset(
            keys.setdefault((name, line), len(keys)) for name, found in lines[nodeid].items() for line in found
        )
    classes: dict[frozenset, list[str]] = {}
    for nodeid in measured:
        classes.setdefault(sets[nodeid], []).append(nodeid)
    distinct = list(classes)
    containing: dict[int, list[int]] = {}
    for index, members in enumerate(distinct):
        for key in members:
            containing.setdefault(key, []).append(index)

    equal_groups = sorted(sorted(members) for members in classes.values() if len(members) > 1)
    strict = []
    for index, members in enumerate(distinct):
        if not members:
            continue
        rarest = min(members, key=lambda key: len(containing[key]))
        larger = [
            other for other in containing[rarest]
            if other != index and len(distinct[other]) > len(members) and members < distinct[other]
        ]
        if not larger:
            continue
        larger.sort(key=lambda other: (len(distinct[other]), min(classes[distinct[other]])))
        supersets = [n for other in larger for n in sorted(classes[distinct[other]])]
        for nodeid in classes[members]:
            strict.append({
                "test": nodeid,
                "supersets": supersets[:SUPERSETS_SHOWN],
                "superset_count": len(supersets),
            })
    strict.sort(key=lambda entry: entry["test"])
    return equal_groups, strict


def unquote(path: str) -> str:
    if len(path) >= 2 and path[0] == path[-1] == '"':
        path = path[1:-1].replace('\\"', '"').replace("\\t", "\t").replace("\\\\", "\\")
    return path


def changed_lines(project: Path, base: str) -> tuple[str, dict]:
    """The merge base of `base` and HEAD, and the added line numbers of each file since it."""
    top = git(project, "rev-parse", "--show-toplevel")
    if top.returncode != 0:
        raise UsageError("diff coverage needs a Git work tree", log_tail=tail(top.stderr, GIT_TAIL))
    root = Path(top.stdout.strip()).resolve()
    found = git(project, "merge-base", base, "HEAD")
    if found.returncode != 0:
        raise UsageError(f"cannot find the merge base of {base} and HEAD", log_tail=tail(found.stderr, GIT_TAIL))
    merge_base = found.stdout.strip()
    diff = git(
        project, "-c", "core.quotePath=false", "diff", "-U0", "--no-color", "--no-ext-diff",
        "--src-prefix=a/", "--dst-prefix=b/", merge_base, "--", ".",
    )
    if diff.returncode != 0:
        raise UsageError(f"git diff against {merge_base} failed", log_tail=tail(diff.stderr, GIT_TAIL))
    changed: dict[Path, set] = {}
    current = None
    in_header = False
    for line in diff.stdout.splitlines():
        if line.startswith("diff --git "):
            in_header, current = True, None
        elif in_header and line.startswith("+++ "):
            target = unquote(line[4:])
            current = None if target == "/dev/null" else (root / target[2:]).resolve()
            if current is not None:
                changed.setdefault(current, set())
        elif line.startswith("@@"):
            in_header = False
            match = HUNK.match(line)
            if match and current is not None:
                start = int(match.group(1))
                count = 1 if match.group(2) is None else int(match.group(2))
                changed[current].update(range(start, start + count))
    untracked = git(project, "ls-files", "-z", "--others", "--exclude-standard", "--", "*.py")
    for name in untracked.stdout.split("\0"):
        if not name:
            continue
        path = (project / name).resolve()
        try:
            count = len(path.read_text(encoding="utf-8").splitlines())
        except (OSError, UnicodeDecodeError):
            continue
        changed[path] = set(range(1, count + 1))
    return merge_base, changed


def error_lines(path: Path) -> tuple[set, set]:
    """Line numbers of the raise statements and the except clauses in a file. Raises PARSE_ERRORS."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    raises = {n.lineno for n in ast.walk(tree) if isinstance(n, ast.Raise)}
    excepts = {n.lineno for n in ast.walk(tree) if isinstance(n, ast.ExceptHandler)}
    return raises, excepts


def diff_coverage(project: Path, base: str, measured_files: dict, test_files: set) -> dict:
    merge_base, changed = changed_lines(project, base)
    files = []
    unmeasured_files = []
    unparsed = []
    totals = {"changed_lines": 0, "executable": 0, "executed": 0, "missed": 0}
    for path in sorted(changed):
        if path.suffix != ".py" or is_test_path(path, test_files, project) or not changed[path]:
            continue
        totals["changed_lines"] += len(changed[path])
        entry = measured_files.get(path)
        if entry is None:
            if path.is_file():
                unmeasured_files.append(rel(path, project))
            continue
        executed = changed[path] & set(entry.get("executed_lines") or [])
        missed = changed[path] & set(entry.get("missing_lines") or [])
        if not executed and not missed:
            continue
        try:
            raises, excepts = error_lines(path)
        except PARSE_ERRORS as error:
            raises, excepts = set(), set()
            unparsed.append({"file": rel(path, project), "reason": parse_failure(error)})
        totals["executable"] += len(executed) + len(missed)
        totals["executed"] += len(executed)
        totals["missed"] += len(missed)
        files.append({
            "path": rel(path, project),
            "executed": sorted(executed),
            "missed": sorted(missed),
            "raise": {"executed": sorted(executed & raises), "missed": sorted(missed & raises)},
            "except": {"executed": sorted(executed & excepts), "missed": sorted(missed & excepts)},
        })
    executable = totals["executable"]
    return {
        "base": base,
        "merge_base": merge_base,
        **totals,
        "percent": None if not executable else round(100.0 * totals["executed"] / executable, 1),
        "files": files,
        "unmeasured_files": unmeasured_files,
        "unparsed": unparsed,
    }
