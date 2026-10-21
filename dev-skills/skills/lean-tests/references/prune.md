# Prune

prune removes redundant tests under one path, `<path>`: a test file or a
test directory, relative to `<project>`. Killed mutants decide, not
coverage. A mutant is a copy of the product code with one small fault. A
test kills a mutant when the test fails on that copy. The bundled mutator
runs every mutant against every in-scope test, so the kill set of each
test is complete. A test is deleted only with a written rationale.
Deletions go in batches, and each batch is checked and committed.

prune changes files only when the user's request asks for pruning, and
only under `<path>`. It writes no report file into the project: each
rationale goes into a commit message.

Done when each in-scope test is kept with a reason, merged, demoted, or
deleted with a rationale; each committed batch passed the killed-set
check; the report is complete; and the work directory is removed.

First complete the [setup](../SKILL.md#setup): `<project>`, `<python>`,
`<work-dir>`, and `<skill-dir>`.

## 1. Check the preconditions

1. Get `<path>` from the user's request. When the request names no path,
   use the path that check recommends, and ask the user to confirm it.
   Prune one path per run.
2. Make sure that no uncommitted change is under `<path>`, because a failed
   batch is reverted with Git:

   ```bash
   git -C <project> status --porcelain -- <path>
   ```

   When this prints a line, stop and ask the user to commit or stash the
   change. When the project is not a Git work tree, stop: prune needs Git
   to commit and revert batches.
3. Run check first ([check.md](check.md)), or use a check of the current
   commit. When check reports flaky or order-dependent tests under
   `<path>`, stop and report them. A flaky test gives kills that do not
   repeat, so the kill matrix is not evidence. check removes its work
   directory at its end, so make a new `<work-dir>` for prune.
4. Make sure that `<python>` can import pytest-cov. prune needs per-test
   coverage contexts to choose the mutation scope and to find unmeasured
   tests. When the project runs under uv, use
   `uv run --no-sync --with pytest-cov python` as `<python>`. Otherwise
   name pytest-cov and this purpose to the user, and add it with the
   project's dependency manager only when the user agrees.
5. Choose `<source>`, the import name of each product package, as in
   check step 1.

## 2. Run the scope with coverage contexts

```bash
<python> <skill-dir>/scripts/lean_tests.py suite --python "<python>" \
  --project <project> --work-dir <work-dir> --label scope \
  --coverage-source <source> --out <work-dir>/scope.json -- <path>
```

Repeat `--coverage-source` for each package. The arguments after `--` go
to pytest, so the run collects only the tests under `<path>`: the in-scope
tests. When the project's pytest options turn on pytest-xdist (`-n`), add
`-n 0` after `<path>`, here and in each later command that takes pytest
arguments. Report each test that does not pass: mutate leaves it out of
the scope.

## 3. Scan the scope

```bash
<python> <skill-dir>/scripts/lean_tests.py scan --suite <work-dir>/scope.json \
  --out <work-dir>/scan.json
```

The scan gives the `protected`, `input-class`, `no-assertion`,
`tautology`, `self-comparison`, `weak-oracle`, and `change-detector`
findings and the `duplicate_groups` (see check step 5). Also read the
subject of the commit that added each test, as in check step 5. A subject
with an issue reference or a protection word makes the test protected.

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
body to `return None`, with at most 3 mutants per line. It skips
docstrings, annotations, logging calls, and `__repr__`. Each mutant runs
against all in-scope tests in one pytest run, in a temporary copy of the
project, so the project does not change. First a sanity mutant, a
`raise` at the end of each mutated module, must be killed. This proves
that the tests import the copy and not an installed copy of the package.

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

Each entry of `tests` gives the test's `kills` (its kill set), `unique`
(the mutants that only this test kills), `subsumed_by`, and `class`:

| `class` | The test | Default decision |
| --- | --- | --- |
| `unique` | kills a mutant that no other in-scope test kills | keep |
| `unmeasured` | ran no measured product line, for example through a subprocess; its value is unknown | keep |
| `incomplete` | has kills that are not known, because a run stopped before the test, and no other test covers them | keep |
| `empty` | kills no mutant | candidate |
| `subsumed` | kills only mutants that each test in `subsumed_by` also kills | candidate |
| `union-only` | kills only mutants that other tests kill, but no one other test kills them all | demote |

`equal_groups` lists tests with equal kill sets. Equal kill sets do not
prove that the tests are the same: step 5 also needs the input class and
the checks. `excluded` lists tests that did not pass in the unchanged
copy; keep them and report them. `unknown` lists, for each test, the
mutants whose run stopped before the test.

## 5. Decide each test

Always keep these tests:

1. Protected tests: a `protected` scan finding, or a protection signal in
   the subject of the commit that added the test.
2. Tests of class `unique`, `unmeasured`, or `incomplete`, and excluded
   tests.
3. At least one test per public test seam, the public boundary where a
   test observes behavior. Keep a happy-path test for each public
   function, class, or command that the in-scope tests call.

A candidate is a test of class `empty`, or of class `subsumed` when a test
in `subsumed_by` stays. In a group of equal kill sets, keep at least one
test. Delete a candidate only when its rationale states both:

1. **Input class.** Why its scenario is not a distinct input class. The
   markers of a distinct input class are boundary values, different types,
   unicode or encoding, time zones and DST, large sizes, error paths,
   concurrency, locale, and platform. An `input-class` scan finding names
   a marker. For a test with such a marker, name the kept test that covers
   the same input class.
2. **Checks.** Each output, state, or error check that the test makes,
   mapped to an assertion in a kept test under equivalent inputs and
   setup. When the test makes no real check (a `no-assertion`,
   `tautology`, or `self-comparison` finding), say so.

When a candidate cannot meet both conditions, do the first of these that
applies:

1. **Merge.** When `duplicate_groups` puts the test in one group with a
   kept test (the ASTs are equal except for literals), merge them into one
   parametrized test. Each literal becomes one case, so each input stays.
2. **Move.** When the input class is covered but some checks are not, move
   each unmapped assertion into the kept test, then delete the candidate.
3. **Keep.** Keep the test, and report why.

Demote a test of class `union-only` to the nightly tier, the test tier
that runs the slow tests, when the project defines one: add the marker
that the project uses for that tier. When the project has no nightly
tier, keep the test and report it as a demotion candidate.

Do not delete or rewrite a test for a `change-detector` or `weak-oracle`
finding. Report these tests for rewriting: a kept test should check
behavior.

## 6. Write the rationale

Write one line for each changed test, in this format:

```text
- remove <nodeid>: kills <none | a subset of <kept nodeid>>; input: <why the scenario is not a distinct input class>; checks: <check> -> <kept nodeid> line <n>[; <check> -> <kept nodeid> line <n>]
- merge <nodeid>, <nodeid> into <new test name>: equal except for literals; cases: <literal>, <literal>
- demote <nodeid> to the nightly tier: its kills need <nodeid> and <nodeid> together
```

For a moved assertion, write `(moved)` after its target line. For a test
that makes no real check, write `checks: none, <the reason>`. Examples:

```text
- remove tests/test_shop.py::test_classify_negative_copy: kills a subset of tests/test_shop.py::test_classify_negative; input: the same negative int as the kept test; checks: classify(-1) == "negative" -> tests/test_shop.py::test_classify_negative line 9
- remove tests/test_shop.py::test_total_tautology: kills none; input: ordinary positive ints, as in tests/test_shop.py::test_total; checks: none, the test compares total(2, 3) with itself
```

## 7. Remove in batches

Group the deletions, merges, and moves by test module. A batch holds the
changes of one module and deletes at most 20 tests. Do the batches one
at a time:

1. Change only files under `<path>`. Delete the batch's tests. Delete an
   import or helper only when no remaining test uses it. Change no other
   test, except a kept test that receives a moved assertion or becomes a
   merged test.
2. Run the scope again. Every test must pass:

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
   held a lost mutant. When `complete` is false or the exit status is 2,
   stop. Otherwise you can make a new batch without these tests.
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

Each later batch uses the same matrix of step 4. mutate stops with exit
status 2 when a mutated product module changed after the matrix run; then
run steps 2 to 4 again.

## 8. Report

Report:

- Each committed batch: its commit, and the tests it deleted, merged,
  moved, or demoted.
- Each reverted batch, with its lost mutants and the tests that held them.
- The kept candidates and demotion candidates, with the reason for each.
- The protected, unmeasured, incomplete, and excluded tests.
- The change-detector and weak-oracle tests, for rewriting.
- The count of survived mutants.
- The test count before and after: `collected` of `scope.json` and of the
  last `batch.json`.

Then remove the work directory:

```bash
rm -r <work-dir>
```
