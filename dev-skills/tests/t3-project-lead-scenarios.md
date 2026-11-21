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
thread of a repository, approved an outcome, and the lead keeps `lead.md` in
the planning folder.

1. **Flagged worker.** A Codex worker on `gpt-6-astra` fails. Its message
   says "This content was flagged for possible cybersecurity risk". It had
   pushed the branch `fix-cache` and opened PR 51 for issue 50.
2. **Stopped lead.** The lead's context was summarized after three workers
   started. The lead wakes with "Delegated task … finished" for one worker.
3. **Worker waits on answers.** A grill-with-research worker finishes its
   turn with three numbered questions for the user. Question 2 is about
   compound toxicity data in a chemistry task.
4. **Duplicate dispatch.** The plan has task B. `t3_thread_list` with
   `includeSubagents` shows a running worker for task B, which an earlier
   lead turn started.
5. **Two pending decisions.** One worker waits on two numbered decisions.
   Another worker is running. A third worker finished, and its PR merged.
6. **Undeclared T3 tool.** In Antigravity, `orchestrator_capabilities` is a
   declared tool, but `delegate_task` is not.

## Expected results

| Case | Next permitted action | Blocked action | Evidence needed |
| --- | --- | --- | --- |
| Flagged worker | Run the same brief, with line 1 in the Claude form, once more in a new worker on `claude-sonnet-5-5`. Add the branch `fix-cache`, PR 51, issue 50, the planning-folder paths, and "Continue from this state." Then settle the flagged thread. | Adding the flagged thread's link to the new brief; a second retry after another flag; settling before the new worker starts. | The failed status and the flag message of the worker. |
| Stopped lead | Read `lead.md` first, then run the `verify` step for the finished worker. | Starting new workers for the tasks in `lead.md` again; trusting the worker's report alone. | `lead.md`, and the merged diff and checks of the finished worker. |
| Worker waits on answers | Run the `answer` step. Ask the user to answer in the worker's thread: give its link, "3 decisions", and a one-line topic for questions 1 and 3 only. Write the items in `lead.md`. | Answering the questions; settling the worker; giving the topic of question 2. | The worker's final message and its thread link. |
| Duplicate dispatch | Record the running worker for task B in `lead.md` and start no second worker. | Starting a second worker for task B. | The `t3_thread_list` output. |
| Two pending decisions | Check the unsettled workers, then report: one status line, then Running, Done (verified), and Decided, and end with the worker link and "2 decisions". Do not settle the lead thread. | Leaving out the waiting worker; settling the lead thread while a worker runs or waits. | The `t3_thread_list` output, the merged PR, and `lead.md`. |
| Undeclared T3 tool | Call `delegate_task` through the T3 terminal fallback that T3's instructions name. Stop with "this skill needs T3 Code" only when that call also fails. | Stopping before the fallback call. | The fallback call's result. |

## Validation limits

A simulated next-action review checks how an agent interprets these cases. It
does not demonstrate a full lead session with real workers. Record static
checks, simulated reviews, and live observations separately.

## Review record

### 2026-11-21, issue #448

**Static checks.** `test_t3_project_lead.py` checks each step's word limit
and `Next:` line, that every step can be reached from `start`, the flag
model, the lines that match matt-automode and grill-with-research, the
standard-library imports, and the frontmatter, invocation setting, and
shared body of the three copies.

**Live observations, before the skill existed.** A Claude Code worker loaded
a skill from `/dev-skills:step-workflow` at the start of its prompt. An
Antigravity worker loaded it from `/step-workflow`; with
`/dev-skills:step-workflow`, the text arrived as plain text, and the worker
found the skill only by reading its skill list. An Antigravity lead on
`gemini-4-neon` called `orchestrator_capabilities` as a declared tool. It
called `delegate_task` through the T3 terminal fallback, started a
`claude-sonnet-5-5` child, woke when the child finished, and read its result.
No Codex lead was tested, because the skill was not installed.
