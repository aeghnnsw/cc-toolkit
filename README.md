# cc-toolkit

Unified Claude Code plugin marketplace for development workflows, scientific content creation, and document processing.

## Overview

**cc-toolkit** is a modular plugin marketplace following the official Claude Code plugin system. Each plugin is self-contained and can include skills, agents, hooks, and commands.

## Repository Structure

```
cc-toolkit/
├── .claude-plugin/
│   └── marketplace.json           # Plugin registry
├── dev-skills/                     # Development workflow plugin
│   ├── .claude-plugin/
│   │   └── plugin.json
│   └── skills/
│       ├── problem-solving-cycle/
│       └── step-workflow/
├── creator-skills/                 # Scientific content creation plugin
│   ├── .claude-plugin/
│   │   └── plugin.json
│   └── skills/
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
└── core-hooks/                     # Safety and workflow hooks plugin
    ├── .claude-plugin/
    │   └── plugin.json
    ├── hooks/
    │   └── hooks.json
    └── scripts/
        ├── safety_guard.py
        ├── pre_git_hook.py
        ├── post_tool_use.py
        └── system_notification.py
```

## Available Plugins

### Development Skills (`dev-skills`)
Development workflow automation and systematic problem-solving.

**Skills:**
- **problem-solving-cycle**: Systematic development workflow from brainstorming to PR merge, including issue creation, branch management, and cleanup
- **step-workflow**: Step-based file naming and folder organization using numbered prefixes (01_, 02_, 03_) for clear workflow order

### Creator Skills (`creator-skills`)
Scientific content creation for figures and presentations.

**Skills:**
- **sci-figure-format**: Publication-quality scientific figure formatting for major journals (Nature, Science, ACS, RSC)
- **sci-slides**: Academic presentation slide creation for STEM fields

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

## Plugin System Benefits

1. **Modular**: Each plugin is self-contained and portable
2. **Scalable**: Easy to add new skills, agents, hooks, or commands to any plugin
3. **Standard**: Follows official Claude Code plugin system architecture
4. **Maintainable**: Clear separation of concerns between plugins
5. **Shareable**: Individual plugins can be distributed independently

## Usage

### As a Marketplace
Install the entire marketplace by linking to this repository in your Claude Code configuration.

### Individual Plugins
Each plugin can be used independently by referencing its directory:
- `./dev-skills`
- `./creator-skills`
- `./doc-skills`
- `./core-hooks`
