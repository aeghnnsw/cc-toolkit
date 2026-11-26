# Give the merge-lock holder suite priority with a marker

> **Superseded in part (2026-11-26, issue #641).** When the marker that a
> run waits for is gone, the run waits up to 15 s for a new marker before it
> takes the suite lock. So a marker wait can end up to 15 s after the limits
> of decisions 4 and 8. Read [Handover wait](#handover-wait).

`dev-skills/scripts/run_suite.py` gave its suite lock to the first run that
asked: one try without a wait, then a blocking `flock` with no priority. In
aeghnnsw/researcher, the worktree that holds the merge lock runs its last
full tier under that lock, and other worktrees run full tiers before review
outside it. In batch 9 (record on aeghnnsw/researcher#967), a full tier of
another worktree started 26 s after the merge lock was taken and held the
suite lock. The full tier of the merge-lock holder waited 473 s for it, then
ran for 218 s. So the merge lock was held for about 12 minutes instead of
about 4, and each other worktree waited longer for it
([#571](https://github.com/aeghnnsw/cc-toolkit/issues/571)).

`run_suite.py` serves more repositories than researcher. It ships to Claude
Code, Codex, and Antigravity, and matt-automode tells each brief to run each
full suite through it. Only researcher has a merge lock, and
[#500](https://github.com/aeghnnsw/cc-toolkit/issues/500) chose an interface
that names no repository.

Decisions:

1. **A marker, read by `run_suite.py`.** A repository's merge-lock tool
   writes a priority marker, and `run_suite.py` reads it. The tool fix covers
   each repository whose merge-lock tool writes the marker.
2. **A generic contract.** The marker is `run-suite-priority.json` in the
   Git common folder (`git rev-parse --path-format=absolute
   --git-common-dir`), beside the suite locks and `run-suite-passes.json`.
   It is a JSON object with two required fields: `worktree`, the absolute
   path of the worktree root, and `started`, a UTC time in the form
   `%Y-%m-%dT%H:%M:%SZ`. `run_suite.py` ignores other fields, so a
   merge-lock tool can write its own lock record there. The tool writes the
   file when it takes or renews its lock, and removes it when it releases
   the lock. `run_suite.py` only reads it. The `run_suite.py` docstring
   states the contract.
3. **Fresh for 60 minutes from `started`.** The limit is a fixed constant.
   It equals the age at which the researcher merge lock is stale. researcher
   writes `started` again at each take and renewal, so the marker stays
   fresh while the holder renews its lock.
4. **A bad marker gives no priority.** A missing, unreadable, or stale
   marker gives no priority. So does a marker that is not a JSON object with
   both fields, that has a time in another form or after the current time,
   or that names a folder that does not exist. A run in the named worktree
   does not wait. `run_suite.py` checks whether the named folder is the
   worktree root, so a path through a symbolic link or in another letter
   case names the same worktree. researcher stores a resolved path. No
   marker state makes a run wait more than 60 minutes after its `started`
   time (superseded in part: 60 minutes and 15 s; read
   [Handover wait](#handover-wait)), and the marker wait holds no lock, so
   it cannot cause a deadlock.
5. **Every suite of the other worktrees waits.** While a fresh marker names
   another worktree, each `run_suite.py` run waits, not only the runs of one
   suite. The merge-lock tool cannot name the suites of the holder: when it
   takes the lock, no suite has started, and a suite is an exact command in
   a folder. So, across worktrees, different suites do not run in parallel
   while a fresh marker exists.
6. **Read the marker before and after the suite lock.** A run that waits in
   the blocking `flock` does not read the marker, and a run that queued
   before the marker appeared can take the suite lock before the holder's
   run. So after a run takes the suite lock, it reads the marker again. When
   a fresh marker names another worktree, it releases the suite lock without
   writing its details to it, and waits again. A run whose command already
   runs is not stopped.
7. **Report the wait.** When the marker wait starts, the run prints one
   line to stderr. The summary has the line
   `Priority marker wait: <N> s, for <worktree>` before the suite lock wait
   line, because a wait must show in the summary
   ([#525](https://github.com/aeghnnsw/cc-toolkit/issues/525)).
8. **No other limit on the wait.** The freshness limit bounds the wait to 60
   minutes after the last take or renewal of the merge lock. (Superseded in
   part: the handover wait adds up to 15 s; read
   [Handover wait](#handover-wait).) The suite lock wait has no limit either.

Rejected alternatives:

- **A rule in researcher's steering file: do not start a full tier while
  another worktree holds the merge lock.** An agent would have to run
  `merge-lock.py status` and read its text, because the command exits 0 in
  both states. Sessions misread two earlier timing rules in researcher's
  `AGENTS.md` (aeghnnsw/researcher#896, aeghnnsw/researcher#952). The rule
  would cover only researcher. The retrospective rule prefers a tool fix to
  new text in a steering file.
- **`run_suite.py` reads researcher's `merge-lock.json`.** That ties the
  script to one repository and its file format.
- **A marker for one suite.** The merge-lock tool cannot name a suite of the
  holder when it takes the lock.

Consequences:

- cc-toolkit writes no marker, so its runs work as before.
- When a holder stops without a release, the full tiers of other worktrees
  wait up to 60 minutes. Without the marker, those worktrees also wait for
  the merge lock until it is stale, at 60 minutes.
- The marker orders only runs that go through `run_suite.py`. It does not
  stop a run that already holds the suite lock when the merge lock is
  taken.
- The marker writer is aeghnnsw/researcher#1119. The two changes can merge
  in either order: a marker without a reader, or a reader without a marker,
  changes nothing.

## Handover wait

Added 2026-11-26 for
[#641](https://github.com/aeghnnsw/cc-toolkit/issues/641).

aeghnnsw/researcher `scripts/merge-lock.py` removes its marker at release,
before the next worktree in its queue takes the lock. That worktree reads
the lock every 10 s, and writes its marker when it takes the lock. In this
gap, a run of a third worktree that waited for the marker found no marker,
took the suite lock, and started its suite. The new merge-lock holder then
waited for that run: 144 s in batch 27 of aeghnnsw/researcher.

Rule: when the marker that a run waits for is gone, the run waits up to
15 s for a new marker before it takes the suite lock. The constant is
`HANDOVER_WAIT` in `run_suite.py`. A fresh marker that names another
worktree in this time continues the marker wait, and the next gap starts a
new 15 s. A marker that names the worktree of the run ends the wait at
once. A missing, stale, or malformed marker counts as gone.

Reason: 15 s is more than the 10 s interval of researcher's merge-lock
tool, so the next holder writes its marker in that time. The fix needs no
change in the merge-lock tool, and the marker contract does not change.

Consequences:

- A run in the worktree that the marker names still waits in `flock` while
  a run of another worktree holds the suite lock. A second run of the same
  suite at the same time would defeat the suite lock.
- A run that waited for a marker waits 15 s more after the last release,
  when no worktree waits for the merge lock.
- A run that starts in the gap, and did not wait for a marker before, finds
  no marker and takes the suite lock.
