---
name: lean-tests
description: This skill should be used when the user asks to "check the test suite", "audit the tests", "find out why the tests are slow", "make the tests faster", or "speed up CI", or asks which pytest tests are flaky, order-dependent, redundant, or check nothing. It measures a Python pytest suite without changing a file and prints a scorecard with one recommended next mode; on request, it makes the suite faster without deleting a test. To write a test first, use tdd; for bugs in a diff, use /code-review; for a broad evaluation of a project, use project-eval.
---

# Lean Tests

Measure a pytest suite and find the tests that cost time or add no
protection: slow tests and fixtures, flaky or order-dependent tests, tests
that check nothing, and tests whose coverage other tests repeat. A test
adds protection when it detects a fault that no other test detects.

## Modes

This version has two modes. With no mode, run check.

- **check**: measure the suite and print a scorecard. It changes no file and
  installs nothing. Follow [references/check.md](references/check.md).
- **speed**: make the suite faster without deleting a test. It measures
  first, applies fixes one at a time in a fixed order, defines test tiers
  with time budgets, and writes the tier commands into `CLAUDE.md` and
  `AGENTS.md`. Run it only when the user's request asks for speed changes,
  such as "make the tests faster" or "speed up CI". A question about speed,
  such as why the tests are slow, runs check. Follow
  [references/speed.md](references/speed.md).

When the user asks to prune or review tests, run check, and say that this
version has no prune or review mode.

## Safety rules

These rules apply to all work on a test suite.

1. Change a file only when the user's request asks for a change.
2. Keep each test's protection. Put no test weakening in a mixed change. A
   mixed change is a commit, or the whole pull request when merges squash,
   that changes product code. A test weakening is a test-side change that
   can lower what existing tests detect, such as removing, skipping,
   loosening, or rewriting an existing test.
3. Delete or merge a test only with killed-mutant evidence: a mutant is a
   copy of the product code with one small fault, and a test kills it when
   the test fails on that copy. Delete in batches of at most 20 tests. Each
   batch is one commit of its own, with a written reason for each test.
   When the evidence is incomplete, delete nothing. Equal coverage is not evidence: tests that
   cover the same lines can detect different faults.
4. Keep protected tests: regression, characterization, security,
   compatibility, and performance tests, and one happy-path test per test
   seam, the public boundary where a test observes behavior. Rewrite a protected test only to fix a defect in the test.
5. Name each new dependency and its purpose before you add it, and add it
   with the project's own dependency manager.
6. Report each measurement that you could not take, with the package that
   enables it.

## Boundaries

- lean-tests works on Python projects that run their tests with pytest.
- The `tdd` skill decides where a new test goes. lean-tests measures which
  tests add protection and how the suite stays fast.
- Use coverage to find untested changes. Do not set a coverage percentage
  as a target.

## Setup

1. Find `<project>`: the directory where the project runs pytest, with its
   pytest configuration in `pyproject.toml`, `pytest.ini`, `tox.ini`, or
   `setup.cfg`.
2. Find `<python>`, the project's interpreter:
   - With `uv.lock` and an existing `.venv`: `uv run --no-sync python`.
     `--no-sync` keeps `uv.lock` and the environment unchanged.
   - Otherwise the interpreter of the project's virtual environment, such as
     `.venv/bin/python`, or the interpreter that the user names.
   - When the project has no environment, stop and ask the user. lean-tests
     creates no environment.
3. Get analysis tools without an install. When the project runs under uv,
   add `--with <package>` for each missing tool, for example
   `uv run --no-sync --with pytest-cov python`. Otherwise use only the
   packages that the environment has.
4. Make one work directory outside the project, and write its printed path
   as `<work-dir>` in later commands:

   ```bash
   mktemp -d
   ```

   Records, logs, coverage data, and reports go there. When the work is
   done, remove it by its path: `rm -r <work-dir>`.
5. Run the bundled command-line entry with `<python>`, so that it parses
   the project's files with the project's Python version. The entry needs
   Python 3.9 or newer and only the standard library:

   ```bash
   <python> <skill-dir>/scripts/lean_tests.py <subcommand> --help
   ```

   Here `<skill-dir>` is this skill's directory. Each subcommand prints
   JSON. With `--out <file>`, it writes the full JSON to the file and prints
   only the summary. Exit status 2 means a usage or environment error: the
   JSON `error` key gives the cause, and `package` names a missing package.
