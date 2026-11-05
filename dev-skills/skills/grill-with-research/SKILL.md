---
name: grill-with-research
version: 1.0.0
description: Research the project, then grill the user only on decisions that research cannot settle; records glossary terms and ADRs. Use when the user asks to grill or stress-test a plan, design, or issue in the current project.
---

# Grill With Research

Research first, so that every question of Matt Pocock's `grill-with-docs`
interview needs the user's judgment. Invoking this skill includes the skills it
names. It starts no implementation or automode.

## Load the Matt skills

Invoke `mattpocock-skills:grill-with-docs` with the Skill tool and follow the
skills it loads. For a missing or user-invoked skill, resolve its path and read
its `SKILL.md`:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/resolve_skill.py" mattpocock-skills:grill-with-docs
```

Resolve nested skills the same way. Report a skill that cannot load as a
blocker; never use another workflow.

## Research

Before each round, research every fact it depends on. For local facts,
read the code, consumers, tests, docs, glossary, ADRs, and issue and PR
decisions, with one fresh sub-agent per independent question. For external
facts, only when local evidence cannot answer, use primary sources and trace
each claim. Current code alone does not prove intent, and research never sets
the user's preferences. Before the round, summarize the findings,
missing access, and inconclusive results.

Research may write and run scripts in the planning folder, or in one
`mktemp -d` folder removed by path. Keep each script that a finding cites. Research never edits tracked files, installs into the project
environment, or changes shared state (pushes, issues, messages). A
citable scientific result is an experiment run, not research.

## Planning folder

Use the repository's planning folder rule, or `.scratch/<issue>-<slug>/`
in the main checkout (`.scratch/<YYYYMMDD>-<slug>/` until an issue exists). If
Git does not ignore `.scratch/`, add it to `.git/info/exclude` and tell the
user. Nothing outside the folder links to it. Use `dev-skills:step-workflow`
prefixes: grilling is the next free step. `<step>_research.md` has one section
per question ID: finding, source, status (verified, assumed, or unresolved),
and cited files. Name scripts, outputs, and long notes `<step>_<n>_<name>`.
Never renumber a cited file.

## Question filter

Before each round, drop a question if the project or conversation
answers it, research can settle it, its answer cannot change the plan, or its
prerequisites, including pending research, are open. Drop duplicates, generic
checklists, and requests to approve authorized research. Settle routine,
reversible details by existing conventions and state each material assumption.

Ask the rest as `grilling` does, with the evidence, viable options, a
reasoned recommendation, and why the user's judgment is needed. After
each answer, research what changed and reopen affected decisions. Stop asking
when no meaningful unresolved decision remains.
