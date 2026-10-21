#!/usr/bin/env python3
"""lean-tests command-line entry: measure and inspect a pytest suite.

Each subcommand prints one JSON object to stdout. Exit status 0 means
success; 2 means a usage or environment error, and the JSON then has an
"error" key. Python 3.9 or newer, standard library only.

  suite     run pytest with one outcome record per test phase
  compare   compare two suite outputs
  scan      find weak, duplicate, and protected tests in the test files
  coverage  read per-test coverage contexts and diff coverage
  mutate    build the kill matrix of a prune scope, or recheck its killed set

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
import lt_mutate  # noqa: E402
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
        help="kill matrix of a prune scope, or the killed-set check after a removal batch",
        description=(
            "Run each mutant of the product modules that the scope's tests cover against every "
            "in-scope test, in temporary copies of the project. Arguments after `--` go to pytest."
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
        "--budget", type=float, default=lt_mutate.DEFAULT_BUDGET,
        help="seconds for the whole run (default: %(default)g)",
    )
    mutate.add_argument(
        "--workers", type=int, default=lt_mutate.DEFAULT_WORKERS, help="parallel copies (default: CPU count minus 1)"
    )
    return parser


def split_pytest_args(argv: list[str]) -> tuple[list[str], list[str]]:
    if argv[:1] in (["suite"], ["mutate"]) and "--" in argv:
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
    return 2 if "error" in result else 0


if __name__ == "__main__":
    sys.exit(main())
