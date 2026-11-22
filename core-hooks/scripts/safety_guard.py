#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.8"
# ///
"""Block dangerous `rm` commands, and commands that print every variable.

This module also owns shell-parsing code that other hooks import. For
example, `pre_git_hook.py` imports `strip_heredoc_bodies` and
`CONTROL_PREFIXES`.
"""

import json
import os
import re
import shlex
import sys
import tempfile
import traceback
from pathlib import Path

from hook_logs import append_log, host_log_dir
from hook_payload import (
    ANTIGRAVITY, CODEX, block_status, get_shell_command, host_argument,
)


SHELL_PUNCTUATION = ";&|()<>\n`"
COMMAND_BOUNDARY_PUNCTUATION = ";&|()\n`"
QUOTED_PUNCTUATION = {
    character: chr(0xE000 + index)
    for index, character in enumerate(SHELL_PUNCTUATION)
}
RESTORED_PUNCTUATION = {
    protected: character
    for character, protected in QUOTED_PUNCTUATION.items()
}
CONTROL_PREFIXES = {
    "!",
    "{",
    "if",
    "then",
    "elif",
    "else",
    "while",
    "until",
    "do",
}
SIMPLE_WRAPPERS = {
    "command": set(),
    "exec": {"-a"},
    "nohup": set(),
    "time": {"-f", "--format", "-o", "--output"},
}
SHELL_PROGRAMS = {"bash", "dash", "fish", "ksh", "sh", "zsh"}
ASSIGNMENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
SUDO_VALUE_OPTIONS = {
    "-u", "--user", "-g", "--group", "-h", "--host", "-p", "--prompt",
    "-C", "--close-from", "-D", "--chdir", "-R", "--chroot",
    "-T", "--command-timeout", "-r", "--role", "-t", "--type",
}
ENV_VALUE_OPTIONS = {
    "-u", "--unset", "-C", "--chdir", "-P",
    "-S", "--split-string",
}
SHELL_VALUE_OPTIONS = {
    "-O", "+O", "-o", "+o", "--init-file", "--rcfile",
}
XARGS_VALUE_OPTIONS = {
    "-a", "--arg-file", "-d", "--delimiter", "-E", "-I", "-J",
    "-L", "--max-lines", "-n", "--max-args",
    "-P", "--max-procs", "--process-slot-var", "-R", "-S",
    "-s", "--max-chars",
}
PROCESS_WRAPPERS = {
    "chroot": (
        {"--groups", "--userspec"},
        1,
    ),
    "ionice": (
        {
            "-c", "--class", "-n", "--classdata", "-p", "--pid",
            "-P", "--pgid", "-u", "--uid",
        },
        0,
    ),
    "nice": (
        {"-n", "--adjustment"},
        0,
    ),
    "parallel": (
        {
            "-a", "--arg-file", "-j", "--jobs", "-L", "--max-lines",
            "-N", "--number-of-args", "-S", "--sshlogin",
        },
        0,
    ),
    "stdbuf": (
        {"-e", "--error", "-i", "--input", "-o", "--output"},
        0,
    ),
    "timeout": (
        {"-k", "--kill-after", "-s", "--signal"},
        1,
    ),
    "watch": (
        {
            "-n", "--interval", "-q", "--equexit",
            "-s", "--shotsdir",
        },
        0,
    ),
    "xargs": (
        XARGS_VALUE_OPTIONS,
        0,
    ),
}
MAX_NESTED_SHELL_DEPTH = 8
# `<<WORD`, `<<-WORD`, and the quoted or escaped delimiter forms. The plain
# word stops at whitespace and at shell punctuation that cannot be part of a
# delimiter, so a following redirection or operator is not consumed.
HEREDOC_OPERATOR_RE = re.compile(
    r"<<-?[ \t]*"
    r"(?:'(?P<single>[^'\n]*)'"
    r"|\"(?P<double>[^\"\n]*)\""
    r"|(?P<plain>(?:\\.|[^\s'\"<>|&;()`\n])+))"
)
# Whole-command forms whose quoted heredoc body is data (#445). The first
# line uses a strict grammar, so the shell ends it in top-level state and
# reads each word as one argument: words of plain characters, `'...'`
# strings, and `"..."` strings without expansions other than `$NAME`;
# redirections with their targets; `&&`; `;`; and one heredoc operator. A
# line outside this grammar is not an allowed form.
_HEREDOC_NAME = r"[A-Za-z_][A-Za-z0-9_]*"
_PARAMETER = rf"\${_HEREDOC_NAME}|\$\{{{_HEREDOC_NAME}\}}"
_QUOTED_DELIMITER = rf"'{_HEREDOC_NAME}'|\"{_HEREDOC_NAME}\"|\\{_HEREDOC_NAME}"
_FORM_WORD = (
    r"(?:[A-Za-z0-9_@%+=:,./~-]|'[^'\n]*'"
    rf"|\"(?:[^\"$`\\!\n]|{_PARAMETER})*\")+"
)
DATA_FORM_TOKEN_RE = re.compile(
    r"(?:"
    rf"(?P<substitution>\"\$\(cat[ \t]+<<(?P<inner>{_QUOTED_DELIMITER})[ \t]*$)"
    rf"|(?P<heredoc><<(?P<outer>{_QUOTED_DELIMITER}))"
    r"|(?P<separator>&&|;)"
    rf"|(?P<redirection>[0-9]?>&[0-9]|[0-9]?>>?[ \t]*{_FORM_WORD})"
    rf"|(?P<word>{_FORM_WORD})"
    r")(?=[ \t;]|&&|$)"
)
GH_DATA_SUBCOMMANDS = {
    "pr": {"create", "edit", "comment", "review"},
    "issue": {"create", "edit", "comment"},
}
# Git subcommands that may share the first line with a form. None of them
# changes how a later `git commit` reads its message.
GIT_SEGMENT_SUBCOMMANDS = {"add", "diff", "log", "show", "status"}
DATA_BODY_CONTROL_RE = re.compile(r"[\x00-\x08\x0b-\x1f\x7f-\x9f]")
RM_MENTION_RE = re.compile(r"\brm\b", re.IGNORECASE)
PROTECTED_SYSTEM_PATHS = (
    "/usr",
    "/var",
    "/private/var",
    "/etc",
    "/bin",
    "/sbin",
    "/lib",
    "/opt",
    "/sys",
    "/proc",
    "/dev",
    "/boot",
)


def _shell_tokens(command):
    command = _protect_quoted_punctuation(command)
    lexer = shlex.shlex(
        command,
        posix=True,
        punctuation_chars=SHELL_PUNCTUATION,
    )
    lexer.whitespace = " \t\r"
    lexer.whitespace_split = True
    lexer.commenters = ""
    return list(lexer)


def _protect_quoted_punctuation(command):
    result = []
    quote = None
    index = 0
    while index < len(command):
        character = command[index]
        if character == "\\" and quote != "'":
            if index + 1 >= len(command):
                result.append(character)
                break
            escaped = command[index + 1]
            if quote is None and escaped in QUOTED_PUNCTUATION:
                result.append(QUOTED_PUNCTUATION[escaped])
            else:
                result.extend((character, escaped))
            index += 2
            continue
        if character in {"'", '"'}:
            if quote is None:
                quote = character
            elif quote == character:
                quote = None
            result.append(character)
            index += 1
            continue
        if quote is not None and character in QUOTED_PUNCTUATION:
            result.append(QUOTED_PUNCTUATION[character])
        else:
            result.append(character)
        index += 1
    return "".join(result)


def _restore_quoted_punctuation(token):
    return "".join(
        RESTORED_PUNCTUATION.get(character, character)
        for character in token
    )


def _is_redirection(token):
    return (
        token
        and ("<" in token or ">" in token)
        and all(character in SHELL_PUNCTUATION for character in token)
    )


def _is_boundary(token):
    return token and all(
        character in COMMAND_BOUNDARY_PUNCTUATION
        for character in token
    )


def _without_redirections(segment):
    result = []
    index = 0
    while index < len(segment):
        if (
            segment[index].isdigit()
            and index + 1 < len(segment)
            and _is_redirection(segment[index + 1])
        ):
            index += 1
        if _is_redirection(segment[index]):
            index += 2
            continue
        result.append(_restore_quoted_punctuation(segment[index]))
        index += 1
    return result


def _remove_line_continuations(command):
    result = []
    quote = None
    index = 0
    while index < len(command):
        character = command[index]
        if (
            character == "\\"
            and quote != "'"
            and index + 1 < len(command)
        ):
            escaped = command[index + 1]
            if escaped == "\n":
                index += 2
                continue
            result.extend((character, escaped))
            index += 2
            continue
        if character in {"'", '"'}:
            if quote is None:
                quote = character
            elif quote == character:
                quote = None
        result.append(character)
        index += 1
    return "".join(result)


def _strip_shell_comments(command):
    result = []
    quote = None
    can_start_comment = True
    index = 0
    while index < len(command):
        character = command[index]
        if character == "\\" and quote != "'":
            result.append(character)
            if index + 1 < len(command):
                result.append(command[index + 1])
            can_start_comment = False
            index += 2
            continue
        if quote is not None:
            result.append(character)
            if character == quote:
                quote = None
            index += 1
            continue
        if character in {"'", '"'}:
            quote = character
            result.append(character)
            can_start_comment = False
            index += 1
            continue
        if character == "#" and can_start_comment:
            newline = command.find("\n", index + 1)
            if newline < 0:
                break
            result.append("\n")
            can_start_comment = True
            index = newline + 1
            continue
        result.append(character)
        can_start_comment = (
            character.isspace()
            or character in SHELL_PUNCTUATION
        )
        index += 1
    return "".join(result)


def _heredoc_delimiters(line, quote):
    """Return the heredoc delimiters that one command line opens.

    Recognizes `<<WORD`, `<<-WORD`, `<<'WORD'`, `<<"WORD"`, and `<<\\WORD`
    outside quotes, in the order the shell reads their bodies. Also returns the
    quote state at the end of the line, so a quoted string that spans lines
    cannot be read as a heredoc operator.

    Detection stays conservative, because a delimiter found where the shell
    reads none would drop the following commands from inspection. `<<` is not
    a heredoc operator in a here string (`<<<`), in a comment, inside an
    arithmetic expansion (`$((1 << 3))`), or where the delimiter it would name
    closes one.
    """
    delimiters = []
    arithmetic_depth = 0
    index = 0
    while index < len(line):
        character = line[index]
        if character == "\\" and quote != "'":
            index += 2
            continue
        if character == "'":
            if quote is None:
                quote = "'"
            elif quote == "'":
                quote = None
            index += 1
            continue
        if character == '"' and quote != "'":
            quote = None if quote == '"' else '"'
            index += 1
            continue
        if quote is not None:
            index += 1
            continue
        if character == "#" and _can_start_comment(line, index):
            break
        if line.startswith("((", index):
            arithmetic_depth += 1
            index += 2
            continue
        if arithmetic_depth and line.startswith("))", index):
            arithmetic_depth -= 1
            index += 2
            continue
        if arithmetic_depth:
            index += 1
            continue
        if line.startswith("<<<", index):
            index += 3
            continue
        if line.startswith("<<", index):
            match = HEREDOC_OPERATOR_RE.match(line, index)
            if match is None or line[match.end():match.end() + 1] in (")", "]"):
                index += 2
                continue
            delimiters.append(_heredoc_delimiter_word(match))
            index = match.end()
            continue
        index += 1
    return delimiters, quote


def _can_start_comment(line, index):
    if index == 0:
        return True
    previous = line[index - 1]
    return previous.isspace() or previous in SHELL_PUNCTUATION


def _heredoc_delimiter_word(match):
    for group in ("single", "double"):
        word = match.group(group)
        if word is not None:
            return word
    return match.group("plain").replace("\\", "")


def strip_heredoc_bodies(command):
    """Remove heredoc bodies so their text is never parsed as shell code.

    A heredoc body is data: the shell writes it to the command's standard
    input. Tokenizing it failed on an ordinary apostrophe (issue #236), and
    matching it blocked a mention of a bulk `git add` (issue #262). The shell
    still expands `$(...)` in an unquoted body, so a caller that checks
    expansions reads them from the unstripped text, as the rm check does.

    Ending a body early keeps more text under inspection, so the delimiter
    comparison ignores surrounding whitespace.
    """
    lines = command.split("\n")
    kept = []
    quote = None
    index = 0
    while index < len(lines):
        line = lines[index]
        index += 1
        kept.append(line)
        delimiters, quote = _heredoc_delimiters(line, quote)
        for delimiter in delimiters:
            while index < len(lines):
                body_line = lines[index]
                index += 1
                if body_line.strip() == delimiter:
                    break
    return "\n".join(kept)


def _data_form_segments(line):
    """Split a form's first line into segments of (kind, text) tokens.

    Return None when the line is outside the grammar of
    `DATA_FORM_TOKEN_RE` or has an empty segment. A heredoc token also
    carries its delimiter word. A redirection token holds its target, so
    the target is never read as a program word.
    """
    segments = [[]]
    index = len(line) - len(line.lstrip(" \t"))
    while index < len(line):
        match = DATA_FORM_TOKEN_RE.match(line, index)
        if match is None:
            return None
        kind = match.lastgroup
        if kind == "separator":
            segments.append([])
        else:
            delimiter = match.group("inner") or match.group("outer")
            segments[-1].append(
                (kind, match.group(kind), delimiter and delimiter.strip("'\"\\"))
            )
        index = match.end()
        while index < len(line) and line[index] in " \t":
            index += 1
    if not all(segment and segment[0][0] == "word" for segment in segments):
        return None
    return segments


def _segment_words(segment):
    return [text for kind, text, _ in segment if kind == "word"]


def _git_subcommand(words):
    """Return the subcommand of `git [-C DIR] SUBCOMMAND ...`, or None."""
    if words[:1] != ["git"]:
        return None
    rest = words[1:]
    if rest[:1] == ["-C"] and len(rest) > 1:
        rest = rest[2:]
    return rest[0] if rest else None


def _data_form_program(words):
    """Return the program of a form segment whose body is data, or None.

    `cat` writes its input, `git commit` reads a message, and the `gh`
    subcommands read a body. None of them runs its input as code.
    """
    if words[:1] == ["cat"]:
        return "cat"
    if _git_subcommand(words) == "commit":
        return "git"
    if (
        words[:1] == ["gh"]
        and len(words) > 2
        and words[2] in GH_DATA_SUBCOMMANDS.get(words[1], ())
    ):
        return "gh"
    return None


def _is_shared_segment(words, before_form):
    """Report whether a segment may share the first line with a form."""
    if before_form and words[:1] in (["cd"], ["mkdir"]):
        return True
    return _git_subcommand(words) in GIT_SEGMENT_SUBCOMMANDS


def _command_without_form_body(command):
    """Return `command` without its body when it is one allowed form (#445).

    A quoted heredoc body is data, but the guard reads its backticks as
    commands. When the whole command is one form whose program does not run
    its input as code, return the command without the body lines. Otherwise
    return None, and the caller scans the whole command.
    """
    lines = command.split("\n")
    segments = _data_form_segments(lines[0])
    if segments is None:
        return None
    operators = [
        (index, token)
        for index, segment in enumerate(segments)
        for token in segment
        if token[0] in ("heredoc", "substitution")
    ]
    if len(operators) != 1:
        return None
    position, (kind, _, delimiter) = operators[0]
    program = _data_form_program(_segment_words(segments[position]))
    if program is None or (kind == "substitution" and program == "cat"):
        return None
    if not all(
        _is_shared_segment(_segment_words(segment), index < position)
        for index, segment in enumerate(segments)
        if index != position
    ):
        return None
    if program == "cat" and position != len(segments) - 1:
        # A later command can run the file that `cat` writes.
        return None

    end = next(
        (index for index in range(1, len(lines)) if lines[index] == delimiter),
        None,
    )
    if end is None:
        return None
    body = lines[1:end]
    if any(
        line.lstrip().startswith(delimiter) or DATA_BODY_CONTROL_RE.search(line)
        for line in body
    ):
        # Bash 3.2 and ksh end a heredoc at a line such as `EOF)`.
        return None
    rest = lines[end + 1:]
    if kind == "substitution":
        # Bash 3.2 reads `"$(cat <<'EOF'` to the first `)` of the body and
        # runs the text after it. Before it reads the heredoc, it also
        # deletes a backslash-newline and expands `$'...'`, which can make a
        # new terminator line. A body without `)`, a backslash, or `$`
        # reaches the heredoc unchanged.
        if any(character in line for line in body for character in ")\\$"):
            return None
        if not rest or not re.fullmatch(r"[ \t]*\)\"[ \t]*", rest[0]):
            return None
        rest = rest[1:]
    if any(line.strip(" \t") for line in rest):
        return None
    return "\n".join([lines[0]] + lines[end:])


def remove_data_heredoc_body(command):
    """Return `command` without the quoted heredoc body of an allowed form.

    Any other command, and any command that the form check fails on, comes
    back unchanged, so the guard scans it in full.
    """
    try:
        reduced = _command_without_form_body(command)
    except Exception:
        return command
    return command if reduced is None else reduced


def _mentions_removal(command):
    """Report whether text that failed tokenization can still invoke `rm`.

    Quote characters and escaping backslashes are removed first, so a
    quote- or backslash-obfuscated invocation (`r''m`, `r\\m`) still counts.
    The check is deliberately broad: it runs only for text the tokenizer
    rejected, where a false match blocks one command but a missed invocation
    removes files.
    """
    collapsed = _remove_line_continuations(command)
    collapsed = re.sub(r"[\\'\"]", "", collapsed)
    return bool(RM_MENTION_RE.search(collapsed))


def _bounded_segments(tokens):
    """Yield each command segment with the boundary token after it, or None."""
    segment = []
    for token in tokens:
        if _is_boundary(token):
            if segment:
                yield _without_redirections(segment), token
                segment = []
        else:
            segment.append(token)
    if segment:
        yield _without_redirections(segment), None


def _command_segments(tokens):
    for segment, _ in _bounded_segments(tokens):
        yield segment


def _program_name(token):
    return token.rsplit("/", 1)[-1].lower()


def _skip_wrapper_options(tokens, index, value_options):
    while index < len(tokens):
        token = tokens[index]
        if token == "--":
            return index + 1
        if ASSIGNMENT_RE.match(token):
            index += 1
            continue
        if not token.startswith("-") or token == "-":
            return index
        option = token.split("=", 1)[0]
        takes_separate_value = (
            option in value_options
            and "=" not in token
        )
        if (
            token.startswith("-")
            and not token.startswith("--")
            and len(token) > 2
            and "=" not in token
        ):
            for option_index, character in enumerate(token[1:]):
                if f"-{character}" not in value_options:
                    continue
                takes_separate_value = (
                    option_index == len(token[1:]) - 1
                )
                break
        index += 1
        if (
            takes_separate_value
            and index < len(tokens)
        ):
            index += 1
    return index


def _initial_command_index(segment):
    index = 0
    if len(segment) >= 2 and segment[0] == "function":
        index = 2
    while index < len(segment) and segment[index] in CONTROL_PREFIXES:
        index += 1
    while index < len(segment) and ASSIGNMENT_RE.match(segment[index]):
        index += 1
    return index


def _next_wrapped_command_index(segment, index):
    program = _program_name(segment[index])
    if program in SIMPLE_WRAPPERS:
        return _skip_wrapper_options(
            segment,
            index + 1,
            SIMPLE_WRAPPERS[program],
        )
    if program == "env":
        return _skip_wrapper_options(
            segment,
            index + 1,
            ENV_VALUE_OPTIONS,
        )
    if program == "sudo":
        return _skip_wrapper_options(
            segment,
            index + 1,
            SUDO_VALUE_OPTIONS,
        )
    if program in PROCESS_WRAPPERS:
        value_options, positional_arguments = PROCESS_WRAPPERS[program]
        command_index = _skip_wrapper_options(
            segment,
            index + 1,
            value_options,
        )
        return min(
            len(segment),
            command_index + positional_arguments,
        )
    return None


def _command_analysis(segment):
    positions = []
    index = _initial_command_index(segment)
    while index < len(segment):
        positions.append(index)
        next_index = _next_wrapped_command_index(segment, index)
        if next_index is None:
            break
        index = next_index
    return positions, index


def _command_index(segment):
    _, index = _command_analysis(segment)
    return index


def _rm_arguments(segment):
    index = _command_index(segment)
    if index < len(segment) and _program_name(segment[index]) == "rm":
        return segment[index + 1:]
    return None


def _invocation_segments(segment):
    yield segment
    index = _command_index(segment)
    if index >= len(segment) or _program_name(segment[index]) != "find":
        return
    marker_index = index + 1
    while marker_index < len(segment):
        if segment[marker_index] not in {"-exec", "-execdir", "-ok", "-okdir"}:
            marker_index += 1
            continue
        command_end = marker_index + 1
        while (
            command_end < len(segment)
            and segment[command_end] not in {";", "+"}
        ):
            command_end += 1
        yield segment[marker_index + 1:command_end]
        marker_index = command_end + 1


def _find_substituted_rm_targets(segment):
    index = _command_index(segment)
    if index >= len(segment) or _program_name(segment[index]) != "find":
        return

    argument_index = index + 1
    while argument_index < len(segment):
        argument = segment[argument_index]
        if argument in {"-H", "-L", "-P"}:
            argument_index += 1
            continue
        if argument == "-D" and argument_index + 1 < len(segment):
            argument_index += 2
            continue
        if argument.startswith("-O") and len(argument) > 2:
            argument_index += 1
            continue
        if argument == "--":
            argument_index += 1
        break

    find_paths = []
    for argument in segment[argument_index:]:
        if (
            argument.startswith("-")
            or argument in {"!", "(", ")", ","}
        ):
            break
        find_paths.append(argument)
    if not find_paths:
        find_paths.append(".")

    first_segment = True
    for invocation in _invocation_segments(segment):
        if first_segment:
            first_segment = False
            continue
        arguments = _rm_arguments(invocation)
        if arguments is None:
            continue
        if any(
            target.startswith("{}")
            for target in _rm_targets(arguments)
        ):
            for path in find_paths:
                yield path


def _nested_shell_command(segment):
    index = _command_index(segment)
    if (
        index >= len(segment)
        or _program_name(segment[index]) not in SHELL_PROGRAMS
    ):
        return None

    arguments = segment[index + 1:]
    argument_index = 0
    while argument_index < len(arguments):
        argument = arguments[argument_index]
        option = argument.split("=", 1)[0]
        if option in SHELL_VALUE_OPTIONS:
            argument_index += 1
            if "=" not in argument:
                argument_index += 1
            continue
        if argument == "--" or not argument.startswith("-"):
            return None
        if not argument.startswith("--") and "c" in argument[1:]:
            command_index = argument_index + 1
            if command_index < len(arguments):
                return arguments[command_index]
            return None
        argument_index += 1
    return None


def _fish_shell_commands(segment):
    index = _command_index(segment)
    if (
        index >= len(segment)
        or _program_name(segment[index]) != "fish"
    ):
        return
    arguments = segment[index + 1:]
    argument_index = 0
    while argument_index < len(arguments):
        argument = arguments[argument_index]
        if argument == "--" or not argument.startswith("-"):
            return
        if argument in {"-c", "--command", "-C", "--init-command"}:
            if argument_index + 1 < len(arguments):
                yield arguments[argument_index + 1]
            argument_index += 2
            continue
        if (
            argument.startswith("--command=")
            or argument.startswith("--init-command=")
        ):
            yield argument.split("=", 1)[1]
        elif argument.startswith("-") and not argument.startswith("--"):
            short_options = argument[1:]
            for option_index, option in enumerate(short_options):
                if option not in {"c", "C"}:
                    continue
                inline_command = short_options[option_index + 1:]
                if inline_command:
                    yield inline_command
                elif argument_index + 1 < len(arguments):
                    yield arguments[argument_index + 1]
                    argument_index += 1
                break
        argument_index += 1


def _nested_launcher_commands(segment):
    index = _command_index(segment)
    if (
        index < len(segment)
        and _program_name(segment[index]) == "fish"
    ):
        for shell_command in _fish_shell_commands(segment):
            yield shell_command
    else:
        shell_command = _nested_shell_command(segment)
        if shell_command is not None:
            yield shell_command

    positions, command_index = _command_analysis(segment)
    for position in positions:
        program = _program_name(segment[position])
        if program in {"parallel", "watch"}:
            nested_index = _next_wrapped_command_index(
                segment,
                position,
            )
            if nested_index is None or nested_index >= len(segment):
                continue
            if program == "watch" and any(
                argument == "--exec"
                or (
                    argument.startswith("-")
                    and not argument.startswith("--")
                    and "x" in argument[1:]
                )
                for argument in segment[position + 1:nested_index]
            ):
                continue
            nested_arguments = segment[nested_index:]
            if program == "parallel" and ":::" in nested_arguments:
                nested_arguments = nested_arguments[
                    :nested_arguments.index(":::")
                ]
            if nested_arguments:
                yield " ".join(nested_arguments)

    if (
        command_index < len(segment)
        and _program_name(segment[command_index]) == "eval"
    ):
        yield " ".join(segment[command_index + 1:])


def _env_split_invocations(segment):
    positions, _ = _command_analysis(segment)
    for position in positions:
        if _program_name(segment[position]) != "env":
            continue
        split_string = None
        remaining_index = None
        argument_index = position + 1
        while argument_index < len(segment):
            argument = segment[argument_index]
            if argument == "--" or ASSIGNMENT_RE.match(argument):
                break
            if argument in {"-S", "--split-string"}:
                if argument_index + 1 < len(segment):
                    split_string = segment[argument_index + 1]
                    remaining_index = argument_index + 2
                break
            if argument.startswith("--split-string="):
                split_string = argument.split("=", 1)[1]
                remaining_index = argument_index + 1
                break
            if argument.startswith("-S") and argument != "-S":
                split_string = argument[2:].lstrip("=")
                remaining_index = argument_index + 1
                break
            if not argument.startswith("-") or argument == "-":
                break
            option = argument.split("=", 1)[0]
            argument_index += 1
            if (
                option in ENV_VALUE_OPTIONS
                and "=" not in argument
                and argument_index < len(segment)
            ):
                argument_index += 1
        if split_string is None or remaining_index is None:
            continue
        split_arguments = shlex.split(
            split_string,
            comments=False,
            posix=True,
        )
        yield split_arguments + segment[remaining_index:]


def _find_backtick_end(command, start):
    index = start
    while index < len(command):
        if command[index] == "\\":
            index += 2
        elif command[index] == "`":
            return index
        else:
            index += 1
    return None


def _find_substitution_end(command, start):
    depth = 1
    quote = None
    index = start
    while index < len(command):
        character = command[index]
        if character == "\\" and quote != "'":
            index += 2
            continue
        if character == "'" and quote != '"':
            quote = None if quote == "'" else "'"
            index += 1
            continue
        if character == '"' and quote != "'":
            quote = None if quote == '"' else '"'
            index += 1
            continue
        if quote is not None:
            index += 1
            continue
        if character == "`":
            end = _find_backtick_end(command, index + 1)
            if end is None:
                return None
            index = end + 1
            continue
        if character == "(":
            depth += 1
        elif character == ")":
            depth -= 1
            if depth == 0:
                return index
        index += 1
    return None


def _command_substitutions(command):
    quote = None
    index = 0
    while index < len(command):
        character = command[index]
        if character == "\\" and quote != "'":
            index += 2
            continue
        if character == "'":
            if quote is None:
                quote = "'"
            elif quote == "'":
                quote = None
            index += 1
            continue
        if character == '"' and quote != "'":
            quote = None if quote == '"' else '"'
            index += 1
            continue
        if quote == "'":
            index += 1
            continue
        if (
            quote is None
            and character in {"<", ">"}
            and index + 1 < len(command)
            and command[index + 1] == "("
        ):
            end = _find_substitution_end(command, index + 2)
            if end is None:
                return
            yield command[index + 2:end]
            index = end + 1
            continue
        if (
            character == "$"
            and index + 1 < len(command)
            and command[index + 1] == "("
            and not command.startswith("$((", index)
        ):
            end = _find_substitution_end(command, index + 2)
            if end is None:
                return
            yield command[index + 2:end]
            index = end + 1
            continue
        if character == "`":
            end = _find_backtick_end(command, index + 1)
            if end is None:
                return
            yield command[index + 1:end]
            index = end + 1
            continue
        index += 1


def _rm_targets(arguments):
    options_finished = False
    for argument in arguments:
        if not options_finished and argument == "--":
            options_finished = True
        elif (
            not options_finished
            and argument.startswith("-")
            and argument != "-"
        ):
            continue
        else:
            yield argument


def _resolved_absolute_path(value):
    path = Path(value).expanduser()
    if not path.is_absolute():
        return None
    return path.resolve(strict=False)


def _matching_protected_system_path(path):
    lowered = path.as_posix().rstrip("/").lower()
    for protected in PROTECTED_SYSTEM_PATHS:
        if lowered == protected or lowered.startswith(protected + "/"):
            return protected
    return None


def _is_macos_user_temp_root(root):
    for parent_value in ("/var/folders", "/private/var/folders"):
        parent = _resolved_absolute_path(parent_value)
        try:
            relative = root.relative_to(parent)
        except ValueError:
            continue
        if len(relative.parts) == 3 and relative.parts[-1] == "T":
            return True
    return False


def _is_trusted_temp_root(root):
    for protected_value in PROTECTED_SYSTEM_PATHS:
        protected_path = _resolved_absolute_path(protected_value)
        try:
            protected_path.relative_to(root)
        except ValueError:
            continue
        return False

    protected = _matching_protected_system_path(root)
    if protected is None:
        return True
    if protected in {"/var", "/private/var"}:
        return _is_macos_user_temp_root(root)
    return False


def _temp_roots():
    roots = []
    for value in (os.environ.get("TMPDIR"), tempfile.gettempdir()):
        if not value:
            continue
        root = _resolved_absolute_path(value)
        if (
            root is not None
            and _is_trusted_temp_root(root)
            and root not in roots
        ):
            roots.append(root)
    return roots


def _temp_relationship(target):
    candidate = _resolved_absolute_path(target)
    if candidate is None:
        return None
    roots = _temp_roots()
    if candidate in roots:
        return "root"
    for root in roots:
        try:
            candidate.relative_to(root)
        except ValueError:
            continue
        return "descendant"
    return None


def _dangerous_target_reason(target):
    if "*" in target:
        return "wildcard rm target"

    normalized = target.rstrip("/") or "/"
    if normalized.startswith("/"):
        normalized = re.sub(r"/+", "/", normalized)
    lowered = normalized.lower()
    if normalized == "/":
        return "root directory"
    if normalized == ".":
        return "current directory target"
    if ".." in target.split("/"):
        return "parent directory reference"
    if (
        lowered.startswith("~")
        or re.match(r"^\$home(?:$|[^a-z0-9_])", lowered)
        or lowered.startswith("${home}")
    ):
        return "home directory target"

    temp_relationship = _temp_relationship(target)
    if temp_relationship == "root":
        return "temporary directory root"
    if temp_relationship == "descendant":
        return None

    for protected in PROTECTED_SYSTEM_PATHS:
        if lowered == protected or lowered.startswith(protected + "/"):
            return f"protected system path {protected}"
    return None


def _dangerous_segment_reason(segment, depth):
    if depth > MAX_NESTED_SHELL_DEPTH:
        return "unparseable rm command"
    for target in _find_substituted_rm_targets(segment):
        reason = _dangerous_target_reason(target)
        if reason:
            return reason
    for invocation in _invocation_segments(segment):
        arguments = _rm_arguments(invocation)
        if arguments is not None:
            for target in _rm_targets(arguments):
                reason = _dangerous_target_reason(target)
                if reason:
                    return reason
        for nested_invocation in _env_split_invocations(invocation):
            reason = _dangerous_segment_reason(
                nested_invocation,
                depth + 1,
            )
            if reason:
                return reason
        for nested_command in _nested_launcher_commands(invocation):
            reason = _dangerous_rm_reason(
                nested_command,
                depth + 1,
            )
            if reason:
                return reason
    return None


def _dangerous_rm_reason(command, depth):
    if depth > MAX_NESTED_SHELL_DEPTH:
        return "unparseable rm command"
    expanded_text = _strip_shell_comments(_remove_line_continuations(command))
    for nested_command in _command_substitutions(expanded_text):
        reason = _dangerous_rm_reason(nested_command, depth + 1)
        if reason:
            return reason

    # Heredoc bodies are data. Strip them before tokenizing, and keep the
    # stripped text for the fallback below so prose cannot decide the outcome.
    executable_text = _executable_text(command)
    try:
        segments = _command_segments(_shell_tokens(executable_text))
        for segment in segments:
            reason = _dangerous_segment_reason(segment, depth)
            if reason:
                return reason
    except ValueError:
        # The tokenizer reports malformed input, usually an unbalanced quote,
        # as a ValueError. Block only when the command text can still invoke
        # `rm`; text the tokenizer rejects removes nothing on its own.
        if _mentions_removal(executable_text):
            return "unparseable rm command"
    return None


def _executable_text(command):
    """Return `command` without heredoc bodies, line continuations, and
    comments, ready to tokenize."""
    return _strip_shell_comments(
        _remove_line_continuations(strip_heredoc_bodies(command))
    )


VARIABLE_LISTING_BUILTINS = {"declare", "export", "typeset"}
HELP_OR_VERSION_OPTIONS = {"--help", "--version"}
AWK_NAMES_ONLY_PROGRAM = r"\{\s*print\s+\$1\s*\}"
AWK_NAMES_ONLY_RE = re.compile(AWK_NAMES_ONLY_PROGRAM)
QUOTED_AWK_NAMES_ONLY_RE = re.compile(f"'{AWK_NAMES_ONLY_PROGRAM}'")


def _shows_help_or_version(segment, start, value_options):
    """Report whether an option word from `segment[start]` on is `--help`
    or `--version`, which print no variable.

    A word counts only where the `_skip_wrapper_options` scan would stop
    at a plain word, so the value of an option before it, as in
    `env -u --help`, does not count.
    """
    return any(
        segment[index] in HELP_OR_VERSION_OPTIONS
        and _skip_wrapper_options(
            segment[:index] + ["word"], start, value_options
        ) == index
        for index in range(start, len(segment))
    )


def _prints_environment(segment):
    """Report whether `segment` prints every environment variable.

    These forms print every value: `env` with only options and
    assignments, `printenv` with no variable name, `export`, `declare`, or
    `typeset` with only option words, and `set` with no argument. `env -S`
    runs a command, `--help` and `--version` print no variable, and
    `command -v env` only looks the command up.
    """
    positions, index = _command_analysis(segment)
    if any(
        _program_name(segment[position]) == "command"
        and re.match(r"-[A-Za-z]*[vV]", segment[position + 1])
        for position in positions
        if position + 1 < len(segment)
    ):
        return False
    if index < len(segment):
        program = _program_name(segment[index])
        arguments = segment[index + 1:]
        if program == "set":
            return not arguments
        if program in VARIABLE_LISTING_BUILTINS:
            return all(
                argument.startswith(("-", "+")) for argument in arguments
            )
        return (
            program == "printenv"
            and all(argument.startswith("-") for argument in arguments)
            and not _shows_help_or_version(segment, index + 1, set())
        )
    return (
        bool(positions)
        and _program_name(segment[positions[-1]]) == "env"
        and next(_env_split_invocations(segment), None) is None
        and not _shows_help_or_version(
            segment, positions[-1] + 1, ENV_VALUE_OPTIONS
        )
    )


def _keeps_names_only(segment, text):
    """Report whether `segment` keeps only the name before the first `=` of
    each line: `cut -d= -f1` in any option form, or `awk -F= '{print $1}'`.

    Tokens lose their quotes, so the awk form counts only when each `$1` in
    the command `text` is in a single-quoted `{print $1}`. The shell
    expands `$1` in other text, usually to nothing, and awk then prints
    each whole line.
    """
    index = _command_index(segment)
    if index >= len(segment):
        return False
    program = _program_name(segment[index])
    arguments = segment[index + 1:]
    if program == "awk":
        return (
            arguments[:-1] in (["-F="], ["-F", "="])
            and AWK_NAMES_ONLY_RE.fullmatch(arguments[-1]) is not None
            and text.count("$1") == len(QUOTED_AWK_NAMES_ONLY_RE.findall(text))
        )
    if program != "cut":
        return False
    options = {}
    words = iter(arguments)
    for word in words:
        if word.startswith("--"):
            name, equals, value = word.partition("=")
            key = {"--delimiter": "d", "--fields": "f"}.get(name)
            if key:
                options[key] = value if equals else next(words, None)
        elif word[:2] in ("-d", "-f"):
            options[word[1]] = word[2:] or next(words, None)
    return options == {"d": "=", "f": "1"}


def prints_environment(command, depth=0):
    """Report whether `command` prints every environment variable (#391).

    A value can be a token. Output piped straight into `cut -d= -f1` or
    `awk -F= '{print $1}'` is allowed, because it keeps the names only.
    Command substitutions are checked too, also inside double quotes.
    """
    if depth > MAX_NESTED_SHELL_DEPTH:
        return False
    substitutions = _command_substitutions(
        _strip_shell_comments(_remove_line_continuations(command))
    )
    if any(prints_environment(nested, depth + 1) for nested in substitutions):
        return True
    text = _executable_text(command)
    try:
        segments = list(_bounded_segments(_shell_tokens(text)))
    except ValueError:
        return False
    for index, (segment, boundary) in enumerate(segments):
        if not _prints_environment(segment):
            continue
        if (
            boundary in ("|", "|&")
            and index + 1 < len(segments)
            and _keeps_names_only(segments[index + 1][0], text)
        ):
            continue
        return True
    return False


def dangerous_rm_reason(command):
    try:
        return _dangerous_rm_reason(command, 0)
    except Exception:
        return "shell command safety analysis failed"


def is_dangerous_rm_command(command):
    """
    Selective detection of dangerous rm commands.
    Only blocks rm commands with dangerous paths or patterns while allowing explicit removals.
    """
    return dangerous_rm_reason(command) is not None


def _log_error(text, host, input_data):
    directory = host_log_dir(host, input_data)
    if directory is not None:
        with open(directory / 'hook_errors.log', 'a') as f:
            f.write(text)


# How to turn off the plugin on each host, so that a bug in the guard does
# not leave the user with no way to run a command (#487).
TURN_OFF_PLUGIN_STEPS = {
    None: "run `claude plugin disable core-hooks@cc-toolkit` in a terminal",
    CODEX: (
        "set `enabled = false` in the `[plugins.\"core-hooks@cc-toolkit\"]` "
        "table of `~/.codex/config.toml`"
    ),
    ANTIGRAVITY: "run `agy plugin disable core-hooks` in a terminal",
}


def error_status(host):
    """Return the exit status after a script error on `host`.

    A script error blocks the tool call on every host, because the guard
    cannot decide (#487). Claude Code blocks on status 2. In Codex and
    Antigravity mode, the status is 1, and the `hooks/hooks.codex.json` and
    root `hooks.json` wrappers block with their "hook failed" line.
    """
    return 1 if host in (ANTIGRAVITY, CODEX) else 2


def block_on_error(error, host, input_data):
    """Log `error`, then block the tool call with a message that names
    `error` and tells how to turn off the plugin."""
    description = f"{type(error).__name__}: {error}"
    try:
        _log_error(f"{description}\n{traceback.format_exc()}\n", host, input_data)
    except Exception:
        pass  # The block must not depend on the log.
    print(
        "BLOCKED: The core-hooks safety guard failed, so it cannot check this "
        f"tool call. Error: {description}",
        file=sys.stderr,
    )
    steps = TURN_OFF_PLUGIN_STEPS.get(host, TURN_OFF_PLUGIN_STEPS[None])
    print(
        f"To turn off the core-hooks plugin, {steps}, then start a new session.",
        file=sys.stderr,
    )
    sys.exit(error_status(host))


def main():
    # In Antigravity mode, stdout stays empty, because Antigravity reads text
    # on stdout as a decision. In Antigravity and Codex mode, a block is exit 3
    # with the reason on stderr, and the root hooks.json and
    # hooks/hooks.codex.json change it to 2.
    host = host_argument(sys.argv[1:])
    input_data = None
    try:
        # Read JSON input from stdin
        input_data = json.load(sys.stdin)

        command = get_shell_command(input_data)
        if command:
            command = remove_data_heredoc_body(command)

        # Block dangerous rm commands while allowing explicit removals
        reason = dangerous_rm_reason(command) if command else None
        if reason:
            print("BLOCKED: Potentially dangerous rm command detected", file=sys.stderr)
            print(f"Reason: {reason}", file=sys.stderr)
            print("Safe explicit removals like 'rm -rf specific_folder' are allowed", file=sys.stderr)
            # The root hooks.json and hooks/hooks.codex.json map 3 to 2.
            sys.exit(block_status(host))

        if command and prints_environment(command):
            print(
                "BLOCKED: The command prints every environment variable, and "
                "a value can be a token. This applies to `env` or `printenv` "
                "with no command, `export`, `declare`, or `typeset` with no "
                "name, and `set` with no argument. To list the names only, "
                "run `env | cut -d= -f1`. To read one variable, run "
                "`printenv NAME`.",
                file=sys.stderr,
            )
            sys.exit(block_status(host))

        directory = host_log_dir(host, input_data)
        if directory is not None:
            append_log('pre_tool_use.jsonl', input_data, directory)

        sys.exit(0)

    except Exception as error:
        block_on_error(error, host, input_data)

if __name__ == '__main__':
    main()
