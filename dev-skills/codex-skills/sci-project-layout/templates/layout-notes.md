# Layout notes

The rules in [layout.md](layout.md) come first. This file explains why
they exist and covers cases that do not happen every day. Read only the
section for your situation.

| Situation | Section |
| --- | --- |
| You want to know why the layout looks like this | [1](#1-sources) |
| The store does not resolve, or you use conda, a sandbox, or HPC storage | [2](#2-the-store) |
| You edit `.gitignore` or the pytest settings | [3](#3-gitignore-and-tool-settings) |
| You add a dataset, lab data, or model weights | [4](#4-datasets) |
| You write `run.json` fields or handle a failed run | [5](#5-runs) |
| A program writes output or scratch files | [6](#6-program-output-and-scratch) |
| You run jobs on a cluster | [7](#7-cluster-jobs) |
| You cite, reuse, or withdraw a result, or need a commit after a squash merge | [8](#8-citation-and-squash-merges) |
| You delete, back up, or move data | [9](#9-deleting-backup-and-transfer) |
| A file to commit is large, or a project passes issue 999 | [10](#10-limits) |

## 1. Sources

| Source | Rule we take | Rule we do not take |
| --- | --- | --- |
| Cookiecutter Data Science v2 ([docs](https://cookiecutter-data-science.drivendata.org/opinions/)) | Raw data does not change. One module holds all paths. | A fixed `DATA_DIR = PROJ_ROOT / "data"`, so each worktree sees an empty `data/`. The `notebooks/`, `models/`, and `reports/` folders. |
| Wilson et al. 2017 ([paper](https://journals.plos.org/ploscompbiol/article?id=10.1371/journal.pcbi.1005510)) | `data/` for inputs, `results/` for generated files. Raw data is read-only and backed up. Large data stays out of git. | The `bin/` folder. |
| Noble 2009 ([paper](https://journals.plos.org/ploscompbiol/article?id=10.1371/journal.pcbi.1000424)) | Results in time order. A note for each dataset with its download date. Driver scripts. | `results/YYYY-MM-DD/` at the top level. We group by experiment, then by time. |
| Sandve et al. 2013 ([paper](https://journals.plos.org/ploscompbiol/article?id=10.1371/journal.pcbi.1003285)) | Record the versions of external programs and the random seeds. | — |
| The Turing Way ([guide](https://book.the-turing-way.org/project-design/pd-overview/project-repo/project-repo-advanced)) | Keep inputs, methods, and outputs apart. | — |
| Snakemake template | Outputs go to `results/`. Code is kept apart from outputs (`--directory`). | `resources/`: the template ignores it. |
| Scientific Python guide ([guide](https://learn.scientific-python.org/development/guides/packaging-simple/)) | `src/` layout. `[project.scripts]` for commands. `AGENTS.md` with a `CLAUDE.md` link. | — |
| Hydra | One folder for each run, with its config. | A timestamp-only `outputs/` folder at the top level. |

Other templates checked: MolSSI cookiecutter-cms, Scientific Python cookie,
Kedro, DataLad YODA, showyourwork, nf-core, lightning-hydra-template,
copier-uv, and TIER 4.0. None of them handles git worktrees, data shared
across worktrees, or agent scratch folders.

## 2. The store

### Why the store is outside worktrees

These facts were tested in scratch repositories:

- A new worktree does not contain the main checkout's ignored files.
- `git worktree remove` deletes ignored files in the worktree with no
  warning. Untracked files that are not ignored make it refuse, unless you
  pass `--force`.
- `git rev-parse --path-format=absolute --git-common-dir` gives the main
  checkout's `.git` from every worktree.
- Nothing loads `.env` by default: neither `python` nor `uv run` does.
  `.worktreeinclude` copies files only into worktrees that Claude Code or
  the Codex app creates. So neither can carry the store path.

### Resolution and errors

`paths.STORE` is the first of these that is set:

1. `$MYPROJ_STORE`, for a job on a node without git.
2. `git config layout.store`. It belongs to one clone and applies to all
   of that clone's worktrees.
3. The main checkout.

`paths.py` runs git in its own folder (`git -C <folder of paths.py>`),
never in the current folder. So a script started from anywhere finds the
right checkout.

Importing `paths` raises `StoreError`, with a message that says how to
set the store, in these cases:

- The value is a relative path.
- `paths.py` is not in a git checkout, or git is not installed, and
  `MYPROJ_STORE` is not set. This happens with an installed wheel or a
  copied code folder. There is no fallback folder, because it would make
  a second store.
- `--git-common-dir` does not end in `.git`: a bare repository, a
  submodule, or a separate git folder.
- Git is older than 2.31. It echoes the unknown `--path-format` option and
  exits 0, so the result is not an absolute path.

### Environments

Each worktree must import its own code, or `run.json` records the wrong
commit. Nothing checks this. Run steps with `uv run`: it sets up the
worktree's own `.venv`, and a bare `python` can be another interpreter.
`uv run` installs `src/myproj` only when `pyproject.toml` has a
`[build-system]` table. With conda, set `PYTHONPATH=src`, and do not
install the project into a shared environment.

### Agents and sandboxes

- A sandboxed worktree session can write only inside its worktree. Add
  the absolute paths of `<store>/data` and `<store>/results` to the write
  allow-list, after the user approves: `sandbox.filesystem.allowWrite` for
  Claude Code, `writable_roots` for Codex. Do not add the store root: by
  default it is the main checkout.
- The paths differ per machine, so put them in an untracked file:
  `.claude/settings.local.json` for Claude Code, `~/.codex/config.toml`
  for Codex. Never put them in the tracked `.claude/settings.json`. In a
  worktree, Claude Code reads the local file at the main checkout's root.
- Agents use absolute store paths in commands, not in tracked files, and
  never `cd` into the store.
- These keys and file locations come from the Claude Code and Codex
  documentation. A write from a live sandbox was not tested. The Codex
  entry in `~/.codex/config.toml` applies to every Codex session on the
  machine.

### Where the store lives

- Use storage that is not purged. On HPC, use project storage, not
  scratch.
- Do not put the repository or the store in a synced folder such as
  OneDrive or Dropbox. Syncing `.git` or large data causes conflicts and
  very large uploads.

## 3. `.gitignore` and tool settings

Every pattern for a top-level folder starts with `/`. A pattern without
it, such as `data/`, also matches `docs/data/` and
`tests/fixtures/data/`. Then `git add docs/` skips the dataset cards with
no error. Patterns have no trailing slash, so a symlinked store also
matches.

Do not ignore tool output folders such as `outputs/`, `multirun/`,
`wandb/`, `mlruns/`, `lightning_logs/`, or `.snakemake/`. When a tool
writes there by mistake, the folder shows as untracked. The run is then
marked dirty, and `git worktree remove` refuses to delete the folder.

The skill's Set up mode adds `testpaths = ["tests"]` to
`pyproject.toml`, so that a plain `pytest` does not collect the tests of
other worktrees. The other settings below keep tests and type checks out
of worktrees and the store:

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["src"]
norecursedirs = [".*", "trees", "data", "results", "*.egg", "build", "dist", "node_modules", "venv"]

[tool.mypy]
exclude = ['^trees/', '^data/', '^results/']
```

`norecursedirs` replaces the pytest defaults, so the list repeats them.

## 4. Datasets

### Dataset cards

The card path is the data path without the version:
`data/raw/chembl/activities/v34/` has the card
`docs/data/raw/chembl/activities.md`. A card records:

- Source URL, license, and retrieval date.
- Each version, its size, and where a copy can be obtained (a URL, a
  shared path, or the backup).
- The command that fetched or built it. For processed data, also the
  commit and the input versions.

### Versions

- **Raw version**: the release (`v34`). If the source has no releases, use
  the retrieval date (`2026-10-20`).
- A raw version is one complete fetch. To add entries, such as more PDB
  structures, fetch the whole list again into a new version. Never add
  files to an existing version.
- **Processed version**: `v1`, `v2`, and so on. The build script picks the
  next number. Build one version at a time: two builds at once can pick the
  same number. If a build fails, delete its partial folder.
- **Read-only**: run `chmod -R a-w` on the version folder when it is
  complete. A tool that writes an index next to its input, such as
  `samtools faidx` or SQLite in WAL mode, needs that index made before the
  `chmod`.
- **Checksums** are optional. When a source publishes checksums, or the
  data cannot be fetched again, the fetch script can write
  `MANIFEST.sha256` (`sha256sum` format, sorted by path).

### Hand-made and special data

The layout page gives the locations. These details add to it:

- A small hand-made file is tracked. Prefer text formats. Examples: a
  curated target list, a receptor fixed by hand.
- Lab data has no public source, so its card names a shared copy.
- `data/processed/` holds only output from our code.

## 5. Runs

- Steps run from the repository root, with `uv run`.
- To change a parameter, commit a new `config.yaml` before the run, or
  pass the value on the command line. `new_run()` copies `config.yaml`
  into the run folder and records the command line in `run.json`.
- `"dirty"` is true when `git status --porcelain --untracked-files=normal`
  prints anything, so untracked files count even when
  `status.showUntrackedFiles` is `no`. Ignored files do not count. It is
  `null` when `git status` fails. `git diff --quiet HEAD` misses untracked
  files, so do not use it.
- A run whose status is `running` but whose process or job no longer
  exists counts as failed.
- When two runs start in the same second with the same label, `new_run()`
  adds `-2`, `-3` to the second run ID.
- Run IDs use local time, and `run.json` records the UTC offset. Run IDs
  from hosts in different time zones can sort out of order. This is
  accepted.
- A step can add fields to `run.json` through `run.info`, for example
  external tool versions (`run.info["tools"] = {"vina": "1.2.5"}`), the
  random seed, the host, or the scheduler's job ID. `new_run()` writes
  them when the run ends. Python package versions are in `uv.lock` at the
  recorded commit.
- `inputs` takes only version folders under `paths.DATA` and run folders
  under `paths.RESULTS`. Any other path raises `ValueError` before the run
  folder is made.

## 6. Program output and scratch

Point every program at the run folder:

| Program | Setting |
| --- | --- |
| Snakemake | `snakemake --directory <run>` |
| Hydra | `hydra.run.dir=<run>` |
| Weights & Biases | `WANDB_DIR=<run>` |
| MLflow | `MLFLOW_TRACKING_URI=file:<run>/mlruns` |
| Lightning | `default_root_dir=<run>` |
| Other programs | Start them with the run folder as the working folder |

Put program scratch in `$TMPDIR`, or in a cluster's node-local scratch
folder. Examples: Gaussian `GAUSS_SCRDIR`, ORCA temporary files, and MD
temporary files.
Copy only restart and checkpoint files into the run folder.

## 7. Cluster jobs

The layout works with any job scheduler.

- A job script used by one experiment is a step. `02_dock.sh` runs
  `uv run python experiments/<key>/02_dock.py`, and the Python step calls
  `new_run()`. Shared job templates go in `scripts/hpc/`.
- In the job script, set the scheduler's log path to `logs/`. Run
  `mkdir -p logs` before you submit, because a scheduler may not make the
  folder. Submit from the repository root, so that relative paths start
  there. If your scheduler starts a job in your home folder, `cd` to the
  submit folder first with the scheduler's variable for it. Do not write
  the path. The scheduler's log is throwaway. The Python step writes its
  own log into the run folder.
- A job imports code from the checkout it started in. Do not remove that
  worktree while the job runs or waits in the queue.
- Outside a git checkout, `new_run()` cannot record the commit, so the run
  cannot be cited. So do not start a job from a copy of the code, and run
  the steps that you plan to cite on nodes that have git. On a node
  without git, export `MYPROJ_STORE` before you submit, and have the
  scheduler pass it to the job. Do not write the path in the job script.
- Copy a run from cluster scratch into the store before you cite it.

## 8. Citation and squash merges

### Cite a run

No command cites a run. Do these steps on the run's branch, before its PR
merges:

1. Read the run's `run.json`. Stop if `status` is not `succeeded`, if
   `git.sha` is empty, or if `git.dirty` is not `false`.
2. Do step 1 for each run in `inputs` (the entries under `results/`), and
   for the runs in their `inputs`.
3. Make each of these run folders read-only:
   `chmod -R a-w <store>/results/<key>/<run-id>`.
4. Add a line under Runs in the experiment README, and commit it:
   `- <key>/<run-id>: <what the run shows>`.

### Why cite before the merge

`run.json` records the commit of the branch that made the run. A squash
merge puts a new commit on the default branch. After `repo-cleanup`
deletes the branch and git runs garbage collection, the recorded commit is
no longer in the local history.

### Get the commit back

GitHub keeps the commits of each pull request after the branch is
deleted. This was not tested here.

1. Find the PR that added the run to the README:
   `git log --oneline -S <run-id> -- experiments/<key>/README.md`. The
   squash commit title ends with the PR number, for example `(#44)`.
2. Fetch the PR commits: `git fetch origin pull/44/head`.
3. Check out the recorded commit: `git checkout <sha from run.json>`.

If a project needs stronger protection, tag the commit when you cite:
`git tag run/<key>/<run-id> <sha>`, then push the tag. A local test showed
that a tag keeps the commit after the branch is deleted and git runs
garbage collection.

### Reuse, figures, and withdrawal

- **Another experiment's run**: list it in `inputs` of your run. Use it
  only after its PR has merged, so its code and README are on the default
  branch.
- **A figure in a README or paper**: a run writes its figures into its own
  folder. Copy a cited figure to `experiments/<key>/figures/` as
  `<run-id>_<name>.<ext>`, so each committed figure names its run.
- **A figure that combines experiments**: it gets its own experiment, for
  example `057-paper-kinase-hits`. Its steps list the runs of the other
  experiments as inputs.
- **Step numbers**: once a step has a cited run, its number does not
  change. Insert new steps as sub-steps (`02_1_`).
- **Withdraw a result**: set `Status: superseded by <key>` in the README.
  Do not delete the cited run.

## 9. Deleting, backup, and transfer

### Deleting

- No helper, agent, or cleanup step deletes anything in the store.
- To free disk space, delete uncited runs by hand. An uncited run is a
  run folder that is still writable. Citation makes a run and every run
  that it depends on read-only, so `rm -rf` by a normal user cannot remove
  them.
  Read-only folders do not stop the root user, for example in some
  containers.
- Delete a processed version by hand only when no cited run lists it as an
  input. It can be rebuilt from its card.
- Never run these commands in the main checkout: `git clean -x`,
  `git clean -X`, `git stash -a`, `git stash --all`. They delete or move
  the store.

### Backup

- Set a backup root once: `git config layout.backup <path or rsync target>`.
- Back up raw data and cited runs. They never change, so this command is
  safe to repeat:
  `rsync -a --ignore-existing <store>/data/raw/ <backup>/data/raw/`. Do
  the same for each cited run folder.
- Processed data can be rebuilt. Back it up if a rebuild takes a long time.

### A new machine or a collaborator

1. Clone the repository.
2. Set the store: `git config layout.store <path>`.
3. Fetch public raw data with the fetch scripts.
4. Copy lab data and cited runs from the locations in the cards and the
   backup with `rsync`.

## 10. Limits

### Tracked file size

- Give a reason in the PR for a tracked file over 1 MB.
- Never track a file over 10 MB. GitHub warns at 50 MB and blocks files
  over 100 MB.
- Strip notebook outputs before you commit.

### Experiment key width

- GitHub issues and PRs share one number sequence, so the numbers grow
  faster than the issue count.
- A number above 999 is written in full (`1234-<slug>`). It then lists
  before `999-<slug>`.

### The `paths` module

Each project has its own copy of `src/myproj/paths.py`. A later fix to
the skill's template does not reach it. To take a fix, copy the new
template and replace the package name again.
