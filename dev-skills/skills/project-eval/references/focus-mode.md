# Focus Mode Workflow

Converge on a specific feature or module until no new issues are found.

## Step 1: Identify Target Scope

Search the codebase to identify all files relevant to the user's target:

```bash
# Example: user says "evaluate the auth middleware"
```

Use Glob and Grep to find relevant files. Establish the evaluation boundary — which files and directories are in scope.

Present the scope to the user briefly:
> "Evaluating auth middleware: `auth/`, `middleware/`, and related test files (~15 files). Dispatching critics..."

## Step 2: Select Directions

Read the angle pool:
```
Read ${CLAUDE_PLUGIN_ROOT}/skills/project-eval/references/angles.md
```

Select 1-3 direction clusters most relevant to the target scope. Examples:
- Auth module → security, code, architecture
- UI component → frontend & design, user experience, accessibility
- API endpoint → data & API, security, code
- Data pipeline → code, architecture, performance

## Step 3: Dispatch Critics

Create the output directory if needed:
```bash
mkdir -p docs/eval
```

Generate a timestamp for this evaluation run:
```bash
date "+%Y%m%d-%H%M%S"
```

For each critic, dispatch as a long-running background agent:

```
Agent(
  subagent_type: "eval-critic",
  name: "eval-critic-<N>",
  run_in_background: true,
  prompt: "
    You are an eval-critic in FOCUS MODE.

    Direction: <cluster name>
    Target scope: <list of files/directories in scope>
    Output file: docs/eval/findings-<timestamp>-critic-<N>.md
    Previous findings: <none for first dispatch, or list of known issues>

    Read these references before starting:
    - ${CLAUDE_PLUGIN_ROOT}/skills/project-eval/references/angles.md
    - ${CLAUDE_PLUGIN_ROOT}/skills/project-eval/references/finding-format.md

    Evaluate the target from your assigned direction. Iterate: evaluate,
    write findings, rotate to a new angle. When a full iteration produces
    no new findings, write your final summary and terminate.
  "
)
```

## Step 4: Inform User

After dispatching, respond to the user immediately. Do not wait for critics to finish.

> "Dispatched <N> critic agents evaluating <target> from <directions>. They'll run in the background and I'll consolidate findings when they converge."

## Step 5: Consolidate on Completion

When all background critic agents complete (you'll receive notifications):

1. Read all per-critic findings files:
   ```
   Glob docs/eval/findings-<timestamp>-critic-*.md
   ```

2. Read the finding format reference:
   ```
   Read ${CLAUDE_PLUGIN_ROOT}/skills/project-eval/references/finding-format.md
   ```

3. Merge findings:
   - Deduplicate: same file + same issue = one finding
   - Assign global IDs: F1, F2, ... ordered by severity (critical first)
   - Build iteration log from each critic's output

4. Write consolidated report to `docs/eval/findings-<YYYY-MM-DD-HHMMSS>.md`

5. Delete per-critic files only after the consolidated report is fully written

6. Present the final report to the user
