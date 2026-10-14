---
name: matt-automode
version: 1.3.0
description: This skill should be used when the user asks to "run matt automode", "use matt-automode", "run the Matt workflow without checkpoints", "take this from design to merge autonomously", or delegates a task fully to the agent for design decisions, issue publication, implementation, code review, a navigation retrospective, PR merge, issue closure, and repository cleanup with no human approval steps. Requires Matt Pocock's engineering skills plugin.
---

# Matt Automode

Use for tasks the user trusts the agent to complete autonomously. The user's
request to use this mode delegates design decisions, issue publication,
implementation, code review, a navigation retrospective, PR creation, merge,
issue closure, and repository cleanup within the task scope.

## Resolve skills in Claude Code

The user's request to use this mode explicitly invokes every skill this file
names. Load and follow each one without a separate user invocation. Do not ask
the user to invoke them.

- If a skill appears in the available skills list, invoke it with the Skill
  tool.
- Resolve every other skill this file names with one command. These are
  user-invoked skills: their frontmatter sets
  `disable-model-invocation: true`, so the Skill tool cannot load them. For
  example:

  ```bash
  python3 "${CLAUDE_PLUGIN_ROOT}/scripts/resolve_skill.py" \
    mattpocock-skills:grill-with-docs mattpocock-skills:to-spec \
    mattpocock-skills:to-tickets mattpocock-skills:implement \
    mattpocock-skills:retro
  ```

  Each output line gives a skill name and the path of its `SKILL.md`. Read
  each `SKILL.md` and every file it references, then follow it. When it
  names another user-invoked skill, resolve that skill with the same
  command. When it says to call the Skill tool for another skill, do so.
- If the command reports an error for a skill, its message names the
  cause: the registry is missing, or the plugin is not installed, is
  disabled, or does not contain the skill. Report the cause as a blocker and
  stop.
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

Run steps 4–7 for each ticket in dependency order. Run cleanup after all tickets
are merged.

1. `mattpocock-skills:grill-with-docs`: resolve the design questions and record
   the domain terms and decisions.
2. `mattpocock-skills:to-spec`: choose the testing seams and publish the spec.
3. `mattpocock-skills:to-tickets`: choose the ticket breakdown and publish it
   with blocking dependencies. Track the parent spec, all task tickets, and their
   PRs through completion. Preserve the parent during ticket publication.
4. `mattpocock-skills:implement`: complete the next ready ticket. Follow its
   testing workflow and commit the changes for review.
5. `mattpocock-skills:code-review`: review the changes against a fixed comparison
   commit and the ticket spec. This phase fulfills `implement`'s code-review
   requirement. Fix actionable Standards and Spec findings before continuing.
6. `mattpocock-skills:retro`: run after code review, including successful
   implementations. Use this prompt:

   > use retro skill read previous implementation sessions and find ways to make my repo easier to navigate. Find where agents take too long to find relevant information, or rely on out-of-date docs.
   > Improving navigability is such an underrated way to save tokens and update docs.

   Select this repository's implementation sessions, including worktrees, by
   recorded workspace or repository metadata before searching their text. Use
   task prompts and actions to judge relevance. Report the sessions read,
   navigation findings, and any unavailable history. If previous sessions are
   unavailable, report that limit and review the current implementation session.
   Apply in-scope navigation and documentation fixes, run affected checks, and
   commit those edits. Run `code-review` again and verify that its diff includes
   those edits before the PR phase. Report other candidates as follow-up work.
7. `mattpocock-skills:pr`: write the PR body and open the PR for the reviewed
   changes. Merge after required checks and review pass. Follow repository rules.
8. `dev-skills:repo-cleanup`: run after all tickets are merged. Pass the
   tracked tickets, parent spec, and merged PRs so cleanup can reconcile issue
   state and verify closure alongside Git cleanup.

## PR issue references

In each GitHub PR description, use a separate `Closes #123` reference for each
ticket the PR fully resolves. Use `Closes owner/repo#123` for another repository.
Use ordinary references for partial work. Closing keywords take effect when the
PR targets the default branch; carry them to the final integration PR for stacked
work. Follow the configured tracker's equivalent closure mechanism elsewhere.

## Finish

Finish when all tickets have completed implementation, code review, retro, and
PR merge, all tickets and any fully satisfied parent spec are verified
closed, and cleanup has reported its results. Report review results, retro
findings and session-history limits, issue and PR links, and any issue left open
with its remaining work.
If progress is blocked by missing access, an enforced restriction, or
repeated failures with no viable next step, report the blocker and retain the
work. This mode does not bypass tool permissions or repository protections.
