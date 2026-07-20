# cc-toolkit

Unified Claude Code and Codex plugin marketplace for development workflows, task-loop orchestration, scientific content creation, and document processing.

## Overview

**cc-toolkit** is a modular plugin marketplace following the Claude Code plugin system, with Codex plugin support where a plugin has been ported. Each plugin is self-contained and can include skills, agents, hooks, commands, scripts, and Codex-specific manifests.

## Repository Structure

```
cc-toolkit/
├── .claude-plugin/
│   └── marketplace.json           # Claude Code plugin registry
├── .agents/
│   └── plugins/
│       └── marketplace.json       # Codex plugin registry
├── dev-skills/                     # Development workflow plugin
│   ├── .claude-plugin/
│   │   └── plugin.json
│   ├── .codex-plugin/
│   │   └── plugin.json
│   ├── skills/
│   │   ├── problem-solving-cycle/
│   │   └── step-workflow/
│   └── codex-skills/
│       ├── doc-update/
│       ├── goal-rubric/
│       ├── pressure-test/
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
    ├── skills/
    │   └── pymol-mcp/
    └── commands/
        └── setup.md
```

## Available Plugins

### Development Skills (`dev-skills`)
Development workflow automation and systematic problem-solving.

**Skills:**
- **problem-solving-cycle**: Systematic development workflow from brainstorming to PR merge, including issue creation, branch management, and cleanup
- **step-workflow**: Step-based file naming and folder organization using numbered prefixes (01_, 02_, 03_) for clear workflow order
- **discuss-with-codex**: Autonomous turn-by-turn adversarial discussion with the Codex CLI that converges on a saved written conclusion
- **goal-rubric**: Draft a binary pass/fail rubric and a ready-to-paste `/goal` completion condition for Claude or Codex
- **doc-update**: Update existing documentation to current project truth and audit it against a documentation quality rubric
- **pressure-test**: Run an independent adversarial review of a design, plan, PR, rubric, or task orchestration decision
- **pr-feedback**: Gather PR feedback and run a structured review-fix-push cycle
- **project-eval**: Dispatch evaluator agents for multi-angle project review
- **discord-setup**: Configure Discord plugin prerequisites

**Codex skills:**
- **doc-update**
- **goal-rubric**
- **pressure-test**
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

**Agents:**
- **paper-reader**: Analyzes research papers and answers questions about content
- **paper-consolidator**: Consolidates multiple paper analysis outputs into unified reports

### Core Hooks (`core-hooks`)
Safety guards and workflow enforcement hooks.

**Hooks:**
- **safety_guard.py**: Blocks dangerous `rm` commands and `.env` file access
- **pre_git_hook.py**: Enforces branch naming conventions, blocks bulk `git add`, prevents Claude attribution in commits
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
PyMOL molecular visualization control via MCP server.

**Skills:**
- **pymol-mcp**: Control PyMOL through natural language for protein visualization and structural analysis

**Commands:**
- **/pymol-skills:setup**: Installation instructions for PyMOL socket plugin

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
