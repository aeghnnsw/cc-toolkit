---
name: matt-automode
version: 1.0.0
description: This skill should be used when the user asks to "run matt automode", "use matt-automode", "run the Matt workflow without checkpoints", "take this from design to merge autonomously", or delegates a task fully to the agent for design decisions, issue publication, implementation, PR merge, issue closure, and repository cleanup with no human approval steps. Requires Matt Pocock's engineering skills plugin.
disable-model-invocation: true
---

# Matt Automode

Use for tasks the user trusts the agent to complete autonomously. The user's
request to use this mode delegates design decisions, issue publication,
implementation, PR creation, merge, issue closure, and repository cleanup within
the task scope.

## Resolve skills in Claude Code

Resolve each skill below by plugin and name. Do not hard-code installation
paths or versions.

- If the skill appears in the available skills list, invoke it with the Skill
  tool.
- If it does not appear, confirm the owning plugin is installed and enabled
  with `claude plugin list`. If it is not, report the blocker and stop.
- If the plugin is installed, the skill is a user-invoked skill: its
  frontmatter sets `disable-model-invocation: true`, so the Skill tool cannot
  load it. Resolve the plugin root from the Claude Code plugin registry. The
  registry is `plugins/installed_plugins.json` under the Claude configuration
  directory (`~/.claude` unless `CLAUDE_CONFIG_DIR` is set). Under its
  `plugins` key, match the entry whose key starts with `<plugin>@`; the suffix
  is the marketplace name. The entry lists one record per install scope, and
  each record's `installPath` is the plugin root. Under that root, the
  `.claude-plugin/plugin.json` `skills` list names the skill directories;
  when the list is absent, search the root for `<skill>/SKILL.md`. Read the
  skill's `SKILL.md` and every file it references, then follow it. When it says
  to call the Skill tool for another skill, do so.
- If a referenced skill stops because the repository lacks issue tracker or
  triage configuration and tells the user to run `/setup-matt-pocock-skills`,
  treat the missing configuration as a blocker: report it and stop.

## Organize the work

Before planning, use `dev-skills:step-workflow` to organize the working folder.
Treat this mode as a request for step-based organization. Apply the skill
throughout the task to planning files, scripts, outputs, tests, and documentation
where repository layout and naming conventions permit. Track the numbered steps
with the session task list.

## Replace human checkpoints

Replace the referenced skills' interview and approval checkpoints with agent
decisions. Do not call `AskUserQuestion`, and do not end the turn to wait for
input. When the grilling skill poses a round of numbered questions, answer each
one with the answer it recommends. Treat "check with the user", "quiz the
user", "confirm the seams", and "ask for the fixed point" as decisions to make. Research facts, choose suitable
answers, and record assumptions and decisions in the numbered planning files.
Continue between phases without asking for input or approval. Use sub-agents
where a referenced skill calls for them; keep orchestration in this session.

## Phases

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

## Finish

Finish when all tickets are implemented, merged, and verified closed, any fully
satisfied parent spec is verified closed, and cleanup has reported its results.
Report issue and PR links, plus any issue left open and its remaining work.
If progress is blocked by missing access, an enforced restriction, or
repeated failures with no viable next step, report the blocker and retain the
work. This mode does not bypass tool permissions or repository protections.
