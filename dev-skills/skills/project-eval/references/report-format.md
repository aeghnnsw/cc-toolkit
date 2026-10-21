# Finding, Verdict, and Report Formats

## Severity

| Severity | Meaning |
|----------|---------|
| Critical | Breaks core behavior, loses or exposes data, or opens a security hole. |
| Major | A real defect or gap that users or maintainers will hit. |
| Minor | A small defect or improvement with low impact. |

## Finding

An evaluator returns each finding in this form:

````markdown
### E<N>-<k>. <Title> (<Severity>)
- **Dimension**: <dimension>: <angle>
- **Location**: `<path>:<start>-<end>`, or the URL and browser steps, or the command
- **Evidence**:
  ```
  <verbatim quote, command and output excerpt, or what the browser showed>
  ```
- **Why it matters**: <the impact; cite the criterion when one applies>
- **Suggested fix**: <one or two sentences>
````

Evidence rules: a quote is verbatim, with the path and line range of the
current file. An observation gives enough detail to repeat it. A finding
about something missing quotes the requirement, the criterion, or the place
where it should be.

## Verdict

A verifier returns one line for each finding ID:

```text
<ID> | <Confirmed, Plausible, or Rejected> | <Severity> | <Reason>
```

- **Confirmed**: the evidence matches the current project, and the verifier
  checked that the problem holds.
- **Plausible**: the evidence matches, but the verifier could not check the
  impact, for example a runtime claim with no app or no browser.
- **Rejected**: the evidence does not match the current project, the claim is
  wrong, the project already handles it, or it is not an issue.

When the verifier changes the severity, the severity field says so, for
example `Major (was Critical: only admins can reach it)`.

A finding with no verdict after the retry is **Not verified**. Not verified
is not a verdict: no verifier judged the finding.

## Report

The main agent writes one report. Default path:
`docs/eval/YYYY-MM-DD-HHMM-<slug>.md`, where the slug names the target in
a few lowercase words, such as `auth-module` or `whole-project`. When the
file exists, add `-2`, `-3`, and so on. The user or a calling skill can name
another path.

````markdown
# Project Evaluation: <target>

- **Date**: <YYYY-MM-DD HH:MM time zone>
- **Scope**: <target, or the whole project>
- **Criteria**: <source, or none>
- **App**: <URL, or none>
- **Evaluators**: E1 <dimensions> (<stop reason>); E2 ...
- **Status**: Complete | Incomplete (<n> findings not verified)
- **Browser checks**: done | not needed | skipped: <reason>
- **Earlier reports**: <paths with the same slug, or none>

## Summary

| Severity | Confirmed | Plausible |
|----------|-----------|-----------|
| Critical | 0 | 0 |
| Major | 0 | 0 |
| Minor | 0 | 0 |

Rejected: <n>. Not verified: <n>.

## Findings

### F1. <Title> (<Severity>, <Verdict>)
- **IDs**: E2-3 (also E1-5)
- **Dimension**: <dimension>: <angle>
- **Location**: ...
- **Evidence**:
  ```
  ...
  ```
- **Why it matters**: ...
- **Suggested fix**: ...
- **Verifier**: <reason>

## Rejected Findings

| ID | Title | Reason |
|----|-------|--------|

## Not Verified Findings

| ID | Title | Why not verified |
|----|-------|------------------|

## Coverage

| Area | Dimensions and angles covered |
|------|-------------------------------|

- **Not covered**: <areas and angles that no evaluator reached>
- **Other areas**: <suspicious things that evaluators noted outside their dimensions>
````

Rules:

- Order the findings by severity, Critical first. Within a severity, put
  Confirmed before Plausible.
- Use the severity from the verdict.
- Merge findings about the same problem at the same place. Keep the clearest
  one, and list every ID.
- Omit the Not Verified Findings section when every finding has a verdict.
