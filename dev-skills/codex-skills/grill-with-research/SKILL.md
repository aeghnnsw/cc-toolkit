---
name: grill-with-research
description: Research the project, then grill the user only on decisions that research cannot settle; records glossary terms and ADRs. Use when the user asks to grill or stress-test a plan, design, or issue in the current project.
---

# Grill With Research

Research first, so that each interview question needs the user's judgment.
Start no implementation. Start automode only when the task names it for
after the user approves the design.

## Load the Matt skills

Follow the `SKILL.md` of `mattpocock-skills:grilling` and
`mattpocock-skills:domain-modeling`. If the skill list omits one, resolve its
path. `<plugin-root>` is two levels above this folder:

```bash
python3 "<plugin-root>/scripts/resolve_skill.py" --host codex --model-invoked \
  mattpocock-skills:grilling mattpocock-skills:domain-modeling
```

In these cases, stop and report the blocker; use no other workflow:

- The resolver exits with status 3: a Matt skill is user-invoked.
- A Matt skill cannot load.

Otherwise, follow the resolved `SKILL.md`.

## Research

Before each round, research the facts its questions need. For local facts, read
the code, consumers, tests, docs, glossary, ADRs, and issue and PR decisions,
with one fresh sub-agent per independent question. When local evidence cannot
answer, trace each claim to external primary sources. Code or recency alone does
not prove intent; research never sets preferences. Then summarize findings,
pending research, missing access, and inconclusive results.

Research may run scripts in the planning folder, where cited scripts stay, or in
one `mktemp -d "${TMPDIR:-/tmp}/grill-with-research.XXXXXX"` folder removed by
path. Research never edits tracked files, installs into the project
environment, or changes shared state (pushes, issues, PRs, messages). A
citable scientific result needs a cited run.

## Planning folder

Use the repository's documented planning folder. Otherwise, run this command in
the checkout where the session started, without `--issue <issue>` until an
issue exists, then again:

```bash
python3 "<plugin-root>/scripts/planning_folder.py" <slug> --issue <issue>
```

It prints the folder and the next free `dev-skills:step-workflow` prefix, which
grilling takes. Tell the user when it changes `info/exclude`. Nothing outside
the folder links to it.
`<step>_research.md` has one section per question ID: finding, source, status
(verified, assumed, pending, or unresolved), and cited files. Name other files
`<step>_<n>_<name>`.

## Question filter

Before each round, drop a question that the project or conversation answers,
that research can settle, or that cannot change the plan. Drop duplicates,
generic checklists, and requests to approve research. Hold a question while its
prerequisites, including pending research, are open. Narrow a broad question to
what research leaves open. Settle routine, reversible details by convention;
state each material assumption.

Ask the rest as `grilling` does, with evidence, viable options, a reasoned
recommendation, and why the user must decide. Missing access does not hold a
question. After each answer, research what changed and reopen affected
decisions. If an answer accepts a recommendation without addressing its
condition, ask about the condition. Record each condition and each promised
follow-up issue with the decision. Open no issue during grilling. When no
meaningful unresolved decision remains, finish as `grilling` does.
