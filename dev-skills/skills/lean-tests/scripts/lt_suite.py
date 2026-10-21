"""suite and compare: run pytest with outcome records, and compare two runs.

Imported by lean_tests.py; never run directly.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import signal
import subprocess
import time
from pathlib import Path

from lt_common import EXAMPLES, UsageError, git, load_json, read_node_ids, suite_node_ids, tail

PLUGIN_DIR = Path(__file__).resolve().parent / "pytest_plugin"
OUTCOMES = ("passed", "failed", "error", "skipped", "xfailed", "xpassed")
PHASES = ("setup", "call", "teardown")
LOG_TAIL = 30
PROBE_TIMEOUT = 600
SLOWEST = 10
# pytest-cov options whose value is the next argument when they have no "=".
COV_VALUE_OPTIONS = frozenset({"--cov-report", "--cov-fail-under", "--cov-context", "--cov-precision"})
PROBE = """\
import json
found = {}
for name in ("pytest", "pytest_cov"):
    try:
        found[name] = getattr(__import__(name), "__version__", "unknown")
    except Exception:
        found[name] = None
print(json.dumps(found))
"""


def interpreter(command: str) -> list[str]:
    try:
        argv = shlex.split(command)
    except ValueError as error:
        raise UsageError(f"cannot split --python {command!r}: {error}") from error
    if not argv:
        raise UsageError("--python is empty")
    return argv


def probe(python: list[str], project: Path, env: dict) -> dict:
    """Ask the target interpreter which test packages it can import."""
    try:
        result = subprocess.run(
            [*python, "-c", PROBE], cwd=project, env=env, capture_output=True, text=True, timeout=PROBE_TIMEOUT
        )
    except OSError as error:
        raise UsageError(f"cannot run the interpreter {python[0]}: {error.strerror}") from error
    except subprocess.TimeoutExpired as error:
        raise UsageError(f"the interpreter did not answer within {PROBE_TIMEOUT} seconds") from error
    lines = result.stdout.strip().splitlines()
    try:
        return json.loads(lines[-1])
    except (IndexError, json.JSONDecodeError) as error:
        raise UsageError(
            f"the interpreter exited with {result.returncode} and printed no package list",
            log_tail=tail(result.stderr, LOG_TAIL),
        ) from error


def ini_addopts(python: list[str], project: Path, env: dict, path: Path) -> list[str]:
    """The addopts of the project's pytest configuration, from a pytest run that exits before collection."""
    cmd = [*python, "-m", "pytest", "-p", "no:cacheprovider", "-p", "lean_tests_report", "--no-cov"]
    try:
        result = subprocess.run(
            cmd, cwd=project, env={**env, "LEAN_TESTS_ADDOPTS": str(path)},
            capture_output=True, text=True, timeout=PROBE_TIMEOUT,
        )
    except subprocess.TimeoutExpired as error:
        raise UsageError(f"pytest did not read its configuration within {PROBE_TIMEOUT} seconds") from error
    try:
        return json.loads(path.read_text(encoding="utf-8"))["addopts"]
    except (OSError, ValueError, KeyError) as error:
        raise UsageError(
            f"pytest exited with {result.returncode} before it reported its addopts",
            log_tail=tail(result.stdout + result.stderr, LOG_TAIL),
        ) from error


def without_cov(args: list[str]) -> list[str]:
    """`args` without the pytest-cov options and their values, except --cov-config.

    --cov-config only names the coverage configuration, and COVERAGE_FILE
    overrides the data file that the configuration sets.
    """
    kept = []
    index = 0
    while index < len(args):
        arg = args[index]
        index += 1
        if not arg.startswith(("--cov", "--no-cov")) or arg.split("=", 1)[0] == "--cov-config":
            kept.append(arg)
        elif arg in COV_VALUE_OPTIONS:
            index += 1
        elif arg == "--cov" and index < len(args) and not args[index].startswith("-"):
            index += 1  # --cov takes an optional value
    return kept


def version_tuple(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in re.findall(r"\d+", version)[:2])


def git_status(project: Path) -> set | None:
    """The porcelain status lines of the project with its ignored files, or None outside a Git work tree.

    Each ignored directory is one line, so a file written inside one is not seen.
    """
    status = ("--no-optional-locks", "status", "--porcelain")
    try:
        found = git(project, *status, "--untracked-files=all", "--", ".")
        ignored = git(project, *status, "--untracked-files=normal", "--ignored=traditional", "--", ".")
    except UsageError:
        return None  # git is not installed
    if found.returncode != 0 or ignored.returncode != 0:
        return None
    return set(found.stdout.splitlines()) | {line for line in ignored.stdout.splitlines() if line.startswith("!! ")}


def pytest_env(records: Path, data_file: Path, roots: tuple[str, ...] = ()) -> dict:
    """The environment of a pytest run.

    The bundled plugin and `roots` come first on PYTHONPATH. pytest writes no
    bytecode, its outcome records go to `records`, and the coverage data that
    a run starts goes to `data_file`, not into the project.
    """
    env = dict(os.environ)
    for key in ("LEAN_TESTS_ADDOPTS", "LEAN_TESTS_REVERSE"):
        env.pop(key, None)
    env["PYTHONPATH"] = os.pathsep.join(p for p in (str(PLUGIN_DIR), *roots, env.get("PYTHONPATH")) if p)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["LEAN_TESTS_RECORDS"] = str(records)
    env["COVERAGE_FILE"] = str(data_file)
    return env


def run_pytest(cmd: list[str], project: Path, env: dict, log: Path, timeout: float | None):
    """Run pytest with its output in `log`; return (exit code, timed out)."""
    with open(log, "w", encoding="utf-8") as out:
        try:
            proc = subprocess.Popen(
                cmd, cwd=project, env=env, stdout=out, stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL, start_new_session=hasattr(os, "killpg"),
            )
        except OSError as error:
            raise UsageError(f"cannot run {cmd[0]}: {error.strerror}") from error
        try:
            return proc.wait(timeout=timeout), False
        except subprocess.TimeoutExpired:
            stop(proc)
            return None, True


def stop(proc: subprocess.Popen) -> None:
    """Stop the process group of `proc`: SIGTERM, then SIGKILL after 5 seconds."""
    if not hasattr(os, "killpg"):
        proc.kill()
        proc.wait()
        return
    for sig in (signal.SIGTERM, signal.SIGKILL):
        try:
            os.killpg(proc.pid, sig)
        except ProcessLookupError:
            break
        try:
            proc.wait(timeout=5)
            return
        except subprocess.TimeoutExpired:
            continue
    proc.wait()


def read_records(path: Path) -> dict:
    found = {
        "rootdir": None, "pytest_version": None, "collected": None, "collection_seconds": None,
        "collect_errors": [], "tests": {},
    }
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        lines = []
    for line in lines:
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue  # a line cut short when pytest was stopped
        event = record.get("event")
        if event == "start":
            found["rootdir"] = record.get("rootdir")
            found["pytest_version"] = record.get("pytest_version")
        elif event == "collected":
            if record.get("nodeids") or found["collected"] is None:
                found["collected"] = record.get("nodeids") or []
            if record.get("seconds") is not None:
                found["collection_seconds"] = round(record["seconds"], 6)
        elif event == "collect-error":
            found["collect_errors"].append(record.get("nodeid"))
        elif event is None and "nodeid" in record:
            test = found["tests"].setdefault(record["nodeid"], {"nodeid": record["nodeid"], "phases": {}})
            test["phases"][record["when"]] = {
                "outcome": record["outcome"],
                "seconds": round(record.get("seconds") or 0.0, 6),
                "exception": record.get("exception"),
                "xfail": bool(record.get("xfail")),
            }
    return found


def final_outcome(phases: dict) -> str:
    for when in PHASES:
        phase = phases.get(when)
        if phase and phase["outcome"] == "failed":
            return "failed" if when == "call" else "error"
    call = phases.get("call")
    if call is None:
        setup = phases.get("setup")
        if setup and setup["outcome"] == "skipped":
            return "xfailed" if setup["xfail"] else "skipped"
        return "incomplete"
    if call["outcome"] == "skipped":
        return "xfailed" if call["xfail"] else "skipped"
    return "xpassed" if call["xfail"] else "passed"


def pytest_command(args, python: list[str], versions: dict, project: Path, env: dict, work: Path) -> list[str]:
    """The pytest command of a run, without the extra arguments. A coverage run also changes `env`."""
    cmd = [*python, "-m", "pytest", "-p", "no:cacheprovider", "-p", "no:randomly", "-p", "lean_tests_report"]
    if args.coverage_source:
        # pytest-cov keeps a report or source that addopts requests, so the run leaves out those options.
        addopts = ini_addopts(python, project, env, work / "addopts.json")
        cmd += ["-o", "addopts=" + shlex.join(without_cov(addopts))]
        if "PYTEST_ADDOPTS" in env:
            env["PYTEST_ADDOPTS"] = shlex.join(without_cov(shlex.split(env["PYTEST_ADDOPTS"])))
        # Under sys.monitoring (the default on Python 3.14+), a line records only the first test's context.
        env["COVERAGE_CORE"] = "ctrace"
        cmd += [f"--cov={source}" for source in args.coverage_source]
        cmd += ["--cov-branch", "--cov-context=test", "--cov-report="]
    elif versions.get("pytest_cov"):
        # Coverage that addopts starts would write its data and reports into the project.
        cmd.append("--no-cov")
    if args.node_ids:
        nodeids = read_node_ids(args.node_ids)
        if version_tuple(versions["pytest"]) >= (8, 2):
            argfile = work / "node-ids.txt"
            argfile.write_text("".join(f"{n}\n" for n in nodeids), encoding="utf-8")
            cmd.append(f"@{argfile}")
        else:
            cmd += nodeids
    return cmd


def test_entries(found: dict) -> list[dict]:
    """One entry per test of the records: the final outcome, the total seconds, and the phases."""
    tests = []
    for test in found["tests"].values():
        phases = test["phases"]
        tests.append({
            "nodeid": test["nodeid"],
            "outcome": final_outcome(phases),
            "seconds": round(sum(p["seconds"] for p in phases.values()), 6),
            "phases": {
                when: {k: v for k, v in phase.items() if k != "xfail"}
                for when, phase in phases.items()
            },
        })
    return tests


def slowest(tests: list[dict]) -> dict:
    """The slowest tests of each phase, slowest first."""
    found = {}
    for when in PHASES:
        timed = [(t["phases"][when]["seconds"], t["nodeid"]) for t in tests if when in t["phases"]]
        timed.sort(key=lambda pair: -pair[0])
        found[when] = [{"nodeid": n, "seconds": s} for s, n in timed[:SLOWEST] if s > 0]
    return found


def run_suite(args, extra: list[str]) -> dict:
    project = Path(args.project).resolve()
    if not project.is_dir():
        raise UsageError(f"project directory {project} does not exist")
    python = interpreter(args.python)
    work = Path(args.work_dir).resolve() / args.label
    work.mkdir(parents=True, exist_ok=True)
    for stale in ("coverage.json", "coverage.data", "node-ids.txt", "addopts.json"):
        if (work / stale).is_file():
            (work / stale).unlink()
    records = work / "records.jsonl"
    records.write_text("", encoding="utf-8")
    log = work / "pytest.log"
    data_file = work / "coverage.data"

    env = pytest_env(records, data_file)
    if args.reverse:
        env["LEAN_TESTS_REVERSE"] = "1"

    versions = probe(python, project, env)
    if not versions.get("pytest"):
        raise UsageError("the target interpreter cannot import pytest", package="pytest")
    coverage = bool(args.coverage_source)
    if coverage and not versions.get("pytest_cov"):
        raise UsageError("the target interpreter cannot import pytest_cov", package="pytest-cov")

    before = git_status(project)
    cmd = pytest_command(args, python, versions, project, env, work) + extra
    start = time.perf_counter()
    exit_code, timed_out = run_pytest(cmd, project, env, log, args.timeout)
    wall = time.perf_counter() - start

    files = {"records": str(records), "log": str(log)}
    result_extra = {}
    if coverage:
        files["coverage_data"] = str(data_file)
        json_path = work / "coverage.json"
        report = subprocess.run(
            [*python, "-m", "coverage", "json", "--show-contexts", "-o", str(json_path)],
            cwd=project, env=env, capture_output=True, text=True,
        )
        if json_path.is_file():
            files["coverage_json"] = str(json_path)
        else:
            result_extra["coverage_error"] = tail(report.stdout + report.stderr, LOG_TAIL)
    after = git_status(project)

    found = read_records(records)
    tests = test_entries(found)
    counts = {outcome: 0 for outcome in OUTCOMES}
    for test in tests:
        counts[test["outcome"]] = counts.get(test["outcome"], 0) + 1
    collected = found["collected"] if found["collected"] is not None else [t["nodeid"] for t in tests]

    log_text = log.read_text(encoding="utf-8", errors="replace") if log.is_file() else ""
    result = {
        "summary": {
            "label": args.label,
            "pytest_exit_code": exit_code,
            "timed_out": timed_out,
            "wall_seconds": round(wall, 3),
            "collection_seconds": found["collection_seconds"],
            "collected": len(collected),
            "counts": counts,
            "collect_errors": len(found["collect_errors"]),
            "slowest": slowest(tests),
            "files_written": None if before is None or after is None else sorted(after - before),
            "reverse": bool(args.reverse),
            "coverage": coverage,
        },
        "command": cmd,
        "project": str(project),
        "rootdir": found["rootdir"] or str(project),
        "pytest_version": versions["pytest"],
        "collected": collected,
        "collect_errors": found["collect_errors"],
        "tests": tests,
        "files": files,
        "log_tail": tail(log_text, LOG_TAIL),
        **result_extra,
    }
    if exit_code in (3, 4):
        kind = "an internal error" if exit_code == 3 else "a usage error"
        result["error"] = f"pytest stopped with {kind} (exit code {exit_code}); see log_tail"
    return result


def failure(test: dict) -> str | None:
    for when in PHASES:
        phase = test["phases"].get(when)
        if phase and phase["outcome"] == "failed":
            return phase.get("exception")
    return None


def load_suite(path: str) -> dict:
    data = load_json(path, "suite output")
    if "tests" not in data or "summary" not in data:
        raise UsageError(f"{path} is not a suite output")
    return data


def compare(first_path: str, second_path: str) -> dict:
    first, second = load_suite(first_path), load_suite(second_path)
    ids_first, ids_second = suite_node_ids(first), suite_node_ids(second)
    tests_first = {t["nodeid"]: t for t in first["tests"]}
    tests_second = {t["nodeid"]: t for t in second["tests"]}
    in_first, in_second = set(ids_first), set(ids_second)

    changed = []
    for nodeid in ids_first:
        a, b = tests_first.get(nodeid), tests_second.get(nodeid)
        if a and b and a["outcome"] != b["outcome"]:
            changed.append({
                "nodeid": nodeid,
                "first": a["outcome"],
                "second": b["outcome"],
                "first_exception": failure(a),
                "second_exception": failure(b),
            })
    missing = [n for n in ids_first if n not in in_second]
    added = [n for n in ids_second if n not in in_first]
    not_run = {
        "first": [n for n in ids_first if n not in tests_first],
        "second": [n for n in ids_second if n not in tests_second],
    }

    def brief(data: dict) -> dict:
        summary = data["summary"]
        return {key: summary.get(key) for key in ("label", "wall_seconds", "timed_out", "counts")}

    def finished(data: dict) -> bool:
        summary = data["summary"]
        return not summary.get("timed_out") and summary.get("pytest_exit_code") in (0, 1)

    return {
        "summary": {
            "first": brief(first),
            "second": brief(second),
            "no_loss": finished(first) and finished(second)
            and not (changed or missing or not_run["first"] or not_run["second"]),
            "changed": len(changed),
            "missing": len(missing),
            "added": len(added),
            "not_run_first": len(not_run["first"]),
            "not_run_second": len(not_run["second"]),
            "wall_delta_seconds": round(
                (second["summary"].get("wall_seconds") or 0) - (first["summary"].get("wall_seconds") or 0), 3
            ),
            "examples": {
                "changed": [c["nodeid"] for c in changed[:EXAMPLES]],
                "missing": missing[:EXAMPLES],
                "added": added[:EXAMPLES],
            },
        },
        "changed": changed,
        "missing": missing,
        "added": added,
        "not_run": not_run,
    }
