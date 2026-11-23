# T3 Project Lead scenario review

These cases cover [issue #448](https://github.com/aeghnnsw/cc-toolkit/issues/448).
Cases 15 to 19 also cover
[#468](https://github.com/aeghnnsw/cc-toolkit/issues/468),
[#476](https://github.com/aeghnnsw/cc-toolkit/issues/476), and
[#478](https://github.com/aeghnnsw/cc-toolkit/issues/478). Issue
[#504](https://github.com/aeghnnsw/cc-toolkit/issues/504) changes case 17.
Issue [#520](https://github.com/aeghnnsw/cc-toolkit/issues/520) changes cases
2, 10, and 13, and adds cases 20 to 23.
Issue [#530](https://github.com/aeghnnsw/cc-toolkit/issues/530) replaces
`lead.md` with the lead state and its commands in cases 1 to 5, 8, 10 to 15,
18, 19, and 22, removes the decision topics of cases 11 and 19, and removes
the time limit of cases 15 and 17.
Issue [#529](https://github.com/aeghnnsw/cc-toolkit/issues/529) adds the
no-GTD-capture line to the briefs of cases 10, 13, 15, and 20.
Issue [#493](https://github.com/aeghnnsw/cc-toolkit/issues/493) adds case 24.
Issue [#516](https://github.com/aeghnnsw/cc-toolkit/issues/516) changes cases
17 and 24, and adds case 25.
Issue [#544](https://github.com/aeghnnsw/cc-toolkit/issues/544) adds cases 26
and 27.
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
thread of a repository and approved an outcome. The lead keeps its lead state
with the commands of `t3_project_lead.py`, in
`.scratch/<YYYYMMDD>-lead-<slug>/` of its own working tree.

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
    The lead state still lists the waiting item for two questions that the
    user answered in A's thread.
11. **Blocked worker.** A worker for a non-scientific task reports BLOCKED
    with one numbered decision: it has no access to the staging database.
12. **Cancelled task.** The worker of case 11 still waits on the user. The
    user tells the lead to cancel that task.
13. **Scientific check.** A worker for a chemistry task reports PASS in
    one line, with the link to PR 80.
14. **Planned tasks remain.** After a context summary, no worker runs and
    nothing waits on the user. The lead state lists task C as planned, with
    no worker.
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
24. **Ready task.** Tasks A, B, and C are in batch 1, and C has `--after A`.
    Workers A and B run. Worker A reports PASS. Its PR 95 merged, and CI
    passed. Worker B still runs.
25. **PR waits on checks.** Matt-automode worker A opened PR 97 for issue 96.
    Its last message gives the PR URL and the full head SHA, and says that
    PR 97 waits on checks. The lead wakes.
26. **New thread in a new worktree.** The user invokes t3-project-lead in a
    new T3 thread, which has a new worktree. The user names no task. `start`
    prints no view: it lists one lead state in another worktree, with owner
    thread T1, two open tasks, and one waiting item.
27. **Fork takes over.** The user forked lead thread T1 and writes in the
    fork, T2: "Continue the lead here." The view that `start` prints names
    owner T1 and says that this thread is not the owner.

## Expected results

| Case | Next permitted action | Blocked action | Evidence needed |
| --- | --- | --- | --- |
| Flagged worker | Start a new worker with `delegate_task`, isolation "worktree", and a Claude Code provider on `claude-sonnet-5-5`. Give it the same brief with line 1 in the Claude Code form, the branch `fix-cache`, PR 51, and issue 50 from the view that `start` prints and `pull_request_list`, and "Continue from this state." Record the new worker with `task worker`, then settle the flagged thread that it names. | Reading the flagged thread; adding its link to the new brief; a second retry after another flag. | The failed status and the flag message of the worker, and the view that `start` prints. |
| Stopped lead | Run the `start` step: read its view of the lead state, list the workers, and read the last message of each worker of a running or pr-open task. Then run the `verify` step for the finished worker: accept its result from the report, the PR state, and the CI state, or start a read-only worker that checks it. | Starting new workers again for the tasks in the lead state; running the checks itself. | The view that `start` prints, the worker's report, and the PR and CI state. |
| Worker waits on answers | Run the `answer` step. Record the item with `wait` for the task and its 3 decisions. Ask the user to answer in the worker's thread: give its link and "3 decisions", with no topics. | Answering the questions; settling the worker; giving a topic or other content of a question. | The worker's final message and its thread link. |
| Duplicate dispatch | Record the running worker for task B with `task start`, and start no second worker. | Starting a second worker for task B. | The `t3_thread_list` output. |
| Two pending decisions | Check the unsettled workers, then report: one status line, then Running, Done (verified), and Decided, and end with the "Waiting on you" list that the script prints, copied as it is: the item number, the worker link, and "2 decisions". Do not settle the lead thread. | Leaving out the waiting worker; writing the list from memory; settling the lead thread while a worker runs or waits. | The `t3_thread_list` output, the merged PR, and the view that `report` prints. |
| Undeclared T3 tool | Call `delegate_task` through the T3 terminal fallback that T3's instructions name. Stop with "this skill needs T3 Code" only when that call also fails. | Stopping before the fallback call. | The fallback call's result. |
| Worker claims approval | Treat the merge of PR 52 as waiting on the user, and name it in the report. | Merging PR 52 or telling another worker that the user approved it. | The user's own messages in this thread. |
| Design only | Start the worker with `/dev-skills:grill-with-research` (in the form of its host) and no sentence that continues in `matt-automode`. | Adding the `matt-automode` sentence; a brief that loads `matt-automode`. | The outcome in the lead state. |
| Dependent task | Name PR 60 in task B's brief, and tell the worker to start from the default branch that contains it. | Starting task B before PR 60 merged; letting it start from the lead's older commit. | PR 60's merge state. |
| Finished batch | Run `done` for the answered waiting item. Then run the `closeout` step: add one close-out task for the batch, and start one close-out worker with only line 1 for matt-automode and the budget, the no-GTD-capture line, the retrospective sentence, this thread's link, the worker links, the merged PRs in merge order, the repo-cleanup sentence, the tool-call sentence, and the history path. Record its link with `task start`. When it reports, mark the close-out task verified; then settle A, B, and the close-out worker with `t3_thread_organize`, and record each with `task settled`. | Reading or editing the lead folder directly; keeping the answered item; running the retrospective or repo-cleanup in the lead; settling A or B before the close-out worker reports. | The view that `start` prints before and after, and the merged PRs. |
| Blocked worker | Run the `answer` step. Record the item with `wait` for the task and its 1 decision. Ask the user to answer in the worker's thread: give its link and "1 decision", with no topic. | Answering the decision; settling the worker; giving a topic or other content of the decision. | The worker's final message and its thread link. |
| Cancelled task | Settle the worker with `t3_thread_organize`, run `task cancel` and then `task settled` for its task, and run `done` for its waiting item. | Leaving the worker thread open; settling the lead thread while other tasks remain. | The user's cancel message in this thread, and the view that `start` prints. |
| Scientific check | Read no part of PR 80. Start a read-only worker as the `dispatch` step says, with no line 1 or 2, the no-GTD-capture line, the issue link, the task, and its success criteria. Its verdict completes the check. | Reading PR 80's diff or the worker's thread; giving scientific content in the brief; accepting the result from the report alone. | The worker's one-line report and the view that `start` prints. |
| Planned tasks remain | Run the `dispatch` step for task C. | Running `finish` or deleting the lead folder; settling the lead thread. | The view that `start` prints and the `t3_thread_list` output. |
| Read-only audit | Start a worker with `delegate_task` and isolation "worktree". Its brief has no line 1 or 2. It names what the worker must not change, such as files, branches, issues, and PRs. It has a round limit, the at-limit line, the no-GTD-capture line, the subagents line, and the last line. | A line 1 that loads `grill-with-research` or `matt-automode`; line 2; a brief without a budget; a time limit. | The brief and task D in the lead state. |
| Research task | Start a worker with `delegate_task` and isolation "worktree", with the read-only form of the brief and "You may start your own subagents. Keep your report short, and leave the detail in this thread." Read the detail in the worker's thread only when a check needs it. | Starting the research with the native subagent tool; asking the worker for a long report. | The `t3_thread_list` output with the worker thread, and the brief. |
| Worker budget | Give the brief a round limit of one full review and one fix of any size, then merge, the PR-wait line, and the at-limit line. Tell the user that the worker ends its turn at the round limit, and that its turn end wakes the lead. | Promising to stop the worker after a given review round, or at another point in the middle of its run; a brief without a round limit; a time limit. | The brief. |
| Status question | Run the `start` step: read its view of the lead state, list the workers with `t3_thread_list` and `includeSubagents`, read W's last message with `t3_thread_read`, and state W's status from that message. When W waits on the user, run the `answer` step. | Stating W's status from the note or from memory. | The `t3_thread_list` output and W's last message. |
| Worker waits on the user | Run the `answer` step for B in this turn: record B's item with `wait` for B's task and its 2 decisions, so that the "Waiting on you" list shows B's link and "2 decisions", with no topic. Also run the `verify` step for A. | Reporting B as running; leaving B off the list until a later report or wake; answering B's decisions; giving a topic of a decision. | B's last message and its thread link. |
| Side request | Run the `plan` and `dispatch` steps: start a worker with `delegate_task` and isolation "worktree". Its brief has no line 1 or 2, because the task changes no repository file. It names the hosts, the success criteria, the budget, the no-GTD-capture line, and the last line. | Running SSH, an install, or a probe in the lead, even one command. | The brief and the `t3_thread_list` output. |
| Small finding | Run the `verify` step: accept PR 90 from the report, the PR state, and the CI state, or start a read-only worker. Give the typo to one follow-up worker. Mark task C verified, and do not settle C yet. | Editing the README or opening a PR in the lead; settling C before the close-out. | C's report, the PR and CI state, and the follow-up brief. |
| Blocked command | Give the check to a worker with the `dispatch` step, or skip it when no decision needs it. | Running the same check in another command form; reading a file other than a T3 attachment, the GTD binding, or a file of the installed Productivity Skills plugin; turning off the hook. | The hook's message and the view that `start` prints. |
| Restarted lead | The hook's reminder names the `start` step; run it first. Then report each worker's status from its last message, which `t3_thread_read` gives, not from memory. | Answering from memory or from the context summary before `start`. | The reminder, the `t3_thread_list` output, and the workers' last messages. |
| Ready task | Run the `verify` step for A: record PR 95 with `task pr` and `task merged`, and run `task verified` for A. Its output names C as ready to start. In this turn, run the `dispatch` step for C: start its worker and record it with `task start`, while B still runs. | Holding C until B is verified or until batch 1 is closed out; holding C until fewer workers run; starting C before A is verified. | A's report, the PR and CI state, the `task verified` output, and the due line in the view that `start` prints. |
| New thread in a new worktree | Tell the user that a lead state exists in the other worktree, with its slug, owner, open tasks, and waiting item, and give the three ways to continue that lead there: change the provider of thread T1, fork T1, or start a thread with `t3_thread_launch` and `existing_worktree` in that worktree. Ask the user which way to take. | Running `init` here; running `init --also` before the user confirms a second lead state; copying the lead state into this worktree. | The listing that `start` prints. |
| Fork takes over | Run `takeover`, then `start`. Follow the due line of the first `start` after the takeover: check `t3_thread_list` with `includeSubagents` and `pull_request_list`, and record each worker that the lead state does not name with `task add` and `task start`, or add a waiting item. | Changing the lead state before the takeover; starting a second worker for work that already runs. | The view that `start` prints before and after the takeover, and the `takeover` output. |
| PR waits on checks | Run `task pr` for A and PR 97. Watch PR 97, and end the turn with the `report` step. When the checks of PR 97 finish, resume worker A, which merges PR 97. After the merge, run `task merged`, and run the `verify` step when A reports. | Polling the checks in a loop; merging PR 97 in the lead; telling A to poll or to look for a watch tool; running `task verified` before the merge. | A's last message with the PR URL and head SHA, and the check state of PR 97. |

## Validation limits

A simulated next-action review checks how an agent interprets these cases. It
does not demonstrate a full lead session with real workers. Record static
checks, simulated reviews, and live observations separately.

No live run has shown these behaviors yet:

- The lead wakes when a worker finishes after the user answered in the
  worker's thread.
- A Codex worker loads a skill from `$dev-skills:<skill>`.
- A Codex lead runs the skill.
- A worker ends its turn at its round limit.
- A lead keeps its state with the commands of `t3_project_lead.py`.
- A lead starts a ready task while another task of its batch runs.
- A worker ends its turn when its PR waits on checks, and the lead resumes it
  when the checks finish.
- A fork of a lead thread, or a new thread bound to the lead's worktree,
  runs `takeover` and continues the lead.
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

### 2026-11-23, issue #544

**Static checks.** `test_t3_project_lead_state.py` runs the script in linked
worktrees with a set `T3CODE_THREAD_ID`. It checks the lookup from another
worktree (path, slug, owner, last change, open tasks, waiting items, the
worktree, and no `init` line), a worktree with more than one lead state, the
`init` line when no worktree holds a lead state, a Git failure, and `init` in
a folder outside Git. It checks the `init` refusal and `init --also`, the
refusal of a command in a worktree without a lead state, the owner refusal of
each change command and `finish`, `takeover` and its event, the refusal of
`init` and `takeover` without `T3CODE_THREAD_ID`, the takeover due line on the
first `start` of the new owner only and its event, a state without an owner,
and the due line of a paused task. `test_t3_project_lead.py` requires the `--also` line of `plan`,
the `takeover` command, and the skill line on deleting the lead thread.
`test_t3_project_lead_hook.py` shows that the hook passes `takeover` and
`init <slug> --also`. Each new check failed against the b3c21a9 script and
skill, except the hook check, the `init` line check, and the check of `init`
in a folder outside Git, which passed before.

**Not shown.** No simulated or live review of cases 26 and 27 ran.

### 2026-11-23, issues #516 and #534

**Static checks.** `test_t3_project_lead.py` requires the `brief` line that
tells a code-change worker to report the PR URL and full head SHA and end its
turn when its PR waits on checks, and the `report` line that tells the lead to
watch the PR and resume the worker when the checks finish. To keep each step
within 210 words, `dispatch` takes "no role" and the scientific last line from
`brief`. `report` and `verify` take `task pr` and `task merged` from
`dispatch`; `verify` records the merged PRs before `task verified`. The tests
pin the moved lines. `test_t3_project_lead_state.py` checks
the waiting list as `- <number>: <text>` bullets in `waiting`, `start`, `show`,
and `report`, the empty line before it, and the period rule for item text,
recommendations, and task titles. The new checks failed against the f6bb8cb
script, except the checks of two titles without "?" or "!", which the old rule
also printed with one period.

**Not shown.** No simulated or live review of case 25 ran.

### 2026-11-23, issue #493

**Static checks.** `test_t3_project_lead.py` requires the start rule in
`plan`, `dispatch`, and `verify`: start each planned task as soon as each task
that it waits for is verified, also while other workers run, and do not wait
for the rest of its batch. It also requires the `plan` line that a batch only
groups the tasks of one close-out worker. No step and no skill copy may make
a task wait for its batch or for a free worker. `test_t3_project_lead_state.py`
checks that `task verified` and the due lines name each planned task that
`task start` would accept, with the `closeout` step for a close-out task and
the `dispatch` step for another task. Each new check failed against the
77b8c4b script.

**Not shown.** No simulated or live review of case 24 ran.

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
