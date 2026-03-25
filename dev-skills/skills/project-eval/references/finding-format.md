# Finding Format Reference

## Per-Critic Output File

Each critic writes to its own file: `docs/eval/findings-<timestamp>-critic-<N>.md`

### File Structure

```markdown
# Eval Critic: <critic-id>
Direction: <assigned direction>
Target: <scope description>
Mode: Focus | Explore
Started: <ISO timestamp>

## Findings

### [C1-F1] <Title> (<Severity>)
- **Direction**: <direction — specific angle>
- **Location**: `<file-path>:<line-start>-<line-end>`
- **Iteration**: <number>
- **Status**: Open
- **Description**: <What is wrong and why it matters. Be specific.>
- **Evidence**:
  ```
  <exact code snippet from the file>
  ```

### [C1-F2] <Title> (<Severity>)
...

## Directions Explored
- <angle 1>: <brief description of what you examined and how deep>
- <angle 2>: ...

## Suggested Directions
- <direction>: <what you noticed and why it's worth investigating>
```

### Field Definitions

| Field | Values | Notes |
|-------|--------|-------|
| Local ID | `C<critic-num>-F<finding-num>` | Renumbered globally during consolidation |
| Severity | `Critical`, `Major`, `Minor` | Critical = breaks functionality or security. Major = significant quality issue. Minor = small improvement. |
| Direction | Cluster name — specific angle | e.g., "Security — auth bypass" |
| Location | `file:line-start-line-end` | Must be exact, verifiable path |
| Iteration | Integer | Which iteration of the critic's loop found this |
| Status | `Open` | Always Open in per-critic files |
| Description | Free text | Must explain WHY it's an issue, not just WHAT |
| Evidence | Code block | Exact snippet from the file, not paraphrased |

## Consolidated Report

The main agent merges all per-critic files into a single report: `docs/eval/findings-<YYYYMMDD-HHMMSS>.md`

### Report Structure

```markdown
# Project Evaluation — <Mode>: <target>
Started: <ISO timestamp>
Mode: Focus | Explore
Status: Complete (<N> critics, <M> total iterations)

## Summary
| Severity | Count |
|----------|-------|
| Critical | 0     |
| Major    | 0     |
| Minor    | 0     |

## Findings

### [F1] <Title> (Critical)
- **Direction**: Security — auth bypass
- **Location**: `auth/session.ts:42-48`
- **Iteration**: 1 (Critic A)
- **Status**: Open
- **Description**: Session tokens are written to localStorage, which is
  accessible to any JS on the page. An XSS vulnerability anywhere in
  the app would expose all user sessions.
- **Evidence**:
  ```typescript
  localStorage.setItem('session', token)
  ```

### [F2] <Title> (Major)
...

## Iteration Log

### Critic A (security) — 3 iterations
- Iteration 1: 2 findings (F1, F2)
- Iteration 2: 1 finding (F3)
- Iteration 3: 0 findings -> converged

### Critic B (code, architecture) — 2 iterations
- Iteration 1: 2 findings (F4, F5)
- Iteration 2: 1 finding (F6) -> converged
```

### Coverage Map (Explore mode only)

```markdown
## Coverage Map
| Area | Directions Explored |
|------|-------------------|
| auth/ | security, code, architecture |
| frontend/components/ | visual-coherence, accessibility |
| api/routes/ | api-contract, validation |
| **Not explored** | billing/, migrations/, tests/ |
```

## Consolidation Rules

1. Read all per-critic files matching `docs/eval/findings-<timestamp>-critic-*.md` (use the timestamp from this run to avoid mixing with other runs)
2. Deduplicate findings that describe the same issue (same file + same problem)
3. Assign global IDs: F1, F2, F3, ... in order of severity (critical first)
4. Write the consolidated report
5. Delete per-critic files only after consolidated report is fully written to disk
