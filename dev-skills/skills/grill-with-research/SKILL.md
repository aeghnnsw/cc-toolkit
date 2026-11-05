---
name: grill-with-research
version: 1.0.0
description: Research the project, then grill the user only on decisions that research cannot settle; records glossary terms and ADRs. Use when the user asks to grill or stress-test a plan, design, or issue in the current project.
---

# Grill With Research

Research first, so that each `grill-with-docs` question needs the user's
judgment. Start no implementation or automode.

## Load the Matt skills

Invoke `mattpocock-skills:grill-with-docs` with the Skill tool, then each skill
it names as `mattpocock-skills:<name>`. If the Skill tool refuses a user-invoked
skill and the user named this skill or a workflow that uses it, resolve and
read its `SKILL.md`:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/resolve_skill.py" mattpocock-skills:grill-with-docs
```

Otherwise, or if a skill cannot load, stop and report the blocker; use no
other workflow.

## Research

Before each round, research the facts its questions need. For local facts, read
the code, consumers, tests, docs, glossary, ADRs, and issue and PR decisions,
with one fresh sub-agent per independent question. When local evidence cannot
answer, use external primary sources and trace each claim. Code alone does not
prove intent, and research never sets preferences. Then summarize findings,
pending research, missing access, and inconclusive results.

Research may run scripts in the planning folder, where cited scripts stay, or in
one `mktemp -d` folder removed by path. Research never edits tracked files,
installs into the project environment, or changes shared state (pushes, issues,
messages). A citable scientific result is an experiment run.

## Planning folder

Use the repository's planning folder, or `.scratch/<issue>-<slug>/` in the main
checkout. Until an issue exists, use `.scratch/<YYYYMMDD>-<slug>/`, then rename
it. If Git does not ignore `.scratch/`, add it to `.git/info/exclude` and tell
the user. Nothing outside the folder links to it. Use `dev-skills:step-workflow`
prefixes: grilling is the next free step. `<step>_research.md` has one section
per question ID: finding, source, status (verified, assumed, pending, or
unresolved), and cited files. Name other files `<step>_<n>_<name>`. Never
renumber a cited file.

## Question filter

Before each round, drop a question that the project or conversation answers,
that research can settle, or that cannot change the plan. Drop duplicates,
generic checklists, and requests to approve authorized research. Hold a question
while its prerequisites, including pending research, are open. Narrow a broad
question to what research leaves open. Settle routine, reversible details by
convention and state each material assumption.

Ask the rest as `grilling` does, with evidence, viable options, a reasoned
recommendation, and why the user's judgment is needed. Missing access does not
hold a question. After each answer, research what changed and reopen affected
decisions. When no meaningful unresolved decision remains, finish as `grilling`
does.
