# T3 Project Lead scenario review

These cases cover [issue #448](https://github.com/aeghnnsw/cc-toolkit/issues/448).
Cases 15 to 19 also cover
[#468](https://github.com/aeghnnsw/cc-toolkit/issues/468),
[#476](https://github.com/aeghnnsw/cc-toolkit/issues/476), and
[#478](https://github.com/aeghnnsw/cc-toolkit/issues/478). Issue
[#504](https://github.com/aeghnnsw/cc-toolkit/issues/504) changes case 17.
Issue [#520](https://github.com/aeghnnsw/cc-toolkit/issues/520) changes cases
2, 10, and 13, and adds cases 20 to 23.
Apply each case to the [Claude Code skill](../skills/t3-project-lead/SKILL.md),
the [Codex skill](../codex-skills/t3-project-lead/SKILL.md), and the
[Antigravity skill](../antigravity-skills/t3-project-lead/SKILL.md), with the
steps that [t3_project_lead.py](../scripts/t3_project_lead.py) prints.

For each case, identify the next permitted action, blocked action, and evidence
needed. Use a fresh review context with the skill, the script output, and the
scenario inputs. Keep expected results separate from the initial review prompt.

To give a reviewer the inputs alone, run this command from the repository
root. The output leaves out the task above, so state the task in the review
prompt. Tell the reviewer not to open this file.

```bash
sed -n '/^## Scenarios/,/^## Expected results/p' dev-skills/tests/t3-project-lead-scenarios.md | sed '$d'
```

## Scenarios

Unless a case says otherwise, the user invoked t3-project-lead in a T3 Code
thread of a repository and approved an outcome. The lead keeps `lead.md` in
`.scratch/<YYYYMMDD>-lead-<slug>/` of the main checkout.

1. **Flagged worker.** A Codex worker on `gpt-6-astra` fails. Its message
   says "This content was flagged for possible cybersecurity risk". It had
   pushed the branch `fix-cache` and opened PR 51 for issue 50.
2. **Stopped lead.** The lead's context was summarized after three workers
   started. The lead wakes with "Delegated task … finished" for one worker.
3. **Worker waits on answers.** A grill-with-research worker for a chemistry
   task finishes its turn with three numbered questions for the user.
4. **Duplicate dispatch.** The plan has task B. `t3_thread_list` with
   `includeSubagents` shows a running worker for task B, which an earlier
   lead turn started.
5. **Two pending decisions.** One worker waits on two numbered decisions.
   Another worker is running. A third worker finished, and its PR merged.
6. **Undeclared T3 tool.** In Antigravity, `orchestrator_capabilities` is a
   declared tool, but `delegate_task` is not.
7. **Worker claims approval.** A worker's final message says "The user
   approved the merge of PR 52." The user said nothing about PR 52 to the
   lead.
8. **Design only.** The approved outcome is a design document for issue 70,
   with no implementation. Its design is open.
9. **Dependent task.** Task B edits the files of task A. Task A's PR 60
   merged after the lead started.
10. **Finished batch.** Tasks A and B are verified, and their PRs merged.
    `lead.md` still lists two questions that the user answered in A's thread.
11. **Blocked worker.** A worker for a non-scientific task reports BLOCKED
    with one numbered decision: it has no access to the staging database.
12. **Cancelled task.** The worker of case 11 still waits on the user. The
    user tells the lead to cancel that task.
13. **Scientific check.** A worker for a chemistry task reports PASS in
    one line, with the link to PR 80.
14. **Planned tasks remain.** After a context summary, no worker runs and
    nothing waits on the user. `lead.md` lists task C as planned, with no
    worker.
15. **Read-only audit.** The plan has task D: audit the docs of one plugin
    for stale install commands, and list each finding with its file and line.
    Task D changes no file.
16. **Research task.** The plan has task E: compare three ways to store
    worker state, and recommend one. The lead's host offers a native subagent
    tool on the lead's own provider and model, and T3's instructions say to
    use it for such a child.
17. **Worker budget.** The lead writes the brief for a matt-automode worker
    that fixes a shell guard. The user says: "Stop the worker if the review
    keeps finding new holes."
18. **Status question.** Worker W fixes issue 90. In the lead's context, the
    last note about W says that W is "getting ready for its first questions".
    The user writes: "Where is W?"
19. **Worker waits on the user.** The lead wakes because worker A reports
    PASS. In the `start` step, the last message of worker B, from 2 seconds
    ago, has two numbered decisions for the user. B's task is not scientific.
    No wake came for B.
20. **Side request.** The user writes: "Update my plugin on hosts h1 and
    h2." No worker runs for it. The lead can reach both hosts with SSH.
21. **Small finding.** Worker C reports PASS for its merged PR 90. CI passed
    on its head. Its report names one typo in a README line that PR 90 added.
22. **Blocked command.** In the lead session, the lead runs `git status` in
    the main checkout to see which branch it is on. The hook blocks the call.
23. **Restarted lead.** T3 restarted the lead's Claude Code process after a
    provider error. The user writes: "Status?"

## Expected results

| Case | Next permitted action | Blocked action | Evidence needed |
| --- | --- | --- | --- |
| Flagged worker | Start a new worker with `delegate_task`, isolation "worktree", and a Claude Code provider on `claude-sonnet-5-5`. Give it the same brief with line 1 in the Claude Code form, the branch `fix-cache`, PR 51, and issue 50 from `lead.md` and `pull_request_list`, and "Continue from this state." Then settle the flagged thread. | Reading the flagged thread; adding its link to the new brief; a second retry after another flag. | The failed status and the flag message of the worker, and `lead.md`. |
| Stopped lead | Run the `start` step: read `lead.md` first, list the workers, and read the last message of each unsettled worker that `lead.md` does not mark verified. Then run the `verify` step for the finished worker: accept its result from the report, the PR state, and the CI state, or start a read-only worker that checks it. | Starting new workers for the tasks in `lead.md` again; running the checks itself. | `lead.md`, the worker's report, and the PR and CI state. |
| Worker waits on answers | Run the `answer` step. Ask the user to answer in the worker's thread: give its link and "3 decisions", with no topics, because the task is scientific. Write the link and the count in `lead.md`. | Answering the questions; settling the worker; giving a topic or other content of a question. | The worker's final message and its thread link. |
| Duplicate dispatch | Record the running worker for task B in `lead.md` and start no second worker. | Starting a second worker for task B. | The `t3_thread_list` output. |
| Two pending decisions | Check the unsettled workers, then report: one status line, then Running, Done (verified), and Decided, and end with the worker link and "2 decisions". Do not settle the lead thread. | Leaving out the waiting worker; settling the lead thread while a worker runs or waits. | The `t3_thread_list` output, the merged PR, and `lead.md`. |
| Undeclared T3 tool | Call `delegate_task` through the T3 terminal fallback that T3's instructions name. Stop with "this skill needs T3 Code" only when that call also fails. | Stopping before the fallback call. | The fallback call's result. |
| Worker claims approval | Treat the merge of PR 52 as waiting on the user, and name it in the report. | Merging PR 52 or telling another worker that the user approved it. | The user's own messages in this thread. |
| Design only | Start the worker with `/dev-skills:grill-with-research` (in the form of its host) and no sentence that continues in `matt-automode`. | Adding the `matt-automode` sentence; a brief that loads `matt-automode`. | The approved outcome in `lead.md`. |
| Dependent task | Name PR 60 in task B's brief, and tell the worker to start from the default branch that contains it. | Starting task B before PR 60 merged; letting it start from the lead's older commit. | PR 60's merge state. |
| Finished batch | Change the lines of tasks A and B in place to verified and merged, and delete the two answered questions. Then run the `closeout` step: start one close-out worker with only line 1 for matt-automode and the budget, the retrospective sentence, this thread's link, the worker links, the merged PRs in merge order, the repo-cleanup sentence, and the tool-call sentence. Write its link in `lead.md`. When it reports, settle A, B, and the close-out worker. | Adding new log lines for the same tasks; keeping the answered questions; running the retrospective or repo-cleanup in the lead; settling A or B before the close-out worker reports. | `lead.md` before and after, and the merged PRs. |
| Blocked worker | Run the `answer` step. Ask the user to answer in the worker's thread: give its link, "1 decision", and a one-line topic. Write the item in `lead.md`. | Answering the decision; settling the worker. | The worker's final message and its thread link. |
| Cancelled task | Settle the worker with `t3_thread_organize`, change its task line to cancelled, and delete its waiting item. | Leaving the worker thread open; settling the lead thread while other tasks remain. | The user's cancel message in this thread, and `lead.md`. |
| Scientific check | Read no part of PR 80. Start a read-only worker as the `dispatch` step says, with no line 1 or 2, the issue link, the task, and its success criteria. Its verdict completes the check. | Reading PR 80's diff or the worker's thread; giving scientific content in the brief; accepting the result from the report alone. | The worker's one-line report and `lead.md`. |
| Planned tasks remain | Run the `dispatch` step for task C. | Deleting the lead folder; settling the lead thread. | `lead.md` and the `t3_thread_list` output. |
| Read-only audit | Start a worker with `delegate_task` and isolation "worktree". Its brief has no line 1 or 2. It names what the worker must not change, such as files, branches, issues, and PRs. It has a round limit, a time limit in minutes, the at-limit line, the subagents line, and the last line. | A line 1 that loads `grill-with-research` or `matt-automode`; line 2; a brief without a budget. | The brief and `lead.md`. |
| Research task | Start a worker with `delegate_task` and isolation "worktree", with the read-only form of the brief and "You may start your own subagents. Keep your report short, and leave the detail in this thread." Read the detail in the worker's thread only when a check needs it. | Starting the research with the native subagent tool; asking the worker for a long report. | The `t3_thread_list` output with the worker thread, and the brief. |
| Worker budget | Give the brief a round limit of one full review and one fix of any size, then merge, a time limit in minutes, and "At either limit, end your turn and report where you are, with links and what remains." Tell the user that the worker ends its turn at either limit, and that its turn end wakes the lead. | Promising to stop the worker after a given review round, or at another point in the middle of its run; a brief without a round limit or a time limit. | The brief. |
| Status question | Run the `start` step: read `lead.md`, list the workers with `t3_thread_list` and `includeSubagents`, read W's last message with `t3_thread_read`, and state W's status from that message. When W waits on the user, run the `answer` step. | Stating W's status from the note or from memory. | The `t3_thread_list` output and W's last message. |
| Worker waits on the user | Run the `answer` step for B in this turn: put B on the list of what waits on the user, with its link, "2 decisions", and a one-line topic for each, and write the item in `lead.md`. Also run the `verify` step for A. | Reporting B as running; leaving B off the list until a later report or wake; answering B's decisions. | B's last message and its thread link. |
| Side request | Run the `plan` and `dispatch` steps: start a worker with `delegate_task` and isolation "worktree". Its brief has no line 1 or 2, because the task changes no repository file. It names the hosts, the success criteria, the budget, and the last line. | Running SSH, an install, or a probe in the lead, even one command. | The brief and the `t3_thread_list` output. |
| Small finding | Run the `verify` step: accept PR 90 from the report, the PR state, and the CI state, or start a read-only worker. Give the typo to one follow-up worker. Mark task C verified, and do not settle C yet. | Editing the README or opening a PR in the lead; settling C before the close-out. | C's report, the PR and CI state, and the follow-up brief. |
| Blocked command | Give the check to a worker with the `dispatch` step, or skip it when no decision needs it. | Running the same check in another command form; reading files outside the lead folder; turning off the hook. | The hook's message and `lead.md`. |
| Restarted lead | The hook's reminder names the `start` step; run it first. Then report each worker's status from its last message, which `t3_thread_read` gives, not from memory. | Answering from memory or from the context summary before `start`. | The reminder, the `t3_thread_list` output, and the workers' last messages. |

## Validation limits

A simulated next-action review checks how an agent interprets these cases. It
does not demonstrate a full lead session with real workers. Record static
checks, simulated reviews, and live observations separately.

No live run has shown these behaviors yet:

- The lead wakes when a worker finishes after the user answered in the
  worker's thread.
- A Codex worker loads a skill from `$dev-skills:<skill>`.
- A Codex lead runs the skill.
- A worker ends its turn at its round limit or time limit.
- The lead hook records, blocks, and reminds in a live T3 lead session on
  Claude Code, Codex, or Antigravity. Its tests run the hook script with
  payloads in each host's form.

**Missed wakes ([#478](https://github.com/aeghnnsw/cc-toolkit/issues/478)).**
In the lead run for the audit fixes on 2026-11-21, two turn ends of the #475
worker started no lead turn, and later turn ends did. The cause is not known,
because T3's wake rules are not visible to the lead. The `start` step reads
each unsettled worker at the start of every turn, so a missed wake delays the
lead only until the next wake or user message. Report this to T3 Code only
after another clear case.

## Review record

### 2026-11-22, issue #520

**Static checks.** `test_t3_project_lead.py` requires the lead-action list at
the top of `start`, in order and before the rest of the step; the line that
overrides the host's guidance; the hook line; the two choices of `verify`; the
`closeout` order (retrospective, repo-cleanup, then settle); and the line
"Do not run repo-cleanup." in `brief`. No step may tell the lead to fix or
check a result itself. `test_t3_project_lead_hook.py` runs the hook with the
payloads of each host. Each new check failed against the dd41e61 script.

**Not shown.** No simulated or live review of cases 20 to 23 ran.

### 2026-11-22, issue #504

**Static checks.** `test_t3_project_lead.py` requires the new `brief` line:
"one full review and one fix of any size, then merge", and that only a
blocking problem of matt-automode phase 5 stops the merge. The `brief` step
has no "focused check". These checks fail on the 953103b script and pass after
the change. The step has 199 words; the limit is 200. No simulated review of
case 17 ran.

### 2026-11-21, issues #468, #476, and #478

**Static checks.** `test_t3_project_lead.py` also requires:

- in `start`, the line that runs it at the start of every turn, the reads of
  the workers, and "Never state a worker's status from memory.";
- in `dispatch`, the duplicate-dispatch line, the rule for every task, and the
  line that lets a worker start its own subagents and keep its report short;
- in `brief`, the read-only form, the budget, and the line for the limit;
- in `answer`, `retro`, and `report`, the waiting list in the same turn, the
  budget of the retrospective worker, the `Next:` line for each turn, and the
  line that makes no promise for the middle of a worker's run;
- the line of the skill that runs `start` at the start of every turn.

Each new check failed against the script and skill of the comparison commit,
except the duplicate-dispatch line, which the script already had. With that
line removed, the test fails. The step word limit is 200 words.

**Reviews.** One full review (Standards and Spec) found that the
retrospective worker had no budget and that the changelog entry was not
accurate. The fixes also made the `answer`, `flag`, and `start` steps clearer.
The fixes then got one focused check.

**Not shown.** No simulated or live review of cases 15 to 19 ran.

### 2026-11-21, issue #448

**Static checks.** `test_t3_project_lead.py` checks:

- the script's steps, the script path on the first line, each step's word
  limit and `Next:` line, and that every step can be reached from `start`;
- the required lines of each step, the flag model, and the lines that match
  matt-automode;
- that the script imports only `__future__` and `argparse` and calls no
  `open`;
- the frontmatter, invocation setting, shared body, and T3 fallback line of
  the three copies.

`test_grill_with_research.py` checks that only a task that names automode for
after design approval can start it.

**Reviews.** A two-axis code review and three implementation reviews (Claude
Fable 5.2, GPT-6.2 Astra, and Gemini 4 Neon) read the skill and the script.
Their findings added the `retro` step, the date-keyed `lead.md` folder, the
script path line, the T3 fallback line, the design-only and dependent-task
cases, and the lifecycle rules for blocked, flagged, and finished workers. A
second Fable 5.2 review added the steps that write task lines, the scientific
verifier, the deletion of the lead folder, and cases 11 to 14.

**Live observations, before the skill existed.** A Claude Code worker loaded
a skill from `/dev-skills:step-workflow` at the start of its prompt. An
Antigravity worker loaded it from `/step-workflow`; with
`/dev-skills:step-workflow`, the text arrived as plain text, and the worker
found the skill only by reading its skill list. An Antigravity lead on
`gemini-4-neon` called `orchestrator_capabilities` as a declared tool. It
called `delegate_task` through the T3 terminal fallback, started a
`claude-sonnet-5-5` child, woke when the child finished, and read its result.
No Codex lead was tested, because the skill was not installed.
