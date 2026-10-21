# Review

review checks the new and changed tests of a change: the commits from the
merge base of `<base>` and HEAD to HEAD. It runs the weakening gate, labels
each new test, decides whether each new test adds protection, and reports
the changed product lines that no test executes. review changes no file in
the project. Only the weakening gate blocks: the other checks give advice.

The weakening gate checks gate units and fails a mixed change with a test
weakening ([safety rule 2](../SKILL.md#safety-rules)). The test side of a
gate unit is its test modules, conftest files, helpers under test paths,
test data, and pytest configuration.

An agent workflow runs [Pin the requirement sources](#pin-the-requirement-sources)
at its start, before the first implementation change. The review steps 1
to 8 run after the change.

Done when the report gives the gate result, the pinned requirement
sources, the label and admission decision of each new test, the diff
coverage, and the weak-oracle notes; each failing gate item has an
acceptance line or is reported as open; and the work directory is removed.

First complete the [setup](../SKILL.md#setup): `<project>`, `<python>`,
`<source>`, `<work-dir>`, and `<skill-dir>`.

## Pin the requirement sources

An agent workflow runs this section once, before the first implementation
change. A pinned requirement source is the user's original request, or the
text of a spec or issue that the request names, recorded with its SHA-256
hash. An acceptance reviewer accepts a failing gate item only with a quote
from one (step 7).

1. Make a pin directory outside the project, and write its printed path as
   `<pin-dir>`. Keep it until the change merges: the review work directory
   does not last that long.

   ```bash
   mktemp -d
   ```

2. Write the user's original request, word for word, to
   `<pin-dir>/request.txt`. Write the text of each issue that the request
   names to its own file:

   ```bash
   gh issue view <n> --json title,body --jq '.title + "\n\n" + .body' > <pin-dir>/issue-<n>.txt
   ```

3. Pin the files:

   ```bash
   <python> <skill-dir>/scripts/lean_tests.py pin --record <pin-dir>/pins.json \
     --source request=<pin-dir>/request.txt --source issue-<n>=<pin-dir>/issue-<n>.txt
   ```

   Give one `--source NAME=PATH` for each file. pin writes a new record
   and never changes one: when the record exists, it exits with status 2.
4. Report the `sha256` value of each source to the user. Step 7 compares
   the pinned texts with these values.

Done when `<pin-dir>/pins.json` exists and the user has the `sha256` value
of each source.

## 1. Choose the change

1. Choose `<base>`. Use the ref that the user names. Otherwise use the
   remote default branch, which
   `git -C <project> rev-parse --abbrev-ref origin/HEAD` prints. When
   neither exists, stop and ask the user for the base ref.
2. Choose the gate units. Use the whole range when the project squashes
   merges, or when you do not know its merge method. Add `--per-commit` to
   the gate command only when the user or the project's instructions say
   that merges keep each commit.
3. Record the starting state:

   ```bash
   git -C <project> status --porcelain --untracked-files=all > <work-dir>/status-before.txt
   ```

   The gate reads commits only. When this file has a line, ask the user
   to commit the change first, or report that the gate does not see the
   uncommitted files.

Done when you have `<base>`, know whether the gate uses `--per-commit`,
and `<work-dir>/status-before.txt` exists.

## 2. Run the weakening gate

```bash
<python> <skill-dir>/scripts/lean_tests.py gate --project <project> --base <base> \
  --python "<python>" --work-dir <work-dir> --out <work-dir>/gate.json
```

Add `--per-commit` when step 1 chose it. The arguments after `--` go to
pytest, as for suite.

The gate checks each gate unit in two layers:

- Layer 1, the compatibility replay, runs the changed base test modules
  against the head product code of a mixed change. It runs all base tests
  when a conftest file, a helper, test data, or the configuration
  changed. A base test that passes against the base product code and not
  against the head product code is a BEHAVIOR CHANGE item. The replay
  checks compatibility; it does not prove that the tests detect the same
  faults.
- Layer 2 reads the syntax trees of the base and head version of each
  test-side file. A module-level or class-level name is new only when base
  does not bind it, also not inside an `if`, `try`, `with`, `for`, or
  `while` block, and head binds it once. A second binding of an existing
  name changes that definition.

The gate runs pytest in a temporary detached worktree under
`<work-dir>/gate`, and removes the worktree at the end. Beside layer 1, the
worktree gives the collection evidence: the gate collects the head tests,
and a base node ID that is missing at head is a WEAKENING item. It also
runs each new test against the base product code for its label (step 3).

Each pytest run stops after 1800 seconds; `--timeout` changes it. A run
that stops gives an UNCLASSIFIED `incomplete-run` item. `--static-only`
runs layer 2 alone and needs no `--python`. It gives no replay, no
collection evidence, and no labels.

The exit status gives the result:

- 0: no mixed change failed.
- 1: the gate failed. A mixed change has a BEHAVIOR CHANGE, WEAKENING, or
  UNCLASSIFIED item, and its status is `fail`.
- 2: stop, and report the `error`. For example, the base tests do not
  collect, or the work directory is inside the repository.

A test-only unit, a gate unit with test-side changes and no product
change, does not fail. Its status is `needs evidence`: report its items
for the user to decide.

Each entry of `units[].items` has an `id`, such as `u1-i2`, a `class`, a
`subtype`, the `path` and `nodeid`, a `detail`, and a `diff` of the base
and head source:

| `class` | `subtype` | The change |
| --- | --- | --- |
| SAFE | `new-test`, `new-definition`, `new-import`, `new-constant` | adds a name without an infrastructure signal |
| SAFE | `appended-cases` | appends literal parametrize cases, and each base node ID stays |
| WEAKENING | `expected-literal` | changes the single literal operand of one `==` assertion of an existing test, with everything else equal; `old` and `new` give both values |
| WEAKENING | `removed-test`, `skip` | removes a test, or adds a skip or xfail marker or call |
| WEAKENING | `changed-assert`, `approx`, `raises` | removes or changes a check; the subtype is `approx` or `raises` when a removed or changed check calls `approx` or `raises` |
| WEAKENING | `self-comparison`, `tautology` | replaces a check with one that cannot fail |
| WEAKENING | `config-deselect` | adds `--deselect`, `--ignore`, `--ignore-glob`, `-k`, or `-m` to the pytest configuration |
| WEAKENING | `missing-node-id` | a base node ID is not collected at head; `missing` lists the IDs of renamed parametrize cases |
| UNCLASSIFIED | `changed-definition`, `rebinding` | adds or changes a statement inside an existing test, fixture, or helper, or binds an existing name again |
| UNCLASSIFIED | `existing-node-id` | adds a test whose node ID the base collected, for example a method that replaces an inherited test |
| UNCLASSIFIED | `no-collection-evidence` | appends parametrize cases, or adds a test to a subclass, and the gate has no collection evidence |
| UNCLASSIFIED | `signal` | adds a name with an infrastructure signal, such as an autouse fixture or a pytest hook; `detail` names the signal |
| UNCLASSIFIED | `conftest`, `configuration`, `test-data` | changes a conftest file, the pytest configuration, or a test data file |
| UNCLASSIFIED | other subtypes | the gate cannot classify the change, a module does not collect, or a run stopped |
| BEHAVIOR CHANGE | none | a base test fails against the head product code; `outcome` and `exception` give the result |

`summary.examples.failing` lists the first failing items. `uncommitted`
counts the files that the gate did not see. `new_tests` and
`changed_tests` in `files` are the node-ID lists that steps 4 and 6 read.

Done when the command exits with status 0 or 1, and you know the status
of each gate unit and the class of each item.

## 3. Read the new-test labels

The gate runs each new test against the base product code and labels it.
A new test is a new test function, or an appended parametrize case that
keeps each base node ID:

| `label` | The test on the base product code |
| --- | --- |
| `catching` | fails in its call phase with an assertion (`AssertionError` or `pytest.fail`) |
| `new-API` | does not collect, fails in setup, or fails with another exception, for example because the code that it calls does not exist at base |
| `hardening` | passes |

A catching test shows the fault that the change fixes. A hardening test
checks behavior that base already had. `label` is null when the test was
skipped, was not collected at head, or the label run stopped: report the
test as unverified.

Done when each new test has a label, or you have reported why it has
none.

## 4. Scan the new and changed tests

When `<work-dir>/gate/new-tests.txt` and
`<work-dir>/gate/changed-tests.txt` are both empty, skip this step.
Otherwise scan the tests that they list:

```bash
cat <work-dir>/gate/new-tests.txt <work-dir>/gate/changed-tests.txt > <work-dir>/review-ids.txt
<python> <skill-dir>/scripts/lean_tests.py scan --project <project> \
  --node-ids <work-dir>/review-ids.txt --out <work-dir>/scan.json
```

Report each `no-assertion`, `tautology`, `self-comparison`,
`weak-oracle`, `change-detector`, `trivial-code`, and `duplicate-shape`
finding, and the `duplicate_groups`, as
[check step 5](check.md#5-scan-the-tests) describes. A `weak-oracle`
finding gives a weak-oracle note: the test checks only truthiness,
non-None, type, or non-empty values, so it detects few faults. The note is
advice and does not fail the review.

Done when you have the scan findings of the new and changed tests.

## 5. Measure diff coverage

Steps 5 and 6 need pytest-cov in `<python>`. Get it as the setup does for
analysis tools. When `<python>` cannot import it, skip both steps, and
report the admission of each new-API and hardening test as unverified,
with pytest-cov as the package that enables it.

```bash
<python> <skill-dir>/scripts/lean_tests.py suite --python "<python>" \
  --project <project> --work-dir <work-dir> --label scope \
  --coverage-source <source> --out <work-dir>/scope.json
<python> <skill-dir>/scripts/lean_tests.py coverage \
  --contexts <work-dir>/scope/coverage.json --suite <work-dir>/scope.json \
  --base <base> --out <work-dir>/coverage.json
```

Repeat `--coverage-source` for each package. When `pytest_exit_code` of
the suite run is 2 or more, read `<work-dir>/scope/pytest.log`, report the
cause, and skip steps 5 and 6.

`diff` gives the product lines changed since the merge base that no test
executed. List them, and name the missed `raise` and `except` lines: an
error path that no test executes is untested behavior. Also report
`unmeasured_files` and `unparsed`.

Done when you have the missed changed lines, or have reported why diff
coverage is not measured.

## 6. Apply the admission rule

```bash
<python> <skill-dir>/scripts/lean_tests.py mutate --python "<python>" \
  --suite <work-dir>/scope.json --work-dir <work-dir> --base <base> \
  --new-tests <work-dir>/gate/new-tests.txt --out <work-dir>/review.json
```

With `--base`, mutate makes mutants only on the review lines:
`review_lines` lists, by module, the product lines changed since the merge
base and the lines that only new tests cover. Each mutant runs against
every test of the suite run, as in
[prune step 4](prune.md#4-build-the-kill-matrix). The run has a budget of
300 seconds; `--budget` changes it. Exit status 2: report the `error`, and
report each admission as unverified.

Each entry of `admission` gives a new test's `verdict`, its `new_kills`
(the mutants that it kills and no existing test kills), and
`exception_kills_only` (it kills mutants only with exceptions other than
assertions, so it checks no value). A collection kill does not count,
because it fails each test of a module alike. A mutant whose run stopped
before an existing test does not count either. Decide each new test with
the first row that applies:

| Label | `verdict` | Decision |
| --- | --- | --- |
| `catching` | any | accept: it fails on the base product code with an assertion |
| `new-API` or `hardening` | `accept` | accept: it kills a mutant that no existing test kills |
| `new-API` or `hardening` | `no unique kill` | reject: redundant, when each check of the test maps to an assertion of an existing test under equivalent inputs and setup; else accept: distinct checks, no unique kill |
| any | `unverified` | unverified: the evidence is incomplete; report the `reason` or the `incomplete_reason` |

For a reject, write the check mapping in the format of
[prune step 6](prune.md#6-write-the-rationale). review deletes no test: it
reports each decision.

Done when each new test has one decision: accept, accept: distinct
checks, no unique kill, reject: redundant, or unverified.

## 7. Accept failing gate items

Do this step for each BEHAVIOR CHANGE, WEAKENING, and UNCLASSIFIED item of
a gate unit with the status `fail`. An accepted item can stay in the
change; the gate result itself does not change.

A human, or an acceptance reviewer, accepts a failing gate item. An
acceptance reviewer is an agent with fresh context in an autonomous run: a
new subagent. Where the host has no subagent, only a human accepts. The
author of the change, agent or person, never accepts its own items.

| Item | Who may accept |
| --- | --- |
| BEHAVIOR CHANGE | a human, or an acceptance reviewer |
| UNCLASSIFIED | a human, or an acceptance reviewer |
| WEAKENING `expected-literal` | a human, or an acceptance reviewer; the acceptance states the `old` and `new` values |
| WEAKENING, each other subtype | a human only; an autonomous run stops and reports the item |

An acceptance reviewer needs the pin record from before the first
implementation change. Without one, only a human accepts, unless history
that predates the change fixes the source text, for example an issue body
that nobody edited after the first commit of the change. Then pin that
text as the pin section says, and name its origin in the report.

An acceptance reviewer accepts an item as follows:

1. Give the reviewer only the pin record, the item, and its failure: the
   item's `detail`, `diff`, `old` and `new`, or `outcome` and `exception`.
   For a BEHAVIOR CHANGE item, also give the base test and the product
   diff of the gate unit.
2. The reviewer accepts only with a quote: one whole sentence of a pinned
   requirement source that requires the change. Text that the author wrote
   or edited after pinning cannot authorize a change. A later change of
   the requirements counts only when it comes from the user, or from a
   principal that the user explicitly authorized. An agent that acts for
   the author never counts.
3. Check the quote. Put the sentence in single quotes. When the sentence
   has a single quote, write each one as `'\''`.

   ```bash
   <python> <skill-dir>/scripts/lean_tests.py pin --check <pin-dir>/pins.json \
     --quote '<sentence>'
   ```

   Exit status 0 means that each pinned text is intact and that
   `quote_found_in` names a source with the quote. Exit status 1 means
   that a pinned text changed (`changed`) or that no source has the
   quote: the item stays open. Also compare the `sha256` of the quoted
   source with the value that the pin section reported.
4. Write one acceptance line for the item:

   ```text
   - accept <item id> <class> <subtype> <nodeid or path>: <old> -> <new>; by <acceptance reviewer>; quote "<sentence>" from <source> sha256 <source sha256>; diff_sha256 <unit diff_sha256>
   ```

   Leave out `<old> -> <new>` for an item other than `expected-literal`.

A human writes the same acceptance line, with the human's name after
`by`. A human needs no quote: leave out the quote and its source.

The acceptance applies only to the gate unit's `diff_sha256` and to the
`sha256` of the quoted source. A new commit gives the gate unit a new
`diff_sha256`: run the gate again, and accept each failing item again.

Done when each failing item has an acceptance line or is reported as
open.

## 8. Report

Report:

- The pinned requirement sources: the name and `sha256` of each, and the
  origin of a text pinned from history. Say when no pin record exists.
- The gate: the exit status, each gate unit with its status, and each
  item that is not SAFE, with its id, class, subtype, node ID, and detail.
- The acceptance lines of step 7, and the open items.
- Each new test with its label and decision. For a reject, give the check
  mapping.
- The changed product lines that no test executes, with the `raise` and
  `except` lines first.
- The weak-oracle notes and the other scan findings of the new and
  changed tests.
- The uncommitted files that the gate did not see, and each measurement
  that you could not take.

Then check the end state and remove the work directory:

```bash
git -C <project> status --porcelain --untracked-files=all | diff <work-dir>/status-before.txt -
rm -r <work-dir>
```

Each difference is a file that the tests wrote. Report these files, and
ask the user before you remove one. Keep `<pin-dir>` until the change
merges.

Done when the report is complete and the work directory is removed.
