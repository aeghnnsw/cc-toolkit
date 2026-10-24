#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.8"
# ///
"""Check a shell command for three zsh traps before it runs.

1. zsh replaces an unquoted word `=name` with the path of the command
   `name` (`=ls` gives `/bin/ls`). For `=====` or `==`, no such command
   exists, so zsh prints "not found" and stops the rest of the command
   line. The commands before the word have already run.
2. zsh does not split an unquoted variable into words. After
   `PY="uv run python"`, `$PY x` looks for one command named
   `uv run python`, and `set -- $pr` sets one positional parameter.
3. zsh stops a command when an unquoted glob matches no file, such as
   `grep --include=*.md`. It prints "no matches found", and the command
   does not run.

The hook runs when the user's shell is zsh, prints JSON, and exits 0. It
denies a command when an `=name` word names no command on `PATH`, because
zsh would stop the command line there. For each other trap, it gives the
agent a warning. It reads the command as shell words, so quoted text,
heredoc bodies, comments, `[[ ... ]]` tests, and `(( ... ))` arithmetic
give no finding. This is a heuristic, not a full zsh parser.
"""

import glob
import json
import os
import re
import shutil
import sys
from collections import namedtuple

from hook_payload import get_shell_command
from safety_guard import (
    CONTROL_PREFIXES,
    MAX_NESTED_SHELL_DEPTH,
    _find_backtick_end,
    _find_substitution_end,
    strip_heredoc_bodies,
)


# Words after which the next word is a command, e.g. `if`, `do`, or `!`.
COMMAND_PREFIXES = CONTROL_PREFIXES | {"time"}
# Builtins whose `NAME=value` arguments are assignments.
DECLARATION_COMMANDS = {
    "declare", "export", "float", "integer", "local", "readonly", "typeset",
}
WORD_BREAKS = set(" \t\n;&|()<>")
OPERATOR_RE = re.compile(r";;&?|;&|;|\|&|\|\||\||&&|&|\n|\(|\)")
REDIRECTION_RE = re.compile(r"\d*(?:<<<|<<-?|<>|>>|>\||>&|<&|&>>?|<|>)")
ASSIGNMENT_RE = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)\+?=")
# A word that is one unquoted variable and nothing else: `$NAME` or `${NAME}`.
BARE_VARIABLE_RE = re.compile(
    r"\$(?:([A-Za-z_][A-Za-z0-9_]*)|\{([A-Za-z_][A-Za-z0-9_]*)\})"
)
# An unquoted `*`, `?`, or `[...]` makes a word a glob.
GLOB_RE = re.compile(r"[*?]|\[[^\]]+\]")
# Quotes, escapes, expansions, and brace lists change what a glob matches,
# so the glob check skips a word that holds one.
UNMODELED_RE = re.compile(r"""['"\\$`{}()]""")
# After one of these commands, a glob expands in another directory.
DIRECTORY_COMMANDS = {"cd", "popd", "pushd"}

EQUALS_WARNING = (
    "zsh trap: the unquoted word `{word}` starts with `=`. zsh replaces "
    "`=name` with the path of the command `name`. If that command does not "
    "exist, zsh stops the whole command line. Quote the word, for example "
    "`'{word}'`. To compare in `[ ]` or `test`, use one `=`."
)
EQUALS_DENIAL = (
    "zsh trap: the unquoted word `{word}` starts with `=`, and no command "
    "`{name}` is on PATH. zsh would stop the whole command line at this "
    "word, after the commands before it had run, so the hook blocked the "
    "command. Quote the word, for example `'{word}'`. To compare in `[ ]` "
    "or `test`, use one `=`."
)
SPLIT_WARNING = (
    "zsh trap: zsh does not split the unquoted variable `{word}` into words. "
    "The value stays one command name or one argument. To keep a command in "
    "a variable, define a function. To split a value into words, run the "
    "commands in a script with `bash`."
)
GLOB_WARNING = (
    "zsh trap: the unquoted glob `{word}` matches no file. zsh stops the "
    "command that holds it with \"no matches found\", so that command did "
    "not run. When the command reads the pattern itself, quote the word, "
    "for example `'{word}'`. Otherwise, name files that exist."
)


# One shell word as written, quotes included. `quoted_space` is true when a
# quoted or escaped part of the word holds whitespace, as in
# `"uv run python"`; text inside `$(...)` does not count.
Word = namedtuple('Word', 'text quoted_space')

# One finding: the message for the agent, and whether zsh would stop the
# whole command line there, so that the hook blocks the command.
Trap = namedtuple('Trap', 'message stops_line')


class Findings:
    """What the analysis of one command and its substitutions found."""

    def __init__(self):
        self.equals_words = []
        # Words that are one unquoted variable, such as `$PY`.
        self.variable_words = []
        # The words of each `set` command and each `for ... in` list.
        self.split_lists = []
        # Variable name -> "array", "spaced", or "scalar".
        self.assignments = {}
        # Unquoted globs, such as `*.md` or `--include=*.md`.
        self.glob_words = []
        # True when the command changes the directory, so that a glob can
        # expand in another directory.
        self.changes_directory = False


def _double_quote_end(text, index, bodies):
    """Read a "..." string whose text starts at `index`.

    Returns the index after the closing `"`, and whether the string holds
    whitespace outside its command substitutions.
    """
    space = False
    while index < len(text):
        character = text[index]
        if character == "\\":
            index += 2
        elif character == '"':
            return index + 1, space
        elif character == "`" or text.startswith("$(", index):
            index = _substitution_end(text, index, bodies, command=True)
        else:
            space = space or character.isspace()
            index += 1
    return len(text), space


def _brace_end(text, index):
    """Return the index of the `}` that closes a `${` before `index`."""
    depth = 1
    while index < len(text):
        character = text[index]
        if character == "{":
            depth += 1
        elif character == "}":
            depth -= 1
            if depth == 0:
                return index
        index += 2 if character == "\\" else 1
    return len(text)


def _substitution_end(text, index, bodies, command):
    """Skip a backtick, `$(`, `$((`, `=(`, `<(`, or `>(` part of a word.

    Adds the text of a command substitution to `bodies`, so that it can be
    read as a command. `$((` arithmetic and the elements of an array
    assignment are not commands.
    """
    if text[index] == "`":
        end = _find_backtick_end(text, index + 1)
        if end is None:
            return len(text)
        bodies.append(text[index + 1:end])
        return end + 1
    end = _find_substitution_end(text, index + 2)
    if end is None:
        return len(text)
    if command and not text.startswith("((", index + 1):
        bodies.append(text[index + 2:end])
    return end + 1


def _read_word(text, index, bodies):
    """Read the word at `index`; return the Word and the index after it."""
    start = index
    quoted_space = False
    while index < len(text):
        character = text[index]
        if character == "\\":
            quoted_space = quoted_space or text[index + 1:index + 2].isspace()
            index += 2
        elif character == "'":
            end = text.find("'", index + 1)
            end = len(text) if end < 0 else end
            quoted_space = quoted_space or any(
                c.isspace() for c in text[index:end]
            )
            index = end + 1
        elif character == '"':
            index, space = _double_quote_end(text, index + 1, bodies)
            quoted_space = quoted_space or space
        elif character == "`":
            index = _substitution_end(text, index, bodies, command=True)
        elif text.startswith("(", index + 1) and (
            character in "$=" or (character in "<>" and index == start)
        ):
            # `name=(...)` assigns an array; `=(...)` at the start of a word
            # is zsh process substitution.
            command = character != "=" or index == start
            index = _substitution_end(text, index, bodies, command)
        elif text.startswith("${", index):
            index = _brace_end(text, index + 2) + 1
        elif character in WORD_BREAKS:
            break
        else:
            index += 1
    return Word(text[start:index], quoted_space), index


def _tokens(text, bodies):
    """Yield ("word", Word), ("operator", text), ("redirection", text), or
    ("arithmetic", text) tokens of `text`.
    """
    index = 0
    while index < len(text):
        character = text[index]
        if character in " \t":
            index += 1
        elif text.startswith("\\\n", index):
            index += 2
        elif character == "#":
            end = text.find("\n", index)
            index = len(text) if end < 0 else end
        elif text.startswith("((", index):
            end = _find_substitution_end(text, index + 1)
            end = len(text) if end is None else end + 1
            yield "arithmetic", text[index:end]
            index = end
        elif character in "<>" and text.startswith("(", index + 1):
            word, index = _read_word(text, index, bodies)
            yield "word", word
        elif REDIRECTION_RE.match(text, index):
            match = REDIRECTION_RE.match(text, index)
            yield "redirection", match.group()
            index = match.end()
        elif OPERATOR_RE.match(text, index):
            match = OPERATOR_RE.match(text, index)
            yield "operator", match.group()
            index = match.end()
        else:
            word, index = _read_word(text, index, bodies)
            yield "word", word


def _starts_with_equals(text):
    """Report whether zsh reads `text` as `=name`; a lone `=` stays a word."""
    return len(text) > 1 and text[0] == "=" and text[1] != "("


def _is_glob(word):
    """Report whether `word` is an unquoted glob that the check can match."""
    return bool(GLOB_RE.search(word)) and not UNMODELED_RE.search(word)


def _variable_name(word):
    """Return NAME when `word` is `$NAME` or `${NAME}`, otherwise None."""
    match = BARE_VARIABLE_RE.fullmatch(word)
    return match and (match.group(1) or match.group(2))


def _record_assignment(word, findings):
    match = ASSIGNMENT_RE.match(word.text)
    value = word.text[match.end():]
    if _starts_with_equals(value):
        findings.equals_words.append(value)
    if value.startswith("("):
        kind = "array"
    elif word.quoted_space:
        kind = "spaced"
    else:
        kind = "scalar"
    findings.assignments[match.group(1)] = kind


def _analyze(text, findings, depth):
    """Add the traps of `text` and its command substitutions to `findings`."""
    if depth > MAX_NESTED_SHELL_DEPTH:
        return
    bodies = []
    command_start = True
    command_word = None
    after_redirection = False
    in_condition = False
    # The state of a `for` loop before its list: "name" or "in".
    for_state = None
    # The words of the current `set` command or `for ... in` list.
    split_words = None
    # True between `case` and `esac`, where words are patterns.
    in_case = False
    for kind, token in _tokens(strip_heredoc_bodies(text), bodies):
        if in_condition:
            in_condition = not (kind == "word" and token.text == "]]")
            continue
        if kind == "operator":
            command_start, command_word = True, None
            for_state = split_words = None
            continue
        if kind == "redirection":
            after_redirection = True
            continue
        if kind == "arithmetic":
            command_start = False
            continue
        word = token.text
        if after_redirection:
            after_redirection = False
            if _starts_with_equals(word):
                findings.equals_words.append(word)
            continue
        if for_state == "name":
            for_state = "in"
            continue
        if for_state == "in":
            for_state = None
            if word == "in":
                split_words = []
                findings.split_lists.append(split_words)
            continue
        if command_start:
            if word == "[[":
                in_condition = True
                continue
            if word in COMMAND_PREFIXES:
                continue
            if ASSIGNMENT_RE.match(word):
                _record_assignment(token, findings)
                continue
            command_start, command_word = False, word
            if word in DIRECTORY_COMMANDS:
                findings.changes_directory = True
            if word in ("case", "esac"):
                in_case = word == "case"
            if word == "for":
                for_state = "name"
                continue
            if word == "set":
                split_words = []
                findings.split_lists.append(split_words)
                continue
        elif command_word in DECLARATION_COMMANDS and ASSIGNMENT_RE.match(word):
            _record_assignment(token, findings)
            continue
        if _starts_with_equals(word):
            findings.equals_words.append(word)
        elif not in_case and command_word != "noglob" and _is_glob(word):
            findings.glob_words.append(word)
        if split_words is not None and not (
            command_word == "set" and word.startswith("-")
        ):
            split_words.append(word)
        # `eval` reads its arguments again as shell code, so it splits them.
        if _variable_name(word) and command_word != "eval":
            findings.variable_words.append(word)
    for body in bodies:
        _analyze(body, findings, depth + 1)


def _names_no_command(word):
    """Report whether `=name` names no command, so that zsh stops there."""
    name = word[1:]
    return "/" not in name and shutil.which(name) is None


def _matches_no_file(word, directory):
    """Report whether the glob `word` matches no file in `directory`.

    A word that starts with `-` is an option, such as `--include=*.md`, and
    matches no file. Without a known directory, and for a recursive `**`
    glob, the check reports no finding.
    """
    if word.startswith("-"):
        return True
    if not directory or "**" in word:
        return False
    pattern = os.path.join(glob.escape(directory), os.path.expanduser(word))
    return next(glob.iglob(pattern), None) is None


def zsh_traps(command, cwd=None):
    """Return one Trap for each zsh trap in `command`.

    A variable is a trap when it holds a quoted value with whitespace, such
    as `PY="uv run python"`, or when it is the only word of a `set` command
    or a `for` list, as in `set -- $pr`. An array is split in zsh too.
    `cwd` is the directory where the command runs. The glob check uses it
    unless the command changes the directory.
    """
    findings = Findings()
    _analyze(command, findings, 0)
    assignments = findings.assignments
    unsplit = [
        word for word in findings.variable_words
        if assignments.get(_variable_name(word)) == "spaced"
    ]
    unsplit += [
        words[0] for words in findings.split_lists
        if len(words) == 1
        and _variable_name(words[0])
        and assignments.get(_variable_name(words[0])) != "array"
    ]
    missing = [word for word in findings.equals_words if _names_no_command(word)]
    directory = None if findings.changes_directory else cwd
    unmatched = [
        word for word in findings.glob_words if _matches_no_file(word, directory)
    ]
    traps = []
    if missing:
        traps.append(Trap(EQUALS_DENIAL.format(word=missing[0], name=missing[0][1:]), True))
    elif findings.equals_words:
        traps.append(Trap(EQUALS_WARNING.format(word=findings.equals_words[0]), False))
    if unsplit:
        traps.append(Trap(SPLIT_WARNING.format(word=unsplit[0]), False))
    if unmatched:
        traps.append(Trap(GLOB_WARNING.format(word=unmatched[0]), False))
    return traps


def _working_directory(input_data):
    """Return the directory where the command runs, or None."""
    cwd = input_data.get("cwd")
    cwd = cwd if isinstance(cwd, str) and os.path.isdir(cwd) else None
    tool_input = input_data.get("tool_input", input_data.get("toolInput"))
    workdir = tool_input.get("workdir") if isinstance(tool_input, dict) else None
    if isinstance(workdir, str) and workdir:
        workdir = os.path.join(cwd or "", workdir)
        return workdir if os.path.isabs(workdir) and os.path.isdir(workdir) else None
    return cwd


def main():
    try:
        input_data = json.load(sys.stdin)
        command = get_shell_command(input_data)
        if not command or os.path.basename(os.environ.get("SHELL", "")) != "zsh":
            sys.exit(0)
        traps = zsh_traps(command, _working_directory(input_data))
    except Exception:
        # A hook error never stops a command.
        sys.exit(0)
    if traps:
        message = "\n".join(trap.message for trap in traps)
        if any(trap.stops_line for trap in traps):
            decision = {"permissionDecision": "deny", "permissionDecisionReason": message}
        else:
            decision = {"additionalContext": message}
        print(json.dumps({
            "systemMessage": message,
            "hookSpecificOutput": {"hookEventName": "PreToolUse", **decision},
        }))
    sys.exit(0)


if __name__ == "__main__":
    main()
