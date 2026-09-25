---
name: matt-automode
description: Run the Matt planning-to-merge workflow when the user delegates a task fully to the agent without human checkpoints.
---

# Matt Automode

Use for tasks the user trusts the agent to complete autonomously. The user's
request to use this mode delegates design decisions, issue publication,
implementation, PR creation, merge, issue closure, and repository cleanup within
the task scope.

## Resolve skills in Codex

The user's request to use this mode explicitly invokes every skill this file
names. Load and follow each one without a separate user invocation. Do not ask
the user to invoke them.

Resolve each skill by plugin and name. Do not hard-code installation paths or
versions.

- If the skill appears in the available skills list, open its `SKILL.md`.
- If it does not appear, it can be a user-invoked skill: its
  `agents/openai.yaml` sets `policy.allow_implicit_invocation: false`, so Codex
  omits it from the list. This policy stops Codex from choosing the skill on its
  own. It does not restrict an explicit invocation or reading the skill file.
  To find the plugin root, take the skill roots table entry of another skill
  from the same plugin. Keep its path up to the version directory
  (`plugins/cache/<marketplace>/<plugin>/<version>`). If no skill from the
  plugin is listed, confirm that `config.toml` in the Codex home (`CODEX_HOME`,
  default `~/.codex`) enables `<plugin>@<marketplace>`, then use its installed
  version under `plugins/cache/<marketplace>/<plugin>/`. Skills can be nested
  below the plugin root, so search it recursively for a `<skill>` directory
  that contains `SKILL.md`.
- Read each `SKILL.md` and every file it references, then follow it. Resolve
  each skill that it names in the same way.
- If no enabled plugin provides the skill, report the blocker and stop.

## Workflow

Before planning, use `dev-skills:step-workflow` to organize the working folder.
Treat this mode as a request for step-based organization. Apply the skill
throughout the task to planning files, scripts, outputs, tests, and documentation
where repository layout and naming conventions permit.

Replace the referenced skills' human interview and approval checkpoints with
agent decisions. Research facts, choose suitable answers, and record assumptions
and decisions in the planning artifacts. Continue between phases without asking
for input or approval.

1. `mattpocock-skills:grill-with-docs`: resolve the design questions and record
   the domain terms and decisions.
2. `mattpocock-skills:to-spec`: choose the testing seams and publish the spec.
3. `mattpocock-skills:to-tickets`: choose the ticket breakdown and publish it
   with blocking dependencies. Track the parent spec, all task tickets, and their
   PRs through completion. Preserve the parent during ticket publication.
4. `mattpocock-skills:implement`: complete every ticket in dependency order.
   Follow its testing and code-review workflow. Fix actionable findings, open
   PRs, and merge after required checks and review pass. Follow repository rules.
5. `dev-skills:repo-cleanup`: run after the implementation is merged. Pass the
   tracked tickets, parent spec, and merged PRs so cleanup can reconcile issue
   state and verify closure alongside Git cleanup.

## PR issue references

In each GitHub PR description, use a separate `Closes #123` reference for each
ticket the PR fully resolves. Use `Closes owner/repo#123` for another repository.
Use ordinary references for partial work. Closing keywords take effect when the
PR targets the default branch; carry them to the final integration PR for stacked
work. Follow the configured tracker's equivalent closure mechanism elsewhere.

Finish when all tickets are implemented, merged, and verified closed, any fully
satisfied parent spec is verified closed, and cleanup has reported its results.
Report issue and PR links, plus any issue left open and its remaining work.
If progress is blocked by missing access, an enforced restriction, or
repeated failures with no viable next step, report the blocker and retain the
work. This mode does not bypass tool permissions or repository protections.
