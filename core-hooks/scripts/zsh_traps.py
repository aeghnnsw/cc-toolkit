#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.8"
# ///
"""Warn about two zsh traps in a shell command before it runs.

1. zsh replaces an unquoted word `=name` with the path of the command
   `name` (`=ls` gives `/bin/ls`). For `=====` or `==`, no such command
   exists, so zsh prints "not found" and stops the whole command line.
2. zsh does not split an unquoted variable into words. After
   `PY="uv run python"`, `$PY x` looks for one command named
   `uv run python`, and `set -- $pr` sets one positional parameter.

The hook only warns. It runs when the user's shell is zsh, prints JSON
with context that the agent reads, and exits 0. It reads the command as
shell words, so quoted text, heredoc bodies, comments, `[[ ... ]]` tests,
and `(( ... ))` arithmetic give no warning. This is a heuristic, not a
full zsh parser.
"""

import json
import os
import re
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

EQUALS_WARNING = (
    "zsh trap: the unquoted word `{word}` starts with `=`. zsh replaces "
    "`=name` with the path of the command `name`. If that command does not "
    "exist, zsh stops the whole command line. Quote the word, for example "
    "`'{word}'`. To compare in `[ ]` or `test`, use one `=`."
)
SPLIT_WARNING = (
    "zsh trap: zsh does not split the unquoted variable `{word}` into words. "
    "The value stays one command name or one argument. To keep a command in "
    "a variable, define a function. To split a value into words, run the "
    "commands in a script with `bash`."
)


# One shell word as written, quotes included. `quoted_space` is true when a
# quoted or escaped part of the word holds whitespace, as in
# `"uv run python"`; text inside `$(...)` does not count.
Word = namedtuple('Word', 'text quoted_space')


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
        if split_words is not None and not (
            command_word == "set" and word.startswith("-")
        ):
            split_words.append(word)
        # `eval` reads its arguments again as shell code, so it splits them.
        if _variable_name(word) and command_word != "eval":
            findings.variable_words.append(word)
    for body in bodies:
        _analyze(body, findings, depth + 1)


def zsh_trap_warnings(command):
    """Return one warning for each zsh trap in `command`.

    A variable is a trap when it holds a quoted value with whitespace, such
    as `PY="uv run python"`, or when it is the only word of a `set` command
    or a `for` list, as in `set -- $pr`. An array is split in zsh too.
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
    warnings = []
    if findings.equals_words:
        warnings.append(EQUALS_WARNING.format(word=findings.equals_words[0]))
    if unsplit:
        warnings.append(SPLIT_WARNING.format(word=unsplit[0]))
    return warnings


def main():
    try:
        input_data = json.load(sys.stdin)
        command = get_shell_command(input_data)
        if not command or os.path.basename(os.environ.get("SHELL", "")) != "zsh":
            sys.exit(0)
        warnings = zsh_trap_warnings(command)
    except Exception:
        # A warning hook never stops a command.
        sys.exit(0)
    if warnings:
        message = "\n".join(warnings)
        print(json.dumps({
            "systemMessage": message,
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "additionalContext": message,
            },
        }))
    sys.exit(0)


if __name__ == "__main__":
    main()
