# Grill With Research scenario review

These cases cover [issue #358](https://github.com/aeghnnsw/cc-toolkit/issues/358).
Apply each case to the [Claude Code skill](../skills/grill-with-research/SKILL.md)
and the [Codex skill](../codex-skills/grill-with-research/SKILL.md), with the
Matt skills that the wrapper loads.

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

Unless a case says otherwise, the user invoked `grill-with-research` by name to
grill a plan in a repository, for issue 42, and the Matt skills load.

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
    exists. The repository documents no planning folder.
13. **Untracked folder not ignored.** The repository's `.gitignore` does not
    list `.scratch/`, and the repository documents no planning folder.
14. **Hidden Matt skill.** In Claude Code, the Skill tool refuses
    `mattpocock-skills:grill-with-docs` because the skill is user-invoked. In
    Codex, the skill list omits it.
15. **Missing Matt skill.** The resolver reports that the
    `mattpocock-skills` plugin is not installed.
16. **Done.** Research settles every remaining candidate question. The user's
    original request also said "then build it".
17. **Started from the description.** The user asked to grill a plan and named
    no skill. The agent started `grill-with-research` from its description. The
    Skill tool refuses `mattpocock-skills:grill-with-docs`, or in Codex, the
    skill list omits it.

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
| Research runs a script | Write the script as a sub-step such as `01_1_flag_check.sh`, run the Git repository in one `mktemp -d` folder, remove that folder by path, and cite the script. | Editing tracked files; installing into the project environment; leaving the temporary folder. | The script, its output, and the finding that cites them. |
| No issue yet | Use `.scratch/<YYYYMMDD>-cache-layer/` in the main checkout. Rename it to `<issue>-cache-layer` when an issue exists. | Inventing an issue number; writing notes in a tracked folder. | The folder path. |
| Untracked folder not ignored | Add `/.scratch/` to `.git/info/exclude` and tell the user. | Editing `.gitignore`; writing untracked notes that Git would show. | `git check-ignore` output before and after. |
| Hidden Matt skill | Run the resolver for the host, read the resolved `SKILL.md`, and follow `mattpocock-skills:grilling` and `mattpocock-skills:domain-modeling`. | Asking the user to invoke the skill by hand; using another workflow. | The resolver output. |
| Missing Matt skill | Report the missing skill as a blocker and stop. | Running an interview without the Matt skills. | The resolver's error message. |
| Done | Stop asking and finish as `grilling` does, after the user confirms the shared understanding. | Inventing questions; starting implementation from this skill. | The final research summary and the recorded glossary terms and ADRs. |
| Started from the description | Stop and report the blocker. Tell the user to invoke `grill-with-research` by name. | Reading the hidden skill by path; running `grilling` and `domain-modeling` without it. | The Skill tool's refusal, or the omitted skill-list entry. |

## Validation limits

A simulated next-action review checks how an agent interprets these cases. It
does not demonstrate a full grilling session in Claude Code or Codex. Record
static checks, simulated reviews, and live observations separately.

## Review record
