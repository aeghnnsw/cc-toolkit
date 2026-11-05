# Grill With Research scenario review

> On 2026-11-05,
> [issue #365](https://github.com/aeghnnsw/cc-toolkit/issues/365) changed the
> loading rule: the wrapper loads `grilling` and `domain-modeling` directly,
> not `grill-with-docs`. The cases and expected results follow #365. The #358
> review record describes the earlier rule, and its case numbers refer to the
> earlier list.

These cases cover [issue #358](https://github.com/aeghnnsw/cc-toolkit/issues/358)
and [issue #365](https://github.com/aeghnnsw/cc-toolkit/issues/365).
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
    exists. The repository documents no planning folder.
13. **Untracked folder not ignored.** The repository's `.gitignore` does not
    list `.scratch/`, and the repository documents no planning folder.
14. **Omitted Matt skill.** In Claude Code, the Skill tool lacks
    `mattpocock-skills:domain-modeling`. In Codex, the skill list omits that
    skill. The resolver finds the skill, which allows model invocation.
15. **Missing Matt skill.** The resolver reports that the
    `mattpocock-skills` plugin is not installed.
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
    omits `grilling`.

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
| Untracked folder not ignored | Add `/.scratch/` to Git's `info/exclude` file, at the path that `git rev-parse --git-path info/exclude` prints, and tell the user. | Editing `.gitignore`; writing untracked notes that Git would show. | `git check-ignore` output before and after. |
| Omitted Matt skill | Run the resolver (with `--host codex` in Codex), check the invocation setting, read the resolved `SKILL.md`, and follow both Matt skills. | Asking the user to invoke the skill by hand; treating the omission as a missing skill. | The resolver output. |
| Missing Matt skill | Report the missing skill as a blocker and stop. | Running an interview without the Matt skills. | The resolver's error message. |
| Done | Stop asking and finish as `grilling` does, after the user confirms the shared understanding. | Inventing questions; starting implementation from this skill. | The final research summary and the recorded glossary terms and ADRs. |
| Started from the description | Load `grilling` and `domain-modeling`, then research before the first round. | Asking the user to name the skill; loading `grill-with-docs`. | The loaded skills and the first research summary. |
| No project | Use Matt's `grilling`. Do not start this skill. | Researching a project that does not exist; creating a planning folder. | The request and the absence of a project. |
| User-invoked Matt skill | Report the blocker and stop. | Reading the user-invoked skill past its frontmatter; running the interview without it. | The Skill tool's refusal, or the frontmatter or `agents/openai.yaml` setting. |

## Validation limits

A simulated next-action review checks how an agent interprets these cases. It
does not demonstrate a full grilling session in Claude Code or Codex. Record
static checks, simulated reviews, and live observations separately.

## Review record

### 2026-11-05, issue #365

**Static checks.** `test_grill_with_research.py` now requires that both copies
load `grilling` and `domain-modeling` and that neither body names
`grill-with-docs`. The test failed before the skill change and passes after
it. The root tests, the package and release validator, and the Codex
skill-creator validator pass.

**Live observations.** In this Claude Code session, the model invoked
`mattpocock-skills:grilling` with the Skill tool, and the tool loaded it. Before
#365, the same tool refused `grill-with-docs`. The resolver found both skills
for Claude Code and, with `--host codex`, for Codex.

**Simulated review, round 1.** One fresh agent read both copies, the two Matt
skills, and cases 14, 15, 17, and 19. It did not receive the expected results.
Both copies gave the expected actions in cases 14, 15, and 17. In case 19, the
Claude Code copy decided only a refusal, and the Codex copy let the resolver
read a skill with `allow_implicit_invocation: false`. Both copies were changed
to stop at a user-invoked setting.

**Simulated review, round 2.** A fresh agent read the changed copies and cases
14, 15, 17, and 19. All cases ended at the expected stop or question. It
reported three gaps: the intro named `grill-with-docs`, which a reader could
try to load; the Claude Code check read the whole user-invoked `SKILL.md`; and
the Codex check came after the file was opened. The intro no longer names
`grill-with-docs`, the Claude Code check reads only the frontmatter, and the
Codex check runs before the file is opened.

**Simulated review, round 3.** A fresh agent read the final copies and cases 14,
17, and 19 before it read the expected results. All cases passed on both hosts.
Neither copy reads a user-invoked `SKILL.md` past its frontmatter. The agent
named small risks that were not changed: any Skill tool refusal stops the
skill, and "A Matt skill cannot load" does not list its causes.

**Simulated review, round 4.** After a second code review, case 14 also
covers Claude Code. A fresh agent read both final copies and cases 14 and 19.
All sub-cases passed. It reported that the Claude Code read limit came after
the condition that it guards. The limit now comes with the resolver step,
before the checks.

**Simulated review, round 5.** A fresh agent read the Claude Code load section
for three sub-cases: an omitted skill that allows model invocation, an omitted
skill with `disable-model-invocation: true`, and a refusal. All three passed.

### 2026-11-05, issue #358

**Static checks.** `dev-skills/tests/test_grill_with_research.py` checks the
description, the invocation policy, the host differences, the resolver lines,
and the 400-word body limit. The root tests, the package and release
validator, and the Codex skill-creator validator pass.

**Simulated review, round 1.** Two fresh agents, one for each host copy, read
the skill, the Matt skills, and cases 1–16. They did not receive the expected
results. Both chose the expected actions in 14 cases. In cases 8 and 10, both
said that the text did not decide the next action. They also reported these
gaps: no `pending` status, a filter that dropped questions that wait for
research, nested skill names without the plugin prefix, cited scripts that a
temporary folder could delete, no rename for a date-keyed folder, and a stop
rule that conflicted with the confirmation step of `grilling`. The skill text
was changed to close these gaps.

**Live observations.** In a Claude Code session with `dev-skills` 3.33.0, the
Skill tool refused `mattpocock-skills:grill-with-docs` and said: "Do not
replicate this skill's workflow by other means — it is reserved for explicit
user invocation." The skill text now reads a user-invoked skill by path only when the
user named this skill or a workflow that uses it. Case 14 states this
condition, and case 17 covers the other condition. The resolver found
`grill-with-docs`, `grilling`, and `domain-modeling` for Claude Code, and with
`--host codex` for Codex, with exit status 0. On both hosts, `grilling` and
`domain-modeling` allow model invocation, and `grill-with-docs` does not. For a
missing skill, the resolver printed `skill no-such-skill not found` on both
hosts, with exit status 1. For a missing plugin, it printed
`plugin no-such-plugin is not installed` for Claude Code and
`plugin no-such-plugin is not enabled in ~/.codex/config.toml` for Codex, with
exit status 1. No full
grilling session ran, because the installed `dev-skills` does not include this
skill.

**Simulated review, round 2.** One fresh agent read the changed text of both
copies and cases 6, 8, 10, 12, 14, 16, and 17. Both copies gave the expected
actions in all seven cases. The agent reported that an "Otherwise" sentence
could be read as a stop after a successful load, and that the Codex copy could
not tell an explicit-only skill from a missing one. The text now says "Without
that request" and "If the skill list omits one".

**Simulated review, round 3.** One fresh agent read the final text and cases
14, 17, and 18. Both copies gave the expected actions in all three cases. The
agent reported that the stop in case 17 did not say what to tell the user. The
text now asks the user to name this skill.

These were simulated instruction reviews and short live checks.
