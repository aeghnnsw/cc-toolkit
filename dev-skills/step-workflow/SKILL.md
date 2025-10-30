---
name: step-workflow
description: This skill should be used when organizing work using step-based file naming and folder structure. Load this skill at the start of working on a new feature to establish sequential, numbered organization for all files (scripts, outputs, tests, documentation). The skill guides the use of numbered prefixes (01_, 02_, 03_) and sub-step notation (01_1_, 01_2_) to maintain clear workflow order and traceability.
---

# Step-Based Workflow Organization

## Overview

Organize all work for a feature using step-based file naming with numbered prefixes. All files (scripts, outputs, tests, documentation) in the feature folder follow this convention.

## File Naming Convention

### Basic Pattern

```
<step_number>_<descriptive_name>.<extension>
```

Examples:
- `01_load_data.py`
- `02_clean_data.py`
- `03_analysis.ipynb`
- `04_results.csv`

### Sub-Steps

When a step has multiple related files:

```
<step>_<substep>_<descriptive_name>.<extension>
```

Examples:
- `01_1_fetch_api.py`
- `01_2_parse_response.py`
- `02_1_clean_text.py`
- `02_2_clean_numbers.py`

### Leading Zeros

Use leading zeros based on expected number of steps:
- 10-99 steps: `01`, `02`, ..., `99`
- 100-999 steps: `001`, `002`, ..., `999`

This ensures proper alphabetical sorting.

## Workflow Rules

1. **Keep everything in one folder** - All files related to the feature stay in the feature folder
2. **Number files sequentially** - Based on execution/workflow order
3. **Use underscores, not spaces** - For file names
4. **Always use TodoWrite tool** - Track progress through numbered steps
5. **Renumber when needed** - When inserting or reordering steps

## Todo List Integration

Each todo item corresponds to a numbered step:

```
1. [in_progress] Load data (01_load_data.py)
2. [pending] Clean data (02_clean_data.py)
3. [pending] Run analysis (03_analysis.py)
```

This makes progress tracking natural and clear.
