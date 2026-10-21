# Project layout

This page is the layout of this project. Read it before you add a file.
Reasons and rare cases are in [layout-notes.md](layout-notes.md).

```
<project>/
├── README.md
├── CLAUDE.md            one line: read docs/agents/layout.md (AGENTS.md links here)
├── pyproject.toml       has [build-system], so uv run installs src/myproj
├── uv.lock              tracked; uv run writes it
├── src/myproj/          reusable code; paths.py finds the store
├── tests/               tests; tiny inputs in tests/fixtures/
├── scripts/             reusable commands: fetch_*, build_*
├── experiments/
│   └── 042-docking-baseline/
│       ├── README.md    Status, Question, Method, Runs, Result
│       ├── config.yaml  parameters
│       ├── 01_prepare.py
│       └── 02_dock.py
├── docs/                documents; dataset cards in docs/data/; this page in docs/agents/
│
│   not tracked:
├── data/                inputs: raw/ and processed/, read-only versions
├── results/             outputs: <key>/<run-id>/
├── .scratch/            throwaway work
├── logs/                throwaway logs: cluster jobs, tools
└── trees/               worktrees (desktop sessions use .claude/worktrees/)
```

Make each folder when you first need it.

## Rules

1. **Tracked or not.** Git tracks code, documents, and experiment folders.
   It does not track `data/`, `results/`, `.scratch/`, `logs/`, or
   worktrees.
2. **One store.** `data/` and `results/` exist only in the main checkout.
   Code in every checkout, worktrees included, gets their paths from
   `paths.DATA` and `paths.RESULTS`. Never copy data into a worktree.
   Nothing durable lives in a worktree. Never write `data/...`,
   `results/...`, or a path on your own machine (home, disk, or cluster
   scratch) in code, notebooks, `config.yaml`, or job scripts. Name data
   relative to `paths.DATA`, and put the store's path in
   `git config layout.store`. Read other machine paths, such as a tool's
   install folder, from an environment variable.
3. **Data versions.** A fetch script writes raw data to
   `data/raw/<source>/<dataset>/<version>/`. A build script writes processed
   data to `data/processed/<dataset>/<version>/`. Each version is written
   once and then made read-only. Changed data is a new version. Each
   dataset has a card in `docs/data/`.
4. **Experiments.** One scientific question is one folder:
   `experiments/<NNN>-<slug>/`. `NNN` is the number of the issue that asks
   the question, padded with zeros to three digits. If that issue is split
   into ticket issues, still use the question's issue number. Start its
   `README.md` from `docs/agents/experiment-README.md`.
5. **Steps.** An experiment's steps are `NN_<name>.py`, `.ipynb`, or
   `.sh`, run in number order from the repository root. Run a `.py`
   step with `uv run python <path>`. Steps import shared code from `src/`.
   Strip notebook outputs before you commit.
6. **Runs.** Each execution of a step writes only into a new folder that
   `paths.new_run()` makes: `results/<key>/<run-id>/`. Point every
   program's output at that folder, and its scratch files at `$TMPDIR`.
   Commit first if you may cite the run: a run with uncommitted changes
   cannot be cited.
7. **Key results.** To keep a result, cite its run on the branch that made
   it, before that branch's PR merges. Follow the four steps in
   [notes section 8](layout-notes.md#8-citation-and-squash-merges): check
   the run and the runs it depends on, make them read-only, and add the
   run to the README. Cited runs are never deleted. Other runs stay until
   you delete them by hand.
8. **Throwaway work.** It goes in `.scratch/`. Nothing outside `.scratch/`
   reads it. If the work turns out to matter, run it again as a step.
9. **Rule of two.** When a second place uses a function, move it to
   `src/myproj/` and add a test. A reusable command goes in `scripts/`; its
   logic goes in `src/`.
10. **Names.** Use lowercase ASCII, no spaces, and ISO dates
    (`2026-10-21`). Put versions in folder names, never in file names such
    as `final_v2.csv`.

## Make a run

```python
from myproj import paths

with paths.new_run("042-docking-baseline", step="02_dock", label="vina-exh16",
                   inputs=[paths.DATA / "processed/kinase-actives/v2"]) as run:
    dock(..., out_dir=run.dir)
```

`inputs` lists the data versions and runs that the step reads: version
folders under `paths.DATA` and run folders under `paths.RESULTS`. Tracked
files need no entry, because the recorded commit pins them. `new_run()`
records the parameters: a copy of `config.yaml` and the command line.

## Names

| Item | Pattern | Example |
| --- | --- | --- |
| Experiment key | `<NNN>-<slug>`; a slug has 5 words or fewer | `042-docking-baseline` |
| Step | `NN_<name>`; an inserted step is `NN_M_<name>` | `02_1_rescore.py` |
| Run ID | `YYYYMMDD-HHMMSS[_<label>]`, local time | `20261020-143005_vina-exh16` |
| Raw version | The release, or the retrieval date | `v34`, `2026-10-20` |
| Processed version | `v1`, `v2`, ... | `v2` |
| Dataset card | `docs/data/` + the data path without the version + `.md` | `docs/data/raw/chembl/activities.md` |
| Module | `snake_case.py` | `docking_scores.py` |
| Script | `<verb>_<noun>.py` | `fetch_chembl.py` |
| Branch | `<type>-<issue>-<slug>`, plain issue number | `feat-43-vina-docking` |
| Cited figure copy | `figures/<run-id>_<name>.<ext>` | `20261020-143005_vina-exh16_enrichment.png` |

## Common cases

| Case | Location |
| --- | --- |
| Small hand-made input (1 MB or less) | `assets/`, or the experiment folder if only one experiment uses it. Tracked. |
| Large hand-made or lab file | `data/raw/lab/<dataset>/<date>/`, with a card that lists the manual steps |
| Downloaded model weights | `data/raw/<source>/<model>/<version>/` |
| Trained model, or another experiment's output | A run output. Put that run's folder in `inputs`. Use another experiment's run only after its PR has merged. |
| Figure for a README or a paper | Copy it from the cited run to `experiments/<key>/figures/` |
| Figure that combines experiments | Its own experiment, for example `057-paper-kinase-hits` |
| Cluster job | A job script `NN_<name>.sh` runs `NN_<name>.py`. It sends the scheduler's log to `logs/`; make that folder before you submit. Submit from the repository root, and keep the worktree until the job ends. |
| Agent planning notes | `.scratch/<issue>-<slug>/` (matt-automode) |
| Secrets | `.env`, not tracked. Never the store path. |

Rare cases: see [layout-notes.md](layout-notes.md).
