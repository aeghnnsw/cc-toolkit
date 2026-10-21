# Prune

prune removes redundant tests under one path, `<path>`: a test file or a
test directory, relative to `<project>`. The tests under `<path>` are the
in-scope tests. The prune scope is these tests and the product modules
that they cover. Killed mutants decide, not coverage.

The kill matrix of the prune scope records, for each mutant of the covered
product modules, the in-scope tests that kill it. The bundled mutator runs
every mutant against every in-scope test, so the kill set of each test,
the mutants that it kills, is complete. The killed set is the mutants that
at least one in-scope test kills. prune deletes a test only with a written
rationale (step 6), in batches that pass the killed-set check (step 7).

prune changes files only when the user's request asks for pruning, and
only under `<path>`. It writes no report file into the project: each
rationale goes into a commit message.

Done when each in-scope test is kept with a reason, merged, moved,
demoted, or deleted with a rationale; each committed batch passed the
killed-set check; the report is complete; and the work directory is
removed.

First complete the [setup](../SKILL.md#setup) except its work directory:
`<project>`, `<python>`, `<source>`, and `<skill-dir>`. Step 1 makes
`<work-dir>` after check, because check removes its work directory at its
end.

## 1. Check the preconditions

1. Get `<path>` from the user's request. When the request names no path,
   use the path that check recommends, and ask the user to confirm it.
   Prune one path per run.
2. Make sure that no uncommitted change is under `<path>`, because step 7
   reverts a failed batch with Git:

   ```bash
   git -C <project> status --porcelain -- <path>
   ```

   When this prints a line, stop and ask the user to commit or stash the
   change. When the project is not a Git work tree, stop: prune needs Git
   to commit and revert batches.
3. Run check first ([check.md](check.md)), or use a check of the current
   commit. When check reports flaky or order-dependent tests under
   `<path>`, stop and report them. A flaky test gives kills that do not
   repeat, so the kill matrix is not evidence.
4. Make sure that `<python>` can import pytest-cov. prune needs per-test
   coverage contexts to choose the prune scope and to find unmeasured
   tests. Under uv, get pytest-cov as the setup does for analysis tools.
   Otherwise ask the user whether to add pytest-cov for this purpose, as
   [safety rule 5](../SKILL.md#safety-rules) says.
5. Make `<work-dir>` with `mktemp -d`, as setup step 5 says.

Done when you have `<path>`, `<path>` has no uncommitted change, check
reports no flaky or order-dependent test under `<path>`, `<python>`
imports pytest-cov, and you have a new `<work-dir>`.

## 2. Run the scope with coverage contexts

```bash
<python> <skill-dir>/scripts/lean_tests.py suite --python "<python>" \
  --project <project> --work-dir <work-dir> --label scope \
  --coverage-source <source> --out <work-dir>/scope.json -- <path>
```

Repeat `--coverage-source` for each package. The arguments after `--` go
to pytest, so the run collects only the in-scope tests. When the project's
pytest options turn on pytest-xdist (`-n`), add `-n 0` after `<path>`,
here and in each later command that takes pytest arguments. Report each
test that does not pass: mutate leaves it out of the prune scope.

When `pytest_exit_code` is 2 or more, read `<work-dir>/scope/pytest.log`,
report the cause, and stop.

Done when the command exits with status 0, `pytest_exit_code` is 0 or 1,
and you have reported each in-scope test that did not pass.

## 3. Scan the scope

```bash
<python> <skill-dir>/scripts/lean_tests.py scan --suite <work-dir>/scope.json \
  --out <work-dir>/scan.json
```

The scan gives the `protected`, `input-class`, `no-assertion`,
`tautology`, `self-comparison`, `weak-oracle`, and `change-detector`
findings and the `duplicate_groups`, as
[check step 5](check.md#5-scan-the-tests) describes. Also read the
subject of the commit that added each in-scope test, with the command of
check step 5. A test is protected when that subject has a protection
signal.

Done when you have the scan findings and know which in-scope tests are
protected.

## 4. Build the kill matrix

```bash
<python> <skill-dir>/scripts/lean_tests.py mutate --python "<python>" \
  --suite <work-dir>/scope.json --work-dir <work-dir> \
  --out <work-dir>/matrix.json
```

mutate makes mutants in the product modules that the in-scope tests
cover, on the lines that the coverage run executed. The operators are
comparison swap, boolean operator swap, arithmetic swap, constant change,
condition negation, return value to `None`, `raise` removal, and function
body to `return None`, with at most 3 mutants per line. Arid code gets no
mutant: docstrings, annotations, logging calls, `pass`, and `__repr__`.
Each mutant runs against all in-scope tests in one pytest run, in a
temporary copy of the project, so the project does not change. First
mutate runs a sanity mutant, a `raise` at the end of each mutated module,
and an in-scope test must kill it. This kill proves that the tests import
the copy and not an installed copy of the package.

The run has a budget of 1800 seconds; `--budget` changes it. `--workers`
sets the number of parallel copies (default: the CPU count minus 1). Each
mutant run stops after 10 seconds, or after 3 times the time of the
unchanged run when that is longer. A run that stops counts as a kill.

- Exit status 2: stop, and report the `error`. Delete nothing. A sanity
  mutant that survives also gives exit status 2.
- `complete` is false: the evidence is incomplete. Delete nothing. Report
  the `incomplete_reason`, and offer a narrower `<path>` or a larger
  `--budget`.

The summary counts the mutants: `killed`, `survived`, `not_run`, and
`timeouts`. A survived mutant is a fault that no in-scope test detects.
Report the count; it is not a reason to delete or keep a test. Each entry
of `mutants` gives the changed line (`before`, `after`) and `killed_by`,
the kill of each test: `assertion`, `exception`, `collection`, `timeout`,
or `crash`.

`skipped_modules` lists the covered product modules that have no mutant,
with the reason: the module is outside the project, it does not parse, or
its executed lines are arid. `excluded` lists the tests that did not pass
in the scope run (`run` is `suite`) or in the unchanged copy (`run` is
`copy`), with their `outcome`.

Each entry of `tests` gives the test's `kills` (its kill set), `unknown`
(the mutants whose run stopped before the test), `unique` (the mutants
that only this test kills), `subsumed_by`, `demote`, and `class`:

| `class` | The test | Default decision |
| --- | --- | --- |
| `unique` | kills a mutant that no other in-scope test kills | keep |
| `unmeasured` | is an unmeasured test: its run covers no line that a mutant changes, for example because it runs the code in a subprocess, reaches only modules in `skipped_modules`, or runs only arid code | keep |
| `incomplete` | has unknown kills that no other test covers | keep |
| `empty` | kills no mutant | delete when redundant (step 5) |
| `subsumed` | kills only mutants that each test in `subsumed_by` also kills | delete when redundant (step 5) |
| `union-only` | kills only mutants that other tests kill, but no one other test kills them all | demote when `demote` is true, else keep |

`equal_groups` lists tests with equal kill sets. Equal kill sets do not
prove that the tests are the same: step 5 also needs the input class and
the checks.

Done when `complete` is true, or you have stopped and reported why.

## 5. Decide each test

Always keep these tests:

1. Protected tests ([safety rule 4](../SKILL.md#safety-rules)): a
   `protected` scan finding, or a protection signal in the subject of the
   commit that added the test.
2. Tests of class `unique`, `unmeasured`, or `incomplete`, and the tests
   in `excluded`.
3. At least one test per public test seam: a happy-path test for each
   public function, class, or command that the in-scope tests call.

A test of class `empty`, or of class `subsumed` when a test in
`subsumed_by` is retained, is a redundant test only when its rationale
states both of these:

1. **Input class.** Why its scenario is not a distinct input class. The
   markers of a distinct input class are boundary values, different types,
   unicode or encoding, time zones and daylight saving time, large sizes,
   error paths, concurrency, locale, and platform. An `input-class` scan
   finding names a marker. For a test with such a marker, name the
   retained test that covers the same input class.
2. **Checks.** Each output, state, or error check that the test makes,
   mapped to an assertion in a retained test under equivalent inputs and
   setup. When the test makes no real check (a `no-assertion`,
   `tautology`, or `self-comparison` finding), say so.

Delete each redundant test. In a group of `equal_groups`, keep at least
one test. For a test of class `empty` or `subsumed` that is not
redundant, do the first of these that applies:

1. **Merge.** When `duplicate_groups` puts the test in one group with an
   unprotected retained test, merge them into one parametrized test. The
   tests of such a group have equal abstract syntax trees (the parsed
   code) except for literals. Each literal becomes one case, so each
   input stays.
2. **Move.** When the input class is covered but some checks are not, move
   each unmapped assertion into an unprotected retained test under
   equivalent inputs and setup, then delete the test.
3. **Keep.** Keep the test, and report why.

Demote each unprotected test whose `demote` is true to the nightly tier,
the test tier that runs the slow tests: add the marker that the project
uses for that tier. The test then leaves the fast tiers, the hand-off and
pull request tiers of the [tier table](speed.md#test-tiers). mutate sets
`demote` to true only when every mutant that the test kills, or may kill,
stays killed by a test that stays in the fast tiers: a test that is not
demoted and is not of class `empty` or `subsumed`. Keep each other test
of class `union-only`. When the project has no nightly tier, keep the
test and report that it could move to a nightly tier.

Report each test with a `change-detector` or `weak-oracle` finding for
rewriting, so that it checks behavior. Decide on such a test by its class
and rationale, as for any other test.

Done when each in-scope test has one decision: keep with a reason, delete,
merge, move, or demote.

## 6. Write the rationale

Write one line for each changed test, in this format:

```text
- remove <nodeid>: kills <none | a subset of <retained nodeid>>; input: <why the scenario is not a distinct input class>; checks: <check> -> <retained nodeid> line <n>[; <check> -> <retained nodeid> line <n>]
- merge <nodeid>, <nodeid> into <new test name>: equal except for literals; cases: <literal>, <literal>
- demote <nodeid> to the nightly tier: its kills need <nodeid> and <nodeid> together
```

For a moved assertion, write `(moved)` after its target line. For a test
that makes no real check, write `checks: none, <the reason>`. Examples:

```text
- remove tests/test_shop.py::test_classify_negative_copy: kills a subset of tests/test_shop.py::test_classify_negative; input: the same negative int as the retained test; checks: classify(-1) == "negative" -> tests/test_shop.py::test_classify_negative line 9
- remove tests/test_shop.py::test_total_tautology: kills none; input: ordinary positive ints, as in tests/test_shop.py::test_total; checks: none, the test compares total(2, 3) with itself
```

Done when each deleted, merged, or demoted test has one rationale line.

## 7. Remove in batches

Group the deletions, merges, moves, and demotions by test module. A batch
holds the changes of one module and keeps to the batch size of
[safety rule 3](../SKILL.md#safety-rules). Do the batches one at a time:

1. Change only files under `<path>`. Delete the batch's tests. Delete an
   import or helper only when no remaining test uses it. Change no other
   test, except an unprotected retained test that receives a moved
   assertion, becomes a merged test, or gets the nightly marker.
2. Run the scope again, and make sure that every test passes:

   ```bash
   <python> <skill-dir>/scripts/lean_tests.py suite --python "<python>" \
     --project <project> --work-dir <work-dir> --label batch \
     --out <work-dir>/batch.json -- <path>
   ```

3. Run the killed-set check. It reruns every mutant of the killed set of
   step 4 against all remaining in-scope tests:

   ```bash
   <python> <skill-dir>/scripts/lean_tests.py mutate --python "<python>" \
     --suite <work-dir>/batch.json --recheck <work-dir>/matrix.json \
     --work-dir <work-dir> --out <work-dir>/recheck.json
   ```

   `passed` is true only when the evidence is complete, each mutant of
   the killed set is still killed, and no test that passed before fails.
4. When `passed` is false, or the command exits with status 2, revert the
   batch:

   ```bash
   git -C <project> restore -- <file>...
   ```

   Name each file of the batch. Report the `lost` mutants and their
   `killed_before_by` tests, and the `broken` tests. Keep the tests that
   `killed_before_by` names. Then do the first of these that applies:

   - When the exit status is 2 and the `error` says that a product module
     changed after the matrix run, run steps 2 to 6 again. Then continue
     the batches with the new matrix.
   - When `complete` is false or the exit status is 2, stop.
   - Make a new batch without the kept tests.
5. When `passed` is true, commit the batch. Stage each file by name. Write
   the commit message to `<work-dir>/batch-message.txt`, and run
   `git -C <project> commit -F <work-dir>/batch-message.txt`. Use the
   project's style for the subject line. The body gives the check result
   and one rationale line for each changed test:

   ```text
   test: remove redundant tests from tests/test_shop.py

   Killed-set check: 18 of 18 mutants still killed.

   - remove tests/test_shop.py::test_classify_negative_copy: ...
   - remove tests/test_shop.py::test_total_tautology: ...
   ```

Done when each batch is committed after a passed killed-set check, or
reverted and reported.

## 8. Report

Report:

- Each committed batch: its commit, and the tests it deleted, merged,
  moved, or demoted.
- Each reverted batch, with its `lost` mutants and their
  `killed_before_by` tests.
- The tests of class `empty` or `subsumed` that you kept, and the tests of
  class `union-only` that you did not demote, with the reason for each.
- The protected, unmeasured, incomplete, and excluded tests, and the
  `skipped_modules` with their reasons.
- The change-detector and weak-oracle tests, for rewriting.
- The count of survived mutants.
- The test count before and after: `collected` of the first scope run
  (step 2) and of the last `batch.json`.

Then remove the work directory:

```bash
rm -r <work-dir>
```

Done when the report is complete and the work directory is removed.
