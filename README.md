# cc-toolkit

Unified Claude Code and Codex plugin marketplace for development workflows, task-loop orchestration, scientific content creation, and document processing.

## Overview

**cc-toolkit** is a modular plugin marketplace following the Claude Code plugin system, with Codex plugin support where a plugin has been ported. Each plugin is self-contained and can include skills, agents, hooks, commands, scripts, and Codex-specific manifests.

## Development

This repository contains both plugin source and shared contributor documentation.
The marketplace registries select individual plugin directories for distribution.
See [CONTRIBUTING.md](CONTRIBUTING.md) for what belongs in Git, local exclusions,
and verification, and [CLAUDE.md](CLAUDE.md) for the development workflow.
`AGENTS.md` links to the same instructions. The documents under `docs/agents/`
configure work on this repository; using its plugins does not require installing
Matt Pocock's development skills.

## Repository Structure

```
cc-toolkit/
├── .claude-plugin/
│   └── marketplace.json           # Claude Code plugin registry
├── .agents/
│   └── plugins/
│       └── marketplace.json       # Codex plugin registry
├── CLAUDE.md                       # Shared contributor instructions
├── AGENTS.md                       # Symlink to CLAUDE.md
├── CONTRIBUTING.md                 # Repository boundaries and verification
├── docs/
│   ├── agents/                     # Shared development skill configuration
│   ├── adr/                        # Accepted architecture decisions
│   └── superpowers/                # Design and planning documents
├── cc-customize/                   # Claude Code model, statusline, and prompt config skills
├── dev-skills/                     # Development workflow plugin
│   ├── .claude-plugin/
│   │   └── plugin.json
│   ├── .codex-plugin/
│   │   └── plugin.json
│   ├── skills/
│   │   ├── discord-setup/
│   │   ├── discuss-with-codex/
│   │   ├── doc-update/
│   │   ├── goal-rubric/
│   │   ├── matt-automode/
│   │   ├── pr-feedback/
│   │   ├── project-eval/
│   │   ├── repo-cleanup/
│   │   └── step-workflow/
│   └── codex-skills/
│       ├── doc-update/
│       ├── goal-rubric/
│       ├── matt-automode/
│       ├── pressure-test/
│       ├── repo-cleanup/
│       └── step-workflow/
├── creator-skills/                 # Scientific content creation plugin
│   ├── .claude-plugin/
│   │   └── plugin.json
│   ├── .codex-plugin/
│   │   └── plugin.json
│   ├── skills/
│   │   ├── sci-figure-format/
│   │   └── sci-slides/
│   └── codex-skills/
│       ├── sci-figure-format/
│       └── sci-slides/
├── doc-skills/                     # Document processing plugin
│   ├── .claude-plugin/
│   │   └── plugin.json
│   ├── skills/
│   │   ├── docling-pdf/
│   │   └── paper-rename/
│   └── agents/
│       ├── paper-reader.md
│       └── paper-consolidator.md
├── core-hooks/                     # Safety and workflow hooks plugin
│   ├── .claude-plugin/
│   │   └── plugin.json
│   ├── .codex-plugin/
│   │   └── plugin.json
│   ├── hooks/
│   │   └── hooks.json
│   └── scripts/
│       ├── safety_guard.py
│       ├── pre_git_hook.py
│       ├── post_tool_use.py
│       └── system_notification.py
├── task-loop/                      # Supabase-backed task-loop workflow plugin
│   ├── .claude-plugin/
│   │   └── plugin.json
│   ├── .codex-plugin/
│   │   └── plugin.json
│   ├── claude-skills/
│   ├── codex-skills/
│   ├── codex-agents/
│   ├── hooks/
│   ├── scripts/
│   └── cli/
├── productivity-skills/            # Personal productivity plugin
│   ├── .claude-plugin/
│   │   └── plugin.json
│   ├── .codex-plugin/
│   │   └── plugin.json
│   ├── skills/
│   │   ├── calendar-manager/
│   │   └── reminder-manager/
│   └── codex-skills/
│       ├── calendar-manager/
│       └── reminder-manager/
└── pymol-skills/                   # PyMOL molecular visualization plugin
    ├── .claude-plugin/
    │   └── plugin.json
    ├── .codex-plugin/
    │   └── plugin.json
    ├── skills/
    │   ├── pymol-mcp/
    │   └── pymol-setup/
    └── codex-skills/
        ├── pymol-mcp/
        └── pymol-setup/
```

## Available Plugins

### Development Skills (`dev-skills`)
Development workflows, repository hygiene, documentation, and review.

**Skills:**
- **repo-cleanup**: Remove merged worktrees and branches, prune the upstream remote, reconcile completed issues, and update the Default Branch
- **step-workflow**: Step-based file naming and folder organization using numbered prefixes (01_, 02_, 03_) for clear workflow order
- **discuss-with-codex**: Autonomous turn-by-turn adversarial discussion with the Codex CLI that converges on a saved written conclusion
- **goal-rubric**: Draft a binary pass/fail rubric and a ready-to-paste `/goal` completion condition for Claude or Codex
- **doc-update**: Update existing documentation to current project truth and audit it against a documentation quality rubric
- **matt-automode**: Run Matt’s planning, ticket implementation, PR merge, and cleanup workflows without human checkpoints; requires the Matt skills plugin
- **pressure-test** (Codex): Run an independent adversarial review of a design, plan, PR, rubric, or task orchestration decision
- **pr-feedback**: Gather PR feedback and run a structured review-fix-push cycle
- **project-eval**: Dispatch evaluator agents for multi-angle project review
- **discord-setup**: Configure Discord plugin prerequisites

**Codex skills:**
- **doc-update**
- **goal-rubric**
- **matt-automode**
- **pressure-test**
- **repo-cleanup**
- **step-workflow**

### Creator Skills (`creator-skills`)
Scientific content creation for figures and presentations.

**Skills:**
- **sci-figure-format**: Publication-quality scientific figure formatting for major journals (Nature, Science, ACS, RSC)
- **sci-slides**: Academic presentation slide creation for STEM fields

**Codex skills:**
- **sci-figure-format**
- **sci-slides**

### Document Skills (`doc-skills`)
Document processing and AI-accessible content extraction.

**Skills:**
- **docling-pdf**: PDF to markdown conversion using IBM's Docling library
- **paper-rename**: Intelligent PDF renaming based on extracted titles and metadata

**Agents (deprecated; retained for compatibility):**
- **paper-reader**: Analyzes research papers and answers questions about content
- **paper-consolidator**: Consolidates multiple paper analysis outputs into unified reports

### Core Hooks (`core-hooks`)
Safety guards and workflow enforcement hooks.

**Hooks:**
- **safety_guard.py**: Blocks dangerous `rm` commands
- **pre_git_hook.py**: Checks Git policy, including branch prefixes, bulk staging, and AI attribution
- **post_tool_use.py**: Logs tool executions to `logs/post_tool_use.json`
- **system_notification.py**: Plays sound notifications on task completion

### Task Loop (`task-loop`)
Supabase-backed task board plus proposal, cycle scaffolding, and worker support.

**Claude Code support:**
- **setup**: Configure Supabase credentials, register the repo, and check required tools and skills
- **specify-aims**: Write `docs/task-loop/proposal.md`
- **create-cycle**: Render `docs/task-loop/task-loop.md`, `directions.md`, and logs scaffolding
- **run-cycle**: Drive the orchestrator and Claude cycle-worker agent

**Codex support:**
- **setup**: Check prerequisites and sync the `task_loop_cycle_worker` custom agent
- **specify-aims**: Write or re-aim the proposal
- **create-cycle**: Render Codex-compatible cycle scaffolding
- **run-cycle**: Run a conservative manual controller pass after proving worker dispatch is observable
- **task_loop_cycle_worker**: Custom agent source synced into `~/.codex/agents/` for controller dispatch

Full unattended Codex scheduling remains pending.

### Productivity Skills (`productivity-skills`)
Personal productivity automation using macOS Calendar and Reminders.

**Skills:**
- **calendar-manager**: Manage macOS Calendar events via EventKit CLI
- **reminder-manager**: Manage macOS Reminders via EventKit CLI
- **gtd-inbox**: Capture thoughts and tasks into the GTD inbox
- **gtd-process**: Process inbox items into projects or actions
- **gtd-project**: Review and manage GTD projects and their actions
- **gtd-next**: Calendar-aware task selection and time-blocked agendas
- **gtd-overview**: Read-only listing of all projects with their actions plus standalone actions

**Codex skills:**
- **calendar-manager**
- **reminder-manager**
- **gtd-inbox**
- **gtd-process**
- **gtd-project**
- **gtd-next**
- **gtd-overview**

### PyMOL Skills (`pymol-skills`)
PyMOL molecular visualization control via MCP server for Claude Code and Codex.
Both hosts share the local Python bridge and socket plugin. See the
[installation guide](pymol-skills/README.md).

**Skills:**
- **pymol-mcp**: Control PyMOL through natural language for protein visualization and structural analysis
- **pymol-setup**: Installation instructions for the PyMOL socket plugin

### Claude Code Customization (`cc-customize`)

**Skills:**
- **model-config**: Configure model, effort level, and auto-compact window
- **statusline-setup**: Configure the Claude Code statusline
- **claude-prompt-config**: Back up and replace the global Claude Code instruction file (`~/.claude/CLAUDE.md`) on this machine or a remote host

## Plugin System Benefits

1. **Modular**: Each plugin is self-contained and portable
2. **Scalable**: Easy to add new skills, agents, hooks, or commands to any plugin
3. **Standard**: Follows Claude Code and Codex plugin packaging conventions where supported
4. **Maintainable**: Clear separation of concerns between plugins
5. **Shareable**: Individual plugins can be distributed independently

## Usage

### As a Marketplace
Install the marketplace by linking to this repository from Claude Code or Codex.

### Individual Plugins
Each plugin can be used independently by referencing its directory:
- `./dev-skills`
- `./creator-skills`
- `./doc-skills`
- `./core-hooks`
- `./task-loop`
- `./productivity-skills`
- `./pymol-skills`
- `./cc-customize`
