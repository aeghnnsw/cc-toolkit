#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.8"
# ///
"""
Claude Code hook for git operations.
Adds context reminders before git commits and PR creation.
"""

import json
import os
import re
import sys


VALID_PREFIXES = ['feat-', 'bugfix-', 'doc-', 'refactor-', 'chore-', 'test-']


def extract_branch_name(command):
    # [^\s;|&]+ instead of \S+ to stop at shell metacharacters (; && || |)
    m = re.search(r'git checkout -b\s+([^\s;|&]+)', command)
    if m:
        return m.group(1)

    m = re.search(r'git switch -c\s+([^\s;|&]+)', command)
    if m:
        return m.group(1)

    if 'git worktree add' in command:
        m = re.search(r'git worktree add\s+[^\s;|&]+\s+(?:-b|--branch)\s+([^\s;|&]+)', command)
        if m:
            return m.group(1)
        m = re.search(r'git worktree add\s+[^\s;|&]+\s+([a-zA-Z][\w-]*)', command)
        if m:
            return m.group(1)
        m = re.search(r'git worktree add\s+([^\s;|&]+)', command)
        if m:
            return os.path.basename(m.group(1))
        return None

    # Rename/copy: short flags (-m/-M/-c/-C) and long flags (--move/--copy)
    m = re.search(r'git branch\s+(?:-[mMcC]|--move|--copy)\s+[^\s;|&]+\s+([^\s;|&]+)', command)
    if m:
        return m.group(1)
    m = re.search(r'git branch\s+(?:-[mMcC]|--move|--copy)\s+([^\s;|&]+)', command)
    if m:
        return m.group(1)

    # Bare creation — skip read-only/delete flags
    if re.search(r'git branch\s+(-[ladDvrV]|--list|--all|--delete|--remotes)', command):
        return None
    m = re.search(r'git branch\s+(?!-)([^\s;|&]+)', command)
    if m:
        return m.group(1)


def main():
    try:
        input_data = json.loads(sys.stdin.read())
    except json.JSONDecodeError:
        print("Error: Invalid JSON input", file=sys.stderr)
        sys.exit(1)

    tool_name = input_data.get("tool_name", "")
    tool_input = input_data.get("tool_input", {})

    if tool_name == "Bash":
        command = tool_input.get("command", "")

        if re.search(r'git add\s+(-A|--all|\.(?:\s|$)|\.\/(?:\s|$))', command):
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

        branch_name = extract_branch_name(command)
        if branch_name:
            if not any(branch_name.startswith(p) for p in VALID_PREFIXES):
                response = {
                    "systemMessage": f"Branch name '{branch_name}' is invalid. Use only these prefixes: {', '.join(VALID_PREFIXES)}",
                    "hookSpecificOutput": {
                        "hookEventName": "PreToolUse",
                        "permissionDecision": "deny",
                        "permissionDecisionReason": f"Branch name must start with one of: {', '.join(VALID_PREFIXES)}"
                    }
                }
                print(json.dumps(response))
                sys.exit(0)

            response = {
                "systemMessage": "Branch Naming Convention: Using approved prefix - good practice!"
            }
            print(json.dumps(response))
            sys.exit(0)

        if "gh pr merge" in command and "--squash" not in command:
            response = {
                "systemMessage": "Merge Strategy: Prefer --squash when merging PRs to keep history clean."
            }
            print(json.dumps(response))
            sys.exit(0)

        elif "git commit" in command or "gh pr create" in command:
            claude_patterns = [
                r'Generated with \[Claude Code\]',
                r'claude\.ai/code',
                r'noreply@anthropic\.com',
                r'Generated with',
                r'Claude Code'
            ]

            for pattern in claude_patterns:
                if re.search(pattern, command, re.IGNORECASE):
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

            response = {
                "systemMessage": "Commit Guidelines: Keep messages concise and accurate. Avoid AI attribution in commit messages or PR descriptions."
            }
            print(json.dumps(response))
            sys.exit(0)

    sys.exit(0)


if __name__ == "__main__":
    main()
