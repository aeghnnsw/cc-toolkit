# Speed

speed makes a pytest suite faster without deleting a test.

Done when each fix that applies is kept with its verification results or
reverted with its reason, `compare` of the before run and the final run
reports `no_loss` true and no `added` test that the user did not ask for,
the "Tests" section is in each agent instruction file that exists or in the
reply, and the before/after table is printed.

## Setup

1. Complete the [setup](../SKILL.md#setup): `<project>`, `<python>`,
   `<work-dir>`, and `<skill-dir>`.
2. Find `<source>`, the import name of each package of the project's own
   code, such as `mypkg` for `src/mypkg/`. Find `<pytest>`, the project's
   way to start pytest, such as `uv run pytest` or `python -m pytest`.
3. In this file, "run `suite` with the label `<label>`" means this command.
   Add the options that the step names; pytest options go after `--`. The
   timeout only stops a run that hangs:

   ```bash
   <python> <skill-dir>/scripts/lean_tests.py suite --python "<python>" \
     --project <project> --work-dir <work-dir> --timeout 3600 \
     --label <label> --out <work-dir>/<label>.json
   ```

   "Compare `<label>`" means:

   ```bash
   <python> <skill-dir>/scripts/lean_tests.py compare <work-dir>/before.json \
     <work-dir>/<label>.json --out <work-dir>/compare-<label>.json
   ```

## Test tiers

A test tier is a named set of tests with a trigger, a command, and a time
budget. These are the defaults; step 5 fits them to the project.

| Tier | When | Command | Default budget |
| --- | --- | --- | --- |
| Inner loop | after each edit | `<pytest> <test-file-or-node-id> -x -q`, or `<pytest> --lf -x -q` | seconds |
| Hand-off | before the agent hands work back | `<pytest> -m "not slow" -n auto -q` | 2 minutes |
| Pull request | CI, on each push to a pull request | the hand-off command with the project's coverage options | 10 minutes |
| Main | CI, after each merge to the default branch | `<pytest> -n auto` | none: the full suite |
| Nightly | CI, once a day | `<pytest> -m slow -n auto` | none: the slow tests |

- A slow test is a test whose setup plus call takes more than the slow
  threshold. The default threshold is 1 second; the project can change it.
- The fast tiers are the hand-off and pull request tiers. They leave out the
  slow tests, which fix 8 marks.
- `--lf` runs the tests that failed in the last run, `-x` stops at the first
  failure, and `-q` keeps the output short for the agent's context.

## Rules

- Keep each test with its name and its outcome: delete, rename, merge, or
  skip no test. `compare` shows a renamed test as one `missing` and one
  `added` node ID.
- Change only test-side files: test modules, conftest files, test helpers,
  the pytest configuration, the development dependencies and their lock
  file, the CI test commands, and the "Tests" section of the agent
  instruction files. Report a needed product-code change, such as a lazy
  import, to the user.
- Put `-n auto` and `-m "not slow"` only in the tier commands, outside the
  default options (`addopts`). Then a plain `pytest` runs the full suite,
  and a run of one test starts no worker processes.
- Follow the [flaky-test policy](#flaky-test-policy) for each flaky failure.
- Put the reason for each fix in its commit message. Keep records and logs
  in `<work-dir>`.

## 1. Start from a clean work tree

Run `git -C <project> status --porcelain`. speed commits each fix on its
own, and a speed commit holds only speed's changes. When the command lists
changes, ask the user how to continue before you change a file. Follow the
project's branch and commit rules.

Done when the command prints nothing, or the user has said how to handle
the listed changes.

## 2. Measure

Run all measurements on the same machine with no other heavy work, because
wall times vary between runs.

1. Run `suite` with the label `before`. This is the before run. Its summary
   has the fields of [check step 2](check.md#2-run-1-file-order). Stop, and
   report to the user, when:
   - `timed_out` is true: a run that did not finish cannot show that no test
     was lost. Report the slowest phases, and ask for a larger timeout.
   - `pytest_exit_code` is 2 or more, or `collect_errors` is above 0: a
     module that fails to collect hides its tests from each later `compare`.
     Report the cause from `<work-dir>/before/pytest.log`.
   - `counts` has a `failed` or `error` test. Report these tests, and ask how
     to continue: speed makes a passing suite faster.
2. Run `suite` with the label `collect-before` and `-- --collect-only -q`,
   and read its `collection_seconds`. pytest-xdist does not distribute a
   `--collect-only` run. A full run with pytest-xdist reports
   `collection_seconds` as `null`.
3. Measure the import cost of each `<source>` with the `-X importtime`
   commands of check step 2. Each pytest-xdist worker pays this cost again.
4. Run `suite` with the label `reversed` and `--reverse`, and compare
   `reversed`. `changed` lists the order-dependent tests. When the project's
   options turn on pytest-xdist (`-n`), add `-- -n 0`, because pytest-xdist
   does not keep the reversed order.
5. Time the inner loop: run `suite` with the label `inner-before` and
   `-- "<node-id>" -x -q`. `<node-id>` is the first node ID in `collected`
   of the before run.
6. When the project runs coverage, for example in CI, time its coverage
   command `<coverage-command>`, such as `<python> -m pytest --cov=<source>`,
   with the shell's `time`, because `suite` turns coverage off.
   `COVERAGE_FILE` keeps the coverage data in `<work-dir>`:

   ```bash
   (cd <project> && time env COVERAGE_FILE=<work-dir>/coverage-before.data <coverage-command>)
   ```

## 3. Choose the fixes

Go through the fixes in this order. Apply a fix only when a measurement
shows the cost that it removes.

| Fix | Apply it when |
| --- | --- |
| 1. Order-dependent tests | the reversed run changed an outcome |
| 2. Parallel runs with pytest-xdist | the before run takes more than about 10 seconds |
| 3. `COVERAGE_CORE=sysmon` | the project runs coverage, and the conditions of fix 3 hold |
| 4. Narrower collection | collection is a large part of the wall time, or the configuration sets no `testpaths` |
| 5. Fixture scope and transaction rollback | `slowest.setup` shows slow setup phases |
| 6. Clock control or polling instead of sleeps | the scan finds a `sleep` call, or a slow test waits for a thread, process, or server |
| 7. No real network in the fast tiers | tests open network connections |
| 8. `slow` markers with `--strict-markers` | the before run has slow tests, or the fast tiers exceed their budgets |

Done when each of the eight fixes is marked "apply" with the measurement
that shows its cost, or "skip" with its reason.

## 4. Apply and verify each fix

Do these steps for each fix that step 3 marked "apply", in order:

1. Name the fix, the measured cost that it removes, and the risk that its
   section gives. Add each new development dependency as
   [safety rule 5](../SKILL.md#safety-rules) says, for example with
   `uv add --dev pytest-xdist` or `poetry add --group dev pytest-xdist`.
2. Make the change.
3. Run `suite` with the label `fix-<n>`, where `<n>` is the number of the
   fix, and compare `fix-<n>`. From fix 2 on, add `-- -n auto` when the
   project kept pytest-xdist.
4. Verify the fix as its section says.
5. Keep the fix only when `no_loss` is true, `added` is empty, and the
   verification passes. Keep fixes 2 to 6 only when the measured time also
   dropped. Otherwise revert the fix, and record the reason.
6. Commit the kept fix on its own. Its commit message names the fix, the
   measured cost, the time before and after, the risk, and the `compare`
   result.

When `no_loss` is false, read `missing`, `changed`, and `not_run`, and
revert or correct the change that caused them. When no change caused an
outcome change, the test is flaky: follow the
[flaky-test policy](#flaky-test-policy).

### Fix 1: order-dependent tests

Risk: low. A changed setup can change what a test detects.

For each test in `changed` of `<work-dir>/compare-reversed.json`, find the
state that another test leaves behind, such as a module or class variable,
an environment variable, the working directory, a file at a fixed path, a
cache such as `functools.lru_cache`, a singleton, a database row, or a patch
that is not undone. Give the test its own state, or restore the state after
each test: use the `monkeypatch` and `tmp_path` fixtures, which pytest
undoes after each test; create shared objects in a function-scoped fixture
instead of at module level; clear a cache or reset a singleton in the
teardown of a fixture.

Remove the dependence, so that each test passes in any order, and keep each
assertion and each input as it is. An order plugin, such as pytest-order,
only hides the dependence.

Verify: run the reversed run of step 2.4 again with the label
`reversed-fix-1`, and compare `reversed-fix-1`. `no_loss` must be true.

### Fix 2: parallel runs with pytest-xdist

Risk: medium. Shared state that the reversed run did not show can make
tests fail only in parallel runs. The order of the output changes.

Add pytest-xdist, and put `-n auto` into the tier commands. When `addopts`
already has `-n`, each CI command that runs plain `pytest` depends on it.
When the user's request covers CI (step 5), move `-n` from `addopts` into
the tier commands and into each such CI command. Otherwise keep `addopts`
as it is, and give the move and the changed CI commands in the reply.

Give each worker its own copy of each shared resource:

- Database: add the worker ID to the database name, for example
  `f"test_app_{os.environ.get('PYTEST_XDIST_WORKER', 'main')}"` in
  `conftest.py`. pytest-django already does this for its test database.
- Files: use `tmp_path` or `tmp_path_factory` instead of a fixed path.
- Ports: let the operating system choose a free port (port 0).

A session-scoped fixture runs once in each worker. When module-scoped or
class-scoped fixtures are slow, `--dist loadscope` sends the tests of one
module or class to one worker.

Verify: run `suite` with the label `fix-2-again` and `-- -n auto`, and
compare `fix-2-again`. This run and the run of step 4.3 must both give
`no_loss` true. Run the inner loop of step 2.5 again with the label
`inner-fix-2`: it must not get slower.

### Fix 3: `COVERAGE_CORE=sysmon`

Risk: low. The measured lines stay the same. A run that falls back to the
default tracer gets no faster.

With `COVERAGE_CORE=sysmon`, coverage.py 7.4.0 and newer measure with
`sys.monitoring`, which has less overhead than the default tracer. Set the
variable only for a coverage run that meets each of these conditions:

- It runs Python 3.12 or 3.13 with coverage.py 7.4.0 or newer. On Python
  3.14 or newer, coverage.py 7.9.1 and newer use `sys.monitoring` by
  default, so the fix changes nothing there.
- It measures no branch coverage. On Python 3.12 and 3.13, coverage.py 7.7
  and newer then warn and use the default tracer.
- It records no per-test contexts, because `sys.monitoring` cannot record
  them. With `--cov-context=test`, coverage.py loses contexts. With
  `dynamic_context = test_function`, coverage.py 7.4 to 7.6 lose them, and
  7.7 and newer warn and use the default tracer.

Set the variable in the environment of each such run, such as the CI job,
the tox or nox session, or the command that runs coverage. When `addopts`
turns on coverage, every run pays for it, the inner loop too. Report this to
the user; the pull request tier can run coverage instead.

Verify: time the coverage command with the variable, and compare the totals
of both coverage runs. They must be equal:

```bash
(cd <project> && time env COVERAGE_CORE=sysmon COVERAGE_FILE=<work-dir>/coverage-sysmon.data <coverage-command>)
(cd <project> && COVERAGE_FILE=<work-dir>/coverage-before.data <python> -m coverage report | tail -n 1)
(cd <project> && COVERAGE_FILE=<work-dir>/coverage-sysmon.data <python> -m coverage report | tail -n 1)
```

### Fix 4: narrower collection

Risk: low. A test outside the new paths is no longer collected, and
`compare` lists it as `missing`.

Set `testpaths` to the directories that hold tests. pytest uses it when the
command names no path. Set `norecursedirs` to skip directories without
tests, such as data, build output, and virtual environments. It replaces
the default list of pytest, so keep the default entries. For example, in
`pyproject.toml`:

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
norecursedirs = ["*.egg", ".*", "_darcs", "build", "CVS", "dist", "node_modules", "venv", "{arch}", "data"]
```

A large import cost of `<source>` (step 2.3) also slows collection. It is
product code: report its largest imports to the user.

Verify: run `suite` with the label `collect-fix-4` and
`-- --collect-only -q`. Its `collection_seconds` must be lower than in
`<work-dir>/collect-before.json`.

### Fix 5: fixture scope and transaction rollback

Risk: high. A shared resource that a test changes makes later tests depend
on the order, and it can hide a bug.

`slowest.setup` of the before run names the tests with slow setup. List the
fixtures of such a test:

```bash
(cd <project> && <python> -m pytest -p no:cacheprovider --fixtures-per-test -q "<node-id>")
```

Widen the scope of a slow fixture to `module` or `session` only when no test
changes the resource, or when each test rolls back its changes. For a
database, open one connection for the session, and start a transaction for
each test that a function-scoped fixture rolls back after the test.
pytest-django uses rollback for `django_db` tests;
`django_db(transaction=True)` empties the database after each test and is
slow.

Verify: run the reversed run of step 2.4 again with the label
`reversed-fix-5`, and compare `reversed-fix-5`. `no_loss` must be true.

### Fix 6: clock control or polling instead of sleeps

Risk: medium. A controlled clock can hide a timing bug in the product code.
A deadline that is too short makes a test flaky on a slow machine.

Run the `scan` command of [check step 5](check.md#5-scan-the-tests) on
`<work-dir>/before.json`. Its `sleep` finding names each test that calls
`time.sleep`. Also search the tests for other fixed waits, such as
`asyncio.sleep`.

- When a test waits for time to pass, for example for an expiry or a retry
  delay, control the clock: patch the clock that the code reads with
  `monkeypatch`, or use a clock library such as time-machine or freezegun.
- When a test waits for another thread, process, or server, poll the
  condition in a helper: evaluate it every 0.01 seconds, return as soon as
  it holds, and raise `AssertionError` after a deadline, such as 10 seconds of
  `time.monotonic()`. A long deadline costs no time when the test passes.

To stop a test that hangs, add pytest-timeout and give the tier commands a
limit, for example `--timeout=300`.

Verify: the call time of each changed test dropped.

### Fix 7: no real network in the fast tiers

Risk: low. A blocked connection fails with a clear error. A fake can differ
from the real service: keep a test against the real service in the main or
nightly tier.

pytest-socket blocks sockets in a test run. Get it for the probe below.
Under uv, use `--python "uv run --no-sync --with pytest-socket python"` in
the `suite` command; this changes no project file. Otherwise add
pytest-socket as a development dependency (step 4.1) before the probe. When
the user declines, skip fix 7, and report why.

Run `suite` with the label `network` and
`-- --disable-socket --allow-unix-socket`, and compare `network`. Each test
in `changed` with the exception `SocketBlockedError` opens a socket.
`--allow-unix-socket` allows Unix sockets, which asyncio uses. A test that
uses only a local service, such as a test database on `127.0.0.1`, also
shows; a local service is not a real network.

For each test that needs a real network service, replace the service with a
local fake or a recorded response, or mark the test `slow` (fix 8). Then add
pytest-socket as a development dependency, when the probe did not add it,
and add `--disable-socket --allow-unix-socket` to the fast tiers. When the
fast tiers use local services, add
`--allow-hosts=127.0.0.1 --allow-unix-socket` instead. These options allow
connections only to that address and to Unix sockets.

Verify: run `suite` with the label `hand-off-fix-7` and the options of the
hand-off tier and the socket options after `--`. No test fails.

### Fix 8: `slow` markers with `--strict-markers`

Risk: medium. A slow test runs only in the main and nightly tiers, so a bug
that only this test detects shows later.

List the slow tests of the before run. The last argument is the slow
threshold in seconds; replace `1.0` when the project uses another
threshold:

```bash
<python> -c "import json, sys; limit = float(sys.argv[2]); tests = json.load(open(sys.argv[1]))['tests']; print('\n'.join(t['nodeid'] for t in tests if sum(t['phases'].get(p, {}).get('seconds', 0) for p in ('setup', 'call')) > limit))" <work-dir>/before.json 1.0
```

Register the marker with the threshold in its description, and add
`--strict-markers` to the existing `addopts` value. With `--strict-markers`,
an unregistered marker, such as a misspelled `slwo`, is an error, not a
filter that selects nothing. Register each other marker that the suite
uses:

```toml
[tool.pytest.ini_options]
addopts = "--strict-markers"
markers = ["slow: setup plus call takes more than <threshold> seconds; runs only in the main and nightly tiers"]
```

Mark a slow test with `@pytest.mark.slow`, a whole module with
`pytestmark = pytest.mark.slow`, or one parameter set with
`pytest.param(..., marks=pytest.mark.slow)`. A module-scoped or
session-scoped fixture adds its setup time to the first test that uses it:
mark each test that needs a slow fixture.

Verify: the hand-off command fits its budget. When it does not, report the
slowest tests that it still runs, and ask the user whether to lower the
threshold or to raise the budget.

## 5. Set the tier commands

Fit the [test tiers](#test-tiers) to the project: fill in `<pytest>`, use
the project's own budgets, and leave out each tier that the project does
not use. Leave out `-n auto` when the project did not keep pytest-xdist.
Add the socket options of fix 7 to the fast tiers when the project kept
pytest-socket.

When the user's request covers CI, for example "speed up CI", put the CI
tier commands into the CI configuration. Otherwise give them in the reply.

Done when each tier that the project uses has a command and a budget, and
the CI configuration runs the new commands or the reply gives them.

## 6. Write the "Tests" section

Find the agent instruction files with
`ls -l <project>/CLAUDE.md <project>/AGENTS.md`.

- Write the section into each file that exists. When one file is a symbolic
  link to the other, `ls -l` shows `->`: write the section once, into the
  file that the link points to.
- When only one file exists, tell the user that agents that read only the
  other file, such as Codex for `AGENTS.md` and Claude Code for
  `CLAUDE.md`, do not see the tiers. Offer to create the other file.
- When neither file exists, create none, and give the section in the reply.
- When a file already has a "Tests" section, show the user the old and the
  new text, and replace the section only when the user agrees.
- Keep each other agent instruction as it is.

Use this text. Replace `<tier-table>` with the tiers of step 5 in a table
with the columns Tier, When, Command, and Budget, and `<threshold>` with
the slow threshold:

```markdown
## Tests

Run the smallest test tier that covers your change, and keep the output short.

<tier-table>

- Mark a test `@pytest.mark.slow` when its setup plus call takes more than <threshold> seconds.
- Keep `-n auto` out of `addopts`: it starts worker processes for a run of one test too.
- When a test passes in one run and fails in another, find the cause: order
  dependence, shared state, time, network, randomness, or a real bug. Fix the
  cause. Keep the failure visible: add no retries, such as `--reruns`.
```

Commit the tier changes and the "Tests" section on their own.

## 7. Prove that no test was lost

Run `suite` with the label `final` and `-- -n auto`, the main tier, and
compare `final`. Leave out `-- -n auto` when the project did not keep
pytest-xdist. The no-loss invariant holds when:

- `no_loss` is true: both runs finished, no node ID is `missing`, no outcome
  `changed`, and each collected test ran.
- `added` lists only tests that the user asked for. speed adds no test of
  its own.

When the invariant fails, find the change that caused it, revert or correct
it, and run this step again until the invariant holds.

## 8. Print the before/after table

Measure each tier command after the fixes. For a command without coverage,
run `suite` with the label of the tier and its options after `--`, for
example the label `hand-off` and `-- -m "not slow" -n auto -q`. For a
command that runs coverage, use the shell's `time`, as in step 2.6.

Print the tiers of step 5 in a table with the columns Tier, Command, Budget,
Before, and After. Take each wall time from `wall_seconds` of a suite
summary. The before value of a tier is its command before the fixes; when
the tier had no command of its own, it is the before run. Below the table,
give:

- The tests collected before and after, the collection time before and
  after, and the `no_loss` result of step 7.
- Each fix: kept, reverted, or skipped, with its reason and its risk.
- Each new development dependency and its purpose.
- Product-code costs that speed did not change, such as a large import
  cost, and each flaky test that is still open.

When the table is complete, remove the work directory: `rm -r <work-dir>`.

## Flaky-test policy

A flaky test passes and fails on the same code. A retry hides the failure,
and a hidden failure can be a real bug.

1. Classify each flaky failure by its cause: order dependence (fix 1),
   shared state between parallel workers (fix 2), time, such as a fixed
   sleep, a short deadline, the clock, or the time zone (fix 6), network
   (fix 7), randomness without a fixed seed, or a real bug in the product
   code.
2. Fix the cause in the test. For randomness, fix the seed, or make the
   assertion true for each value. Report a real bug to the user with the
   runs that failed; speed changes no product code.
3. Keep each flaky failure visible. Add no retry, such as `--reruns` of
   pytest-rerunfailures or a `flaky` decorator, and no `skip` or non-strict
   `xfail` marker.
4. When you cannot find the cause, report the test, the runs that failed,
   and the class that fits best, and leave the test as it is.
