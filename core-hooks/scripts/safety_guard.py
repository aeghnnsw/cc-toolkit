#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.8"
# ///

import json
import os
import re
import shlex
import sys
import tempfile
from pathlib import Path


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


def get_shell_command(tool_name, tool_input):
    if not isinstance(tool_input, dict):
        return ''
    if tool_name == 'Bash':
        return tool_input.get('command', '')
    if tool_name == 'exec_command':
        return tool_input.get('cmd', '')
    return ''


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


def _command_segments(tokens):
    segment = []
    for token in tokens:
        if _is_boundary(token):
            if segment:
                yield _without_redirections(segment)
                segment = []
        else:
            segment.append(token)
    if segment:
        yield _without_redirections(segment)


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
        or "$home" in lowered
        or "${home}" in lowered
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
    try:
        executable_text = _remove_line_continuations(command)
        executable_text = _strip_shell_comments(executable_text)
        for nested_command in _command_substitutions(executable_text):
            reason = _dangerous_rm_reason(nested_command, depth + 1)
            if reason:
                return reason
        segments = _command_segments(_shell_tokens(executable_text))
        for segment in segments:
            reason = _dangerous_segment_reason(segment, depth)
            if reason:
                return reason
    except ValueError:
        if re.search(r"\brm(?:\s|$)", command, re.IGNORECASE):
            return "unparseable rm command"
    return None


def dangerous_rm_reason(command):
    return _dangerous_rm_reason(command, 0)


def is_dangerous_rm_command(command):
    """
    Selective detection of dangerous rm commands.
    Only blocks rm commands with dangerous paths or patterns while allowing explicit removals.
    """
    return dangerous_rm_reason(command) is not None


def main():
    try:
        # Read JSON input from stdin
        input_data = json.load(sys.stdin)

        tool_name = input_data.get('tool_name', '')
        tool_input = input_data.get('tool_input', {})

        command = get_shell_command(tool_name, tool_input)

        # Block dangerous rm commands while allowing explicit removals
        reason = dangerous_rm_reason(command) if command else None
        if reason:
            print("BLOCKED: Potentially dangerous rm command detected", file=sys.stderr)
            print(f"Reason: {reason}", file=sys.stderr)
            print("Safe explicit removals like 'rm -rf specific_folder' are allowed", file=sys.stderr)
            sys.exit(2)  # Exit code 2 blocks tool call and shows error to Claude/Codex

        # Ensure log directory exists
        log_dir = Path.cwd() / 'logs'
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / 'pre_tool_use.json'

        # Read existing log data or initialize empty list
        if log_path.exists():
            with open(log_path, 'r') as f:
                try:
                    log_data = json.load(f)
                except (json.JSONDecodeError, ValueError):
                    log_data = []
        else:
            log_data = []

        # Append new data
        log_data.append(input_data)

        # Write back to file with formatting
        with open(log_path, 'w') as f:
            json.dump(log_data, f, indent=2)

        sys.exit(0)

    except json.JSONDecodeError as e:
        # Log error and allow command (fail-open for JSON errors)
        debug_log = Path.cwd() / 'logs' / 'hook_errors.log'
        debug_log.parent.mkdir(parents=True, exist_ok=True)
        with open(debug_log, 'a') as f:
            f.write(f"JSONDecodeError: {e}\n")
        sys.exit(0)
    except Exception as e:
        # Log error and allow command (fail-open for safety)
        debug_log = Path.cwd() / 'logs' / 'hook_errors.log'
        debug_log.parent.mkdir(parents=True, exist_ok=True)
        with open(debug_log, 'a') as f:
            import traceback
            f.write(f"Exception: {e}\n{traceback.format_exc()}\n")
        sys.exit(0)

if __name__ == '__main__':
    main()
