"""scorecard: the check scorecard and its one next mode, from the files that check writes to its work directory.

Imported by lean_tests.py; never run directly. It reads run1.json,
run2.json, compare.json, scan.json, and coverage.json, the import-time
files of check step 2, growth.txt of check step 7, and end-state.txt of
check step 8. A row whose file is missing or unreadable is "not measured",
with the reason, so a measurement that check did not take never stops the
scorecard.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from lt_common import EXAMPLES, UsageError
from lt_scan import function_id

DEFAULT_HAND_OFF_BUDGET = 120.0
SCAN_ROWS = (
    ("No assertion", ("no-assertion",)),
    ("Tautology or self-comparison", ("tautology", "self-comparison")),
    ("Weak oracle, change detector, trivial code", ("weak-oracle", "change-detector", "trivial-code")),
)
PRUNE_CODES = ("no-assertion", "tautology", "self-comparison", "duplicate-shape")
COVERAGE_ROWS = ("Coverage-subset candidates", "Unmeasured tests", "Diff coverage against `<base>`")
# An -X importtime line: self and cumulative microseconds, then two spaces per nesting level and the module name.
IMPORT_LINE = re.compile(r"^import time:\s+(\d+) \|\s+(\d+) \| ( *)(\S.*)$")
TIMEOUT = "run 1 exceeded the check budget"
REQUESTS = {
    "speed": "make the tests faster",
    "review": "review the tests in this change",
    "prune": "prune the tests in {path}",
}


def scorecard_command(args) -> dict:
    work = Path(args.work_dir).resolve()
    if not work.is_dir():
        raise UsageError(f"the work directory {work} does not exist")
    if args.hand_off_budget <= 0:
        raise UsageError("--hand-off-budget must be more than 0 seconds")
    return Scorecard(work, args.hand_off_budget).build()


def read_output(path: Path) -> tuple[dict | None, str | None]:
    """The JSON object of a lean-tests output, or None and the reason that its rows are not measured."""
    if not path.is_file():
        return None, f"no {path.name} in the work directory"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        return None, f"cannot read {path.name}: {error}"
    if not isinstance(data, dict) or not isinstance(data.get("summary"), dict):
        return None, f"{path.name} is not a lean-tests output"
    return data, None


def not_measured(reason: str, package: str | None = None) -> str:
    return f"not measured: {reason}" + (f"; needs {package}" if package else "")


def listed(head: str, items: list[str]) -> str:
    """`head`, then up to EXAMPLES of `items`."""
    shown = items[:EXAMPLES]
    if not shown:
        return head
    more = f", and {len(items) - len(shown)} more" if len(items) > len(shown) else ""
    return f"{head}: {', '.join(shown)}{more}"


def seconds(value: float | None) -> str:
    return "not reported" if value is None else f"{value:.2f} s"


def phases(entries: list[dict]) -> list[str]:
    return [f"{entry['nodeid']} {seconds(entry.get('seconds'))}" for entry in entries]


def counted(found: dict[str, list[str]], codes: tuple) -> tuple[list[str], str]:
    """The tests with one of `codes`, and the count of each code."""
    tests = list(dict.fromkeys(nodeid for code in codes for nodeid in found.get(code, [])))
    counts = ", ".join(f"{code} {len(found.get(code, []))}" for code in codes) if len(codes) > 1 else ""
    return tests, counts


def import_cost(path: Path) -> str:
    """The cumulative import time of one `<source>` and its five largest imports, from one -X importtime file."""
    source = path.name[len("importtime-"):-len(".txt")]
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as error:
        return f"{source} {not_measured(f'cannot read {path.name}: {error.strerror}')}"
    entries = []
    for line in lines:
        match = IMPORT_LINE.match(line)
        if match:
            entries.append((int(match.group(2)), len(match.group(3)) // 2, match.group(4).strip()))
    top = [index for index, (_, depth, name) in enumerate(entries) if depth == 0 and name == source]
    if not top:
        last = next((line.strip() for line in reversed(lines) if line.strip()), "the file is empty")
        return f"{source} {not_measured(f'the import failed: {last}')}"
    end = top[-1]
    start = max([index for index in range(end) if entries[index][1] == 0], default=-1) + 1
    largest = sorted(entries[start:end], key=lambda entry: -entry[0])
    return listed(
        f"{source} {entries[end][0] / 1000:.0f} ms; largest imports",
        [f"{name} {cumulative / 1000:.0f} ms" for cumulative, _, name in largest],
    )


def text_lines(path: Path) -> list[str] | None:
    try:
        return [line.rstrip() for line in path.read_text(encoding="utf-8", errors="replace").splitlines()]
    except OSError:
        return None


def cell(text: str) -> str:
    return text.replace("\n", " ").replace("|", "\\|")


class Scorecard:
    """The rows and the next mode of one check work directory."""

    def __init__(self, work: Path, hand_off_budget: float) -> None:
        self.work = work
        self.budget = hand_off_budget
        self.run1, self.run1_reason = read_output(work / "run1.json")
        self.run2, self.run2_reason = read_output(work / "run2.json")
        self.compare, self.compare_reason = read_output(work / "compare.json")
        self.scan, self.scan_reason = read_output(work / "scan.json")
        self.coverage, self.coverage_reason = read_output(work / "coverage.json")
        summary = (self.run1 or {}).get("summary") or {}
        self.timed_out = bool(summary.get("timed_out"))
        self.no_git = self.run1 is not None and summary.get("files_written") is None
        self.findings: dict[str, list[str]] = {}
        self.files: dict[str, str] = {}
        for finding in (self.scan or {}).get("findings", []):
            tests = self.findings.setdefault(finding["code"], [])
            if finding["nodeid"] not in tests:
                tests.append(finding["nodeid"])
            self.files[finding["nodeid"]] = finding["file"]
        self.unknown: list[str] = []

    def build(self) -> dict:
        rows = [*self.run_rows(), *self.compare_rows(), *self.scan_rows(), *self.coverage_rows(), *self.end_rows()]
        mode = self.next_mode()
        lines = ["| Row | Value |", "| --- | --- |", *(f"| {cell(row)} | {cell(value)} |" for row, value in rows), ""]
        if mode["mode"] == "check":
            lines.append(f"Next mode: check again after the next change. {mode['reason']}")
        else:
            lines.append(f"Next mode: {mode['mode']}. {mode['reason']}")
            lines.append(f'This mode runs only on request: ask, for example, "{mode["request"]}".')
        return {
            "summary": {
                "next_mode": mode,
                "not_measured": [row for row, value in rows if value.startswith("not measured")],
                "markdown": lines,
            },
            "work_dir": str(self.work),
            "rows": [{"row": row, "value": value} for row, value in rows],
        }

    def run_rows(self) -> list[tuple[str, str]]:
        names = ("Tests collected", "Outcomes", "Wall time and collection time")
        later = ("Slowest tests", "Slowest setup and teardown")
        imports = ("Import cost", self.import_rows())
        if self.run1 is None:
            reason = not_measured(self.run1_reason)
            return [*((name, reason) for name in names), imports, *((name, reason) for name in later)]
        summary = self.run1["summary"]
        counts = summary.get("counts") or {}
        outcomes = ", ".join(f"{outcome} {count}" for outcome, count in counts.items() if count) or "no test ran"
        failing = [t["nodeid"] for t in self.run1.get("tests", []) if t.get("outcome") in ("failed", "error")]
        outcomes = listed(outcomes, failing)
        code = summary.get("pytest_exit_code")
        if code == 5:
            outcomes += "; pytest collected no test (exit code 5)"
        elif code is not None and code >= 2:
            outcomes += f"; pytest exit code {code}: read {self.work / 'run1' / 'pytest.log'}"
        wall = f"{seconds(summary.get('wall_seconds'))} wall, collection {seconds(summary.get('collection_seconds'))}"
        if self.timed_out:
            wall += f"; {TIMEOUT}"
        slowest = {when: phases(entries)[:EXAMPLES] for when, entries in (summary.get("slowest") or {}).items()}
        setup, teardown = (f"{when}: {', '.join(slowest.get(when) or ['none'])}" for when in ("setup", "teardown"))
        return [
            ("Tests collected", str(summary.get("collected"))),
            ("Outcomes", outcomes),
            ("Wall time and collection time", wall),
            imports,
            ("Slowest tests", ", ".join(slowest.get("call") or ["none"])),
            ("Slowest setup and teardown", f"{setup}; {teardown}"),
        ]

    def import_rows(self) -> str:
        files = sorted(self.work.glob("importtime-*.txt"))
        if not files:
            return not_measured("no `importtime-<source>.txt` file in the work directory")
        return "; ".join(import_cost(path) for path in files)

    def compare_rows(self) -> list[tuple[str, str]]:
        name = "Flaky or order-dependent"
        if self.timed_out:
            return [(name, not_measured(TIMEOUT))]
        if self.compare is None:
            return [(name, not_measured(self.compare_reason))]
        changed = [f"{c['nodeid']} ({c['first']} -> {c['second']})" for c in self.compare.get("changed", [])]
        value = listed(f"{len(changed)} tests changed their outcome", changed) if changed else "none"
        unstable = [*self.compare.get("missing", []), *self.compare.get("added", [])]
        if unstable:
            summary = self.compare["summary"]
            value += "; " + listed(
                f"collection is not stable: {summary.get('missing')} missing, {summary.get('added')} added", unstable
            )
        not_run = (self.compare.get("not_run") or {}).get("second") or []
        if not_run:
            value += f"; {len(not_run)} tests not run in run 2"
        return [(name, value)]

    def scan_rows(self) -> list[tuple[str, str]]:
        names = [*(name for name, _ in SCAN_ROWS), "Duplicate-shape groups", "Sleep calls", "Protected tests"]
        if self.scan is None:
            return [(name, not_measured(self.scan_reason)) for name in names]
        rows = []
        for name, codes in (*SCAN_ROWS, ("Sleep calls", ("sleep",)), ("Protected tests", ("protected",))):
            tests, counts = counted(self.findings, codes)
            rows.append((name, listed(f"{len(tests)} tests" + (f" ({counts})" if counts else ""), tests)))
        groups = [f"({', '.join(group['nodeids'])})" for group in self.scan.get("duplicate_groups", [])]
        rows.insert(3, ("Duplicate-shape groups", listed(f"{len(groups)} groups", groups)))
        if self.scan["summary"].get("git_history") is None:
            name, value = rows[-1]
            rows[-1] = (name, f"{value}; commit subjects not measured: the scan ran without --git-history")
        return rows

    def coverage_rows(self) -> list[tuple[str, str]]:
        if self.timed_out:
            return [(name, not_measured(TIMEOUT)) for name in COVERAGE_ROWS]
        if self.coverage is None:
            if self.run2 is not None and not self.run2["summary"].get("coverage"):
                reason = not_measured("run 2 has no coverage contexts", "pytest-cov")
            else:
                reason = not_measured(self.coverage_reason)
            return [(name, reason) for name in COVERAGE_ROWS]
        equal = [f"({', '.join(group)})" for group in self.coverage.get("equal_groups", [])]
        subsets = [f"{entry['test']} < {entry['supersets'][0]}" for entry in self.coverage.get("strict_subsets", [])]
        candidates = listed(f"{len(equal)} equal groups", equal)
        candidates += "; " + listed(f"{len(subsets)} strict subsets", subsets)
        unmeasured = self.coverage.get("unmeasured", [])
        return [
            ("Coverage-subset candidates", candidates),
            ("Unmeasured tests", listed(f"{len(unmeasured)} tests", unmeasured)),
            ("Diff coverage against `<base>`", self.diff_row()),
        ]

    def diff_row(self) -> str:
        diff = self.coverage.get("diff")
        if diff is None:
            return not_measured("coverage ran without --base, so no base ref")
        missed = [f"{entry['path']}:{line}" for entry in diff.get("files", []) for line in entry.get("missed", [])]
        raises = sum(len(entry["raise"]["missed"]) for entry in diff.get("files", []))
        excepts = sum(len(entry["except"]["missed"]) for entry in diff.get("files", []))
        percent = "" if diff.get("percent") is None else f" ({diff['percent']}%)"
        value = listed(
            f"{diff.get('executed')} of {diff.get('executable')} changed lines executed{percent} against "
            f"{diff.get('base')}; {diff.get('missed')} missed, {raises} raise and {excepts} except lines among them",
            missed,
        )
        if diff.get("unmeasured_files"):
            value += "; " + listed(f"{len(diff['unmeasured_files'])} unmeasured files", diff["unmeasured_files"])
        if diff.get("unparsed"):
            value += "; " + listed(f"{len(diff['unparsed'])} unparsed files", [u["file"] for u in diff["unparsed"]])
        return value

    def end_rows(self) -> list[tuple[str, str]]:
        names = ("Instructions that force test growth", "Files the tests wrote")
        if self.no_git:
            return [(name, not_measured("the project is not a Git work tree")) for name in names]
        growth = text_lines(self.work / "growth.txt")
        if growth is None:
            growth_value = not_measured("no growth.txt from check step 7 in the work directory")
        else:
            found = [line for line in growth if line]
            growth_value = listed(f"{len(found)} lines", found) if found else "none"
        end = text_lines(self.work / "end-state.txt")
        if end is None:
            return [(names[0], growth_value), (names[1], not_measured("no end-state.txt from check step 8"))]
        written = {}
        for run in (self.run1, self.run2):
            summary = (run or {}).get("summary") or {}
            for line in summary.get("files_written") or []:
                written.setdefault(line, []).append(summary.get("label") or "run")
        changes = []
        for line in dict.fromkeys(line for line in end if line[:2] in ("< ", "> ")):
            runs = written.get(line[2:])
            changes.append(f"{line} ({', '.join(runs)})" if runs else line)
        return [(names[0], growth_value), (names[1], listed(f"{len(changes)} lines", changes) if changes else "none")]

    def next_mode(self) -> dict:
        """The first rule of check step 9 that applies; rules whose input was not measured are noted."""
        for rule in (self.speed, self.review, self.prune):
            found = rule()
            if found:
                mode, reason, path = found
                request = REQUESTS[mode].format(path=path)
                return {"mode": mode, "reason": reason, "path": path, "request": request}
        if self.unknown:
            reason = (
                "No rule applies to the measured rows, but these inputs were not measured: "
                + ", ".join(self.unknown) + ". Measure them before you conclude that the suite needs no work."
            )
        else:
            reason = "No rule applies: the suite needs no lean-tests work now."
        return {"mode": "check", "reason": reason, "path": None, "request": None}

    def speed(self) -> tuple | None:
        if self.run1 is None:
            self.unknown.append("run 1")
            return None
        summary = self.run1["summary"]
        slowest = sorted(
            ((entry.get("seconds") or 0.0, when, entry["nodeid"])
             for when, entries in (summary.get("slowest") or {}).items() for entry in entries),
            reverse=True,
        )
        named = listed("slowest phases", [f"{when} of {nodeid} {value:.2f} s" for value, when, nodeid in slowest][:3])
        if self.timed_out:
            return "speed", f"Run 1 exceeded the check budget; {named}.", None
        wall = summary.get("wall_seconds")
        if wall is not None and wall > self.budget:
            over = f"Run 1 took {wall:.1f} s, more than the hand-off budget of {self.budget:g} s"
            return "speed", f"{over}; {named}.", None
        if self.compare is None:
            self.unknown.append("the comparison of the runs")
            return None
        changed = [entry["nodeid"] for entry in self.compare.get("changed", [])]
        if changed:
            return "speed", listed(f"{len(changed)} tests changed their outcome between the runs", changed) + (
                ". speed fixes order-dependent tests before it turns on parallel runs."
            ), None
        return None

    def review(self) -> tuple | None:
        diff = (self.coverage or {}).get("diff")
        if diff is None:
            self.unknown.append("diff coverage")
            return None
        if not diff.get("missed"):
            return None
        files = diff.get("files", [])
        missed = [f"{entry['path']}:{line}" for entry in files for line in entry.get("missed", [])]
        raises = sum(len(entry["raise"]["missed"]) for entry in files)
        excepts = sum(len(entry["except"]["missed"]) for entry in files)
        head = f"No test executes {diff['missed']} changed product lines ({raises} raise and {excepts} except lines)"
        return "review", listed(head, missed) + ".", None

    def prune(self) -> tuple | None:
        if self.scan is None:
            self.unknown.append("the scan")
            return None
        protected = set(self.findings.get("protected", []))
        candidates: dict[str, dict[str, set]] = {}

        def add(nodeid: str, source: str) -> None:
            path, parts = function_id(nodeid)
            key = "::".join([path, *parts])
            if key not in protected:
                candidates.setdefault(self.files.get(key, path), {}).setdefault(key, set()).add(source)

        for code in PRUNE_CODES:
            for nodeid in self.findings.get(code, []):
                add(nodeid, code)
        if self.coverage is None:
            self.unknown.append("the coverage subsets")
        else:
            for group in self.coverage.get("equal_groups", []):
                for nodeid in group:
                    add(nodeid, "coverage-subset")
            for entry in self.coverage.get("strict_subsets", []):
                add(entry["test"], "coverage-subset")
        if not candidates:
            return None
        path = min(candidates, key=lambda name: (-len(candidates[name]), name))
        tests = candidates[path]
        sources = {}
        for found in tests.values():
            for source in found:
                sources[source] = sources.get(source, 0) + 1
        counts = ", ".join(f"{source} {count}" for source, count in sorted(sources.items()))
        return "prune", (
            f"{path} has the most unprotected candidates: {len(tests)} tests ({counts})."
        ), path
