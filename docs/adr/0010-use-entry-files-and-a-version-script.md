# Use entry files and a version script for parallel pull requests

Parallel pull requests conflicted in `CHANGELOG.md` and in plugin versions
([#298](https://github.com/aeghnnsw/cc-toolkit/issues/298)). The navigation
retrospectives of the project-lead batches recorded the cost:

- In batch 10, the lead ordered 7 rebases. Each cost 2–6 minutes of worker
  time, a full local suite run, and a new CI run of about 9 minutes. Two
  workers took dev-skills 3.62.0 within one minute. Two first `CHANGELOG.md`
  resolutions were wrong: one dropped three entries, and one duplicated
  entries.
- In batch 12, both sides of a rebase held the same versions, so Git merged
  the manifests without a conflict and left the branch at the version of
  `master`. The worker found it and set the versions by hand.
- After a rebase that changed only `CHANGELOG.md` and versions, workers ran
  the full suites again, which made the suite-lock queue longer.

The rule "keep both entries, the rebased branch's entry first" was in
CONTRIBUTING, and the cost continued. Branch protection on `master` requires
no status check and no up-to-date branch, and auto-merge is off. The lead's
merge rule ("merged tree = tested head") makes each pull request rebase
after another one merges. CI runs only on pull requests, on the merge of the
pull request into `master`.

Decisions:

1. **Entry files.** A pull request adds its changelog bullets in a new entry
   file and does not edit `CHANGELOG.md`. The file is
   `changelog.d/<N>.md`, where `<N>` is the issue number, or
   `changelog.d/<N>-<words>.md` when another change already uses the number.
   It holds the headings `### Added`, `### Removed`, or `### Changed`, each
   with bullets in the current form. The package validator applies the
   current bullet rules to the new bullets of entry files: the form, 600
   characters, a heading of the three, the versions, and one bullet for each
   version increase. A bullet is new when its text is in neither
   `CHANGELOG.md` nor an entry file at the merge base, so a bullet that the
   release step moves is not new. A new bullet in `CHANGELOG.md` fails. The
   validator does not check prose above the first `## ` heading of
   `CHANGELOG.md`.
2. **Release step.** `scripts/release_changelog.py` moves the bullets of
   each entry file into `## [Unreleased]` of `CHANGELOG.md`, under the same
   headings, and deletes the files. The file that the newest commit added
   comes first. The maintainer runs the release step, or asks an agent to
   run it, on a branch from `master`, in a pull request that changes nothing
   else, for example between batches of parallel pull requests. A feature
   pull request never runs it. The validator fails a branch that deletes an
   entry file of the merge base and changes another file, or that drops a
   bullet of a deleted entry file. The release changes only files that no
   feature pull request edits, so it causes no conflict.
3. **Version script.** `scripts/next_versions.py --base origin/master`
   finds the plugins and skills that the branch changes with the validator's
   rules for affected hosts and changed skills. It sets each of their
   versions that is not above the tip of the base ref to the tip version,
   raised in one part: minor by default, or `--part patch` or
   `--part major`. A version above the tip stays, so a second run changes
   nothing. It changes only the version value of a manifest, so the JSON
   format stays. Then it writes the new versions into the plugin bullets of
   the branch's entry files, and into `<skill> <version>` in their text. It
   compares with the tip and not with the merge base, so a run before a
   rebase also takes a version above `master`. Most changes in this
   repository raise the minor number; the script cannot tell a fix from a
   feature, so the author passes `--part patch`.
4. **Checks after a rebase.** When the resolution of a rebase changes no
   file other than versions and changelog entries, only the package
   validator runs locally, and CI runs the suites on the new head. A suite
   runs locally again only when the resolution changes another file.
   CONTRIBUTING and each host copy of matt-automode state this rule.

Rejected alternatives:

- **A documented rebase order alone.** The CONTRIBUTING rule existed, and
  the cost continued.
- **`merge=union` in `.gitattributes`.** A merge on GitHub does not use it,
  it does not fix versions, and in a rebase it writes the side of `master`
  first, against the CONTRIBUTING order.
- **Versions only at release.** A host updates an installed plugin when its
  manifest version changes, and the hosts install from `master`. So each
  merged change needs its own increase.
- **Merges without a rebase.** The merged tree would differ from the tree
  that CI tested.

Consequences:

- Two pull requests that add different entry files do not conflict in a
  changelog file. A version can still conflict; the author keeps either
  side and runs the version script.
- Two open pull requests can still take the same version. The second one to
  merge rebases and runs the script, which takes the next version above
  `master`. The validator in CI fails a merge result that holds the version
  of `master`.
- `CHANGELOG.md` lists a merged change only after the release step. Its
  first lines name `changelog.d/`.
- The validator fails each new or edited bullet in `CHANGELOG.md`, also the
  correction of an older bullet.
