#!/usr/bin/env python3
"""lean-tests command-line entry: measure and inspect a pytest suite.

Each subcommand prints one JSON object to stdout. Exit status 0 means
success; 1 means that the gate failed, or that pin --check found a changed
source or no source with the quote; 2 means a usage or environment error,
and the JSON then has an "error" key. Python 3.9 or newer, standard library
only.

  suite     run pytest with one outcome record per test phase
  compare   compare two suite outputs
  scan      find weak, duplicate, and protected tests in the test files
  coverage  read per-test coverage contexts and diff coverage
  mutate    build the kill matrix of a prune or review scope, or recheck its killed set
  gate      the weakening gate between two Git refs, with the labels of the new tests
  pin       pin requirement sources with SHA-256 hashes, or check a pin record

Run `lean_tests.py <subcommand> --help` for the options.
"""

# No `from __future__ import annotations` here: Python 3.6 must reach the version check.
import json
import sys

if sys.version_info < (3, 9):
    MESSAGE = "needs Python 3.9 or newer, not Python %d.%d" % sys.version_info[:2]
    print(json.dumps({"error": MESSAGE}, indent=1))
    print("lean_tests.py: " + MESSAGE, file=sys.stderr)
    sys.exit(2)

# Leave no __pycache__ directory beside the scripts.
sys.dont_write_bytecode = True

import argparse  # noqa: E402
from typing import Optional  # noqa: E402

import lt_coverage  # noqa: E402
import lt_gate  # noqa: E402
import lt_mutate  # noqa: E402
import lt_pin  # noqa: E402
import lt_scan  # noqa: E402
import lt_suite  # noqa: E402
from lt_common import UsageError  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="lean_tests.py",
        description="Measure and inspect a pytest suite. Each subcommand prints JSON.",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    output = argparse.ArgumentParser(add_help=False)
    output.add_argument("--out", help="write the full JSON to this file and print only its summary")

    suite = sub.add_parser(
        "suite",
        parents=[output],
        help="run pytest with per-test outcome records",
        description=(
            "Run pytest in the project with the pytest cache off and one outcome "
            "record per test phase. Arguments after `--` go to pytest."
        ),
    )
    suite.add_argument(
        "--python",
        required=True,
        help="target interpreter, or a command that runs it, split like a shell "
        "(for example: uv run --no-sync --with pytest-cov python)",
    )
    suite.add_argument("--project", default=".", help="project directory; pytest runs here (default: .)")
    suite.add_argument("--work-dir", required=True, help="directory for records, logs, and coverage data")
    suite.add_argument("--label", default="suite", help="name of this run's folder in the work directory")
    suite.add_argument("--reverse", action="store_true", help="run the collected tests in reversed order")
    suite.add_argument(
        "--coverage-source",
        action="append",
        default=[],
        metavar="SRC",
        help="record per-test coverage contexts for this package or path (repeatable; needs pytest-cov)",
    )
    suite.add_argument("--timeout", type=float, help="stop pytest after this many seconds")
    suite.add_argument("--node-ids", help="file with one node ID per line; run only these tests")

    compare = sub.add_parser(
        "compare",
        parents=[output],
        help="compare two suite outputs",
        description=(
            "Compare two suite outputs: changed outcomes, node IDs missing or added, and tests not run. "
            "summary.no_loss is true when both runs finished and no test is missing, changed, or not run."
        ),
    )
    compare.add_argument("first", help="suite output JSON of the first run")
    compare.add_argument("second", help="suite output JSON of the second run")

    scan = sub.add_parser("scan", parents=[output], help="AST scan of the collected tests")
    scan.add_argument(
        "--project", help="project directory of the --node-ids file (default: .); --suite names its own"
    )
    source = scan.add_mutually_exclusive_group(required=True)
    source.add_argument("--suite", help="suite output JSON; scan its collected node IDs")
    source.add_argument("--node-ids", help="file with one node ID per line, relative to --project")

    coverage = sub.add_parser("coverage", parents=[output], help="per-test coverage, subsets, unmeasured tests, diff coverage")
    coverage.add_argument("--contexts", required=True, help="output of `coverage json --show-contexts`")
    coverage.add_argument("--suite", required=True, help="suite output JSON of the run that recorded the contexts")
    coverage.add_argument("--base", help="base Git ref for diff coverage of changed product lines")

    mutate = sub.add_parser(
        "mutate",
        parents=[output],
        help="kill matrix of a prune or review scope, or the killed-set check after a removal batch",
        description=(
            "Run each mutant of the product modules that the scope's tests cover against every "
            "in-scope test, in temporary copies of the project. With --base and --new-tests, mutate "
            "only the review lines and give each new test its admission verdict. Arguments after `--` "
            "go to pytest."
        ),
    )
    mutate.add_argument("--python", required=True, help="target interpreter, or a command that runs it (as for suite)")
    mutate.add_argument(
        "--suite",
        required=True,
        help="suite output of the scope: a --coverage-source run for a matrix, or the run after a removal batch",
    )
    mutate.add_argument("--work-dir", required=True, help="directory outside the project for the copies and records")
    mutate.add_argument(
        "--recheck", metavar="MATRIX", help="rerun the killed set of this mutate output against the tests of --suite"
    )
    mutate.add_argument(
        "--base",
        help="review scope: mutate only the product lines changed since the merge base of BASE and HEAD, "
        "and the lines that only the --new-tests tests cover",
    )
    mutate.add_argument(
        "--new-tests", metavar="FILE", help="file with the node IDs of the new tests; goes with --base"
    )
    mutate.add_argument(
        "--budget", type=float,
        help=f"seconds for the whole run (default: {lt_mutate.DEFAULT_BUDGET:g}, "
        f"or {lt_mutate.DEFAULT_REVIEW_BUDGET:g} with --base)",
    )
    mutate.add_argument(
        "--workers", type=int, default=lt_mutate.DEFAULT_WORKERS, help="parallel copies (default: CPU count minus 1)"
    )

    gate = sub.add_parser(
        "gate",
        parents=[output],
        help="the weakening gate between two Git refs",
        description=(
            "Classify each test-side change from BASE to HEAD, replay the changed base tests against the "
            "head product code, and run each new test against the base product code, in a temporary "
            "detached worktree. Exit status 1 means that a mixed change has a BEHAVIOR CHANGE, WEAKENING, "
            "or UNCLASSIFIED item. Arguments after `--` go to pytest."
        ),
    )
    gate.add_argument("--project", default=".", help="project directory in a Git work tree (default: .)")
    gate.add_argument(
        "--base", required=True, help="base Git ref; the change starts at the merge base of BASE and HEAD"
    )
    gate.add_argument("--head", default="HEAD", help="head Git ref (default: HEAD)")
    gate.add_argument(
        "--per-commit", action="store_true",
        help="one gate unit per commit, for a merge method that keeps commits (default: the whole range is one unit)",
    )
    gate.add_argument("--python", help="target interpreter, or a command that runs it (as for suite)")
    gate.add_argument("--work-dir", help="directory outside the repository for the worktree, records, and logs")
    gate.add_argument(
        "--static-only", action="store_true",
        help="run only the static classification: no replay, no collection evidence, and no new-test labels",
    )
    gate.add_argument(
        "--timeout", type=float, default=lt_gate.DEFAULT_TIMEOUT,
        help="stop each pytest run after this many seconds (default: %(default)g)",
    )

    pin = sub.add_parser(
        "pin",
        parents=[output],
        help="pin requirement sources with SHA-256 hashes, or check a pin record",
        description=(
            "With --record, write each --source file's text and SHA-256 hash to a new pin record. With "
            "--check, recompute the hash of each pinned text, and with --quote, find the pinned requirement "
            "sources that contain the quote. Exit status 1 means that the check failed."
        ),
    )
    action = pin.add_mutually_exclusive_group(required=True)
    action.add_argument("--record", metavar="FILE", help="write a new pin record; the file must not exist")
    action.add_argument("--check", metavar="FILE", help="check the pin record FILE")
    pin.add_argument(
        "--source", action="append", default=[], metavar="NAME=PATH",
        help="a requirement source to pin (repeatable; goes with --record)",
    )
    pin.add_argument(
        "--quote",
        help="text that a pinned requirement source must contain (goes with --check); "
        "white space matches any white space",
    )
    return parser


def split_pytest_args(argv: list[str]) -> tuple[list[str], list[str]]:
    if argv[:1] in (["suite"], ["mutate"], ["gate"]) and "--" in argv:
        index = argv.index("--")
        return argv[:index], argv[index + 1:]
    return argv, []


def main(argv: Optional[list[str]] = None) -> int:
    own, extra = split_pytest_args(list(sys.argv[1:] if argv is None else argv))
    args = build_parser().parse_args(own)
    try:
        if args.command == "suite":
            result = lt_suite.run_suite(args, extra)
        elif args.command == "compare":
            result = lt_suite.compare(args.first, args.second)
        elif args.command == "scan":
            result = lt_scan.scan_command(args)
        elif args.command == "mutate":
            result = lt_mutate.mutate_command(args, extra)
        elif args.command == "gate":
            result = lt_gate.gate_command(args, extra)
        elif args.command == "pin":
            result = lt_pin.pin_command(args)
        else:
            result = lt_coverage.coverage_command(args)
    except UsageError as error:
        print(json.dumps({"error": str(error), **error.extra}, indent=1))
        print(f"lean_tests.py: {error}", file=sys.stderr)
        return 2
    if args.out:
        try:
            with open(args.out, "w", encoding="utf-8") as handle:
                json.dump(result, handle, indent=1)
        except OSError as error:
            print(json.dumps({"error": f"cannot write {args.out}: {error.strerror}"}, indent=1))
            return 2
        brief = {"summary": result["summary"], "output": args.out}
        if "error" in result:
            brief["error"] = result["error"]
        print(json.dumps(brief, indent=1))
    else:
        print(json.dumps(result, indent=1))
    if "error" in result:
        return 2
    failed = args.command in ("gate", "pin") and result["summary"].get("passed") is False
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
