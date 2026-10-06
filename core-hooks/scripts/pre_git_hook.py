#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.8"
# ///
"""Cross-runtime policy hook for git operations."""

import json
import os
import re
import sys

from hook_payload import get_shell_command
from safety_guard import CONTROL_PREFIXES, strip_heredoc_bodies


VALID_PREFIXES = ['feat-', 'bugfix-', 'doc-', 'refactor-', 'chore-', 'test-']

# AI tool attribution that must not appear in commit messages or PR
# descriptions/comments.
#
# Match attribution forms, not product names. A tool's name on its own is
# descriptive and legitimate: "Add a Claude Code hook" states what a commit
# changes in a repository that develops Claude Code plugins (issue #236).
AI_TOOL_NAME = r'\[?(?:Claude(?:[ \t]+Code)?|Codex(?:[ \t]+CLI)?|Anthropic|OpenAI)\b'
CO_AUTHOR_TRAILER = r'Co-?Authored-?By:'
ATTRIBUTION_PATTERNS = [
    # Attribution wording, e.g. `Generated with [Claude Code](...)`,
    # `Co-authored by Codex`, `🤖 Created by Claude`.
    r'(?:Generated|Created|Written|Authored|Co-?authored)'
    r'[ \t]+(?:with|by)[ \t]+' + AI_TOOL_NAME,
    # Attribution trailer, e.g. `Co-Authored-By: Claude <noreply@...>`. A
    # trailer that names a person stays allowed.
    #
    # The match starts at a line start and skips to the first trailer on the
    # line; a later trailer reaches no text that the first one misses. A
    # search from every trailer would read the rest of the line again from
    # each one, which is quadratic (#280). `(?:(?!X)[^\n])*` stops at the
    # first X without an atomic group, which needs Python 3.11.
    r'(?m)^(?:(?!' + CO_AUTHOR_TRAILER + r')[^\n])*' + CO_AUTHOR_TRAILER
    + r'[^\n]*(?:Claude|Codex|Anthropic|OpenAI)\b',
    # Attribution links and addresses.
    r'claude\.ai/code',
    r'claude\.com/claude-code',
    r'noreply@anthropic\.com',
    r'openai\.com/codex',
    r'noreply@openai\.com',
]

# gh subcommands that introduce a PR body/comment where attribution can appear.
# [^;&|\n]* tolerates global flags (e.g. `gh -R owner/repo pr edit`) and extra
# spaces between tokens, while the excluded chars stop it from matching across
# chained (; && ||), piped, or newline-separated commands.
#
# As with the attribution trailer, the match starts after one of those
# separators (or at the start) and skips to the first `gh` word, so a failed
# search reads each command once (#280).
PR_CONTRIBUTION_RE = re.compile(
    r'(?:\A|(?<=[;&|\n]))(?:(?!\bgh\b)[^;&|\n])*'
    r'\bgh\b[^;&|\n]*\bpr[ \t]+(?:create|edit|comment|review)\b'
)

# Shell syntax that can come before the command word of one command segment
# (see split_commands): a subshell `(`, a control prefix, or `time`, e.g.
# `(git add .)` or `if ...; then git switch -c x; fi`.
COMMAND_PREFIXES = sorted(CONTROL_PREFIXES | {"time"})
SEGMENT_START = (
    r'(?:\(\s*|(?:' + '|'.join(re.escape(p) for p in COMMAND_PREFIXES) + r')\s+)*'
)

# A bulk `git add` at the start of one command segment.
BULK_ADD_RE = re.compile(
    SEGMENT_START + r'git\s+add\s+(?:-A|--all|\.(?=[\s)<>]|$)|\./(?=[\s)<>]|$))'
)

# The words of a segment for option parsing: a redirection operator such as
# `>`, `2>&`, or `<`, or a shell word, which can contain quoted text.
REDIRECTION = r'\d*[<>]+&?'
SHELL_WORD = r'''(?:"[^"]*"|'[^']*'|[^\s;|&()<>'"])+'''
REDIRECTION_RE = re.compile(REDIRECTION)
WORD_RE = re.compile(REDIRECTION + '|' + SHELL_WORD)

# Git options between `git` and its subcommand, e.g. `git -C dir` or
# `git -c key=value` (#272). The listed options can take a separate value;
# any other option is a flag with an optional `=value`. A separate value
# cannot start with `-`. Otherwise each `-C` in `git -C -C -C ...` is a flag
# or a value, and a failed match backtracks exponentially.
GIT_GLOBAL_OPTION = (
    r'(?:-[Cc]|--(?:git-dir|work-tree|namespace|config-env))[ \t]+(?!-)' + SHELL_WORD
    + r'|--?[A-Za-z][\w-]*(?:=' + SHELL_WORD + r')?'
)
GIT_COMMAND = SEGMENT_START + r'git(?:[ \t]+(?:' + GIT_GLOBAL_OPTION + r'))*[ \t]+'

# Branch creations at the start of one command segment. A branch name ends at
# whitespace or shell punctuation, so `(git checkout -b x)` names `x`. A
# segment has no unquoted newline (see split_commands); [ \t]+ separators also
# keep a quoted newline from joining two words (see issue #104).
BRANCH_NAME = r'([^\s;|&()<>]+)'
CHECKOUT_RE = re.compile(GIT_COMMAND + r'checkout[ \t]+-b[ \t]+' + BRANCH_NAME)
SWITCH_RE = re.compile(GIT_COMMAND + r'switch[ \t]+-c[ \t]+' + BRANCH_NAME)
WORKTREE_ADD_RE = re.compile(GIT_COMMAND + r'worktree[ \t]+add(?=[ \t]|$)')
BRANCH_RE = re.compile(GIT_COMMAND + r'branch[ \t]+')


def block(reason):
    print(f"BLOCKED: {reason}", file=sys.stderr)
    sys.exit(2)


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
        if ch == '\\' and quote != "'" and command[i + 1:i + 2] != '\n':
            # A backslash escapes the next char everywhere except inside single
            # quotes, where bash treats it literally. Without this, an escaped
            # quote desyncs quote state and a later separator can be swallowed
            # into one segment, re-masking an invalid branch creation (#107).
            # Exception: a line-continuation (\ + newline) is NOT escaped, so the
            # newline still splits. Bash would join the lines, but each segment
            # must stay one command — joining could let a creation hide behind a
            # neighbor (check_branch_names only reads the first verb per segment).
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


def command_segments(command):
    """Split `command` into command segments after removing heredoc bodies.

    A heredoc body is data, and a quoted argument stays inside its segment.
    So text that only mentions a git command is not read as one (#262, #272).
    """
    return split_commands(strip_heredoc_bodies(command))


def extract_branch_name(segment):
    """Return the branch that one command segment creates, or None.

    Each pattern matches at the segment start, so a git command inside a
    quoted argument does not count (#272).
    """
    for pattern in (CHECKOUT_RE, SWITCH_RE):
        m = pattern.match(segment)
        if m:
            return m.group(1)

    m = WORKTREE_ADD_RE.match(segment)
    if m:
        return extract_worktree_branch_name(segment[m.end():])

    m = BRANCH_RE.match(segment)
    if not m:
        return None
    arguments = segment[m.end():]

    # Rename/copy: short flags (-m/-M/-c/-C) and long flags (--move/--copy).
    # With two names, the second is the new branch.
    m = re.match(
        r'(?:-[mMcC]|--move|--copy)[ \t]+' + BRANCH_NAME + r'(?:[ \t]+' + BRANCH_NAME + r')?',
        arguments,
    )
    if m:
        return m.group(2) or m.group(1)

    # Bare creation — skip read-only/delete flags. Callers pass one command at a
    # time (see command_segments / check_branch_names), so a listing/delete
    # here cannot mask a real creation elsewhere in a compound command.
    if re.match(r'-[ladDvrV]|--list|--all|--delete|--remotes', arguments):
        return None
    m = re.match(r'(?!-)' + BRANCH_NAME, arguments)
    if m:
        return m.group(1)
    return None


def extract_worktree_branch_name(arguments):
    """Return the branch that `git worktree add <arguments>` creates, or None.

    Options can come before or after the path (#272). `-b` or `-B` names the
    branch, and `--detach` creates none. Otherwise a name-like commit-ish
    names it, and then the basename of the path.
    """
    words = iter(WORD_RE.findall(arguments))
    positional = []
    detach = False
    for word in words:
        if REDIRECTION_RE.fullmatch(word) or word == '--reason':
            next(words, None)  # skip the redirection target or option value
        elif word in ('-b', '-B'):
            return next(words, None)
        elif word in ('-d', '--detach'):
            detach = True
        elif not word.startswith('-'):
            positional.append(word)
    if detach or not positional:
        return None
    if len(positional) > 1:
        m = re.match(r'[a-zA-Z][\w-]*', positional[1])
        if m:
            return m.group(0)
    return os.path.basename(positional[0].rstrip('/'))


def has_bulk_add(command):
    """Report whether a segment of `command` starts with a bulk `git add`."""
    return any(BULK_ADD_RE.match(segment) for segment in command_segments(command))


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
    for segment in command_segments(command):
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

    command = get_shell_command(input_data)
    if command:
        if has_bulk_add(command):
            block(
                "Bulk git add operations are prohibited. "
                "Use specific file names instead of 'git add .', 'git add -A', "
                "or 'git add --all'."
            )

        # AI attribution is a hard block. Check it before the advisory handlers
        # below so a compound command (e.g. `gh pr edit ... && gh pr merge`)
        # cannot short-circuit the deny via an earlier advisory exit.
        is_contribution_cmd = bool("git commit" in command or PR_CONTRIBUTION_RE.search(command))
        if is_contribution_cmd:
            for pattern in ATTRIBUTION_PATTERNS:
                if re.search(pattern, command, re.IGNORECASE):
                    block(
                        "AI tool attribution detected in git operation. "
                        "Remove AI contribution messages from commit messages and "
                        "PR descriptions/comments."
                    )

        invalid_branch, saw_valid_branch = check_branch_names(command)
        if invalid_branch:
            block(
                f"Branch name '{invalid_branch}' is invalid. "
                f"Branch name must start with one of: {', '.join(VALID_PREFIXES)}"
            )

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
