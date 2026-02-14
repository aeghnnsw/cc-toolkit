#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.8"
# ///
"""
Claude Code hook for git operations.
Adds context reminders before git commits and PR creation.
"""

import json
import sys

def main():
    # Read input from stdin
    try:
        input_data = json.loads(sys.stdin.read())
    except json.JSONDecodeError:
        print("Error: Invalid JSON input", file=sys.stderr)
        sys.exit(1)

    tool_name = input_data.get("tool_name", "")
    tool_input = input_data.get("tool_input", {})

    # Check if this is a git operation
    if tool_name == "Bash":
        command = tool_input.get("command", "")
        import re
        # Block git add . and git add -A operations
        if re.search(r'git add\s+(-A|--all|\.|\.\/)', command):
            # Allow git add for specific dotfiles, but block git add . and git add -A
            # Check if it's adding a specific dotfile (like .gitignore, .env.example, etc.)
            dotfile_pattern = r'git add \.[a-zA-Z][a-zA-Z0-9._-]*(?:\s|$)'
            if not re.search(dotfile_pattern, command) or re.search(r'git add\s+(-A|--all|\s+\.\s*$)', command):
                # Block bulk git add operations
                response = {
                    "systemMessage": "BLOCKED: Use 'git add <filename>' with specific file names instead of 'git add .', 'git add -A', or 'git add --all' for precise change control.",
                    "hookSpecificOutput": {
                        "hookEventName": "PreToolUse",
                        "permissionDecision": "deny",
                        "permissionDecisionReason": "Bulk git add operations are prohibited - use specific file names"
                    }
                }
                print(json.dumps(response))
                sys.exit(0)
        elif "git checkout -b" in command or "git switch -c" in command or "git worktree add" in command:
            # Extract branch name and validate naming convention
            import re

            # Extract branch name from command
            branch_name = None
            if "git checkout -b" in command:
                match = re.search(r'git checkout -b\s+(\S+)', command)
                if match:
                    branch_name = match.group(1)
            elif "git switch -c" in command:
                match = re.search(r'git switch -c\s+(\S+)', command)
                if match:
                    branch_name = match.group(1)
            elif "git worktree add" in command:
                # Match git worktree add with -b or --branch flag
                match = re.search(r'git worktree add\s+\S+\s+(?:-b|--branch)\s+(\S+)', command)
                if match:
                    branch_name = match.group(1)
                else:
                    # Check for positional branch name: git worktree add <path> <branch>
                    match = re.search(r'git worktree add\s+\S+\s+([a-zA-Z][\w-]*)', command)
                    if match:
                        branch_name = match.group(1)
                    else:
                        # No explicit branch — git derives branch name from last path component
                        # e.g. git worktree add trees/my-feature -> branch "my-feature"
                        match = re.search(r'git worktree add\s+(\S+)', command)
                        if match:
                            import os
                            branch_name = os.path.basename(match.group(1))

            if branch_name:
                valid_prefixes = ['feat-', 'bugfix-', 'doc-', 'refactor-', 'chore-', 'test-']

                if not any(branch_name.startswith(prefix) for prefix in valid_prefixes):
                    # Block invalid branch name
                    response = {
                        "systemMessage": f"Branch name '{branch_name}' is invalid. Use only these prefixes: feat-, bugfix-, doc-, refactor-, chore-, test-",
                        "hookSpecificOutput": {
                            "hookEventName": "PreToolUse",
                            "permissionDecision": "deny",
                            "permissionDecisionReason": f"Branch name must start with one of: {', '.join(valid_prefixes)}"
                        }
                    }
                    print(json.dumps(response))
                    sys.exit(0)

            # Valid branch name, just show reminder
            response = {
                "systemMessage": "Branch Naming Convention: Using approved prefix - good practice!"
            }
            print(json.dumps(response))
            sys.exit(0)
        elif "gh pr merge" in command and "--squash" not in command:
            # Encourage squash merge
            response = {
                "systemMessage": "Merge Strategy: Prefer --squash when merging PRs to keep history clean."
            }
            print(json.dumps(response))
            sys.exit(0)
        elif "git commit" in command or "gh pr create" in command:
            # Check for Claude Code attribution patterns
            import re
            claude_patterns = [
                r'Generated with \[Claude Code\]',
                r'claude\.ai/code',
                r'Co-Authored-By: Claude <noreply@anthropic\.com>',
                r'Generated with',
                r'Claude Code'
            ]

            # Check the command content for Claude attribution
            for pattern in claude_patterns:
                if re.search(pattern, command, re.IGNORECASE):
                    # Block the operation
                    response = {
                        "systemMessage": "BLOCKED: Git operation contains Claude Code attribution. Remove AI contribution messages from commit messages and PR descriptions.",
                        "hookSpecificOutput": {
                            "hookEventName": "PreToolUse",
                            "permissionDecision": "deny",
                            "permissionDecisionReason": "Claude Code attribution detected in git operation"
                        }
                    }
                    print(json.dumps(response))
                    sys.exit(0)

            # Output JSON with systemMessage to show reminder to user
            response = {
                "systemMessage": "Commit Guidelines: Keep messages concise and accurate. Avoid AI attribution in commit messages or PR descriptions."
            }
            print(json.dumps(response))
            sys.exit(0)

    # Allow the operation to continue (no git operation detected)
    sys.exit(0)

if __name__ == "__main__":
    main()
