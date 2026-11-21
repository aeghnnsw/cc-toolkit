---
name: step-workflow
description: Use when the user requests step-based file naming and folder organization for a new feature, including sequential numbered prefixes, sub-step notation, and plan tracking across scripts, outputs, tests, or documentation.
---

# Step-Based Workflow Organization

## Overview

Organize all work for a feature using step-based file naming with numbered
prefixes. Apply this convention only when the user requests it and it does not
conflict with an established repository layout or naming convention.

## File Naming Convention

### Basic Pattern

```text
<step_number>_<descriptive_name>.<extension>
```

Examples:

- `01_load_data.py`
- `02_clean_data.py`
- `03_analysis.ipynb`
- `04_results.csv`

### Sub-Steps

When a step has multiple related files:

```text
<step>_<substep>_<descriptive_name>.<extension>
```

Examples:

- `01_1_fetch_api.py`
- `01_2_parse_response.py`
- `02_1_clean_text.py`
- `02_2_clean_numbers.py`

### Leading Zeros

Use leading zeros based on the expected number of steps:

- 10–99 steps: `01`, `02`, ..., `99`
- 100–999 steps: `001`, `002`, ..., `999`

This ensures proper alphabetical sorting.

## Workflow Rules

1. **Respect repository conventions** - Apply step-based names only when the
   user requests them and they do not conflict with established project layout
2. **Keep related artifacts together** - Keep files for the feature in its
   feature folder while preserving the repository's expected subdirectories
3. **Number files sequentially** - Order prefixes by execution or workflow
4. **Use underscores, not spaces** - Keep file names shell- and tool-friendly
5. **Track the numbered work in a Markdown task list** - Keep the list in
   your own task artifact, never in a tracked file. Map each task to its
   corresponding step, keep at most one task in progress, and leave none in
   progress after completion
6. **Renumber when needed** - Restore a clear sequence after inserting or
   reordering steps

## Task List Integration

Each task in the Markdown task list corresponds to a numbered step:

```markdown
- [ ] Load data (01_load_data.py) - in progress
- [ ] Clean data (02_clean_data.py)
- [ ] Run analysis (03_analysis.py)
```

Update the list as the work advances so file order and task state remain
aligned. Mark a finished task `[x]`.
