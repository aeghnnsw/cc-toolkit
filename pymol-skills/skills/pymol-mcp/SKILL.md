---
name: pymol-mcp
version: 1.0.0
description: Control PyMOL molecular visualization software through natural language. This skill should be used when the user wants to visualize protein structures, create molecular representations, perform structural analysis, or generate publication-quality molecular images using PyMOL.
---

# PyMOL MCP Integration

## Overview

Control PyMOL molecular visualization software directly from Claude using the Model Context Protocol (MCP). Execute PyMOL commands, create visualizations, and perform structural analysis through natural language.

## When to Use This Skill

Use this skill when the user wants to:
- Load and visualize protein/molecular structures (PDB, CIF, etc.)
- Create molecular representations (cartoon, surface, sticks, etc.)
- Color molecules by chain, secondary structure, or custom selections
- Perform structural alignments and superpositions
- Measure distances, angles, and dihedrals
- Generate publication-quality images

## Prerequisites

Before using PyMOL commands, ensure:
1. PyMOL is running with the socket plugin active
2. The plugin shows "Listening on port 9876"

Run `/pymol-skills:setup` for installation instructions.

## Available MCP Tools

### pymol_command
Execute direct PyMOL commands using native syntax.

**Examples:**
```
fetch 1ubq              # Load structure from PDB
show cartoon, all       # Display as cartoon
color red, chain A      # Color chain A red
bg_color white          # Set white background
zoom all                # Zoom to fit all
```

### pymol_python_api
Execute PyMOL Python API commands for complex operations.

**Examples:**
```python
cmd.fetch('1ubq')
cmd.show('cartoon', 'all')
cmd.color('red', 'chain A')
cmd.align('mobile', 'target')
cmd.select('active_site', 'resi 50-100')
```

## Common Workflows

### Load and Visualize a Protein
1. Fetch structure: `fetch 1ubq`
2. Set representation: `show cartoon`
3. Color by chain: `color auto, all`
4. Set background: `bg_color white`

### Compare Two Structures
1. Fetch both: `fetch 1ubq` and `fetch 1ubi`
2. Align: `align 1ubi, 1ubq`
3. Color differently: `color green, 1ubq` and `color cyan, 1ubi`

### Highlight Active Site
1. Select residues: `select active, resi 45-50`
2. Show as sticks: `show sticks, active`
3. Color highlight: `color yellow, active`

## Troubleshooting

- **Connection refused**: Start PyMOL socket plugin before using commands
- **Command not recognized**: Check PyMOL command syntax
- **No output**: Some commands don't produce visible output
