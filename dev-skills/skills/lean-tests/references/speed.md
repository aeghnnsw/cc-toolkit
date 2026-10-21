# Speed

speed makes a pytest suite faster without deleting a test. It measures the
suite first. Then it applies fixes in a fixed order, one at a time, and
verifies each fix before the next. It defines test tiers with time budgets,
writes the tier commands into the agent instruction files, and prints a
before/after table. Run speed only when the user's request asks for speed
changes, such as "make the tests faster" or "speed up CI".

Done when each fix that applies is kept with its check results or reverted
with its reason, `compare` of the before run and the final run reports
`no_loss` true and no `added` test that the user did not ask for, the
"Tests" section is in each agent instruction file that exists, and the
before/after table is printed.

First complete the [setup](../SKILL.md#setup): `<project>`, `<python>`,
`<work-dir>`, and `<skill-dir>`.

## Rules

- Do not delete, rename, merge, or skip a test. A renamed test shows in
  `compare` as one `missing` and one `added` node ID, and it fails the
  no-loss invariant of step 7.
- Change only test-side files: test modules, conftest files, test helpers,
  the pytest configuration, the development dependencies and their lock
  file, the CI test commands, and the "Tests" section of the agent
  instruction files. When a fix needs a product-code change, such as a lazy
  import, report it to the user and do not make it.
- Name each new development dependency and its purpose before you add it.
  Add it with the project's own dependency manager, for example
  `uv add --dev pytest-xdist` or `poetry add --group dev pytest-xdist`.
- Keep `-n auto` out of the default options (`addopts`). With it, each run
  starts one worker process per CPU, and a run of one test in the inner
  loop gets slower. Also keep `-m "not slow"` out of `addopts`, so that a
  plain `pytest` runs the full suite. Put both options in the tier
  commands.
- Hide no flaky failure. Follow the [flaky-test policy](#flaky-test-policy).
- Write no report file into the project. Put the reason for each fix in its
  commit message, and keep temporary data in `<work-dir>`.

## 1. Check the starting state

```bash
git -C <project> status --porcelain
```

speed commits each fix on its own. When the command lists changes, ask the
user how to continue before you change a file: a speed commit holds only
speed's changes. Follow the project's branch and commit rules.

## 2. Measure

Each later step compares with these measurements. Run all measurements on
the same machine with no other heavy work, because wall times vary between
runs.

1. Run the full suite in file order. This is the before run:

   ```bash
   <python> <skill-dir>/scripts/lean_tests.py suite --python "<python>" \
     --project <project> --work-dir <work-dir> --label before --timeout 3600 \
     --out <work-dir>/before.json
   ```

   This is run 1 of [check step 2](check.md#2-run-1-file-order) with a
   larger timeout, which only stops a run that hangs. The summary gives
   `wall_seconds`, `collection_seconds`, and the `slowest` call, setup, and
   teardown phases.
   - When `timed_out` is true, stop. A run that did not finish cannot prove
     the no-loss invariant. Report the slowest phases, and ask the user for
     a larger timeout.
   - When `counts` has a `failed` or `error` test, report these tests and ask
     the user how to continue. speed does not fix failing tests.
2. Measure the import cost of each `<source>` with the `-X importtime`
   commands of check step 2. Each test process pays this cost once during
   collection, and each pytest-xdist worker pays it again.
3. Run the suite in reversed order, and compare the run with the before run:

   ```bash
   <python> <skill-dir>/scripts/lean_tests.py suite --python "<python>" \
     --project <project> --work-dir <work-dir> --label reversed --reverse \
     --timeout 3600 --out <work-dir>/reversed.json
   <python> <skill-dir>/scripts/lean_tests.py compare <work-dir>/before.json \
     <work-dir>/reversed.json --out <work-dir>/order.json
   ```

   `changed` lists the order-dependent tests. When the project's options turn
   on pytest-xdist (`-n`), add `-- -n 0` at the end of the `suite` command,
   because pytest-xdist does not keep the reversed order.
4. Time the inner loop. Use the first node ID in `collected` of the before
   run as `<node-id>`:

   ```bash
   <python> <skill-dir>/scripts/lean_tests.py suite --python "<python>" \
     --project <project> --work-dir <work-dir> --label inner-before \
     --out <work-dir>/inner-before.json -- "<node-id>" -x -q
   ```

5. When the project runs coverage, for example in CI, time its coverage
   command. `suite` turns coverage off, so use the shell's `time`:

   ```bash
   (cd <project> && time env COVERAGE_FILE=<work-dir>/coverage-before.data <coverage-command>)
   ```

   Here `<coverage-command>` is the project's command, such as
   `<python> -m pytest --cov=<source>`. `COVERAGE_FILE` puts the coverage
   data into the work directory.

## 3. Choose the fixes

Go through the fixes in this order. Apply a fix only when a measurement
shows the cost that it removes. Skip the others, and give the reason in the
table of step 8.

| Fix | Apply it when | Risk |
| --- | --- | --- |
| 1. Order-dependent tests | the reversed run changed an outcome | low |
| 2. Parallel runs with pytest-xdist | the before run takes more than about 10 seconds | medium |
| 3. `COVERAGE_CORE=sysmon` | the project runs coverage on Python 3.12 or newer | low |
| 4. Narrower collection | collection is a large part of the wall time, or the configuration sets no `testpaths` | low |
| 5. Fixture scope and transaction rollback | `slowest.setup` shows slow setup phases | high |
| 6. Clock control or polling instead of sleeps | the scan finds a `sleep` call, or a slow test waits for a thread, process, or server | medium |
| 7. No real network in fast tiers | tests open network connections | low |
| 8. `slow` markers with `--strict-markers` | tests take more than 1 second, or the fast tests exceed the hand-off budget | medium |

A suite that takes less than about 10 seconds gains little from pytest-xdist,
because each worker needs time to start.

## 4. Apply and verify each fix

Do these steps for each fix, in the order of step 3:

1. Name the fix, the measured cost that it removes, and its risk. When it
   needs a new development dependency, name the package and its purpose.
2. Make the change.
3. Run the full suite in file order, and compare the run with the before
   run. `<n>` is the number of the fix:

   ```bash
   <python> <skill-dir>/scripts/lean_tests.py suite --python "<python>" \
     --project <project> --work-dir <work-dir> --label fix-<n> --timeout 3600 \
     --out <work-dir>/fix-<n>.json
   <python> <skill-dir>/scripts/lean_tests.py compare <work-dir>/before.json \
     <work-dir>/fix-<n>.json --out <work-dir>/compare-fix-<n>.json
   ```

   From fix 2 on, add `-- -n auto` to the `suite` command when the project
   kept pytest-xdist.
4. Do the check of the fix, which its section below gives.
5. Keep the fix only when `no_loss` is true, `added` is empty, and the
   check passes. Keep fixes 2 to 6 only when the measured time also
   dropped. Otherwise revert the fix, and record the reason.
6. Commit the kept fix on its own. Its commit message names the fix, the
   measured cost, the time before and after, the risk, and the `compare`
   result.

When `no_loss` is false, read `missing`, `changed`, and `not_run`. Revert or
correct the change that caused them. When no change caused an outcome
change, the test is flaky: follow the
[flaky-test policy](#flaky-test-policy).

### Fix 1: order-dependent tests

Do this fix first: parallel runs and wider fixture scopes make order
dependence worse. For each test in `changed` of `<work-dir>/order.json`,
find the state that another test leaves behind. Examples are a module or
class variable, an environment variable, the working directory, a file at a
fixed path, a cache such as `functools.lru_cache`, a singleton, a database
row, and a patch that is not undone. Give the test its own state, or restore
the state after each test:

- Use the `monkeypatch` and `tmp_path` fixtures. pytest undoes their changes
  after each test.
- Create shared objects in a function-scoped fixture, not at module level.
- Clear a cache or reset a singleton in the teardown of a fixture.

Do not force an order, for example with pytest-order, and do not merge
tests. Keep each assertion and each input as it is.

Risk: low. A changed setup can change what a test checks.

Check: run the reversed run of step 2.3 again with a new label, and compare
it with the before run: `no_loss` must be true. pytest-randomly, an optional
dependency, runs the tests in a new random order in each run and prints the
seed; `--randomly-seed=<seed>` repeats an order. It can find order
dependence that the reversed run does not show. `suite` turns it off, so
that its own runs keep a fixed order.

### Fix 2: parallel runs with pytest-xdist

Add pytest-xdist. Put `-n auto` into the tier commands of step 5, never into
`addopts`. When `addopts` already has `-n`, move it into the tier commands,
and add it to each CI command that ran plain `pytest`.

Give each worker its own copy of each shared resource:

- Database: one database for each worker. The environment variable
  `PYTEST_XDIST_WORKER` holds the worker ID (`gw0`, `gw1`, and so on); the
  `worker_id` fixture gives the same ID, or `master` without pytest-xdist.
  Add the ID to the database name, for example in `conftest.py`:

  ```python
  import os

  WORKER = os.environ.get("PYTEST_XDIST_WORKER", "main")
  TEST_DATABASE = f"test_app_{WORKER}"
  ```

  pytest-django already adds the worker ID to the name of its test
  database.
- Files: use `tmp_path` or `tmp_path_factory`, not a fixed path.
- Ports: let the operating system choose a free port (port 0).

A session-scoped fixture runs once in each worker, not once in each run.
When module-scoped or class-scoped fixtures are slow, `--dist loadscope`
sends the tests of one module or class to one worker.

Risk: medium. Shared state that the reversed run did not show can make
tests fail only in parallel runs. The order of the output changes.

Check: run the full suite with `-- -n auto` two times. Both runs must give
`no_loss` true against the before run. Time the inner loop of step 2.4 again
with the label `inner-fix-2`: it must not get slower.

### Fix 3: `COVERAGE_CORE=sysmon`

`sys.monitoring`, which Python 3.12 added, lets coverage.py measure code
with less overhead than its default tracer. coverage.py 7.4.0 and newer
uses it when the environment sets `COVERAGE_CORE=sysmon`. Set the variable
in the environment of each ordinary coverage run, such as the CI job, the
tox or nox session, or the command that runs coverage. Do not set it:

- for a run that records per-test coverage contexts (`--cov-context=test`
  or `dynamic_context = test_function`), because `sys.monitoring` loses
  them. check's run 2 uses `COVERAGE_CORE=ctrace` for this reason.
- on Python 3.11 or older, or with coverage.py older than 7.4.0.
- with branch coverage on Python older than 3.14. coverage.py then uses its
  default tracer, and the run gets no faster.

When `addopts` turns on coverage, every run pays for it, the inner loop too.
Report this to the user; the pull request tier can run coverage instead.

Risk: low. The measured lines stay the same. A run that falls back to the
default tracer is only slower.

Check: time the coverage command with the variable, and compare the totals
of both coverage runs. They must be equal:

```bash
(cd <project> && time env COVERAGE_CORE=sysmon COVERAGE_FILE=<work-dir>/coverage-sysmon.data <coverage-command>)
(cd <project> && COVERAGE_FILE=<work-dir>/coverage-before.data <python> -m coverage report | tail -n 1)
(cd <project> && COVERAGE_FILE=<work-dir>/coverage-sysmon.data <python> -m coverage report | tail -n 1)
```

### Fix 4: narrower collection

Set `testpaths` to the directories that hold tests, so that pytest does not
search the whole project. Set `norecursedirs` to skip directories without
tests, such as data, build output, and virtual environments.
`norecursedirs` replaces the default list of pytest, so keep its entries
in the new value. Edit the configuration file that the project
uses, for example `pyproject.toml`:

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
norecursedirs = ["*.egg", ".*", "_darcs", "build", "CVS", "dist", "node_modules", "venv", "{arch}", "data"]
```

pytest uses `testpaths` only when the command names no path. A large import
cost of `<source>` (step 2.2) also slows collection. It is product code:
report its largest imports, and do not change them.

Risk: low. A test outside the new paths is no longer collected, and
`compare` lists it as `missing`.

Check: `collection_seconds` of the fix run is lower than in the before run.

### Fix 5: fixture scope and transaction rollback

`slowest.setup` of the before run names the tests with slow setup. List the
fixtures of such a test:

```bash
(cd <project> && <python> -m pytest -p no:cacheprovider --fixtures-per-test -q "<node-id>")
```

Widen the scope of a slow fixture to `module` or `session` only when no test
changes the resource, or when each test rolls back its changes. For a
database, open one connection for the session, and start a transaction for
each test that a function-scoped fixture rolls back after the test.
pytest-django tests marked `django_db` use rollback; tests marked
`django_db(transaction=True)` empty the database after each test and are
slow.

Risk: high. A shared resource that a test changes makes later tests depend
on the order, and it can hide a bug.

Check: run the reversed run of step 2.3 again, and the full suite with
`-- -n auto` when the project kept pytest-xdist. Compare each run with the
before run: `no_loss` must be true.

### Fix 6: clock control or polling instead of sleeps

Find the waits:

```bash
<python> <skill-dir>/scripts/lean_tests.py scan --suite <work-dir>/before.json \
  --out <work-dir>/scan.json
```

The `sleep` finding names each test that calls `time.sleep`. Also search the
tests for other fixed waits, such as `asyncio.sleep`.

- When a test waits for time to pass, for example for an expiry or a retry
  delay, control the clock: patch the clock that the code reads with
  `monkeypatch`, or use a clock library such as time-machine or freezegun.
- When a test waits for another thread, process, or server, poll the
  condition with a short interval and a deadline. The poll stops as soon as
  the condition holds, so a long deadline costs no time when the test
  passes:

  ```python
  import time


  def wait_until(condition, timeout=10.0, interval=0.01):
      deadline = time.monotonic() + timeout
      while not condition():
          if time.monotonic() > deadline:
              raise AssertionError(f"condition not met within {timeout} seconds")
          time.sleep(interval)
  ```

To stop a test that hangs, add pytest-timeout and give the tier commands a
limit, for example `--timeout=300`.

Risk: medium. A controlled clock can hide a timing bug in the product code.
A deadline that is too short makes a test flaky on a slow machine.

Check: the call time of each changed test dropped.

### Fix 7: no real network in fast tiers

pytest-socket blocks sockets in a test run. Find the tests that open a
socket:

```bash
<python> <skill-dir>/scripts/lean_tests.py suite --python "<python>" \
  --project <project> --work-dir <work-dir> --label network --timeout 3600 \
  --out <work-dir>/network.json -- --disable-socket --allow-unix-socket
<python> <skill-dir>/scripts/lean_tests.py compare <work-dir>/before.json \
  <work-dir>/network.json --out <work-dir>/network-compare.json
```

Under uv, get pytest-socket for this run with
`--python "uv run --no-sync --with pytest-socket python"`. Each test in
`changed` with the exception `SocketBlockedError` opens a socket.
`--allow-unix-socket` allows Unix sockets, which asyncio uses. A test that
uses only a local service, such as a test database on `127.0.0.1`, also
shows; a local service is not a real network.

For each test that needs a real network service, replace the service with a
local fake or a recorded response, or mark the test `slow` (fix 8), so that
the fast tiers leave it out. Then add pytest-socket, and add
`--disable-socket --allow-unix-socket` to the hand-off and pull request
commands. When the fast tests use local services, add
`--allow-hosts=127.0.0.1` instead, which allows only connections to that
address.

Risk: low. A blocked connection fails with a clear error. A fake can differ
from the real service: keep a test against the real service in the main or
nightly tier.

Check: the hand-off command of step 5 passes with the socket options.

### Fix 8: `slow` markers with `--strict-markers`

A test is slow when its setup plus call takes more than 1 second. This is
the default threshold; the project can change it. List the slow tests of the
before run:

```bash
<python> -c "import json, sys; tests = json.load(open(sys.argv[1]))['tests']; print('\n'.join(t['nodeid'] for t in tests if sum(t['phases'].get(p, {}).get('seconds', 0) for p in ('setup', 'call')) > 1.0))" <work-dir>/before.json
```

Register the marker, and add `--strict-markers` to the existing `addopts`
value. With `--strict-markers`, an unregistered marker, such as a
misspelled `slwo`, is an error, not a filter that selects nothing:

```toml
[tool.pytest.ini_options]
addopts = "--strict-markers"
markers = ["slow: setup plus call takes more than 1 second; the fast tiers leave it out"]
```

Each unregistered marker that the suite already uses is then an error too.
Register those markers. Mark a slow test with
`@pytest.mark.slow`, a whole module with `pytestmark = pytest.mark.slow`, or
one parameter set with `pytest.param(..., marks=pytest.mark.slow)`. A
module-scoped or session-scoped fixture adds its setup time to the first
test that uses it. Mark each test that needs a slow fixture, not only the
first one.

Risk: medium. A slow test runs only in the main and nightly tiers, so a bug
that only this test detects shows later.

Check: the hand-off command of step 5 fits the hand-off budget. When it does
not, report the slowest tests that it still runs, and ask the user whether
to lower the threshold or to raise the budget.

## 5. Define the tiers

A test tier is a named set of tests with a trigger and a time budget. Use
these defaults unless the project has its own; the project can change each
budget. `<pytest>` is the project's way to start pytest, such as
`uv run pytest` or `python -m pytest`.

| Tier | When | Command | Default budget |
| --- | --- | --- | --- |
| Inner loop | after each edit | `<pytest> <test-file-or-node-id> -x -q`, or `<pytest> --lf -x -q` | seconds |
| Hand-off | before the agent hands work back | `<pytest> -m "not slow" -n auto -q` | 2 minutes |
| Pull request | CI, on each push to a pull request | the hand-off command with the project's coverage options | 10 minutes |
| Main | CI, after each merge to the default branch | `<pytest> -n auto` | none: the full suite |
| Nightly | CI, once a day | `<pytest> -m slow -n auto` | none: the slow tests |

`--lf` runs the tests that failed in the last run, `-x` stops at the first
failure, and `-q` keeps the output short, so that test output fills less of
the agent's context. Leave out `-n auto` when the project did not keep
pytest-xdist. Add the socket options of fix 7 to the hand-off and pull
request commands when the project kept pytest-socket.

Change the CI configuration only when the user's request covers CI, for
example "speed up CI". Otherwise give the CI commands in the reply.

## 6. Write the "Tests" section

Find the agent instruction files:

```bash
ls -l <project>/CLAUDE.md <project>/AGENTS.md
```

- Write the section into each file that exists. When one file is a symbolic
  link to the other, `ls -l` shows `->`: write the section once, into the
  file that the link points to.
- When neither file exists, create none, and give the section in the reply.
- When a file already has a "Tests" section, show the user the old and the
  new text, and replace the section only when the user agrees.
- Change no other agent instruction.

Fill in the commands of step 5, and leave out the row of a tier that the
project does not use:

```markdown
## Tests

Run the smallest test tier that covers your change, and keep the output short.

| Tier | When | Command | Budget |
| --- | --- | --- | --- |
| Inner loop | After each edit | `<pytest> <test-file-or-node-id> -x -q`, `<pytest> --lf -x -q` | Seconds |
| Hand-off | Before you hand work back | `<pytest> -m "not slow" -n auto -q` | 2 minutes |
| Pull request | CI, on each push | `<pull-request-command>` | 10 minutes |
| Main | CI, after each merge | `<pytest> -n auto` | Full suite |
| Nightly | CI, once a day | `<pytest> -m slow -n auto` | Slow tests |

- Mark a test `@pytest.mark.slow` when its setup plus call takes more than 1 second.
- Do not add `-n auto` to `addopts`: it slows a run of one test.
- When a test passes in one run and fails in another, find the cause: order
  dependence, shared state, time, network, randomness, or a real bug. Fix the
  cause. Do not rerun the test until it passes, and do not add retries such
  as `--reruns`.
```

Commit the tier changes and the "Tests" section on their own.

## 7. Prove that no test was lost

Run the full suite with the main tier command, and compare the run with the
before run:

```bash
<python> <skill-dir>/scripts/lean_tests.py suite --python "<python>" \
  --project <project> --work-dir <work-dir> --label final --timeout 3600 \
  --out <work-dir>/final.json -- -n auto
<python> <skill-dir>/scripts/lean_tests.py compare <work-dir>/before.json \
  <work-dir>/final.json --out <work-dir>/final-compare.json
```

Leave out `-- -n auto` when the project did not keep pytest-xdist. The
no-loss invariant holds when:

- `no_loss` is true: both runs finished, no node ID is `missing`, no outcome
  `changed`, and each collected test ran.
- `added` lists only tests that the user asked for. speed adds no test of
  its own.

When the invariant fails, find the change that caused it, revert or correct
it, and run this step again. Do not end the work with a failed invariant.

## 8. Print the before/after table

Measure each tier command after the fixes. For a command without coverage,
run `suite` with the options of the tier after `--`, for example for the
hand-off tier:

```bash
<python> <skill-dir>/scripts/lean_tests.py suite --python "<python>" \
  --project <project> --work-dir <work-dir> --label hand-off \
  --out <work-dir>/hand-off.json -- -m "not slow" -n auto -q
```

For a command that runs coverage, use the shell's `time`, as in step 2.5.

Print one table. Take each wall time from `wall_seconds` of a suite
summary. The before value of a tier is its command before the fixes; when
the tier had no command of its own, it is the before run, because the
project ran the full suite there.

| Tier | Command | Budget | Before | After |
| --- | --- | --- | --- | --- |
| Inner loop | `<command>` | seconds | `<seconds>` | `<seconds>` |
| Hand-off | `<command>` | 2 minutes | `<seconds>` | `<seconds>` |
| Pull request | `<command>` | 10 minutes | `<seconds>` | `<seconds>` |
| Main | `<command>` | none | `<seconds>` | `<seconds>` |
| Nightly | `<command>` | none | `<seconds>` | `<seconds>` |

Below the table, give:

- The tests collected before and after, the collection time before and
  after, and the `no_loss` result of step 7.
- Each fix: kept, reverted, or skipped, with its reason and its risk.
- Each new development dependency and its purpose.
- Product-code costs that speed did not change, such as a large import
  cost, and each flaky test that is still open.

When the table is complete, remove the work directory:

```bash
rm -r <work-dir>
```

## Flaky-test policy

A flaky test passes and fails on the same code. A retry hides the failure,
and a hidden failure can be a real bug.

1. Classify each flaky failure by its cause:
   - order dependence: the outcome depends on the tests that ran before it
     (fix 1).
   - shared state: tests in parallel workers share a file, a database, a
     port, or an environment variable (fix 2).
   - time: a fixed sleep, a short deadline, the clock, or the time zone
     (fix 6).
   - network: a real service is slow or not available (fix 7).
   - randomness: random data without a fixed seed. Fix the seed, or make the
     check true for each value.
   - real bug: a race condition or another defect in the product code.
2. Fix the cause in the test. Report a real bug to the user with the runs
   that failed; speed does not change product code.
3. Do not hide a flaky failure. Add no retry, such as `--reruns` of
   pytest-rerunfailures or a `flaky` decorator, and no `skip` or non-strict
   `xfail` marker.
4. When you cannot find the cause, report the test, the runs that failed,
   and the class that fits best, and leave the test as it is.
