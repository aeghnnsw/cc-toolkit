# Explore Mode Workflow

Diverge across the entire project for a time-limited period, maximizing diversity and depth.

## Step 1: Parse Time Limit

Extract time limit from the user's message. Default: 30 minutes.

Examples:
- "run a deep eval" → 30 min
- "evaluate the project for 45 minutes" → 45 min
- "explore for 1 hour" → 60 min

Calculate deadline timestamp:
```bash
# Get current unix timestamp + time limit in seconds
echo $(( $(date +%s) + 30 * 60 ))
```

## Step 2: Survey the Project

Before dispatching critics, build a map of the project:

1. Read project structure using Glob:
   ```
   Glob **/*.{ts,tsx,py,js,jsx,go,rs,md}
   ```
   Or use `ls` to survey top-level directories:
   ```bash
   ls -la
   ```

2. Read README.md and CLAUDE.md if they exist

3. Check recent changes:
   ```bash
   git log --oneline -20
   git diff --stat HEAD~5
   ```

4. Identify major areas of the codebase (directories, modules, features)

## Step 3: Dispatch Critics

Create the output directory:
```bash
mkdir -p docs/eval
```

Generate timestamp and deadline:
```bash
TIMESTAMP=$(date "+%Y%m%d-%H%M%S")
DEADLINE=$(( $(date +%s) + TIME_LIMIT_SECONDS ))
```

Dispatch 3-5 critics with diverse starting directions. Assign different project areas to each to maximize coverage:

```
Agent(
  subagent_type: "eval-critic",
  name: "eval-critic-<N>",
  run_in_background: true,
  prompt: "
    You are an eval-critic in EXPLORE MODE.

    Direction: <cluster name>
    Target scope: entire project
    Output file: docs/eval/findings-<timestamp>-critic-<N>.md
    Previous findings: <none for first dispatch>
    Deadline timestamp: <unix timestamp>

    Read these references before starting:
    - ${CLAUDE_PLUGIN_ROOT}/skills/project-eval/references/angles.md
    - ${CLAUDE_PLUGIN_ROOT}/skills/project-eval/references/finding-format.md

    Evaluate the project from your assigned direction. Before each
    iteration, check: date +%s — if past <deadline>, finish current
    iteration and terminate. Otherwise, pick a new angle, go deeper
    or broader, and continue. Maximize diversity — explore areas you
    haven't looked at yet. If you found issues in an area, dig deeper.

    Start by surveying: <suggested starting area for this critic>
  "
)
```

**Direction assignment strategy**: spread critics across cluster families:
- Critic 1: Code or Architecture
- Critic 2: Security or Data & API
- Critic 3: Frontend & Design or User Experience
- Critic 4: Product or Documentation & Convention
- Critic 5: whichever cluster seems most relevant based on the project survey

Adapt if the project doesn't have a frontend, API layer, etc.

## Step 4: Inform User

> "Dispatched <N> critic agents for a <time_limit> minute evaluation. Directions: <list>. They'll self-terminate at the deadline and I'll consolidate the findings."

## Step 5: Consolidate on Completion

When all background critic agents complete:

1. Read all per-critic findings files
2. Read the finding format reference
3. Merge findings (same process as Focus mode)
4. Additionally, build a **Coverage Map**:
   - Parse each critic's findings for file paths
   - Group by project area (directory)
   - Map which directions were explored in which areas
   - Identify areas that were NOT explored
5. Write consolidated report with the Coverage Map section
6. Delete per-critic files after consolidated report is written
7. Present the final report to the user, highlighting:
   - Total findings by severity
   - Areas with the most issues
   - Unexplored areas for potential future runs

## Resource Constraints

If the platform limits concurrent sub-agents, reduce fan-out:
- Dispatch 2-3 critics initially
- When they complete, dispatch remaining directions in a second batch
- Adjust deadline for second batch to use remaining time
