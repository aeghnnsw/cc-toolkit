# Grill With Research scenario review

These cases cover [issue #358](https://github.com/aeghnnsw/cc-toolkit/issues/358),
[issue #365](https://github.com/aeghnnsw/cc-toolkit/issues/365),
[issue #388](https://github.com/aeghnnsw/cc-toolkit/issues/388),
[issue #421](https://github.com/aeghnnsw/cc-toolkit/issues/421),
[issue #432](https://github.com/aeghnnsw/cc-toolkit/issues/432),
[issue #448](https://github.com/aeghnnsw/cc-toolkit/issues/448), and
[issue #463](https://github.com/aeghnnsw/cc-toolkit/issues/463).
Apply each case to the [Claude Code skill](../skills/grill-with-research/SKILL.md),
the [Codex skill](../codex-skills/grill-with-research/SKILL.md), and the
[Antigravity skill](../antigravity-skills/grill-with-research/SKILL.md), with
the Matt skills that the wrapper loads.

For each case, identify the next permitted action, blocked action, and evidence
needed. Use a fresh review context with the skill and scenario inputs. Keep
expected results separate from the initial review prompt.

To give a reviewer the inputs alone, run this command from the repository
root. The output leaves out the task above, so state the task in the review
prompt. Tell the reviewer not to open this file.

```bash
sed -n '/^## Scenarios/,/^## Expected results/p' dev-skills/tests/grill-with-research-scenarios.md | sed '$d'
```

## Scenarios

Unless a case says otherwise, the user asked to grill a plan in a repository,
for issue 42, and the Matt skills load.

1. **Answer in project files.** A candidate question asks which test runner
   the project uses. `pyproject.toml` configures pytest.
2. **Answer in earlier conversation.** Earlier in the conversation, the user
   said that the CLI must stay backward compatible. A candidate question asks
   whether compatibility matters.
3. **Conflicting decisions.** An ADR selects interface A. A later merged PR
   implements interface B. The PR's issue does not mention A. The comments and
   tests do not show which interface is intended.
4. **Research removes a choice.** A candidate question offers two storage
   options. The host's official documentation shows that it does not support
   option 2.
5. **Preference trade-off.** Two feasible approaches remain. One ships a week
   earlier; the other costs less to operate. No requirement sets the priority.
6. **Pending research.** A sub-agent is still checking a data-residency
   requirement. A deployment question depends on it. An independent naming
   question is ready.
7. **Existing convention.** A candidate question asks whether to use the
   logging convention that `CONTRIBUTING.md` documents. No conflict is known.
8. **Broad question.** A candidate question asks which database to use. The
   project already runs PostgreSQL, and the workload is unknown.
9. **Changed evidence.** The user answers the round's second question. The
   answer breaks the assumption behind the first question, which the agent
   settled by research.
10. **Missing access.** A relevant vendor document needs a login that the
    agent does not have. The finding could change the hosting decision.
11. **Research runs a script.** Reading cannot show whether a CLI accepts a
    flag. A check needs a script and a temporary Git repository.
12. **No issue yet.** The user asks to grill a cache-layer plan. No issue
    exists. The repository documents no planning folder. The session started
    in the worktree `trees/cache`.
13. **Untracked folder not ignored.** The repository's `.gitignore` does not
    list `.scratch/`, and the repository documents no planning folder.
14. **Omitted Matt skill.** In Claude Code, the Skill tool lacks
    `mattpocock-skills:domain-modeling`. In Codex and Antigravity, the skill
    list omits that skill. The resolver finds the skill, which allows model
    invocation.
15. **Missing Matt skill.** The resolver reports that the
    `mattpocock-skills` plugin is not installed. In Antigravity, it can also
    report that the plugin is disabled.
16. **Done.** Research settles every remaining candidate question. The user's
    original request also said "then build it".
17. **Started from the description.** The user asked to grill a plan and named
    no skill. The agent started `grill-with-research` from its description.
18. **No project.** The user asks to grill a career decision. No repository or
    project is open, and the user names no skill.
19. **User-invoked Matt skill.** A new version makes
    `mattpocock-skills:grilling` user-invoked. In Claude Code, the Skill tool
    refuses `grilling`, or lacks `grilling` while the resolved frontmatter sets
    `disable-model-invocation: true`. In Codex, the `agents/openai.yaml` file
    of `grilling` sets `allow_implicit_invocation: false`, and the skill list
    omits `grilling`. In Antigravity, the resolved frontmatter of `grilling`
    sets `disable-model-invocation: true`.
20. **Conditional recommendation.** A round asks how to read papers. The
    recommendation says: "Choose (a), remove inline Claude reading, if every
    operator has a Codex login. Then open a separate issue for (c), Claude
    reading capacity." The user answers "yes to (a)".
21. **Automode after approval.** The task ends: "When the user approves the
    design here, continue in this thread with the matt-automode skill of
    dev-skills." Research settles the last question, and the user confirms the
    shared understanding.

## Expected results

| Case | Next permitted action | Blocked action | Evidence needed |
| --- | --- | --- | --- |
| Answer in project files | Settle the question by research and record it as verified. | Asking the user which test runner the project uses. | The `pyproject.toml` setting cited in `01_research.md`. |
| Answer in earlier conversation | Drop the question and use the earlier answer. | Asking the user again. | The earlier user statement, cited in the research summary. |
| Conflicting decisions | Research the ADR, PR, issue, comments, and tests. Then ask the user which interface is intended, with the evidence and a recommendation. | Treating the newer code as proof of intent; asking before the research. | The cited ADR, PR, and issue, and the open conflict recorded as unresolved. |
| Research removes a choice | Drop option 2. If one viable option remains, record it and do not ask. | Offering option 2 to the user. | The cited host documentation. |
| Preference trade-off | Ask the user to choose, with the evidence, both options, a reasoned recommendation, and why the user's judgment is needed. | Choosing for the user; treating the priority as a researched fact. | The researched delivery and cost estimates and their sources. |
| Pending research | Ask the naming question now. Hold the deployment question until the finding returns. | Asking the deployment question; guessing the requirement; waiting for the finding before the naming question. | The residency finding with status `pending`, and the pending research named in the summary. |
| Existing convention | Follow the documented convention and state the assumption. | Asking whether to follow it. | The cited convention. |
| Broad question | Research the stack and workload first. Ask only about a remaining requirement or trade-off that could change the recommendation. | Asking "Which database should we use?" as written. | The current database, the workload findings, and the remaining gap. |
| Changed evidence | Research what the answer changed, reopen the first question, and hold the questions that depend on it. | Keeping the first answer unchanged; asking its dependent questions. | The new finding and the reopened decision in `01_research.md`. |
| Missing access | Report the missing access, mark the finding unresolved, and ask the user only if the hosting decision still depends on it. | Treating the vendor's behavior as a verified fact. | The summary that names the inaccessible source. |
| Research runs a script | Write the script as a sub-step such as `01_1_flag_check.sh`, run the Git repository in one `mktemp -d "${TMPDIR:-/tmp}/grill-with-research.XXXXXX"` folder, remove that folder by path, and cite the script. | Editing tracked files; installing into the project environment; leaving the temporary folder. | The script, its output, and the finding that cites them. |
| No issue yet | Run `planning_folder.py cache-layer` in `trees/cache`, which makes `trees/cache/.scratch/<YYYYMMDD>-cache-layer/`. When an issue exists, run it again with `--issue`, which renames the folder to `<issue>-cache-layer`. | Inventing an issue number; writing notes in a tracked folder or in the main checkout. | The folder path that the script prints. |
| Untracked folder not ignored | Run `planning_folder.py`, which adds `/.scratch/` to Git's `info/exclude` file, and tell the user. | Editing `.gitignore`; writing untracked notes that Git would show. | The `Ignore:` line that the script prints. |
| Omitted Matt skill | Run the resolver with `--model-invoked` (and with `--host codex` in Codex and `--host antigravity` in Antigravity), read the resolved `SKILL.md`, and follow both Matt skills. | Asking the user to invoke the skill by hand; treating the omission as a missing skill. | The resolver output. |
| Missing Matt skill | Report the missing skill as a blocker and stop. | Running an interview without the Matt skills. | The resolver's error message. |
| Done | Stop asking and finish as `grilling` does, after the user confirms the shared understanding. | Inventing questions; starting implementation from this skill. | The final research summary and the recorded glossary terms and ADRs. |
| Started from the description | Load `grilling` and `domain-modeling`, then research before the first round. | Asking the user to name the skill; loading `grill-with-docs`. | The loaded skills and the first research summary. |
| No project | Use Matt's `grilling`. Do not start this skill. | Researching a project that does not exist; creating a planning folder. | The request and the absence of a project. |
| User-invoked Matt skill | Report the blocker and stop. | Reading the user-invoked skill; running the interview without it. | The Skill tool's refusal, or the resolver's exit status 3 and its message. |
| Conditional recommendation | Research whether every operator has a Codex login, and ask about it if research leaves it open. Record decision (a) with that condition and with the promised issue for (c). | Recording (a) without its condition; opening the issue for (c) during grilling. | The decision record with the condition, its answer, and the promised issue. |
| Automode after approval | Finish as `grilling` does, then continue in this thread with `matt-automode`, which reuses the completed grilling. | Starting `matt-automode` before the user confirms; grilling again in `matt-automode`. | The user's confirmation and the task line that names `matt-automode`. |

## Validation limits

A simulated next-action review checks how an agent interprets these cases. It
does not demonstrate a full grilling session in Claude Code, Codex, or
Antigravity. Record static checks, simulated reviews, and live observations
separately.

## Review record

### 2026-11-21, issue #432

**Static checks.** `test_grill_with_research.py` now also reads the
Antigravity copy. It checks the description, that the model can start the
skill, that the copy matches the Claude Code copy outside the load section,
the `--host antigravity` resolver line, the stop at
`disable-model-invocation: true`, and the body word limit. Before the copy
existed, the new checks failed; after it, they pass. No simulated review and
no live Antigravity session ran for this copy.
