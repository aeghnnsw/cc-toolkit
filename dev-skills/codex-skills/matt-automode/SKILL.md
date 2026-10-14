---
name: matt-automode
description: Run the Matt planning-to-merge workflow with explicit code review and a navigation retrospective when the user delegates a task fully to the agent without human checkpoints.
---

# Matt Automode

Use for tasks the user trusts the agent to complete autonomously. The user's
request to use this mode delegates design decisions, issue publication,
implementation, code review, a navigation retrospective, PR creation, merge,
issue closure, and repository cleanup within the task scope.

## Resolve skills in Codex

The user's request to use this mode explicitly invokes every skill this file
names. Load and follow each one without a separate user invocation. Do not ask
the user to invoke them.

- If a skill appears in the available skills list, open its `SKILL.md`.
- Resolve every other skill this file names with one command. These can be
  user-invoked skills: their `agents/openai.yaml` sets
  `policy.allow_implicit_invocation: false`, so Codex omits them from the
  list. This policy does not restrict an explicit invocation or reading the
  skill file. `<plugin-root>` is the root of this `dev-skills` plugin, two
  levels above this skill folder. For example:

  ```bash
  python3 "<plugin-root>/scripts/resolve_skill.py" --host codex \
    mattpocock-skills:grill-with-docs mattpocock-skills:to-spec \
    mattpocock-skills:to-tickets mattpocock-skills:implement \
    mattpocock-skills:retro
  ```

  Each output line gives a skill name and the path of its `SKILL.md`. Read
  each `SKILL.md` and every file it references, then follow it. Resolve each
  skill that it names in the same way.
- If the command reports an error for a skill, its message names the
  cause: the Codex config is missing, or the plugin is not enabled, is not
  installed, or does not contain the skill. Report the cause as a blocker
  and stop.

## Workflow

Before planning, use `dev-skills:step-workflow` to organize the working folder.
Treat this mode as a request for step-based organization. Apply the skill
throughout the task to planning files, scripts, outputs, tests, and documentation
where repository layout and naming conventions permit.

Replace the referenced skills' human interview and approval checkpoints with
agent decisions. Research facts, choose suitable answers, and record assumptions
and decisions in the planning artifacts. Continue between phases without asking
for input or approval.

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

Finish when all tickets have completed implementation, code review, retro, and
PR merge, all tickets and any fully satisfied parent spec are verified
closed, and cleanup has reported its results. Report review results, retro
findings and session-history limits, issue and PR links, and any issue left open
with its remaining work.
If progress is blocked by missing access, an enforced restriction, or
repeated failures with no viable next step, report the blocker and retain the
work. This mode does not bypass tool permissions or repository protections.
