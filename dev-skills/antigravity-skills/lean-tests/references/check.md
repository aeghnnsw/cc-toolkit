# Check

check measures a pytest suite and prints a scorecard. It changes no file in
the project and installs nothing. It runs the suite at most twice: run 1 in
file order, and run 2 in reversed order with per-test coverage. A test whose
outcome differs between the runs is flaky or order-dependent.

Done when the scorecard gives each row a value or a "not measured" reason,
it names one next mode with its reason, and the project's Git status is the
same as at the start, or the difference is reported as files the tests
wrote.

First complete the [setup](../SKILL.md#setup): `<project>`, `<python>`,
`<source>`, `<work-dir>`, and `<skill-dir>`.

## 1. Record the starting state

```bash
git -C <project> status --porcelain --untracked-files=all > <work-dir>/status-before.txt
git -C <project> status --porcelain --untracked-files=normal --ignored=traditional > <work-dir>/ignored-before.txt
```

The second command also lists ignored files, such as a `.coverage` file
that the project's `.gitignore` names. It lists an ignored directory as one
line.

When the project is not a Git work tree, these commands fail. Then report
that check cannot prove that it changed no file, skip diff coverage, and
continue.

Choose `<base>`, the base ref for diff coverage. Use the ref that the user
names. Otherwise use the remote default branch, which
`git -C <project> rev-parse --abbrev-ref origin/HEAD` prints. When neither
exists, skip diff coverage and report why.

## 2. Run 1: file order

```bash
<python> <skill-dir>/scripts/lean_tests.py suite --python "<python>" \
  --project <project> --work-dir <work-dir> --label run1 --timeout 600 \
  --out <work-dir>/run1.json
```

The 600-second timeout is the default check budget. When the user names
another budget, use it here, and use three times that value in step 3. The
command
turns off the pytest cache and bytecode files, and loads a bundled plugin
that records each test phase. It sets `COVERAGE_FILE` to the work
directory, and when pytest-cov is installed, it adds `--no-cov`, so that the
project's coverage options write no file. The printed summary gives:

- `counts`, `wall_seconds`, and `collection_seconds`.
- `slowest`: the slowest `call`, `setup`, and `teardown` phases. Slow setup
  or teardown points at a fixture, not at the test body.
- `files_written`: Git status lines that the tests added, ignored files
  included. A new file inside a directory that was already ignored does
  not show.

Then measure the import cost of the product code. Run the command in
`<project>` for each `<source>`. When the pytest configuration sets
`pythonpath`, such as `src`, set `PYTHONPATH` to the same directories;
otherwise leave out `PYTHONPATH=<pythonpath>`.

```bash
(cd <project> && PYTHONPATH=<pythonpath> <python> -B -X importtime -c "import <source>") 2> <work-dir>/importtime-<source>.txt
grep -E '[|] <source>$' <work-dir>/importtime-<source>.txt
sort -t '|' -k 2 -n -r <work-dir>/importtime-<source>.txt | head -n 8
```

`-B` writes no bytecode file into the project. Each line gives the self
time and the cumulative time in microseconds, and the module name; nested
imports are indented. The `grep` line is `<source>` itself: its cumulative
time is the import cost. The `sort` lines are the imports with the largest
cumulative time; skip interpreter start-up modules such as `site` and
`encodings` among them. When the import fails, the file ends with the
error: report the import cost as not measured, with that error. A test
module that imports `<source>` adds this cost to collection.

When `pytest_exit_code` is 2 or more, read `<work-dir>/run1/pytest.log`
and report the cause. Exit code 5 means that pytest collected no test.

When `timed_out` is true, the suite is too slow to measure twice. Skip
steps 3, 4, and 6, report their rows as "not measured: run 1 exceeded the
check budget", and recommend the speed mode.

## 3. Run 2: reversed order with coverage contexts

```bash
<python> <skill-dir>/scripts/lean_tests.py suite --python "<python>" \
  --project <project> --work-dir <work-dir> --label run2 --reverse \
  --coverage-source <source> --timeout 1800 --out <work-dir>/run2.json
```

Repeat `--coverage-source` for each package. Run 2 records which lines
each test runs (pytest-cov `--cov-context=test`). It sets
`COVERAGE_CORE=ctrace`, the C tracer of coverage.py. Under
`sys.monitoring`, the default of coverage.py 7.9.1 and newer on Python 3.14
or newer, coverage.py records a line only for the first test that runs it.
It removes the project's pytest-cov options, except `--cov-config`, from
`addopts` and `PYTEST_ADDOPTS` for this run, so that no coverage report
goes into the project. Coverage contexts slow a run, so the timeout is
three times the budget.

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
<python> <skill-dir>/scripts/lean_tests.py compare <work-dir>/run1.json \
  <work-dir>/run2.json --out <work-dir>/compare.json
```

- `changed`: the tests whose outcome differs between the runs. Report them
  as flaky or order-dependent.
- `missing` and `added`: node IDs that only one run collected. Report them:
  collection is not stable.
- `not_run`: tests that a timed-out run did not reach. They are not missing.

## 5. Scan the tests

```bash
<python> <skill-dir>/scripts/lean_tests.py scan --suite <work-dir>/run1.json \
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
example a test inherited from another module, with the reason. A syntax
error reason names the Python version that parsed the file. When that
version is not the project's, run the scan again with `<python>`.

The scan does not read Git history. The subject of the commit that added a
test is also a protection signal. For each test in the no-assertion,
tautology, self-comparison, duplicate-shape, and coverage-subset rows, read
that subject:

```bash
git -C <project> log --reverse --format=%s -G "def <test-name>\(" -- <file> | head -n 1
```

Here `<test-name>` is the function name without parameters, and `<file>`
is the test file. Count the test as protected when the subject has an
issue reference, or the words fix, bug, regression, characterization,
security, compat, or perf, and add it to the Protected tests row.

## 6. Read per-test coverage and diff coverage

Skip this step when run 2 has no coverage contexts. Then
`<work-dir>/run2/coverage.json` does not exist.

```bash
<python> <skill-dir>/scripts/lean_tests.py coverage \
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
  not measure. `unparsed` are changed files whose `raise` and `except`
  lines the command could not find, with the reason. Report them.

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
git -C <project> status --porcelain --untracked-files=normal --ignored=traditional | diff <work-dir>/ignored-before.txt -
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
| Import cost | step 2 import time of each `<source>`, with its five largest imports |
| Slowest tests | run 1 `slowest.call` |
| Slowest setup and teardown | run 1 `slowest.setup`, `slowest.teardown` |
| Flaky or order-dependent | compare `changed` |
| No assertion | scan `no-assertion` |
| Tautology or self-comparison | scan `tautology`, `self-comparison` |
| Weak oracle, change detector, trivial code | scan `weak-oracle`, `change-detector`, `trivial-code` |
| Duplicate-shape groups | scan `duplicate_groups` |
| Sleep calls | scan `sleep` |
| Protected tests | scan `protected`, and the commit subjects of step 5 |
| Coverage-subset candidates | coverage `equal_groups`, `strict_subsets` |
| Unmeasured tests | coverage `unmeasured` |
| Diff coverage against `<base>` | coverage `diff`, with the missed `raise` and `except` lines |
| Instructions that force test growth | step 7 |
| Files the tests wrote | step 8 |

Then name exactly one next mode, with its reason. Use the first rule that
applies:

1. **speed**, when run 1 exceeded the check budget, run 1 took longer than
   the hand-off budget (default 2 minutes; speed defines a hand-off tier
   that must fit it), or a test changed its outcome between the runs. speed fixes
   order-dependent tests before it turns on parallel runs. Name the slowest
   phases or the changed tests.
2. **review**, when no test executes some changed product lines, such as
   changed `raise` or `except` lines.
3. **prune** of one path, when a test directory or file has unprotected
   `no-assertion`, `tautology`, `self-comparison`, `duplicate-shape`, or
   coverage-subset candidates. Name the path with the most candidates.
4. **check** again after the next change, when no other rule applies. Say
   that the suite needs no lean-tests work now.

When the next mode is speed, prune, or review, say that the user can ask
for it, for example with "make the tests faster", "prune the tests in
<path>", or "review the tests in this change": these modes run only on
request.

When the scorecard is complete, remove the work directory:

```bash
rm -r <work-dir>
```
