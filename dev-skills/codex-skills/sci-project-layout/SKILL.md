---
name: sci-project-layout
description: This skill should be used when the user asks to set up or adopt the layout of a scientific Python research project, such as a computational chemistry or drug discovery project, or asks where datasets, experiment runs, results, or scratch files go in such a project.
---

# Scientific Project Layout

Give code, data, experiments, and results one place each in a Python
research project. The layout is one page,
[templates/layout.md](templates/layout.md). Its reasons and rare cases are
in [templates/layout-notes.md](templates/layout-notes.md). The Set up mode
copies both into the project, so the project keeps its layout without this
skill.

This skill ships no script to run. Copy the templates and edit files
yourself.

Choose the mode from the request:

- **Set up**: a project with no layout yet.
- **Adopt**: a project that already has its own layout.
- **Place**: a question about where a file goes.

In every mode, leave the files that other workflows own where they are:
`GLOSSARY.md`, `GLOSSARY-MAP.md`, `CODING_STANDARDS.md`, `docs/adr/`,
`docs/pressure-test/`, and every file in `docs/agents/` except
`layout.md`, `layout-notes.md`, and `experiment-README.md`.

## Set up

1. Stop if the project's issues are not on GitHub. Experiment keys are
   issue numbers, and citation gets a run's commit back from a GitHub pull
   request.
2. Copy the templates. Never overwrite a file; report each file that
   already exists.
   - [templates/layout.md](templates/layout.md) to `docs/agents/layout.md`
   - [templates/layout-notes.md](templates/layout-notes.md) to
     `docs/agents/layout-notes.md`
   - [templates/experiment-README.md](templates/experiment-README.md) to
     `docs/agents/experiment-README.md`
   - [templates/paths.py](templates/paths.py) to `src/<package>/paths.py`
   - [templates/gitignore](templates/gitignore) to `.gitignore`, if the
     project has no `.gitignore`
3. If `.gitignore` exists, add the template lines that it does not have.
4. In `pyproject.toml`, add `testpaths = ["tests"]` under
   `[tool.pytest.ini_options]`. If the file has no `[build-system]` table,
   ask the user before you add one. Without it, `uv run` does not install
   the package, and the steps cannot import `paths`.
5. In the copied files, replace `myproj` with the package name, and
   `MYPROJ` with the package name in capitals.
6. Add one line to the project's agent instructions file, `CLAUDE.md` or
   `AGENTS.md` (when one links to the other, edit the target): "Before you
   add a file, read `docs/agents/layout.md`."
7. Print the store path with
   `uv run python -c "from <package> import paths; print(paths.STORE)"`.
   Make `<store>/data` and `<store>/results`. Then ask the user before you
   add these two absolute paths to the sandbox write allow-list, in an
   untracked file: `sandbox.filesystem.allowWrite` in
   `.claude/settings.local.json` for Claude Code, and
   `sandbox_workspace_write.writable_roots` in `~/.codex/config.toml` for
   Codex. Never add the store root: by default it is the main checkout.

Report the files that you added, the files that you skipped, and the store
path.

## Adopt

1. Read the project's tree, README, agent instructions file, `.gitignore`,
   and `pyproject.toml`.
2. Compare them with [templates/layout.md](templates/layout.md). Report
   each difference: folders, data and results inside the repository, paths
   written in code, and names.
3. Write a migration plan: each move, each new file, and each code path to
   change to `paths.DATA` or `paths.RESULTS`.
4. Move no file until the user approves the plan. Then do the Set up
   mode, and then the moves.

## Place

1. Read the project's `docs/agents/layout.md`. If it does not answer the
   question, read the section of `docs/agents/layout-notes.md` for the
   situation.
2. Answer with the path and the rule that sets it.
3. If the project has no `docs/agents/layout.md`, answer from
   [templates/layout.md](templates/layout.md), and say that the project
   has not set up the layout.
