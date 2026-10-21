---
name: project-eval
version: 2.0.0
description: This skill should be used when the user asks to "evaluate the project", "run a deep eval", "evaluate the auth module", "evaluate this design doc", "find issues in this feature", or "check the running app for UX issues", or wants a broad evaluation of a feature, a design document or plan, a running web app, or a whole project across code, security, architecture, data and APIs, user experience, frontend design, product, and documentation. It dispatches skeptical evaluator agents, has a separate verifier check every finding, and writes one report. For a diff or PR, use /code-review; for one decision or design choice, use pressure-test.
---

# Project Evaluation

Skeptical evaluator agents search a target for issues, each along assigned
dimensions. A neutral verifier agent checks every finding against the current
project. You write one report with the verified findings.

## When to Use

- **Use** for a feature or module, a design document or plan, a running web
  app, or a whole project.
- **Use instead**: `/code-review` for a diff or PR, `/security-review` for
  the security of a diff, and `pressure-test` for one decision, design
  choice, or position.

## Inputs

Take these from the user's message, or from a calling skill. Ask only when
the target is unclear.

- **Target**: files, a feature or module, a document, an app URL, or the
  whole project.
- **Time budget**: 30 minutes by default.
- **Evaluator count**: 1-3 for a target and 3-5 for the whole project by
  default. A count that the user gives wins.
- **Criteria** (optional): a spec, issue, rubric (for example from
  `goal-rubric`), or design document to check against.
- **App URL** (optional): the URL of a running app. Without one, use a local
  dev server only if it already runs. Do not start or stop a server.
- **Report path** (optional): by default
  `docs/eval/YYYY-MM-DD-HHMM-<slug>.md`. The slug is a few lowercase words
  that name the target, such as `auth-module`.

## Workflow

### 1. Scope the Target

1. Find the files in scope, or survey the whole project: README,
   CLAUDE.md or AGENTS.md, the top-level layout, and `git log --oneline -20`.
2. If the target is a web app and you have no app URL, look for a local dev
   server that already runs, for example with
   `lsof -nP -iTCP -sTCP:LISTEN`. Use its URL as the app URL.
3. Read [references/dimensions.md](references/dimensions.md). Choose
   dimensions that fit the target:
   - Code feature or module: Code, Security, Architecture, and Data & API
     for endpoints.
   - Design document or plan: Architecture, Product, Documentation &
     Convention, and the dimensions of the system that it designs.
   - Running web app: User Experience, Frontend & Design, and Product.
   - Whole project: spread the evaluators across all eight dimensions.
     Give each evaluator a different starting area.
4. Assign dimensions so that evaluators do not overlap.

### 2. Set Up the Run

Set up the run just before dispatch, so that scoping does not use the time
budget. Each Bash call can start a new shell, so keep the run state in a
file. Set `MINUTES` to the time budget:

```bash
MINUTES=30
RUN="$(mktemp -d "${TMPDIR:-/tmp}/project-eval.XXXXXX")"
printf 'RUN="%s"\nDEADLINE=%s\nSTARTED="%s"\n' "$RUN" \
  "$(( $(date +%s) + MINUTES * 60 ))" "$(date '+%Y-%m-%d %H:%M %Z')" > "$RUN/run.env"
cat "$RUN/run.env"
```

Use the printed `RUN` path and `DEADLINE` value in the steps below. If you
lose the `RUN` path, find the newest run with
`ls -dt "${TMPDIR:-/tmp}"/project-eval.* | head -1`.

Tell the user the scope, the dimensions of each evaluator, and the deadline
in two or three lines.

### 3. Dispatch the Evaluators

Send one Agent call for each evaluator, all in one message:

```text
Agent(
  subagent_type: "dev-skills:project-evaluator",
  description: "Evaluator E<N>: <dimensions>",
  prompt: "
    Evaluator number: <N>
    Target: <files, feature, document, URL, or the whole project>
    Dimensions: <names>
    Deadline: <DEADLINE>
    Criteria: <path or issue, or none>
    App URL: <URL, or none>
    Starting point: <area, or none>
  "
)
```

The evaluators run in the background. Reply to the user and do not wait.
Do not stop an evaluator unless the user asks.

### 4. Verify Each Result When It Arrives

When an evaluator finishes:

1. If its result has no findings list, or the result is partial (turn
   limit), resume the evaluator once with SendMessage and ask for its
   findings so far in its final-message format.
2. Save its full result, verbatim, as `<RUN>/E<N>.md`. Do not shorten it:
   the saved files are the record of the run if your context is compacted.
3. Check that each finding has a unique ID that starts with `E<N>-`. If a
   finding has no ID or a duplicate ID, give it a new ID, and append the
   change to `<RUN>/E<N>.md`.
4. Split its findings into batches of at most 10.
5. Send one verifier for each batch:

   ```text
   Agent(
     subagent_type: "dev-skills:finding-verifier",
     description: "Verify E<N> batch <b>",
     prompt: "
       Target: <as for the evaluator>
       Criteria: <as for the evaluator>
       App URL: <as for the evaluator>
       Findings:
       <the findings of this batch, verbatim, with their IDs>
     "
   )
   ```

When a verifier finishes:

1. Save its full result, verbatim, as `<RUN>/V-E<N>-<b>.md`.
2. Compare the IDs in its verdicts with the IDs of its batch.
3. For missing IDs, resume the verifier once with SendMessage. If it cannot
   resume, send one new verifier for the missing IDs only.
4. A finding that still has no verdict is **Not verified**.

### 5. Write the Report

When every evaluator and verifier has finished:

1. Read the saved results in `<RUN>`.
2. Choose the report path. For the default path, follow the name rules in
   [references/report-format.md](references/report-format.md).
3. Find the earlier reports with the same slug in the report directory.
4. Write the report in the format of `report-format.md`. Merge duplicates,
   use the verified severities, and list Rejected and Not verified findings
   in their own sections.
5. Save the report at the report path.
6. Present the report path, the status line, the summary table, the
   Critical and Major findings, and what was not covered.

## Rules

- Evaluators and verifiers return their results as text. They write no
  report files, and they create, change, or delete no project files. They do
  experiments only in a temporary directory. Only you write the run results
  and the report.
- Evaluators and verifiers change no Git state, start no server, and take no
  action with external effects.
- When no browser tools are available, or the session refuses a browser
  call, the report says that browser checks were skipped.
- Earlier reports are context for the reader. Do not pass their findings to
  evaluators: an old finding must not hide a new one.

## Browser Servers

Both agents can use the tools of these browser MCP servers: the desktop
app's browser (`Claude_Browser`), Claude in Chrome (`claude-in-chrome`),
Chrome DevTools (`chrome-devtools`), and Playwright (`playwright`, or the
Playwright plugin). To support another server, add its tool prefix to the
`tools` line of both agents in the dev-skills plugin:
`mcp__<server>__*` for a server that the user configured, or
`mcp__plugin_<plugin>_<server>__*` for a server that a plugin provides.

A tool in the list still needs permission in the session. A server that
connects after an agent starts gives that agent no tools.
