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
apply. It denies other commands when an `=name` word names no command on
`PATH`, because zsh would stop the command line there. The denial ends with
the corrected command, which has a backslash before the `=` of each such
word, when the command has at most 1500 characters and the check blocks no
part of the corrected command. With `--host claude`, it denies a
parameter flag, so that the agent reads how to replace it. For each other
trap, it gives the agent a warning. It reads the command as shell words, so
single-quoted text, heredoc bodies, and comments give no finding. Traps 1
to 3 also skip double-quoted text, `[[ ... ]]` tests, and `(( ... ))`
arithmetic; zsh expands traps 4 and 5 in double quotes and tests too. This
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
    _find_backtick_end,
    _find_substitution_end,
    _heredoc_delimiters,
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
# `NAME=`, `NAME+=`, or an element assignment such as `NAME[1]=`.
ASSIGNMENT_RE = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)(\[[^\]]*\])?\+?=")
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
CORRECTED_COMMAND = (
    "Corrected command, with a backslash before the `=` of each unquoted "
    "word that names no command. Run it as it is:\n{command}"
)
# The denial gives the corrected command for a command of at most this many
# characters, the limit of the market_metrics guard that it replaces.
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
# The corrected command of an `=name` denial is a blocking Trap too.
Trap = namedtuple('Trap', 'message blocks')

# One unquoted word that starts with `=`, and the index of that `=` in the
# whole command.
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

    Adds (start, text) of a command substitution to `bodies`, so that it can
    be read as a command; `start` is the index of the text in `text`. `$((`
    arithmetic and the elements of an array assignment are not commands.
    """
    if text[index] == "`":
        end = _find_backtick_end(text, index + 1)
        if end is None:
            return len(text)
        bodies.append((index + 1, text[index + 1:end]))
        return end + 1
    # A `)` in a heredoc body is data, so it does not close the substitution.
    end = _find_substitution_end(_blank_heredoc_bodies(text[index + 2:]), 0)
    if end is None:
        return len(text)
    end += index + 2
    if command and not text.startswith("((", index + 1):
        bodies.append((index + 2, text[index + 2:end]))
    return end + 1


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
            index = _brace_end(text, index + 2) + 1
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
        elif text.startswith("((", index):
            end = _find_substitution_end(text, index + 1)
            index = len(text) if end is None else end + 1
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


def _expansions(text):
    """Yield the text after each `$` that zsh expands in the word `text`.

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
            index = _substitution_end(text, index, [], command=False)
        elif character == "$":
            index += 1
            yield text[index:]
        else:
            index += 1


def _record_expansions(text, findings):
    """Add the parameter flags and modifiers of the word `text` to
    `findings`."""
    for expansion in _expansions(text):
        flag = FLAG_RE.match(expansion)
        if flag:
            findings.flags.append("${(" + flag.group(1) + ")...}")
        modifier = MODIFIER_RE.match(expansion)
        if modifier:
            findings.modifiers.append(modifier.groups())


def _record_assignment(word, start, findings):
    """Add the assignment `word`, which starts at the index `start` of the
    whole command, to `findings`."""
    match = ASSIGNMENT_RE.match(word.text)
    value = word.text[match.end():]
    if _starts_with_equals(value):
        findings.equals_words.append(EqualsWord(start + match.end(), value))
    if value.startswith("("):
        kind = "array"
    elif word.quoted_space:
        kind = "spaced"
    else:
        kind = "scalar"
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
    # The words of the current command, without redirection targets.
    words = []
    # The test word of an earlier command of the current pipeline.
    piped_test = None
    # Blank heredoc bodies keep the index of each token in `text`.
    code = strip_heredoc_bodies(text, blank=True)
    for kind, token, start, _ in _spanned_tokens(code, bodies):
        if kind == "word":
            _record_expansions(token.text, findings)
        if in_condition:
            in_condition = not (kind == "word" and token.text == "]]")
            continue
        if kind == "operator":
            piped_test = _end_command(words, token, piped_test, findings)
            words = []
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
                findings.equals_words.append(EqualsWord(offset + start, word))
            continue
        words.append(word)
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
                _record_assignment(token, offset + start, findings)
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
            _record_assignment(token, offset + start, findings)
            continue
        if _starts_with_equals(word):
            findings.equals_words.append(EqualsWord(offset + start, word))
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
    """Report whether `=name` names no command, so that zsh stops there."""
    name = word[1:]
    return "/" not in name and shutil.which(name) is None


def _corrected_command(command, words, cwd, host):
    """Return `command` with a backslash before the `=` of each EqualsWord
    of `words`, or None.

    A backslash keeps the rest of each word, such as a `$name` expansion,
    which single quotes would stop. Returns None when `command` has more
    than MAX_CORRECTED_LENGTH characters, or when the check blocks the
    corrected command.
    """
    starts = sorted({word.start for word in words})
    if len(command) > MAX_CORRECTED_LENGTH or any(command[start] != "=" for start in starts):
        return None
    parts = []
    end = 0
    for start in starts:
        parts.extend((command[end:start], "\\"))
        end = start
    parts.append(command[end:])
    corrected = "".join(parts)
    if any(trap.blocks for trap in zsh_traps(corrected, cwd, host, correct=False)):
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


def zsh_traps(command, cwd=None, host=None, correct=True):
    """Return one Trap for each zsh trap in `command`.

    When an `=name` word names no command and `correct` is true, the last
    Trap can give the corrected command; see `_corrected_command`.

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
        traps.append(Trap(EQUALS_WARNING.format(word=findings.equals_words[0].text), False))
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
    if missing and correct:
        try:
            corrected = _corrected_command(command, missing, cwd, host)
        except Exception:
            # The corrected command is optional; the denial stays without it.
            corrected = None
        if corrected is not None:
            # Last, so that the command ends the message.
            traps.append(Trap(CORRECTED_COMMAND.format(command=corrected), True))
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
        cwd = _working_directory(input_data)
        host = host_argument(sys.argv[1:])
        traps = zsh_traps(command, cwd, host)
        updated_input = None
        corrected = None
        # Both current hosts supply Bash.command. Compatibility payloads
        # keep their existing decisions and never select a rewrite contract.
        if (
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
        # A hook error never stops a command.
        sys.exit(0)
    if host == ANTIGRAVITY:
        if corrected is not None:
            message = REWRITE_DENIAL.format(command=corrected)
        elif traps:
            message = "\n".join(trap.message for trap in traps)
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
        message = "\n".join(trap.message for trap in traps)
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
