#!/usr/bin/env python3
"""Hold a t3-project-lead session to lead actions (issue #520).

Claude Code, Codex, and Antigravity run this hook before a tool call
(PreToolUse), and Claude Code and Codex also run it on each user message
(UserPromptSubmit). It reads the host's JSON payload on stdin. Run it as
`python3 t3_project_lead_hook.py --host claude|codex|antigravity`.

- Record: when a shell call is exactly `python3 <path>/t3_project_lead.py
  start`, and the script is this hook's sibling or a copy outside every Git
  work tree, the hook writes an empty file named by the session ID to the
  state folder. A copy inside a Git work tree, such as a developer's
  worktree, records nothing, and so does `start` with more words. Each new
  record deletes records older than 30 days.
- Other sessions: without a record, the hook exits 0 with no output, even on
  an error.
- Gate (issue #530): in a recorded session, the hook allows one simple shell
  command `python3 <script> <subcommand> [arguments...]`, where the script
  passes the record check, and file reads in T3 Code's attachments folder.
  It blocks every other shell command, every other file read, every file
  edit, and native subagents, so only the script reads or writes the lead
  state. MCP tools and other tools pass. A blocked call exits 2 with the
  reason on stderr. A call that the hook cannot check also exits 2.
- Reminder: on a user message in a recorded session, Claude Code and Codex
  get additional context that tells the lead to run `start` first.

`T3_PROJECT_LEAD_STATE_DIR` sets the state folder; the default is
`${XDG_STATE_HOME:-$HOME/.local/state}/dev-skills/t3-project-lead/sessions`.
"""

from __future__ import annotations

import os
import sys

SCRIPT_NAME = "t3_project_lead.py"
ANTIGRAVITY = "antigravity"
SESSION_CHARACTERS = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789._-")
RECORD_DAYS = 30
BLOCK_LINE = ("BLOCKED: t3-project-lead: This is not a lead action. Give it to a worker with "
              "`t3_project_lead.py dispatch`.")
ALLOWED = {
    "shell": ('Allowed commands: python3 "{script}" <step or command> [arguments], as one simple '
              "command: no pipe, redirect, list, or substitution. Quote text with single quotes."),
    "read": "Allowed reads: T3 attachments. Print the lead state with t3_project_lead.py show.",
    "edit": "No file edits. Change the lead state with t3_project_lead.py commands.",
    "agent": "Start a worker with delegate_task, as t3_project_lead.py dispatch says.",
    "error": "The hook could not check this call ({error}). Allowed: the lead actions that "
             "t3_project_lead.py start lists.",
}

# Tool names of each kind, for all three hosts.
SHELL_TOOLS = {"Bash": "command", "Monitor": "command", "exec_command": "cmd", "shell": "command",
               "run_command": "CommandLine"}
READ_TOOLS = frozenset({"Read", "Grep", "Glob", "read_file", "view_file", "view_file_outline",
                        "view_code_item", "list_dir", "grep_search", "find_by_name", "codebase_search"})
EDIT_TOOLS = frozenset({"Write", "Edit", "MultiEdit", "NotebookEdit", "write_file", "edit_file",
                        "write_to_file", "replace_file_content", "multi_replace_file_content"})
AGENT_TOOLS = frozenset({"Agent", "Task", "spawn_agent", "invoke_subagent"})
# Path arguments: Claude Code first, then Antigravity.
PATH_KEYS = ("file_path", "notebook_path", "path", "AbsolutePath", "Path", "File", "FilePath",
             "TargetFile", "DirectoryPath", "SearchPath", "SearchDirectory")
WRAPPER_SHELLS = frozenset({"bash", "sh", "zsh"})


class Blocked(Exception):
    """The call is not a lead action. The argument names the kind of call."""


def host_argument(argv):
    for index, argument in enumerate(argv[:-1]):
        if argument == "--host":
            return argv[index + 1]
    return "claude"


def session_id(payload, host):
    """Return the session ID of `payload`, or None when it has no valid one."""
    value = payload.get("conversationId" if host == ANTIGRAVITY else "session_id")
    if (not isinstance(value, str) or not value or value.strip(".") == ""
            or not SESSION_CHARACTERS.issuperset(value)):
        return None
    return value


def state_dir():
    folder = os.environ.get("T3_PROJECT_LEAD_STATE_DIR")
    if folder:
        return folder
    base = os.environ.get("XDG_STATE_HOME") or os.path.join(os.path.expanduser("~"), ".local", "state")
    return os.path.join(base, "dev-skills", "t3-project-lead", "sessions")


def sibling_script():
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), SCRIPT_NAME)


def main(argv):
    host = host_argument(argv)
    try:
        raw = sys.stdin.read()
        folder = state_dir()
        try:
            names = os.listdir(folder)
        except OSError:
            names = []
        # Fast path, with no JSON import: when no record name is in the
        # payload, the session has no record, and only a start run matters.
        if SCRIPT_NAME not in raw and not any(name in raw for name in names):
            return 0
        import json

        payload = json.loads(raw)
        session = session_id(payload, host) if isinstance(payload, dict) else None
        if session is None:
            return 0
        recorded = os.path.isfile(os.path.join(folder, session))
        if not recorded and SCRIPT_NAME not in raw:
            return 0
    except Exception:
        return 0
    if not recorded:
        try:
            start_run(payload, host, folder, session)
        except Exception:
            pass
        return 0
    event = payload.get("hookEventName" if host == ANTIGRAVITY else "hook_event_name")
    if event == "UserPromptSubmit":
        if host != ANTIGRAVITY:
            reminder = ("This is a t3-project-lead session. Before anything else in this turn, run: "
                        f'python3 "{sibling_script()}" start')
            print(json.dumps({"hookSpecificOutput": {"hookEventName": "UserPromptSubmit",
                                                     "additionalContext": reminder}}))
        return 0
    if event not in (None, "PreToolUse"):
        return 0
    try:
        gate(payload, host, folder, session)
    except Blocked as blocked:
        return block(ALLOWED[blocked.args[0]].format(script=sibling_script()))
    except Exception as error:
        return block(ALLOWED["error"].format(error=f"{type(error).__name__}: {error}"))
    return 0


def block(allowed_line):
    print(BLOCK_LINE, file=sys.stderr)
    print(allowed_line, file=sys.stderr)
    return 2


# Tool calls.

def tool_call(payload, host):
    """Return the tool name and input of a PreToolUse payload."""
    if host == ANTIGRAVITY:
        call = payload["toolCall"]
        name, arguments = call["name"], call["args"]
    else:
        name, arguments = payload["tool_name"], payload.get("tool_input")
    if not isinstance(name, str):
        raise ValueError("the tool name is not a string")
    return name, arguments


def payload_cwd(payload):
    cwd = payload.get("cwd")
    return cwd if isinstance(cwd, str) and os.path.isabs(cwd) else None


def start_run(payload, host, folder, session):
    """Write the record when `payload` is a start run of a qualifying script."""
    event = payload.get("hookEventName" if host == ANTIGRAVITY else "hook_event_name")
    if event not in (None, "PreToolUse"):
        return
    name, arguments = tool_call(payload, host)
    if name not in SHELL_TOOLS or not isinstance(arguments, dict):
        return
    words, cwd = shell_words(arguments, SHELL_TOOLS[name], payload_cwd(payload))
    if (words is not None and len(words) == 3 and words[0] in ("python3", "python")
            and words[2] == "start" and step_script(words, cwd)):
        write_record(folder, session)


def gate(payload, host, folder, session):
    """Return when the call is a lead action; raise Blocked otherwise."""
    name, arguments = tool_call(payload, host)
    if name in AGENT_TOOLS or name.endswith("spawn_agent"):
        raise Blocked("agent")
    if name == "apply_patch" or name in EDIT_TOOLS:
        raise Blocked("edit")  # Only t3_project_lead.py writes the lead state.
    if name in SHELL_TOOLS:
        kind = "shell"
    elif name in READ_TOOLS:
        kind = "read"
    else:
        return  # MCP tools and all other tools pass.
    if not isinstance(arguments, dict):
        raise Blocked(kind)
    cwd = payload_cwd(payload)
    if kind == "shell":
        check_shell(arguments, SHELL_TOOLS[name], cwd, folder, session)
        return
    if name == "Glob":
        pattern = arguments.get("pattern")
        if not isinstance(pattern, str) or pattern.startswith(("/", "~")) or ".." in pattern.split("/"):
            raise Blocked(kind)
    default = cwd if name in ("Grep", "Glob") else None
    check_reads(tool_paths(arguments, default), cwd)


def tool_paths(arguments, default):
    """Return the path arguments of a file tool call."""
    paths = []
    for key in PATH_KEYS:
        value = arguments.get(key)
        if value is not None:
            paths.append(value)
    if not paths and default is not None:
        paths.append(default)
    return paths


def check_reads(paths, cwd):
    """Raise Blocked unless `paths` is not empty and each path is in T3 attachments."""
    if not paths:
        raise Blocked("read")
    for path in paths:
        resolved = resolve(path, cwd)
        if resolved is None or not in_attachments(resolved):
            raise Blocked("read")


def resolve(path, cwd):
    """Return the real absolute path of `path`, or None when it cannot be resolved."""
    if not isinstance(path, str) or not path or "\0" in path:
        return None
    path = os.path.expanduser(path)
    if not os.path.isabs(path):
        if cwd is None:
            return None
        path = os.path.join(cwd, path)
    return os.path.realpath(path)


def in_attachments(path):
    """Return whether `path` is in T3 Code's attachments folder, where the user's files arrive."""
    folder = os.path.realpath(os.path.join(os.path.expanduser("~"), ".t3", "userdata", "attachments"))
    return path == folder or path.startswith(folder + os.sep)


def git(cwd, *args):
    """Return the stripped stdout of a git command in `cwd`, or "" on failure."""
    import subprocess

    env = {key: value for key, value in os.environ.items()
           if key not in ("GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR")}
    result = subprocess.run(["git", "-C", cwd, *args], capture_output=True, text=True, env=env,
                            timeout=10, check=False)
    return result.stdout.strip() if result.returncode == 0 else ""


# Records.

def write_record(folder, session):
    import time

    os.makedirs(folder, mode=0o700, exist_ok=True)
    record = os.path.join(folder, session)
    with open(record, "a", encoding="utf-8"):
        pass
    os.utime(record, None)
    oldest = time.time() - RECORD_DAYS * 24 * 60 * 60
    for entry in os.scandir(folder):
        try:
            if entry.is_file(follow_symlinks=False) and entry.stat().st_mtime < oldest:
                os.unlink(entry.path)
        except OSError:
            pass


# Shell commands.

def check_shell(arguments, key, cwd, folder, session):
    """Return when the shell command runs the step script; raise Blocked otherwise.

    The command is `python3|python <script> <subcommand> [arguments...]`.
    Only an exact `python3|python <script> start` refreshes the record.
    """
    words, cwd = shell_words(arguments, key, cwd)
    if (not words or len(words) < 3 or words[0] not in ("python3", "python") or not is_step(words[2])
            or not step_script(words, cwd)):
        raise Blocked("shell")
    if words[2:] == ["start"]:
        try:
            write_record(folder, session)
        except OSError:
            pass  # The record exists; a failed refresh does not stop the step.


def shell_words(arguments, key, cwd):
    """Return the words of the shell command in `arguments` and the folder where it runs.

    The words are None when the command is not one simple command. A Codex
    `bash -lc <script>` wrapper gives the words of the script.
    """
    command = arguments.get(key)
    if isinstance(command, list) and all(isinstance(word, str) for word in command):
        words = list(command)
    elif isinstance(command, str):
        words = split_words(command)
    else:
        raise ValueError(f"the shell command is not a string: {key}")
    if words is not None and len(words) == 3 and words[0] in WRAPPER_SHELLS and words[1] in ("-c", "-lc"):
        words = split_words(words[2])
    workdir = arguments.get("workdir", arguments.get("Cwd"))
    if isinstance(workdir, str) and workdir:
        cwd = os.path.join(cwd, workdir) if cwd is not None else workdir
        cwd = cwd if os.path.isabs(cwd) else None
    return words, cwd


def is_step(word):
    return word.isascii() and word.isalpha() and word.islower()


def step_script(words, cwd):
    """Return whether `words[1]` names this hook's sibling step script, or a
    copy outside every Git work tree."""
    if not words[1].endswith(SCRIPT_NAME):
        return False
    path = resolve(words[1], cwd)
    if path is None or os.path.basename(path) != SCRIPT_NAME:
        return False
    if path == os.path.realpath(sibling_script()):
        return True
    return os.path.isfile(path) and git(os.path.dirname(path), "rev-parse", "--is-inside-work-tree") != "true"


def split_words(command):
    """Return the words of one simple shell command, or None.

    The result is None for a command list, a pipe, a redirect, `&`, a
    subshell, command or process substitution, an unquoted glob or brace,
    a comment, a leading variable assignment, an unset variable, or a quote
    that does not end. Quotes and backslashes are removed, and `$NAME`,
    `${NAME}`, and a leading `~` are expanded from this process's environment.
    """
    command = command.strip()
    words = []
    word = []
    in_word = False
    index = 0
    length = len(command)
    while index < length:
        char = command[index]
        if char in " \t":
            if in_word:
                words.append("".join(word))
                word = []
                in_word = False
            index += 1
            continue
        if char in "\n\r|&;<>()`*?[]{}" or (char in "#=" and not in_word):
            return None
        if char == "~" and not in_word:
            following = command[index + 1:index + 2]
            if following not in ("", "/", " ", "\t"):
                return None
            word.append(os.path.expanduser("~"))
            in_word = True
            index += 1
            continue
        in_word = True
        if char == "\\":
            if index + 1 >= length:
                return None
            word.append(command[index + 1])
            index += 2
        elif char == "'":
            end = command.find("'", index + 1)
            if end < 0:
                return None
            word.append(command[index + 1:end])
            index = end + 1
        elif char == '"':
            index += 1
            while True:
                if index >= length:
                    return None
                char = command[index]
                if char == '"':
                    index += 1
                    break
                if char == "`":
                    return None
                if char == "\\" and command[index + 1:index + 2] in ('"', "\\", "$", "`"):
                    word.append(command[index + 1])
                    index += 2
                elif char == "$":
                    value, index = expand(command, index, quoted=True)
                    if value is None:
                        return None
                    word.append(value)
                else:
                    word.append(char)
                    index += 1
        elif char == "$":
            value, index = expand(command, index, quoted=False)
            # An unquoted expansion splits on spaces and globs in bash.
            if value is None or any(c in value for c in " \t\n*?[]{}"):
                return None
            word.append(value)
        else:
            word.append(char)
            index += 1
    if in_word:
        words.append("".join(word))
    if words and "=" in words[0] and words[0].split("=", 1)[0].isidentifier():
        return None
    return words


def expand(command, index, *, quoted):
    """Expand the `$` at `command[index]`; return (value or None, next index)."""
    following = command[index + 1:index + 2]
    if following in ("", " ", "\t") or (quoted and following == '"'):
        return "$", index + 1
    if following == "{":
        end = command.find("}", index + 2)
        if end < 0:
            return None, index
        name, after = command[index + 2:end], end + 1
    else:
        end = index + 1
        while end < len(command) and (command[end].isalnum() or command[end] == "_"):
            end += 1
        name, after = command[index + 1:end], end
    if not name.isidentifier() or not name.isascii():
        return None, index
    value = os.environ.get(name)
    return (value, after) if value is not None else (None, index)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
