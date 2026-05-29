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

# AI tool attribution that must not appear in commit messages or PR
# descriptions/comments.
ATTRIBUTION_PATTERNS = [
    # Claude Code
    r'Generated (?:with|by) \[?Claude Code\]?',
    r'claude\.ai/code',
    r'noreply@anthropic\.com',
    r'Claude Code',
    # Codex / OpenAI
    r'Generated (?:with|by) Codex',
    r'noreply@openai\.com',
    r'openai\.com/codex',
    r'Codex CLI',
]

# gh subcommands that introduce a PR body/comment where attribution can appear.
# [^;&|\n]* tolerates global flags (e.g. `gh -R owner/repo pr edit`) and extra
# spaces between tokens, while the excluded chars stop it from matching across
# chained (; && ||), piped, or newline-separated commands.
PR_CONTRIBUTION_RE = re.compile(r'\bgh\b[^;&|\n]*\bpr[ \t]+(?:create|edit|comment|review)\b')


def get_shell_command(tool_name, tool_input):
    if not isinstance(tool_input, dict):
        return ""
    if tool_name == "Bash":
        return tool_input.get("command", "")
    if tool_name == "exec_command":
        return tool_input.get("cmd", "")
    return ""


def split_commands(command):
    """Split a shell command line into its individual commands.

    Splits on the unquoted control operators `;`, `&`, `|` and newlines (so
    `&&`, `||` and pipelines all break a command boundary). Quote- and
    escape-aware: a separator inside '...' or "..." (e.g. a commit message or
    PR body) does not create a spurious segment, and a backslash-escaped quote
    does not prematurely close the surrounding string. `&` splits only as a
    control operator, not when it is part of a redirection token such as
    `2>&1` or `&>file`. This is a heuristic, not a full shell parser.

    Returned segments are stripped of surrounding whitespace.
    """
    segments = []
    buf = []
    quote = None
    escaped = False
    for i, ch in enumerate(command):
        if escaped:
            buf.append(ch)
            escaped = False
            continue
        if ch == '\\' and quote != "'":
            # A backslash escapes the next char everywhere except inside single
            # quotes, where bash treats it literally. Without this, an escaped
            # quote desyncs quote state and a later separator can be swallowed
            # into one segment, re-masking an invalid branch creation (#107).
            escaped = True
            buf.append(ch)
            continue
        if quote:
            buf.append(ch)
            if ch == quote:
                quote = None
        elif ch in ("'", '"'):
            quote = ch
            buf.append(ch)
        elif ch in (';', '|', '\n'):
            segments.append(''.join(buf))
            buf = []
        elif ch == '&' and command[i - 1:i] != '>' and command[i + 1:i + 2] != '>':
            # `&` is a boundary only as a control operator (`&`, `&&`). Adjacent
            # to `>` it is part of a redirection (`2>&1`, `&>file`), not a split.
            segments.append(''.join(buf))
            buf = []
        else:
            buf.append(ch)
    segments.append(''.join(buf))
    return [seg.strip() for seg in segments if seg.strip()]


def extract_branch_name(command):
    # [^\s;|&]+ instead of \S+ to stop at shell metacharacters (; && || |).
    # [ \t]+ (not \s+) for separators so a newline cannot pull in the next
    # command's first token as a false branch name (see issue #104).
    m = re.search(r'git checkout -b[ \t]+([^\s;|&]+)', command)
    if m:
        return m.group(1)

    m = re.search(r'git switch -c[ \t]+([^\s;|&]+)', command)
    if m:
        return m.group(1)

    if 'git worktree add' in command:
        m = re.search(r'git worktree add[ \t]+[^\s;|&]+[ \t]+(?:-b|--branch)[ \t]+([^\s;|&]+)', command)
        if m:
            return m.group(1)
        m = re.search(r'git worktree add[ \t]+[^\s;|&]+[ \t]+([a-zA-Z][\w-]*)', command)
        if m:
            return m.group(1)
        m = re.search(r'git worktree add[ \t]+([^\s;|&]+)', command)
        if m:
            return os.path.basename(m.group(1))
        return None

    # Rename/copy: short flags (-m/-M/-c/-C) and long flags (--move/--copy)
    m = re.search(r'git branch[ \t]+(?:-[mMcC]|--move|--copy)[ \t]+[^\s;|&]+[ \t]+([^\s;|&]+)', command)
    if m:
        return m.group(1)
    m = re.search(r'git branch[ \t]+(?:-[mMcC]|--move|--copy)[ \t]+([^\s;|&]+)', command)
    if m:
        return m.group(1)

    # Bare creation — skip read-only/delete flags. Callers pass one command at a
    # time (see split_commands / check_branch_names), so a listing/delete here
    # cannot mask a real creation elsewhere in a compound command.
    if re.search(r'git branch[ \t]+(-[ladDvrV]|--list|--all|--delete|--remotes)', command):
        return None
    m = re.search(r'git branch[ \t]+(?!-)([^\s;|&]+)', command)
    if m:
        return m.group(1)


def check_branch_names(command):
    """Inspect every sub-command for a branch being created.

    Evaluating each command separately stops an invalid creation from being
    masked by a read-only/delete invocation or an earlier valid creation in the
    same compound command (issue #107). Returns (invalid_name, saw_valid_name):
    the first invalid-prefix branch found (or None) and whether any valid branch
    name was seen.
    """
    invalid = None
    saw_valid = False
    for segment in split_commands(command):
        name = extract_branch_name(segment)
        if not name:
            continue
        if any(name.startswith(p) for p in VALID_PREFIXES):
            saw_valid = True
        elif invalid is None:
            invalid = name
    return invalid, saw_valid


def main():
    try:
        input_data = json.loads(sys.stdin.read())
    except json.JSONDecodeError:
        print("Error: Invalid JSON input", file=sys.stderr)
        sys.exit(1)

    tool_name = input_data.get("tool_name", "")
    tool_input = input_data.get("tool_input", {})

    command = get_shell_command(tool_name, tool_input)
    if command:
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

        # AI attribution is a hard block. Check it before the advisory handlers
        # below so a compound command (e.g. `gh pr edit ... && gh pr merge`)
        # cannot short-circuit the deny via an earlier advisory exit.
        is_contribution_cmd = bool("git commit" in command or PR_CONTRIBUTION_RE.search(command))
        if is_contribution_cmd:
            for pattern in ATTRIBUTION_PATTERNS:
                if re.search(pattern, command, re.IGNORECASE):
                    response = {
                        "systemMessage": "BLOCKED: Git operation contains AI tool attribution. Remove AI contribution messages from commit messages and PR descriptions/comments.",
                        "hookSpecificOutput": {
                            "hookEventName": "PreToolUse",
                            "permissionDecision": "deny",
                            "permissionDecisionReason": "AI tool attribution detected in git operation"
                        }
                    }
                    print(json.dumps(response))
                    sys.exit(0)

        invalid_branch, saw_valid_branch = check_branch_names(command)
        if invalid_branch:
            response = {
                "systemMessage": f"Branch name '{invalid_branch}' is invalid. Use only these prefixes: {', '.join(VALID_PREFIXES)}",
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": f"Branch name must start with one of: {', '.join(VALID_PREFIXES)}"
                }
            }
            print(json.dumps(response))
            sys.exit(0)

        if saw_valid_branch:
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

        if is_contribution_cmd:
            response = {
                "systemMessage": "Contribution Guidelines: Keep messages concise and accurate. Avoid AI attribution in commit messages or PR descriptions/comments."
            }
            print(json.dumps(response))
            sys.exit(0)

    sys.exit(0)


if __name__ == "__main__":
    main()
