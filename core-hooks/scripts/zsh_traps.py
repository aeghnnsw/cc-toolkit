#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.8"
# ///
"""Check a shell command for six zsh traps and three BSD tool traps before it runs.

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
4. The Claude Code Bash safety check cannot read a zsh parameter flag,
   such as `${(f)...}`. It denies the whole command with a message about
   `rm` operations, also when the command has no `rm`.
5. zsh can read a letter after `$NAME:` as a modifier of the variable:
   `$C:AGENTS.md` gives the absolute path of `$C` and then `GENTS.md`.
6. zsh gives a pipeline the exit status of its last command. Without the
   `pipefail` option, `pytest | tail` exits 0 when the tests fail, because
   `tail` succeeds. The check covers `pytest`, `python -m unittest`, and
   the package validator `validate_packages.py` when their output goes
   through a pipe to `tail` or `head`.
7. macOS has BSD tools, which reject some GNU options. BSD `head` rejects
   a count of 0, as in `head -0` or `head -n 0`. BSD `cat` has no `-A`,
   `-E`, `-T`, or long option, as in `cat -A`. Some macOS releases have
   no `timeout` command, so the check warns about `timeout` when no
   `timeout` command is on `PATH`.

The hook runs when the user's shell is zsh, prints JSON, and exits 0. With
`--host claude` or `--host codex`, it quotes missing-command separators in
each simple `echo` command of a list that `;`, `&&`, `||`, or newlines
join, such as `cat a; echo =====; cat b`. Normal host permissions still
apply. It denies other commands with an unquoted `=name` word that zsh
expands. When `name` is no command on `PATH`, zsh would stop the command
line there. When it is a command, the command gets its path instead of the
word. The word can start with parts that can expand to nothing, as in
`""==a` or `$x=a`, and brace expansion can put the `=` first, as in
`{=a,b}`. The check reads array elements, the parts after a `:` of an
assignment value, `[[ ... ]]` operands, and the default word of
`${name:-word}` too. The denial of a word that names no command ends with
the corrected command, which has a backslash before the `=` of each such
word. The hook gives it only for a command with no heredoc and at most 1500
characters, and only when the hook does not block the corrected command.
Where the check cannot read a command, it fails closed: it denies a command
with substitutions nested deeper than it reads when the unread text holds an
`=`, and a command that the hook fails to read because of an error.
With `--host claude`, it denies a
parameter flag, so that the agent reads how to replace it. For each other
trap, it gives the agent a warning. It reads the command as shell words, so
single-quoted text, heredoc bodies, and comments give no finding. Traps 1
to 3 also skip double-quoted text and `(( ... ))` arithmetic, and traps 2
and 3 skip `[[ ... ]]` tests; zsh expands traps 4 and 5 in double quotes
and tests too. This
is a heuristic, not a full zsh parser. The rewrite uses a separate strict
recognizer for each `echo` command. It changes nothing in a command with a
heredoc, or with a quote, backslash, backtick, `$`, or `#` before the end
of the last `echo` command that it would change.

An Antigravity PreToolUse hook cannot warn without blocking the command,
and no measured Antigravity contract changes the command. So with
`--host antigravity`, the hook writes nothing to stdout. It blocks a
command that the rewrite fixes, with a reason on stderr that names the
corrected command, and it blocks a command with any other trap, with the
trap messages on stderr. It skips the glob check: the check reads the
files before the command runs, so it can block a command that first
creates the files, and no warning can replace the block. It also skips
the pipefail check and the `head` and `cat` checks, which must not block
a command: GNU tools accept those options.
"""

import glob
import json
import os
import re
import shutil
import sys
from collections import namedtuple

from hook_payload import ANTIGRAVITY, block_status, get_shell_command, host_argument
from safety_guard import (
    CONTROL_PREFIXES,
    MAX_NESTED_SHELL_DEPTH,
    TURN_OFF_PLUGIN_STEPS,
    _find_backtick_end,
    _find_substitution_end,
    _heredoc_delimiters,
    strip_heredoc_bodies,
)


# Words after which the next word is a command, e.g. `if`, `do`, or `!`.
COMMAND_PREFIXES = CONTROL_PREFIXES | {"coproc", "nocorrect", "time"}
# Builtins whose `NAME=value` arguments are assignments.
DECLARATION_COMMANDS = {
    "declare", "export", "float", "integer", "local", "private", "readonly",
    "typeset",
}
WORD_BREAKS = set(" \t\n;&|()<>")
OPERATOR_RE = re.compile(r";;&?|;&|;\||;|\|&|\|\||\||&&|&|\n|\(|\)")
# Redirections, including the zsh forms with `|` or `!`, such as `>!`.
REDIRECTION_RE = re.compile(
    r"\d*(?:<<<|<<-?|<>|<&|<|&>>?[|!]?|>>&?[|!]?|>&?[|!]?)"
)
# The redirections whose target is a heredoc end word, which zsh does not
# expand.
HEREDOC_OPERATORS = {"<<", "<<-"}
# `NAME=`, `NAME+=`, or an element assignment such as `NAME[1]=`.
ASSIGNMENT_RE = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)(\[[^\]]*\])?\+?=")
# The `[key]=` or `[key]+=` start of an element of an array assignment.
ARRAY_KEY_RE = re.compile(r"\[[^\]]*\]\+?=")
IDENTIFIER_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
# A `$` expansion of a name or of a special parameter, such as `$x`, `$1`,
# or `$x[1]`.
NAME_EXPANSION_RE = re.compile(
    r"\$(?:[A-Za-z_][A-Za-z0-9_]*(?:\[[^\]]*\])*|[0-9@*#?$!-])"
)
# Expansions that always give text: `$#`, `$?`, `$$`, `$[...]`, and the
# length `${#name}`. `$((` gives text when it is arithmetic.
NEVER_EMPTY_RE = re.compile(r"\$(?:[#?$]|\[|\{#[A-Za-z_][A-Za-z0-9_]*\})")
# The flags and modifiers after `${`, the name or special parameter, and
# the subscripts of a `${...}` expansion.
PARAMETER_START_RE = re.compile(r"\$\{(?:\([^)]*\))?[\^=~#]*")
PARAMETER_NAME_RE = re.compile(r"(?:[A-Za-z_][A-Za-z0-9_]*|[0-9]+|[@*#?$!-])")
SUBSCRIPTS_RE = re.compile(r"(?:\[[^\]]*\])*")
# The operators whose word zsh expands as a word, such as `:-` in
# `${x:-word}`. zsh does not expand an `=word` in the word of `?` or of a
# pattern operator, such as `#`.
DEFAULT_OPERATOR_RE = re.compile(r"::=|:?[-+=]")
# The binary operators of a `[[ ... ]]` test that start with `=`.
CONDITION_EQUALS_OPERATORS = {"=", "==", "=~"}
# Precommand modifiers after which a declaration command still reads
# assignments, as in `builtin local x==y`.
DECLARATION_PRECOMMANDS = {"-", "builtin", "exec", "noglob"}
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

EQUALS_COMMAND_DENIAL = (
    "zsh trap: the unquoted word `{word}` starts with `=`, so zsh replaces "
    "it with the path of the command `{name}`. The command gets that path "
    "instead of the word, so the hook blocked the command. Quote the word, "
    "for example `'{word}'`. For the path of a command, use "
    "`$(command -v {name})`. To compare in `[ ]` or `test`, use one `=`."
)
NESTING_DENIAL = (
    "zsh trap: the command nests substitutions more than {depth} levels "
    "deep, and the hook reads no deeper. The unread text holds an `=`, which "
    "can start a word that zsh replaces with the path of a command, so the "
    "hook blocked the command. Use fewer nested substitutions, for example "
    "by setting a variable first."
)
READ_ERROR_DENIAL = (
    "zsh trap: the hook failed to read the command ({error}), so it cannot "
    "tell whether zsh would stop the command line at an unquoted word that "
    "starts with `=`. The hook blocked the command. Write the command in a "
    "simpler form, and quote each word that starts with `=`. To turn off the "
    "core-hooks plugin, {steps}, then start a new session."
)
EQUALS_DENIAL = (
    "zsh trap: the unquoted word `{word}` starts with `=`, and no command "
    "`{name}` is on PATH. zsh would stop the whole command line at this "
    "word, after the commands before it had run, so the hook blocked the "
    "command. Quote the word, for example `'{word}'`. To compare in `[ ]` "
    "or `test`, use one `=`."
)
CORRECTED_COMMAND = (
    "Corrected command, with a backslash before the `=` of each unquoted "
    "word that names no command. Run it as it is:\n{command}"
)
# The denial gives the corrected command only for a command of at most this
# many characters, so that the message stays short.
MAX_CORRECTED_LENGTH = 1500
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
FLAG_DENIAL = (
    "zsh trap: the Claude Code Bash safety check cannot read the zsh "
    "parameter flag `{flag}`. It denies the whole command with a message "
    "about `rm` operations, also when the command has no `rm`, so the hook "
    "blocked the command. To split a value into words, use `${{=list}}`, an "
    "array literal such as `files=(a b c)`, or a `while read -r line` loop."
)
# A zsh parameter flag after `$`, such as `{(f)` in `${(f)x}`.
FLAG_RE = re.compile(r"\{\(([^)]*)\)")
MODIFIER_WARNING = (
    "zsh trap: zsh can read `:{letter}` in `${name}:{letter}` as a modifier "
    "of the variable `${name}`, such as `:A` for an absolute path or `:h` "
    "for its directory. A modifier changes the value with no error. Brace "
    "the variable: `${{{name}}}:{letter}`."
)
# An unbraced variable followed by `:` and a letter, after `$`.
MODIFIER_RE = re.compile(r"([A-Za-z_][A-Za-z0-9_]*):([A-Za-z])")
REWRITE_DENIAL = (
    "zsh trap: zsh reads an unquoted word that starts with `=` as the path "
    "of a command. No such command exists, so zsh would stop the command "
    "line at this word. Run this corrected command, which quotes the "
    "word:\n{command}"
)
# A simple `echo` command that the rewrite accepts: an optional -n, then
# ASCII label words and separators. A separator starts with at least two
# equals signs and can hold a label and trailing equals signs.
ECHO_COMMAND_RE = re.compile(
    r"[ \t]*echo(?:[ \t]+-n)?"
    r"(?:[ \t]+(?:[A-Za-z0-9_]+|={2,}(?:[A-Za-z0-9_]+=*)?))+[ \t]*"
)
SEPARATOR_RE = re.compile(r"={2,}[A-Za-z0-9_]*=*")
# Operators that join the commands of a list; None is an edge of the command.
LIST_OPERATORS = {None, ";", "&&", "||", "\n"}
# A heredoc redirection, such as `<<` or `<<-`, but not a `<<<` string.
HEREDOC_RE = re.compile(r"(?<!<)<<(?!<)")
# Quotes, escapes, expansions, and comments, which the tokenizer can read
# wrongly. With none of them, it splits a command at the right operators.
UNSAFE_SPLIT_RE = re.compile(r"""['"\\`$#]""")
PIPEFAIL_WARNING = (
    "zsh trap: the output of `{test}` goes through a pipe to `{pager}`. zsh "
    "gives a pipeline the exit status of its last command, so the pipeline "
    "can exit 0 when `{test}` fails. Start the command with "
    "`set -o pipefail;`."
)
# Programs that print part of their input.
PAGER_COMMANDS = {"head", "tail"}
# Test and validator programs, and the test modules of `python -m`.
TEST_PROGRAMS = {"py.test", "pytest", "validate_packages.py"}
TEST_MODULES = {"pytest", "unittest"}
# Words after which a test program is a command, as in `uv run pytest`.
RUN_WORDS = {"run", "uvx"}
PYTHON_RE = re.compile(r"python[0-9.]*")
HEAD_WARNING = (
    "BSD tool trap: BSD `head`, as on macOS, rejects the count 0 in "
    "`head {option}`. It prints \"illegal line count -- 0\" or \"illegal "
    "byte count -- 0\" and exits 1. To discard the output, redirect it to "
    "/dev/null. To print lines, give a count of 1 or more."
)
# A `head` option that holds the count 0, such as `-0`, `-n0`, or
# `--lines=0`; and the options whose next word is the count.
HEAD_ZERO_RE = re.compile(r"-[nc]?0+|--(?:lines|bytes)=0+")
HEAD_COUNT_OPTIONS = {"-n", "-c", "--lines", "--bytes"}
CAT_WARNING = (
    "BSD tool trap: BSD `cat`, as on macOS, has no option `{option}`, so "
    "the command fails with \"illegal option\". BSD `cat` accepts only "
    "-b, -e, -l, -n, -s, -t, -u, and -v. To show tabs and line ends, use "
    "`cat -vet`."
)
# A GNU `cat` option that BSD `cat` lacks: -A, -E, -T, or a long option.
GNU_CAT_OPTION_RE = re.compile(r"-[A-Za-z]*[AET][A-Za-z]*|--.+")
TIMEOUT_WARNING = (
    "BSD tool trap: no `timeout` command is on PATH, so the shell stops "
    "this command with \"command not found\". Some macOS releases have no "
    "`timeout`. Leave it out, and give the time limit to the tool that "
    "runs the command."
)


# One shell word as written, quotes included. `quoted_space` is true when a
# quoted or escaped part of the word holds whitespace, as in
# `"uv run python"`; text inside `$(...)` does not count.
Word = namedtuple('Word', 'text quoted_space')

# One finding: the message for the agent, and whether the hook blocks the
# command, for example because zsh would stop the whole command line there.
Trap = namedtuple('Trap', 'message blocks')

# One unquoted word that starts with `=`, and the index of that `=` in the
# whole command. The index is correct only for a command with no heredoc,
# because the analysis reads the command without its heredoc bodies.
EqualsWord = namedtuple('EqualsWord', 'start text')


class Findings:
    """What the analysis of one command and its substitutions found."""

    def __init__(self):
        # EqualsWord items, such as `=====`.
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
        # zsh parameter flags, such as `${(f)...}`.
        self.flags = []
        # (name, letter) of each `$NAME:` followed by a letter.
        self.modifiers = []
        # True after a `set` or `setopt` command that turns on `pipefail`.
        self.pipefail = False
        # (test, pager) of each test command whose output goes through a
        # pipe to `tail` or `head` while `pipefail` is off.
        self.hidden_statuses = []
        # The options of `head` with the count 0, such as `-n 0`.
        self.head_zero_counts = []
        # The GNU options of `cat`, such as `-A`.
        self.gnu_cat_options = []
        # True when a command runs `timeout`.
        self.timeout = False
        # True when substitutions nest deeper than the analysis reads, and
        # the unread text holds an `=`.
        self.too_deep = False


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


def _substitution_end(text, index, bodies, command=True):
    """Skip a backtick, `$(`, `$((`, `=(`, `<(`, or `>(` part of a word.

    Adds (start, text) of each command to `bodies`, so that it can be read
    as a command; `start` is the index of the text in `text`. `$((`
    arithmetic is not a command, but a command substitution in it is. With
    `command` false, the part is the elements of an array assignment, which
    `_record_array` reads.
    """
    if text[index] == "`":
        end = _find_backtick_end(text, index + 1)
        if end is None:
            return len(text)
        bodies.append((index + 1, text[index + 1:end]))
        return end + 1
    if not command:
        end = _find_substitution_end(text, index + 2)
        return len(text) if end is None else end + 1
    if text[index] == "$" and text.startswith("((", index + 1):
        end = _arithmetic_end(text, index + 1)
        if end is not None:
            _nested_bodies(text, index + 3, end - 2, bodies)
            return end
    end = _command_end(text, index + 2)
    if end is None:
        return len(text)
    bodies.append((index + 2, text[index + 2:end]))
    return end + 1


def _arithmetic_end(text, index):
    """Return the index after the `))` of the `((` at `index`, or None.

    zsh reads `((` as arithmetic only when the inner `(` closes with `))`.
    Otherwise, as in `((echo a) ; echo b)`, the parentheses are a subshell
    in a subshell, or a command substitution that starts with a subshell.
    """
    inner = _find_substitution_end(text, index + 2)
    if inner is None or not text.startswith(")", inner + 1):
        return None
    return inner + 2


def _nested_bodies(text, start, end, bodies):
    """Add the command substitutions in text[start:end], the inside of
    arithmetic or of a `${...}` expansion, to `bodies`.

    zsh runs them, as in `${x:-$(cmd)}`, but not in single quotes.
    """
    index = start
    while index < end:
        if text[index] == "`" or text.startswith("$(", index):
            index = _substitution_end(text, index, bodies)
        elif text[index] == "'":
            index = _single_quote_end(text, index + 1) + 1
        else:
            index += 2 if text[index] == "\\" else 1


def _command_end(text, start):
    """Return the index of the `)` that ends the commands that start at
    `start`, as in `$(...)`, or None.

    A `)` that ends a `case` pattern does not end the commands, and neither
    does a `)` in a heredoc body, which is data.
    """
    blanked = _blank_heredoc_bodies(text[start:])
    depth = 0
    # The state of each open `case`: "word", "in", "pattern", or "body".
    cases = []
    command_start = True
    for kind, token, token_start, _ in _spanned_tokens(blanked, []):
        state = cases[-1] if cases else None
        if kind == "operator":
            if state == "pattern":
                if token == ")":
                    cases[-1] = "body"
                    command_start = True
                continue
            if state == "body" and token in (";;", ";&", ";;&", ";|"):
                cases[-1] = "pattern"
            elif token == "(":
                depth += 1
            elif token == ")":
                if depth == 0:
                    return start + token_start
                depth -= 1
            command_start = True
            continue
        if kind != "word":
            command_start = False
            continue
        word = token.text
        if state == "word":
            cases[-1] = "in"
        elif state == "in":
            cases[-1] = "pattern"
        elif state == "pattern":
            if word == "esac":
                cases.pop()
        elif command_start and word == "case":
            cases.append("word")
        elif command_start and word == "esac" and state == "body":
            cases.pop()
        command_start = word in COMMAND_PREFIXES
    return None


def _blank_heredoc_bodies(text):
    """Replace each heredoc body line of `text` with spaces.

    Unlike `strip_heredoc_bodies`, this keeps every index of `text`.
    """
    lines = text.split("\n")
    quote = None
    index = 0
    while index < len(lines):
        delimiters, quote = _heredoc_delimiters(lines[index], quote)
        index += 1
        for delimiter in delimiters:
            while index < len(lines):
                body_line = lines[index]
                lines[index] = " " * len(body_line)
                index += 1
                if body_line.strip() == delimiter:
                    break
    return "\n".join(lines)


def _single_quote_end(text, index):
    """Return the index of the `'` that closes a string opened before `index`.

    In `$'...'`, a backslash escapes the next character, such as `\'`.
    """
    ansi = text[index - 2:index - 1] == "$"
    while index < len(text):
        if ansi and text[index] == "\\":
            index += 2
        elif text[index] == "'":
            return index
        else:
            index += 1
    return len(text)


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
            end = _single_quote_end(text, index + 1)
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
            end = _brace_end(text, index + 2)
            _nested_bodies(text, index + 2, end, bodies)
            index = end + 1
        elif character in WORD_BREAKS:
            break
        else:
            index += 1
    return Word(text[start:index], quoted_space), index


def _spanned_tokens(text, bodies):
    """Yield (kind, token, start, end) for each token of `text`.

    The kind and token are ("word", Word), ("operator", text),
    ("redirection", text), or ("arithmetic", text); `text[start:end]` is the
    token.
    """
    index = 0
    while index < len(text):
        character = text[index]
        start = index
        if character in " \t":
            index += 1
        elif text.startswith("\\\n", index):
            index += 2
        elif character == "#":
            end = text.find("\n", index)
            index = len(text) if end < 0 else end
        elif text.startswith("((", index) and (end := _arithmetic_end(text, index)):
            # A `((` that is no arithmetic is read as two `(` operators.
            index = end
            _nested_bodies(text, start + 2, index - 2, bodies)
            yield "arithmetic", text[start:index], start, index
        elif character in "<>" and text.startswith("(", index + 1):
            word, index = _read_word(text, index, bodies)
            yield "word", word, start, index
        elif REDIRECTION_RE.match(text, index):
            match = REDIRECTION_RE.match(text, index)
            index = match.end()
            yield "redirection", match.group(), start, index
        elif OPERATOR_RE.match(text, index):
            match = OPERATOR_RE.match(text, index)
            index = match.end()
            yield "operator", match.group(), start, index
        else:
            word, index = _read_word(text, index, bodies)
            yield "word", word, start, index


def _expansion_end(text, index):
    """Return the index after the expansion at `index`: a backtick command,
    `$(...)`, `$((...))`, `${...}`, `$[...]`, or `$name`. Returns None when
    no expansion starts at `index`."""
    if text[index] == "`" or text.startswith("$(", index):
        return _substitution_end(text, index, [])
    if text.startswith("${", index):
        return _brace_end(text, index + 2) + 1
    if text.startswith("$[", index):
        end = text.find("]", index)
        return None if end < 0 else end + 1
    match = NAME_EXPANSION_RE.match(text, index)
    return match.end() if match else None


def _part_end(text, index):
    """Return the index after the quoted string, expansion, escaped
    character, or other character at `index`."""
    character = text[index]
    if character == "\\":
        return index + 2
    if character == "'":
        return _single_quote_end(text, index + 1) + 1
    if character == '"':
        return _double_quote_end(text, index + 1, [])[0]
    if character in "$`":
        return _expansion_end(text, index) or index + 1
    return index + 1


def _only_expansions(text, start, end):
    """Report whether text[start:end], the inside of a "..." string, holds
    only expansions, which can all be empty."""
    index = start
    while index < end:
        index = _expansion_end(text, index) if text[index] in "$`" else None
        if index is None:
            return False
    return True


def _empty_part_end(text, index):
    """Return the index after a part of a word that can expand to nothing,
    such as `""`, `$''`, `$x`, `"$x"`, or `$(cmd)`, or None when the part at
    `index` is literal text or an expansion that always gives text, such as
    `$#` or `$((1))`."""
    if text.startswith(('""', "''"), index):
        return index + 2
    if text.startswith("$''", index):
        return index + 3
    if NEVER_EMPTY_RE.match(text, index) or (
        text.startswith("$((", index) and _arithmetic_end(text, index + 1) is not None
    ):
        return None
    if text[index] == '"':
        end = _double_quote_end(text, index + 1, [])[0]
        return end if _only_expansions(text, index + 1, end - 1) else None
    if text[index] in "$`":
        return _expansion_end(text, index)
    return None


def _brace_alternatives(text, index, end):
    """Return the (start, end) span of each alternative of the brace
    expansion `{a,b}` at `index`, and the index of its `}`. Returns None
    when the `{` starts no list."""
    depth = 0
    commas = []
    position = index + 1
    while position < end:
        character = text[position]
        if character == "{":
            depth += 1
        elif character == "}":
            if depth == 0:
                if not commas:
                    return None
                bounds = [index, *commas, position]
                return [(a + 1, b) for a, b in zip(bounds, bounds[1:])], position
            depth -= 1
        elif character == "," and depth == 0:
            commas.append(position)
        position = _part_end(text, position)
    return None


def _leading_equals(text, spans, braces=True, memo=None):
    """Return (index, end) of the `=` that zsh reads as the start of
    `=name` in one word, or None; the `=` belongs to text[index:end].

    `spans` are the (start, end) parts of `text` that zsh joins into the
    word. The `=` counts when only parts that can expand to nothing come
    before it, such as `""`, `$x`, or `$(cmd)`: zsh expands it when they
    are empty, and the check cannot know their values. With `braces`, brace
    expansion can put the `=` first, as in `{=a,b}` or `{a,}=b`. A lone `=`
    and the process substitution `=(` stay words. `memo` keeps the result for
    each list of spans, so that many brace lists with empty alternatives, as
    in `{,}{,}{,}a`, take linear time.
    """
    memo = {} if memo is None else memo
    key = tuple(spans)
    if key not in memo:
        memo[key] = _first_equals(text, spans, braces, memo)
    return memo[key]


def _first_equals(text, spans, braces, memo):
    """Do the work of `_leading_equals` for one list of spans."""
    if not spans:
        return None
    (index, end), rest = spans[0], spans[1:]
    while index < end:
        if text[index] == "=":
            following = text[index + 1:end] or "".join(text[a:b] for a, b in rest)
            return (index, end) if following and following[0] != "(" else None
        if text[index] == "{" and braces:
            found = _brace_alternatives(text, index, end)
            if found is None:
                return None
            alternatives, close = found
            for start, stop in alternatives:
                result = _leading_equals(
                    text, [(start, stop), (close + 1, end), *rest], braces, memo
                )
                if result is not None:
                    return result
            return None
        index = _empty_part_end(text, index)
        if index is None:
            return None
    return _leading_equals(text, rest, braces, memo)


def _part_starts(text, start, end):
    """Yield the index where each part after a `:` of the assignment value
    text[start:end] starts, outside braces and expansions.

    zsh also splits the value at a quoted or escaped `:`. A part that starts
    in quotes holds the rest of the quoted text, so only a `:` at the end of
    the quoted text starts a part that can start with `=`, as in `"a:"=b`.
    """
    index = start
    depth = 0
    while index < end:
        character = text[index]
        following = _part_end(text, index)
        if character == "{":
            depth += 1
        elif character == "}":
            depth = max(depth - 1, 0)
        elif depth == 0 and (
            character == ":" or text.startswith("\\:", index)
            or character in "'\"" and text[index + 1:following - 1].endswith(":")
        ):
            yield following
        index = following


def _equals_words(text, base, start=0, end=None, colon=False, braces=True):
    """Return an EqualsWord for each `=` that zsh reads as `=name` in the
    word text[start:end]; `base` is the index of `text` in the whole command.

    With `colon`, as in an assignment value, each part after a `:` counts as
    the start of a word too, and the `=word` ends at the next `:`. `braces`
    is false where zsh does no brace expansion, as in a scalar assignment or
    a `[[ ... ]]` test.
    """
    end = len(text) if end is None else end
    starts = [start, *_part_starts(text, start, end)] if colon else [start]
    words = []
    for part_start in starts:
        found = _leading_equals(text, [(part_start, end)], braces)
        if found is not None:
            index, stop = found
            word = text[index:stop]
            words.append(EqualsWord(base + index, word.split(":")[0] if colon else word))
    return words


def _is_glob(word):
    """Report whether `word` is an unquoted glob that the check can match."""
    return bool(GLOB_RE.search(word)) and not UNMODELED_RE.search(word)


def _variable_name(word):
    """Return NAME when `word` is `$NAME` or `${NAME}`, otherwise None."""
    match = BARE_VARIABLE_RE.fullmatch(word)
    return match and (match.group(1) or match.group(2))


def _expansions(text):
    """Yield (index, quoted) for each `$` that zsh expands in the word
    `text`; `quoted` is true for a `$` in double quotes.

    zsh expands a `$` in unquoted and double-quoted text, not in single
    quotes or after a backslash. The commands of a `$(...)` or backtick
    substitution are skipped; `_analyze` reads them on their own.
    """
    index = 0
    double = False
    while index < len(text):
        character = text[index]
        if character == "\\":
            index += 2
        elif character == "'" and not double:
            index = _single_quote_end(text, index + 1) + 1
        elif character == '"':
            double = not double
            index += 1
        elif character == "`" or text.startswith("$(", index):
            index = _substitution_end(text, index, [])
        elif character == "$":
            yield index, double
            index += 1
        else:
            index += 1


def _default_word_start(text, index):
    """Return the index where the word of the `${...}` expansion at `index`
    starts, when zsh expands that word as a word, as in `${x:-word}` or
    `${${x}:-word}`. Returns None for another expansion."""
    match = PARAMETER_START_RE.match(text, index)
    if not match:
        return None
    position = match.end()
    if text.startswith(("$", "`"), position):
        position = _expansion_end(text, position)
    else:
        name = PARAMETER_NAME_RE.match(text, position)
        position = name and name.end()
    if position is None:
        return None
    position = SUBSCRIPTS_RE.match(text, position).end()
    operator = DEFAULT_OPERATOR_RE.match(text, position)
    return operator.end() if operator else None


def _record_expansions(text, start, findings):
    """Add the parameter flags, modifiers, and default-word `=word`s of the
    word `text`, which starts at the index `start` of the whole command, to
    `findings`.

    zsh expands the word of an unquoted `${x:-word}` as a word, so an
    `=word` there is a trap, as in `${x:-==}`.
    """
    for index, quoted in _expansions(text):
        expansion = text[index + 1:]
        flag = FLAG_RE.match(expansion)
        if flag:
            findings.flags.append("${(" + flag.group(1) + ")...}")
        modifier = MODIFIER_RE.match(expansion)
        if modifier:
            findings.modifiers.append(modifier.groups())
        word_start = None if quoted else _default_word_start(text, index)
        if word_start is not None:
            close = _brace_end(text, index + 2)
            findings.equals_words.extend(_equals_words(text, start, word_start, close))


def _record_array(text, start, base, findings, depth, equals_words):
    """Add the `=word`s of the array assignment whose `(` is at the index
    `start` of the word `text` to `equals_words`, and read the commands of
    its elements.

    `base` is the index of `text` in the whole command. zsh expands each
    element as a word, with the parts after a `:`, and the value after a
    `[key]=` start.
    """
    close = _find_substitution_end(text, start + 1)
    body_start = start + 1
    body = text[body_start:len(text) if close is None else close]
    bodies = []
    for kind, token, token_start, _ in _spanned_tokens(body, bodies):
        if kind != "word":
            continue
        key = ARRAY_KEY_RE.match(token.text)
        equals_words.extend(_equals_words(
            token.text, base + body_start + token_start,
            key.end() if key else 0, colon=True,
        ))
    for command_index, command in bodies:
        _analyze(command, findings, depth + 1, base + body_start + command_index)


def _record_condition(words, findings):
    """Add the `=word`s of one `[[ ... ]]` primary to `findings`.

    `words` are (text, start) pairs; a binary operator such as `<`, and a
    pattern group such as `(a|b)`, has no start. zsh does no brace expansion
    in a test. zsh reads three words as an operand, a binary operator, and an
    operand, and fewer words as a test and its operand. So `==` is an
    operand in `[[ -n == ]]` and an operator in `[[ a == b ]]`.
    """
    for position, (text, start) in enumerate(words):
        operator = position == 1 and len(words) >= 3 and text in CONDITION_EQUALS_OPERATORS
        if start is not None and not operator:
            findings.equals_words.extend(_equals_words(text, start, braces=False))


def _record_assignment(word, start, findings, depth, equals_words):
    """Add the assignment `word`, which starts at the index `start` of the
    whole command, to `findings`, and its `=word`s to `equals_words`.

    zsh expands the value and each part after a `:` in it as a word, as in
    `PATH=$PATH:=x`, but does no brace expansion in a scalar value.
    """
    match = ASSIGNMENT_RE.match(word.text)
    value = word.text[match.end():]
    if value.startswith("("):
        _record_array(word.text, match.end(), start, findings, depth, equals_words)
        kind = "array"
    else:
        equals_words.extend(_equals_words(
            word.text, start, match.end(), colon=True, braces=False,
        ))
        kind = "spaced" if word.quoted_space else "scalar"
    # An element assignment does not change the kind of the variable.
    if match.group(2) is None:
        findings.assignments[match.group(1)] = kind


def _command_words(words):
    """Return `words` from the command name on, without prefixes such as
    `time` and without assignments."""
    index = 0
    while index < len(words) and (
        words[index] in COMMAND_PREFIXES or ASSIGNMENT_RE.match(words[index])
    ):
        index += 1
    return words[index:]


def _test_command(words):
    """Return the test or validator word of one command, or None.

    The word is the command name, such as `pytest`; the module of
    `-m pytest` or `-m unittest`; a test program after `run` or `uvx`, as
    in `uv run pytest`; or the first argument of a Python interpreter, as
    in `python3 scripts/validate_packages.py`.
    """
    words = _command_words(words)
    for index, word in enumerate(words):
        module = words[index + 1] if word == "-m" and index + 1 < len(words) else word[2:]
        if word.startswith("-m") and module in TEST_MODULES:
            return module
    python = bool(words) and PYTHON_RE.fullmatch(os.path.basename(words[0]))
    for index, word in enumerate(words):
        if os.path.basename(word) not in TEST_PROGRAMS:
            continue
        if index == 0 or RUN_WORDS.intersection(words[:index]):
            return word
        if python and all(option.startswith("-") for option in words[1:index]):
            return word
    return None


def _record_bsd_options(words, findings):
    """Add the BSD tool traps of one command to `findings`.

    `words` start at the command name. A `--` word ends the options. A path
    to `timeout`, such as `/usr/bin/timeout`, is not a trap.
    """
    if not words:
        return
    if words[0] == "timeout":
        findings.timeout = True
    name = os.path.basename(words[0])
    if name not in ("head", "cat"):
        return
    arguments = words[1:]
    for index, word in enumerate(arguments):
        if word == "--":
            return
        following = arguments[index + 1] if index + 1 < len(arguments) else ""
        if name == "cat" and GNU_CAT_OPTION_RE.fullmatch(word):
            findings.gnu_cat_options.append(word)
        elif name == "head" and HEAD_ZERO_RE.fullmatch(word):
            findings.head_zero_counts.append(word)
        elif name == "head" and word in HEAD_COUNT_OPTIONS and re.fullmatch(r"0+", following):
            findings.head_zero_counts.append(f"{word} {following}")


def _end_command(words, operator, piped_test, findings):
    """Record the pipefail and BSD tool findings of one command that ends at
    `operator`.

    `piped_test` is the test word of an earlier command of the pipeline.
    Returns the test word that the next command of the pipeline reads, or
    None.
    """
    words = _command_words(words)
    name = os.path.basename(words[0]) if words else ""
    _record_bsd_options(words, findings)
    if name in ("set", "setopt", "unsetopt"):
        for previous, word in zip(words, words[1:]):
            if word.lower().replace("_", "") == "pipefail":
                findings.pipefail = name != "unsetopt" and not previous.startswith("+")
    if piped_test and name in PAGER_COMMANDS and not findings.pipefail:
        findings.hidden_statuses.append((piped_test, name))
    if operator in ("|", "|&"):
        return piped_test or _test_command(words)
    return None


def _analyze(text, findings, depth, offset=0):
    """Add the traps of `text` and its command substitutions to `findings`.

    `offset` is the index of `text` in the whole command.
    """
    if depth > MAX_NESTED_SHELL_DEPTH:
        # The analysis reads no deeper. An `=` in the unread text can start
        # an `=word`, so the check fails closed.
        findings.too_deep = findings.too_deep or "=" in text
        return
    bodies = []
    command_start = True
    command_word = None
    # The redirection operator before the next word, such as `>` or `<<`.
    redirection = None
    # The (text, start) words of the current `[[ ... ]]` primary, or None
    # outside a test, and the depth of a pattern group such as `(b|c)` in
    # `[[ a == (b|c) ]]`.
    condition = None
    group_depth = 0
    # The state of a `for` loop before its list: "name", "in", or "list",
    # inside the parentheses of `for x (a b)`.
    for_state = None
    # The words of the current `set` command or `for ... in` list.
    split_words = None
    # True between `case` and `esac`, where words are patterns.
    in_case = False
    # The part of a `case` statement: "word", "in", "pattern", or "body".
    # zsh does no brace expansion in the word and the patterns.
    case_state = None
    # The words of the current command, without redirection targets.
    words = []
    # The test word of an earlier command of the current pipeline.
    piped_test = None
    # True after a `time` that starts the current command, and the `=word`s
    # of the assignments after it. zsh expands them only when a command, a
    # redirection, or a pipe follows, as in `time x==y true`, not in
    # `time x==y`.
    timed = False
    timed_equals = []
    # True after the word `repeat`, whose next word is a count.
    repeat_count = False
    for kind, token, start, _ in _spanned_tokens(strip_heredoc_bodies(text), bodies):
        if kind == "word":
            _record_expansions(token.text, offset + start, findings)
        if condition is not None:
            if group_depth:
                if kind == "operator" and token in "()":
                    group_depth += 1 if token == "(" else -1
            elif kind == "operator" and token == "(" and condition:
                # After an operand, `(` starts a pattern group, not a group
                # of tests.
                group_depth = 1
                condition.append(("(...)", None))
            elif kind == "word" and token.text == "]]" or kind == "operator":
                _record_condition(condition, findings)
                condition = None if kind == "word" else []
            elif kind == "redirection":
                condition.append((token, None))
            elif kind == "word" and (condition or token.text != "!"):
                condition.append((token.text, offset + start))
            continue
        if kind == "operator":
            if for_state == "in" and token == "(":
                for_state, split_words = "list", []
                findings.split_lists.append(split_words)
                continue
            if for_state == "list" and token == ")":
                for_state = split_words = None
                command_start, command_word, words = True, None, []
                continue
            if case_state == "pattern" and token in ("(", "|"):
                continue
            if case_state == "pattern" and token == ")":
                case_state = "body"
            elif case_state == "body" and token in (";;", ";&", ";;&", ";|"):
                case_state = "pattern"
            if token in ("|", "|&"):
                findings.equals_words.extend(timed_equals)
            piped_test = _end_command(words, token, piped_test, findings)
            words = []
            command_start, command_word = True, None
            for_state = split_words = None
            timed, timed_equals = False, []
            continue
        if kind == "redirection":
            redirection = token
            findings.equals_words.extend(timed_equals)
            timed_equals = []
            continue
        if kind == "arithmetic":
            command_start = False
            continue
        word = token.text
        if redirection is not None:
            operator = redirection.lstrip("0123456789")
            if operator not in HEREDOC_OPERATORS:
                # zsh does no brace expansion in a here-string word.
                findings.equals_words.extend(
                    _equals_words(word, offset + start, braces=operator != "<<<")
                )
            redirection = None
            continue
        words.append(word)
        if for_state == "name":
            for_state = "in"
            continue
        if for_state == "in":
            # `for x y in ...` names more than one variable.
            if word not in ("do", "in") and IDENTIFIER_RE.fullmatch(word):
                continue
            for_state = None
            if word == "in":
                split_words = []
                findings.split_lists.append(split_words)
            continue
        if case_state in ("word", "pattern") and word != "esac":
            findings.equals_words.extend(_equals_words(word, offset + start, braces=False))
            case_state = "in" if case_state == "word" else case_state
            continue
        if case_state == "in":
            case_state = "pattern"
            continue
        if repeat_count:
            # zsh expands the count of `repeat` too.
            findings.equals_words.extend(_equals_words(word, offset + start))
            repeat_count = False
            command_start = True
            continue
        if command_start:
            if word == "[[":
                condition = []
                continue
            if word in COMMAND_PREFIXES:
                timed = word == "time" and all(prefix == "!" for prefix in words[:-1])
                continue
            if ASSIGNMENT_RE.match(word):
                target = timed_equals if timed else findings.equals_words
                _record_assignment(token, offset + start, findings, depth, target)
                continue
            command_start, command_word = False, word
            findings.equals_words.extend(timed_equals)
            timed_equals = []
            repeat_count = word == "repeat"
            if word in DIRECTORY_COMMANDS:
                findings.changes_directory = True
            if word in ("case", "esac"):
                in_case = word == "case"
                case_state = "word" if in_case else None
            if word == "for":
                for_state = "name"
                continue
            if word == "set":
                split_words = []
                findings.split_lists.append(split_words)
                continue
        elif command_word in DECLARATION_COMMANDS and ASSIGNMENT_RE.match(word):
            _record_assignment(token, offset + start, findings, depth, findings.equals_words)
            continue
        elif command_word in DECLARATION_PRECOMMANDS and word in DECLARATION_COMMANDS:
            command_word = word
            continue
        elif command_word == "function" and word == "{":
            # The body of `function NAME {` or `function {` starts here.
            command_start, command_word = True, None
            continue
        equals = _equals_words(word, offset + start)
        if equals:
            findings.equals_words.extend(equals)
        elif not in_case and command_word != "noglob" and _is_glob(word):
            findings.glob_words.append(word)
        if split_words is not None and not (
            command_word == "set" and word.startswith("-")
        ):
            split_words.append(word)
        # `eval` reads its arguments again as shell code, so it splits them.
        if _variable_name(word) and command_word != "eval":
            findings.variable_words.append(word)
    _end_command(words, None, piped_test, findings)
    for body_start, body in bodies:
        _analyze(body, findings, depth + 1, offset + body_start)


def _names_no_command(word):
    """Report whether `=name` names no command, so that zsh stops there.

    A name with a `/`, such as `=missing/path`, names a file: zsh stops
    there too when the file is no command.
    """
    return shutil.which(word[1:]) is None


def corrected_command(command, cwd=None, host=None):
    """Return `command` with a backslash before the `=` of each `=name` word
    that names no command, or None.

    A backslash keeps the rest of each word, such as a `$name` expansion,
    which single quotes would stop. Returns None when no word needs a
    backslash, when `command` has more than MAX_CORRECTED_LENGTH characters,
    or when the hook blocks the corrected command. Also returns None for a
    command with a heredoc: the analysis can read a heredoc body as code,
    and a backslash in a body or in its end word changes the command.
    """
    if len(command) > MAX_CORRECTED_LENGTH or HEREDOC_RE.search(command):
        return None
    findings = Findings()
    _analyze(command, findings, 0)
    starts = sorted({
        word.start for word in findings.equals_words if _names_no_command(word.text)
    })
    if not starts or any(command[start] != "=" for start in starts):
        return None
    parts = []
    end = 0
    for start in starts:
        parts.extend((command[end:start], "\\"))
        end = start
    parts.append(command[end:])
    corrected = "".join(parts)
    if any(trap.blocks for trap in zsh_traps(corrected, cwd, host)):
        return None
    return corrected


def _quote_echo_separators(command):
    """Quote missing-command separators in the simple echo commands of a list.

    A list joins commands with `;`, `&&`, `||`, or newlines; one command is
    a list too. An echo command must match `ECHO_COMMAND_RE`, with a list
    operator or an edge of the command on each side. Operators inside a
    `[[ ... ]]` test do not split it. Other commands stay as they are.

    The tokenizer is a heuristic, so the text up to the end of the last
    rewritten echo command must hold no quote, backslash, backtick, `$`, or
    `#`. A command with a heredoc anywhere also keeps the existing
    decision.
    """
    if HEREDOC_RE.search(command):
        return None
    edges = [(None, 0, 0)]
    # Operators inside a `[[ ... ]]` test join conditions, not commands.
    condition = False
    for kind, token, start, end in _spanned_tokens(command, []):
        if kind == "word" and token.text in ("[[", "]]"):
            condition = token.text == "[["
        elif kind == "operator" and not condition:
            edges.append((token, start, end))
    edges.append((None, len(command), len(command)))
    separators = []
    # The end of the last echo command with a separator.
    last_end = 0
    for (left, _, start), (right, end, _) in zip(edges, edges[1:]):
        if (
            left in LIST_OPERATORS and right in LIST_OPERATORS
            and ECHO_COMMAND_RE.fullmatch(command, start, end)
        ):
            words = list(SEPARATOR_RE.finditer(command, start, end))
            if words:
                separators.extend(words)
                last_end = end
    # Every equals word must qualify before any edit is made.
    if not separators or any(not _names_no_command(word.group()) for word in separators):
        return None
    if UNSAFE_SPLIT_RE.search(command, 0, last_end):
        return None
    parts = []
    end = 0
    for word in separators:
        parts.extend((command[end:word.start()], "'", word.group(), "'"))
        end = word.end()
    parts.append(command[end:])
    return "".join(parts)


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
    # zsh negates a bracket with `^` or `!`; Python's glob only with `!`.
    word = os.path.expanduser(word).replace("[^", "[!")
    pattern = os.path.join(glob.escape(directory), word)
    return next(glob.iglob(pattern), None) is None


def zsh_traps(command, cwd=None, host=None):
    """Return one Trap for each zsh trap in `command`.

    A variable is a trap when it holds a quoted value with whitespace, such
    as `PY="uv run python"`, or when it is the only word of a `set` command
    or a `for` list, as in `set -- $pr`. An array is split in zsh too.
    `cwd` is the directory where the command runs. The glob check uses it
    unless the command changes the directory. The glob and pipefail checks
    do not run when `host` is "antigravity", and neither do the `head` and
    `cat` checks. A parameter flag is a trap only when `host` is "claude",
    because only the Claude Code safety check rejects it. `timeout` is a
    trap only when no `timeout` command is on PATH.
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
    missing = [word for word in findings.equals_words if _names_no_command(word.text)]
    directory = None if findings.changes_directory else cwd
    glob_words = [] if host == ANTIGRAVITY else findings.glob_words
    unmatched = [word for word in glob_words if _matches_no_file(word, directory)]
    traps = []
    if findings.flags and host == "claude":
        traps.append(Trap(FLAG_DENIAL.format(flag=findings.flags[0]), True))
    if missing:
        word = missing[0].text
        traps.append(Trap(EQUALS_DENIAL.format(word=word, name=word[1:]), True))
    elif findings.equals_words:
        word = findings.equals_words[0].text
        traps.append(Trap(EQUALS_COMMAND_DENIAL.format(word=word, name=word[1:]), True))
    elif findings.too_deep:
        traps.append(Trap(NESTING_DENIAL.format(depth=MAX_NESTED_SHELL_DEPTH), True))
    if unsplit:
        traps.append(Trap(SPLIT_WARNING.format(word=unsplit[0]), False))
    if unmatched:
        traps.append(Trap(GLOB_WARNING.format(word=unmatched[0]), False))
    if findings.modifiers:
        name, letter = findings.modifiers[0]
        traps.append(Trap(MODIFIER_WARNING.format(name=name, letter=letter), False))
    if findings.hidden_statuses and host != ANTIGRAVITY:
        test, pager = findings.hidden_statuses[0]
        traps.append(Trap(PIPEFAIL_WARNING.format(test=test, pager=pager), False))
    if findings.head_zero_counts and host != ANTIGRAVITY:
        traps.append(Trap(HEAD_WARNING.format(option=findings.head_zero_counts[0]), False))
    if findings.gnu_cat_options and host != ANTIGRAVITY:
        traps.append(Trap(CAT_WARNING.format(option=findings.gnu_cat_options[0]), False))
    if findings.timeout and host != ANTIGRAVITY and shutil.which("timeout") is None:
        traps.append(Trap(TIMEOUT_WARNING, False))
    return traps


def _trap_message(traps, command, cwd, host):
    """Join the messages of `traps`. A denial ends with the corrected
    command of `corrected_command`, when there is one."""
    message = "\n".join(trap.message for trap in traps)
    if not any(trap.blocks for trap in traps):
        return message
    try:
        corrected = corrected_command(command, cwd, host)
    except Exception:
        # The corrected command is optional; the denial stays without it.
        return message
    if corrected is None:
        return message
    return message + "\n" + CORRECTED_COMMAND.format(command=corrected)


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
        cwd = _working_directory(input_data)
        host = host_argument(sys.argv[1:])
    except Exception:
        # Without a command, the hook has nothing to check.
        sys.exit(0)
    read_failed = False
    try:
        traps = zsh_traps(command, cwd, host)
    except Exception as error:
        # The check cannot tell whether zsh would stop the command line, so
        # it blocks the command: it fails closed.
        read_failed = True
        steps = TURN_OFF_PLUGIN_STEPS.get(host, TURN_OFF_PLUGIN_STEPS[None])
        reason = f"{type(error).__name__}: {error}"
        traps = [Trap(READ_ERROR_DENIAL.format(error=reason, steps=steps), True)]
    updated_input = None
    corrected = None
    try:
        # Both current hosts supply Bash.command. Compatibility payloads
        # keep their existing decisions and never select a rewrite contract.
        # A command that the hook failed to read gets no rewrite.
        if read_failed:
            pass
        elif (
            host in ("claude", "codex")
            and input_data.get("tool_name") == "Bash"
            and isinstance(input_data.get("tool_input"), dict)
        ):
            quoted = _quote_echo_separators(command)
            if quoted is not None and not zsh_traps(quoted, cwd, host):
                updated_input = dict(input_data["tool_input"], command=quoted)
        elif host == ANTIGRAVITY:
            quoted = _quote_echo_separators(command)
            if quoted is not None and not zsh_traps(quoted, cwd, host):
                corrected = quoted
    except Exception:
        # The rewrite is optional; the decision of the checks stays.
        updated_input = corrected = None
    if host == ANTIGRAVITY:
        if corrected is not None:
            message = REWRITE_DENIAL.format(command=corrected)
        elif traps:
            message = _trap_message(traps, command, cwd, host)
        else:
            sys.exit(0)
        print(f"BLOCKED: {message}", file=sys.stderr)
        sys.exit(block_status(host))
    if updated_input is not None:
        output = {"hookEventName": "PreToolUse", "updatedInput": updated_input}
        # Codex requires allow to apply the rewrite; its normal execution
        # approval still runs. Claude must omit it to preserve permissions.
        if host == "codex":
            output["permissionDecision"] = "allow"
        print(json.dumps({"hookSpecificOutput": output}))
    elif traps:
        message = _trap_message(traps, command, cwd, host)
        if any(trap.blocks for trap in traps):
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
