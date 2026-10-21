# Check

check measures a pytest suite and prints a scorecard. It changes no file in
the project and installs nothing. It runs the suite at most twice: run 1 in
file order, and run 2 in reversed order with per-test coverage. A test whose
outcome differs between the runs is flaky or order-dependent.

Done when the scorecard gives each row a value or a "not measured" reason,
it names one next step with its reason, and the project's Git status is the
same as at the start, or the difference is reported as files the tests
wrote.

First complete the [setup](../SKILL.md#setup): `<project>`, `<python>`,
`<work-dir>`, and `<skill-dir>`.

## 1. Record the starting state

```bash
git -C <project> status --porcelain --untracked-files=all > <work-dir>/status-before.txt
```

When the project is not a Git work tree, this command fails. Then report
that check cannot prove that it changed no file, skip diff coverage, and
continue.

Choose two values for later steps:

- `<base>`: the base ref for diff coverage. Use the ref that the user names.
  Otherwise use the remote default branch, which
  `git -C <project> rev-parse --abbrev-ref origin/HEAD` prints. When neither
  exists, skip diff coverage and report why.
- `<source>`: the import name of each package of the project's own code,
  for example `mypkg` for `src/mypkg/`. Read it from the package layout and
  `pyproject.toml`.

## 2. Run 1: file order

```bash
python3 <skill-dir>/scripts/lean_tests.py suite --python "<python>" \
  --project <project> --work-dir <work-dir> --label run1 --timeout 600 \
  --out <work-dir>/run1.json
```

The 600-second timeout is the check budget. The command turns off the
pytest cache and bytecode files, and loads a bundled plugin that records
each test phase. The printed summary gives:

- `counts`, `wall_seconds`, and `collection_seconds`.
- `slowest`: the slowest `call`, `setup`, and `teardown` phases. Slow setup
  or teardown points at a fixture, not at the test body.
- `files_written`: Git status lines that the tests added.

When `pytest_exit_code` is 2 or more, read `<work-dir>/run1/pytest.log`
and report the cause. Exit code 5 means that pytest collected no test.

When `timed_out` is true, the suite is too slow to measure twice. Skip
steps 3, 4, and 6, report their rows as "not measured: run 1 exceeded the
check budget", and recommend speed work.

## 3. Run 2: reversed order with coverage contexts

```bash
python3 <skill-dir>/scripts/lean_tests.py suite --python "<python>" \
  --project <project> --work-dir <work-dir> --label run2 --reverse \
  --coverage-source <source> --timeout 1800 --out <work-dir>/run2.json
```

Repeat `--coverage-source` for each package. Run 2 records which lines
each test runs (pytest-cov `--cov-context=test`). It sets
`COVERAGE_CORE=ctrace`, because `sys.monitoring` loses per-test contexts.
Coverage contexts slow a run, so the timeout is three times the budget.

- When the command exits with status 2 and `package` is `pytest-cov`: under
  uv, run it again with
  `--python "uv run --no-sync --with pytest-cov python"`. Otherwise run it
  again without `--coverage-source`. The order check still
  works. Report per-test coverage, coverage subsets, unmeasured tests, and
  diff coverage as "not measured: needs pytest-cov".
- When the project's pytest options turn on pytest-xdist (`-n`), add
  `-- -n 0` at the end of the command. Under pytest-xdist, the order is not
  reversed.

## 4. Compare the runs

```bash
python3 <skill-dir>/scripts/lean_tests.py compare <work-dir>/run1.json \
  <work-dir>/run2.json --out <work-dir>/compare.json
```

- `changed`: the tests whose outcome differs between the runs. Report them
  as flaky or order-dependent.
- `missing` and `added`: node IDs that only one run collected. Report them:
  collection is not stable.
- `not_run`: tests that a timed-out run did not reach. They are not missing.

## 5. Scan the tests

```bash
python3 <skill-dir>/scripts/lean_tests.py scan --suite <work-dir>/run1.json \
  --out <work-dir>/scan.json
```

The scan reads the test functions of the node IDs that pytest collected.
Each finding has a code, a node ID, a file, and a line. A finding is a
candidate from the test source alone, not a verdict.

| Code | The test |
| --- | --- |
| `no-assertion` | makes no check: no `assert`, `pytest.raises`, `pytest.fail`, assert method, or `raise`, also not through a helper |
| `tautology` | compares a constant with itself, or recomputes the expected value the way the code does |
| `self-comparison` | compares an expression with itself |
| `weak-oracle` | checks only truthiness, non-None, type, or non-empty |
| `change-detector` | checks only mock calls, their order, or their arguments |
| `trivial-code` | only compares an imported constant with a literal |
| `duplicate-shape` | equals other tests except for literals; `duplicate_groups` lists the groups |
| `protected` | has a protection signal: an issue reference, or regression, characterization, security, compat, or perf in a name, marker, docstring, or comment |
| `input-class` | has a marker of a distinct input class: boundary, types, unicode, timezone, large-size, error-path, concurrency, locale, or platform |
| `sleep` | calls `time.sleep` |

`unresolved` lists node IDs whose function the scan did not find, for
example a test inherited from another module.

## 6. Read per-test coverage and diff coverage

Skip this step when run 2 has no coverage contexts. Then
`<work-dir>/run2/coverage.json` does not exist.

```bash
python3 <skill-dir>/scripts/lean_tests.py coverage \
  --contexts <work-dir>/run2/coverage.json --suite <work-dir>/run2.json \
  --base <base> --out <work-dir>/coverage.json
```

Without a `<base>`, leave out `--base`.

- `equal_groups`: tests that run the same product lines. `strict_subsets`:
  tests whose lines are a strict subset of the lines of other tests. Both
  are redundancy candidates only. Equal coverage does not mean equal fault
  detection.
- `unmeasured`: tests whose call phase ran no measured line, for example a
  test that runs the code in a subprocess. Their value is unknown, not zero.
- `diff`: the product lines changed since the merge base of `<base>` and
  HEAD, with uncommitted and untracked files. It counts the changed lines
  that the tests executed and missed, and the `raise` and `except` lines
  among them. `unmeasured_files` are changed Python files that coverage did
  not measure.

## 7. Find agent instructions that force test growth

```bash
git -C <project> grep -n -i -E 'even if (nobody|no one|not) asked|always (add|write) (new )?tests|add (or update )?tests for (every|each|all|any)|never (delete|remove) (a |any )?tests?|do not (delete|remove) (a |any )?tests?|coverage[^.]{0,40}[0-9]+ ?%|[0-9]+ ?% (test |line |branch )?coverage' -- '*CLAUDE.md' '*AGENTS.md' '*GEMINI.md' '.cursorrules' '.cursor/rules/*' '.github/copilot-instructions.md'
git -C <project> grep -n -E 'fail[-_]under' -- '*.toml' '*.cfg' '*.ini' '.coveragerc' '*.yml' '*.yaml'
```

Report each line that tells agents to add tests by default, forbids the
deletion of tests, or sets a coverage percentage target. Together these
rules make a suite that can only grow. Change them only when the user asks.

## 8. Check the end state

```bash
git -C <project> status --porcelain --untracked-files=all | diff <work-dir>/status-before.txt -
```

Each difference is a file that the tests wrote. The `files_written` list
of each run names the run that wrote it. Report these files, and ask the
user before you remove one.

## 9. Write the scorecard

Write one table. Give each row a value with up to five examples, or "not
measured" with the reason and the package that enables it.

| Row | Source |
| --- | --- |
| Tests collected | run 1 `collected` |
| Outcomes | run 1 `counts` |
| Wall time and collection time | run 1 `wall_seconds`, `collection_seconds` |
| Slowest tests | run 1 `slowest.call` |
| Slowest setup and teardown | run 1 `slowest.setup`, `slowest.teardown` |
| Flaky or order-dependent | compare `changed` |
| No assertion | scan `no-assertion` |
| Tautology or self-comparison | scan `tautology`, `self-comparison` |
| Weak oracle, change detector, trivial code | scan `weak-oracle`, `change-detector`, `trivial-code` |
| Duplicate-shape groups | scan `duplicate_groups` |
| Sleep calls | scan `sleep` |
| Protected tests | scan `protected` |
| Coverage-subset candidates | coverage `equal_groups`, `strict_subsets` |
| Unmeasured tests | coverage `unmeasured` |
| Diff coverage against `<base>` | coverage `diff`, with the missed `raise` and `except` lines |
| Instructions that force test growth | step 7 |
| Files the tests wrote | step 8 |

Then name exactly one next step, with its reason. Use the first rule that
applies:

1. **Speed work**, when run 1 exceeded the check budget, a test changed its
   outcome between the runs, or run 1 took longer than 2 minutes. Name the
   slowest phases or the changed tests.
2. **A review of the current change**, when no test executes some changed
   product lines, such as changed `raise` or `except` lines.
3. **Pruning of one path**, when a test directory or file has
   `no-assertion`, `tautology`, `self-comparison`, `duplicate-shape`, or
   coverage-subset candidates. Name the path with the most candidates.
4. **None**, when no rule applies.

This version of lean-tests has no mode for these steps. Say that the step
is work for the user or a later version.

When the scorecard is complete, remove the work directory:

```bash
rm -r <work-dir>
```
