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
SIMPLE_WRAPPERS = {"command", "exec", "nohup", "time"}
SHELL_PROGRAMS = {"bash", "dash", "fish", "ksh", "sh", "zsh"}
ASSIGNMENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
SUDO_VALUE_OPTIONS = {
    "-u", "--user", "-g", "--group", "-h", "--host", "-p", "--prompt",
    "-C", "--chdir", "-r", "--role", "-t", "--type",
}
ENV_VALUE_OPTIONS = {"-u", "--unset", "-C", "--chdir"}
SHELL_VALUE_OPTIONS = {"-O", "+O", "-o", "--init-file", "--rcfile"}
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
    lexer = shlex.shlex(
        command,
        posix=True,
        punctuation_chars=SHELL_PUNCTUATION,
    )
    lexer.whitespace = " \t\r"
    lexer.whitespace_split = True
    lexer.commenters = ""
    return list(lexer)


def _is_boundary(token):
    return token and all(
        character in SHELL_PUNCTUATION
        for character in token
    )


def _command_segments(tokens):
    segment = []
    in_comment = False
    for token in tokens:
        if in_comment:
            if "\n" in token:
                if segment:
                    yield segment
                    segment = []
                in_comment = False
            continue
        if token.startswith("#"):
            in_comment = True
        elif _is_boundary(token):
            if segment:
                yield segment
                segment = []
        else:
            segment.append(token)
    if segment:
        yield segment


def _program_name(token):
    return token.rsplit("/", 1)[-1]


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
        index += 1
        if (
            option in value_options
            and "=" not in token
            and index < len(tokens)
        ):
            index += 1
    return index


def _command_index(segment):
    index = 0
    if len(segment) >= 2 and segment[0] == "function":
        index = 2
    while index < len(segment) and segment[index] in CONTROL_PREFIXES:
        index += 1
    while index < len(segment) and ASSIGNMENT_RE.match(segment[index]):
        index += 1

    while index < len(segment):
        program = _program_name(segment[index])
        if program in SIMPLE_WRAPPERS:
            index = _skip_wrapper_options(segment, index + 1, set())
        elif program == "env":
            index = _skip_wrapper_options(
                segment,
                index + 1,
                ENV_VALUE_OPTIONS,
            )
        elif program == "sudo":
            index = _skip_wrapper_options(
                segment,
                index + 1,
                SUDO_VALUE_OPTIONS,
            )
        else:
            break

    return index


def _rm_arguments(segment):
    index = _command_index(segment)
    if index < len(segment) and _program_name(segment[index]) == "rm":
        return segment[index + 1:]
    return None


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
        if argument == "--" or not argument.startswith("-"):
            return None
        option = argument.split("=", 1)[0]
        if option in SHELL_VALUE_OPTIONS and "=" not in argument:
            argument_index += 2
            continue
        if not argument.startswith("--") and "c" in argument[1:]:
            command_index = argument_index + 1
            if command_index < len(arguments):
                return arguments[command_index]
            return None
        argument_index += 1
    return None


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
        if len(relative.parts) >= 3 and relative.parts[-1] == "T":
            return True
    return False


def _is_trusted_temp_root(root):
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


def _dangerous_rm_reason(command, depth):
    if depth > MAX_NESTED_SHELL_DEPTH:
        return "unparseable rm command"
    try:
        for nested_command in _command_substitutions(command):
            reason = _dangerous_rm_reason(nested_command, depth + 1)
            if reason:
                return reason
        segments = _command_segments(_shell_tokens(command))
        for segment in segments:
            arguments = _rm_arguments(segment)
            if arguments is not None:
                for target in _rm_targets(arguments):
                    reason = _dangerous_target_reason(target)
                    if reason:
                        return reason
            nested_command = _nested_shell_command(segment)
            if nested_command is not None:
                reason = _dangerous_rm_reason(nested_command, depth + 1)
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
