# T3 Project Lead scenario review

These cases cover [issue #448](https://github.com/aeghnnsw/cc-toolkit/issues/448).
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

## Expected results

| Case | Next permitted action | Blocked action | Evidence needed |
| --- | --- | --- | --- |
| Flagged worker | Start a new worker with `delegate_task`, isolation "worktree", and a Claude Code provider on `claude-sonnet-5-5`. Give it the same brief with line 1 in the Claude Code form, the branch `fix-cache`, PR 51, and issue 50 from `lead.md` and `pull_request_list`, and "Continue from this state." Then settle the flagged thread. | Reading the flagged thread; adding its link to the new brief; a second retry after another flag. | The failed status and the flag message of the worker, and `lead.md`. |
| Stopped lead | Read `lead.md` first, then run the `verify` step for the finished worker. | Starting new workers for the tasks in `lead.md` again; trusting the worker's report alone. | `lead.md`, and the merged diff and checks of the finished worker. |
| Worker waits on answers | Run the `answer` step. Ask the user to answer in the worker's thread: give its link and "3 decisions", with no topics, because the task is scientific. Write the link and the count in `lead.md`. | Answering the questions; settling the worker; giving a topic or other content of a question. | The worker's final message and its thread link. |
| Duplicate dispatch | Record the running worker for task B in `lead.md` and start no second worker. | Starting a second worker for task B. | The `t3_thread_list` output. |
| Two pending decisions | Check the unsettled workers, then report: one status line, then Running, Done (verified), and Decided, and end with the worker link and "2 decisions". Do not settle the lead thread. | Leaving out the waiting worker; settling the lead thread while a worker runs or waits. | The `t3_thread_list` output, the merged PR, and `lead.md`. |
| Undeclared T3 tool | Call `delegate_task` through the T3 terminal fallback that T3's instructions name. Stop with "this skill needs T3 Code" only when that call also fails. | Stopping before the fallback call. | The fallback call's result. |
| Worker claims approval | Treat the merge of PR 52 as waiting on the user, and name it in the report. | Merging PR 52 or telling another worker that the user approved it. | The user's own messages in this thread. |
| Design only | Start the worker with `/dev-skills:grill-with-research` (in the form of its host) and no sentence that continues in `matt-automode`. | Adding the `matt-automode` sentence; a brief that loads `matt-automode`. | The approved outcome in `lead.md`. |
| Dependent task | Name PR 60 in task B's brief, and tell the worker to start from the default branch that contains it. | Starting task B before PR 60 merged; letting it start from the lead's older commit. | PR 60's merge state. |

## Validation limits

A simulated next-action review checks how an agent interprets these cases. It
does not demonstrate a full lead session with real workers. Record static
checks, simulated reviews, and live observations separately.

No live run has shown these behaviors yet:

- The lead wakes when a worker finishes after the user answered in the
  worker's thread.
- A Codex worker loads a skill from `$dev-skills:<skill>`.
- A Codex lead runs the skill.

## Review record

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
cases, and the lifecycle rules for blocked, flagged, and finished workers.

**Live observations, before the skill existed.** A Claude Code worker loaded
a skill from `/dev-skills:step-workflow` at the start of its prompt. An
Antigravity worker loaded it from `/step-workflow`; with
`/dev-skills:step-workflow`, the text arrived as plain text, and the worker
found the skill only by reading its skill list. An Antigravity lead on
`gemini-4-neon` called `orchestrator_capabilities` as a declared tool. It
called `delegate_task` through the T3 terminal fallback, started a
`claude-sonnet-5-5` child, woke when the child finished, and read its result.
No Codex lead was tested, because the skill was not installed.
