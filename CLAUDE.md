# Claude Code Toolkit

## Project Overview

**cc-toolkit** is a unified Claude Code plugin marketplace that extends Claude Code functionality. This is a modular plugin system that provides capabilities for development workflows, scientific content creation, and document processing.

### Purpose
- Store and version-control custom Claude Code plugins (skills, agents, hooks)
- Enable discovery and reusability of modular capabilities through a unified marketplace
- Provide systematic development workflow automation
- Facilitate scientific content creation and document processing
- Support personal workflow automation and development practices

### Key Technologies
- Claude Code plugin system (official modular architecture)
- GitHub Actions for CI/CD automation
- Git worktrees for isolated development environments
- GitHub CLI (gh) for issue and PR management

## Repository Structure

```
cc-toolkit/
├── .claude-plugin/
│   └── marketplace.json                 # Plugin marketplace registry
├── .github/
│   └── workflows/
│       ├── claude-code-review.yml       # Claude Code Review automation
│       └── claude.yml                   # Claude Code trigger automation
├── cc-customize/                        # Claude Code customization plugin
│   ├── .claude-plugin/
│   │   └── plugin.json
│   └── skills/
│       ├── compact-percentage/
│       │   └── SKILL.md
│       └── statusline-setup/
│           ├── SKILL.md
│           └── scripts/
│               └── statusline-command.sh
├── dev-skills/                          # Development workflow plugin
│   ├── .claude-plugin/
│   │   └── plugin.json                  # Plugin manifest
│   └── skills/
│       ├── pr-feedback/
│       │   └── SKILL.md
│       ├── problem-solving-cycle/
│       │   └── SKILL.md
│       └── step-workflow/
│           └── SKILL.md
├── creator-skills/                      # Scientific content creation plugin
│   ├── .claude-plugin/
│   │   └── plugin.json
│   └── skills/
│       ├── sci-figure-format/
│       │   └── SKILL.md
│       └── sci-slides/
│           └── SKILL.md
├── doc-skills/                          # Document processing plugin
│   ├── .claude-plugin/
│   │   └── plugin.json
│   ├── skills/
│   │   ├── docling-pdf/
│   │   │   └── SKILL.md
│   │   └── paper-rename/
│   │       └── SKILL.md
│   └── agents/
│       ├── paper-reader.md
│       └── paper-consolidator.md
├── productivity-skills/                 # Personal productivity plugin
│   ├── .claude-plugin/
│   │   └── plugin.json
│   └── skills/
│       ├── calendar-manager/
│       │   └── SKILL.md
│       ├── gtd-inbox/
│       │   └── SKILL.md
│       ├── gtd-next/
│       │   └── SKILL.md
│       ├── gtd-process/
│       │   └── SKILL.md
│       ├── gtd-project/
│       │   └── SKILL.md
│       └── reminder-manager/
│           └── SKILL.md
├── pymol-skills/                        # PyMOL molecular visualization plugin
│   ├── .claude-plugin/
│   │   └── plugin.json
│   └── skills/
│       ├── pymol-mcp/
│       │   └── SKILL.md
│       └── pymol-setup/
│           └── SKILL.md
├── logs/                                # Claude Code execution logs
├── trees/                               # Git worktrees for active development
└── README.md                            # Project overview
```

## Development Commands

### Setting Up for Development
```bash
# Clone the repository
git clone git@github.com:aeghnnsw/cc-toolkit.git

# Navigate to repository
cd cc-toolkit
```

### Creating a New Skill
Skills are defined by a `SKILL.md` file placed in a plugin's `skills/` directory. Each plugin has its own `plugin.json` manifest that registers its skills and agents.

Example skill structure:
```
<plugin-name>/
├── .claude-plugin/
│   └── plugin.json          # Plugin manifest
└── skills/
    └── my-new-skill/
        └── SKILL.md         # Skill definition
```

### Using the Problem-Solving Cycle Workflow
This is the primary skill included in the repository. It provides guidance for:
- Issue-driven development
- Branch creation and worktree management
- PR-based code review
- Merge and cleanup

Use this workflow by asking Claude Code to apply the "problem-solving-cycle" skill.

### Managing Worktrees
The repository uses git worktrees stored in the `trees/` directory for isolated development:

```bash
# Create a worktree for a new feature
git worktree add trees/feat-<issue>-<description> feat-<issue>-<description>

# Navigate into worktree
cd trees/feat-<issue>-<description>

# Complete your development work

# Return to main repo
cd /path/to/main/repo

# Remove worktree after work is complete
git worktree remove trees/feat-<issue>-<description>
```

### Publishing Changes
```bash
# Push branch to remote with tracking
git push -u origin <branch-name>

# Create PR via GitHub CLI
gh pr create --title "Brief title" --body "Description and closes #<issue>"

# Merge PR after review
gh pr merge <pr-number> --merge
```

### Managing the Plugin Marketplace

#### Root Marketplace Registry
The `.claude-plugin/marketplace.json` file maintains the plugin registry:

```json
{
  "name": "cc-toolkit",
  "plugins": [
    {
      "name": "dev-skills",
      "source": "./dev-skills"
    },
    {
      "name": "creator-skills",
      "source": "./creator-skills"
    },
    {
      "name": "doc-skills",
      "source": "./doc-skills"
    }
  ]
}
```

#### Plugin Manifest
Each plugin has a `.claude-plugin/plugin.json` manifest:

```json
{
  "name": "dev-skills",
  "description": "Development workflow skills",
  "version": "1.0.0"
}
```

**Note:** Skills and agents are auto-discovered from their respective directories (`skills/` and `agents/`). You do NOT need to list them explicitly in `plugin.json`.

To add a new skill to an existing plugin:
1. Create the skill directory and `SKILL.md` in the plugin's `skills/` directory
2. The skill will be automatically discovered
3. Commit changes

To add a new plugin:
1. Create the plugin directory with `.claude-plugin/plugin.json`
2. Add skills in `skills/` subdirectory (auto-discovered)
3. Add agents in `agents/` subdirectory if needed (auto-discovered)
4. Update root `marketplace.json` to reference the new plugin
5. Commit changes

### Testing/Verification
Since this is a skill repository (not application code), testing consists of:
- Verifying SKILL.md files have correct frontmatter and content
- Checking marketplace.json validity
- Ensuring workflow files are valid GitHub Actions YAML

Manual verification:
```bash
# Validate JSON marketplace configuration
cat .claude-plugin/marketplace.json | jq .

# Validate YAML workflows
# (GitHub will validate on push)
```

### No Build or Lint Steps
This repository does not require:
- Compilation/transpilation
- Linting (markdown and JSON are simple text formats)
- Installation of dependencies
- Test execution

It is a configuration and documentation repository.

## Code Architecture

### Plugin System Architecture
The repository follows the official Claude Code plugin system with a modular architecture:

1. **Marketplace Registry** (`.claude-plugin/marketplace.json`)
   - Root registry pointing to plugin directories
   - Enables discovery of all plugins in the marketplace
   - Simple source-based plugin references

2. **Plugin Manifest** (`<plugin>/.claude-plugin/plugin.json`)
   - Each plugin has its own manifest
   - Declares plugin name, description, version
   - Skills and agents are auto-discovered from default directories
   - Makes plugin self-contained and portable

3. **Skill Definition** (`SKILL.md`)
   - YAML frontmatter (name, description)
   - Markdown documentation of workflow/capability
   - Usage guidance for when/how to invoke
   - Located in plugin's `skills/` subdirectory (auto-discovered)

4. **Agent Definition** (`.md` files)
   - Agent configuration and behavior
   - Located in plugin's `agents/` subdirectory (auto-discovered)

5. **Discovery Flow**
   - Claude Code reads root marketplace.json
   - Loads each plugin's plugin.json manifest
   - Auto-discovers skills from `skills/` directory
   - Auto-discovers agents from `agents/` directory
   - Matches user requests to appropriate capabilities

### Problem-Solving Cycle Skill
The core skill defines a complete development workflow with 8 phases:

**Phase 1: Brainstorming**
- Discuss problem and solutions with user
- Understand requirements and constraints
- Categorize change type (feature, bugfix, docs, refactor, chore, test)

**Phase 2: Issue Creation**
- Create GitHub issue via `gh issue create`
- Document problem and solution approach
- Note issue number for branch naming

**Phase 3: Worktree & Branch Setup**
- Create isolated git worktree
- Follow branch naming convention: `<type>-<issue>-<description>`
- Types: feat, bugfix, doc, refactor, chore, test

**Phase 4: Development & Testing**
- Implement changes in worktree
- Write/update tests
- Run test suite before PR

**Phase 5: Push & PR Creation**
- Push branch with tracking: `git push -u origin`
- Create PR with simple, concise description
- Reference issue: "Closes #<number>"

**Phase 6: Review Process**
- Respond to reviewer feedback
- Make requested changes
- Re-run tests after updates

**Phase 7: Merge & Close**
- Merge via `gh pr merge --merge` (not squash)
- Issue auto-closes if PR description references it

**Phase 8: Cleanup**
- Remove worktree: `git worktree remove trees/<type>-<issue>-<description>`
- Delete local branch if needed
- Keep workspace organized

### GitHub Actions Integration
The repository includes two automation workflows:

**1. Claude Code Review Workflow** (claude-code-review.yml)
- Triggers on PR open/sync
- Uses Claude Code to review code quality, bugs, performance, security, test coverage
- Posts review as PR comment
- Uses repository CLAUDE.md for style guidance
- Restricted tool access for security

**2. Claude Code Trigger Workflow** (claude.yml)
- Triggers on comments, PR reviews, and issues
- Responds to @claude mentions
- Executes custom Claude Code commands based on context
- Can read CI results on PRs
- Flexible prompt and tool restrictions

Both workflows use OAuth token authentication and restrict Claude Code tool access for security.

## Development Patterns & Conventions

### Branch Naming Convention
All branches follow strict naming with prefixes:
- `feat-<issue>-<description>` - New features
- `bugfix-<issue>-<description>` - Bug fixes
- `doc-<issue>-<description>` - Documentation
- `refactor-<issue>-<description>` - Refactoring
- `chore-<issue>-<description>` - Maintenance
- `test-<issue>-<description>` - Tests

Issue number is mandatory and used for linking.

### Communication Style
- Simple, concise issue and PR descriptions
- Focus on "why" not "what"
- No unnecessary boilerplate
- No test plans in PR descriptions
- No "Created by Claude Code" attribution messages
- Plain, professional language

### Git Workflow Principles
1. **Issue-Driven**: Every change starts with a documented issue
2. **Isolated Development**: Use worktrees to keep work separated
3. **Consistent Naming**: Follow branch naming conventions strictly
4. **Test Before PR**: Always run tests before creating PRs
5. **Simple Communication**: Keep issues and PRs concise and clear
6. **Clean History**: Use regular merges to preserve commit context
7. **Proper Cleanup**: Remove worktrees and branches when done

### Flexibility
While the workflow is structured, adapt based on context:
- Small changes may skip extensive brainstorming
- Urgent fixes may proceed more quickly
- Complex features may need longer development cycles
- Multiple worktrees can run simultaneously for related changes

## Configuration Rules

### From User's Global CLAUDE.md
The following rules apply to all commits, issues, and PRs:
- Do not add "created by claude code" or similar attribution messages
- Keep PR descriptions simple, concise and accurate
- Do not create test plans in PR descriptions

## Repository-Specific Notes

### Worktree Directory
The `trees/` directory contains active git worktrees. These are temporary working directories and should not be committed to version control (git worktrees are inherently local). The directory is listed in `.gitignore`.

### Logs Directory
The `logs/` directory contains Claude Code execution logs from GitHub Actions. These are local artifacts and not committed.

### Marketplace and Plugin Configuration

#### Root Marketplace
The root `marketplace.json` must be updated whenever:
- A new plugin is added to the marketplace
- A plugin is removed or renamed
- Plugin source paths change

#### Plugin Manifests
Each plugin's `plugin.json` must be updated whenever:
- Plugin description or version changes
- Hooks configuration changes

**Note:** Skills and agents are auto-discovered from `skills/` and `agents/` directories. No manifest update is needed when adding or removing them.

### Skill Documentation
Each skill's `SKILL.md` file serves as both:
- Documentation for humans understanding the skill
- Context for Claude Code deciding when to invoke the skill
- Guidance for Claude Code on how to execute the skill

Well-written skill documentation is critical for discoverability and correct usage.

