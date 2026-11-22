#!/usr/bin/env python3
"""Hold a t3-project-lead session to lead actions (issue #520).

Claude Code, Codex, and Antigravity run this hook before a tool call
(PreToolUse), and Claude Code and Codex also run it on each user message
(UserPromptSubmit). It reads the host's JSON payload on stdin. Run it as
`python3 t3_project_lead_hook.py --host claude|codex|antigravity`.

- Record: when a shell call runs `python3 <path>/t3_project_lead.py start`,
  and the script is this hook's sibling or a copy outside every Git work
  tree, the hook writes an empty file named by the session ID to the state
  folder. A copy inside a Git work tree, such as a developer's worktree,
  records nothing. Each new record deletes records older than 30 days.
- Other sessions: without a record, the hook exits 0 with no output, even on
  an error.
- Gate: in a recorded session, a call that is not a lead action exits 2 with
  the reason on stderr. A call that the hook cannot check also exits 2.
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
LEAD_FOLDER = ".scratch/<YYYYMMDD>-lead-<slug>/ of the main checkout"
ALLOWED = {
    "shell": ('Allowed commands: python3 "{script}" <step>; one cat, head, tail, wc, ls, grep, or '
              "sed -n of lead files; rm -r of the lead folder; no pipe, redirect, list, or substitution."),
    "read": (f"Allowed reads: the lead folder {LEAD_FOLDER}, its .gitignore, Git's info/exclude, "
             "and T3 attachments."),
    "edit": f"Allowed edits: files in the lead folder {LEAD_FOLDER}, and Git's info/exclude.",
    "agent": "Start a worker with delegate_task, as t3_project_lead.py dispatch says.",
    "error": "The hook could not check this call ({error}). Allowed: the lead actions that "
             "t3_project_lead.py start lists.",
}

# Tool names of each kind, for all three hosts.
SHELL_TOOLS = {"Bash": "command", "exec_command": "cmd", "shell": "command", "run_command": "CommandLine"}
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
    if words is not None and len(words) == 3 and words[2] == "start" and step_script(words, cwd):
        write_record(folder, session)


def gate(payload, host, folder, session):
    """Return when the call is a lead action; raise Blocked otherwise."""
    name, arguments = tool_call(payload, host)
    if name in AGENT_TOOLS or name.endswith("spawn_agent"):
        raise Blocked("agent")
    if name in SHELL_TOOLS:
        kind = "shell"
    elif name == "apply_patch" or name in EDIT_TOOLS:
        kind = "edit"
    elif name in READ_TOOLS:
        kind = "read"
    else:
        return  # MCP tools and all other tools pass.
    if not isinstance(arguments, dict):
        raise Blocked(kind)
    cwd = payload_cwd(payload)
    if kind == "shell":
        check_shell(arguments, SHELL_TOOLS[name], cwd, folder, session)
    elif name == "apply_patch":
        paths = patch_paths(arguments.get("command", arguments.get("input")))
        check_paths(paths, cwd, LeadFiles(cwd).editable, kind)
    elif kind == "edit":
        check_paths(tool_paths(arguments, None), cwd, LeadFiles(cwd).editable, kind)
    else:
        if name == "Glob":
            pattern = arguments.get("pattern")
            if not isinstance(pattern, str) or pattern.startswith(("/", "~")) or ".." in pattern.split("/"):
                raise Blocked(kind)
        default = cwd if name in ("Grep", "Glob") else None
        check_paths(tool_paths(arguments, default), cwd, LeadFiles(cwd).readable, kind)


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


def patch_paths(patch):
    """Return each path that an apply_patch patch adds, updates, deletes, or moves to."""
    if not isinstance(patch, str):
        return []
    headers = ("*** Add File: ", "*** Update File: ", "*** Delete File: ", "*** Move to: ")
    return [line[len(header):].strip() for line in patch.splitlines() for header in headers
            if line.startswith(header)]


def check_paths(paths, cwd, allowed, kind):
    """Raise Blocked unless `paths` is not empty and `allowed` accepts each path."""
    if not paths:
        raise Blocked(kind)
    for path in paths:
        resolved = resolve(path, cwd)
        if resolved is None or not allowed(resolved):
            raise Blocked(kind)


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


class LeadFiles:
    """The lead files of the repository that holds `cwd`."""

    def __init__(self, cwd):
        if cwd is None:
            raise ValueError("the payload has no absolute cwd")
        common = git(cwd, "rev-parse", "--path-format=absolute", "--git-common-dir")
        if not common:
            raise ValueError(f"no Git repository at {cwd}")
        common = os.path.realpath(common)
        main = os.path.dirname(common) if os.path.basename(common) == ".git" else None
        self.scratch = os.path.join(main, ".scratch") if main else None
        self.gitignore = os.path.join(main, ".gitignore") if main else None
        self.exclude = os.path.join(common, "info", "exclude")

    def in_lead_folder(self, path, *, folder_itself):
        """Return whether `path` is in a lead folder, or is one when `folder_itself`."""
        if self.scratch is None or not path.startswith(self.scratch + os.sep):
            return False
        parts = path[len(self.scratch) + 1:].split(os.sep)
        if not lead_folder_name(parts[0]):
            return False
        return len(parts) > 1 or folder_itself

    def readable(self, path):
        return (self.in_lead_folder(path, folder_itself=True) or path in (self.gitignore, self.exclude)
                or in_attachments(path))

    def editable(self, path):
        return self.in_lead_folder(path, folder_itself=False) or path == self.exclude

    def removable(self, path):
        return self.in_lead_folder(path, folder_itself=True)


def in_attachments(path):
    """Return whether `path` is in T3 Code's attachments folder, where the user's files arrive."""
    folder = os.path.realpath(os.path.join(os.path.expanduser("~"), ".t3", "userdata", "attachments"))
    return path == folder or path.startswith(folder + os.sep)


def lead_folder_name(name):
    """Return whether `name` has the form <8 digits>-lead-<slug>."""
    import re

    return re.fullmatch(r"\d{8}-lead-[A-Za-z0-9._-]+", name) is not None


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
    """Return when the shell command is a lead action; raise Blocked otherwise."""
    words, cwd = shell_words(arguments, key, cwd)
    if not words:
        raise Blocked("shell")
    program, args = words[0], words[1:]
    if program in ("python3", "python"):
        if len(words) != 3 or not is_step(words[2]) or not step_script(words, cwd):
            raise Blocked("shell")
        if words[2] == "start":
            try:
                write_record(folder, session)
            except OSError:
                pass  # The record exists; a failed refresh does not stop the step.
        return
    if program == "rm":
        paths = rm_paths(args)
        if paths is None:
            raise Blocked("shell")
        check_paths(paths, cwd, LeadFiles(cwd).removable, "shell")
        return
    paths = read_paths(program, args)
    if paths is None:
        raise Blocked("shell")
    check_paths(paths, cwd, LeadFiles(cwd).readable, "shell")


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


def rm_paths(args):
    """Return the paths of `rm` with -r, -f, -rf, or -fr only, or None."""
    paths = [word for word in args if not word.startswith("-")]
    options = [word for word in args if word.startswith("-")]
    if not paths or any(option not in ("-r", "-f", "-rf", "-fr") for option in options):
        return None
    return paths


def read_paths(program, args):
    """Return the file arguments of one simple read command, or None."""
    if program == "sed":
        return sed_paths(args)
    if program == "grep":
        return grep_paths(args)
    flags = {"cat": "AbeEnstTuv", "wc": "clmwL", "ls": "1@aAcdFghilLnoprRsStu"}.get(program)
    if flags is None and program not in ("head", "tail"):
        return None
    paths = []
    index = 0
    while index < len(args):
        word = args[index]
        index += 1
        if paths or word == "-" or not word.startswith("-"):
            if word.startswith("-"):
                return None
            paths.append(word)
        elif word == "--":
            paths.extend(args[index:])
            break
        elif flags is not None:
            if not set(word[1:]) <= set(flags):
                return None
        elif word[1:].isdigit() or word in ("-q", "-v"):
            continue
        elif word[1:2] in ("n", "c"):
            value = word[2:]
            if not value:
                if index >= len(args):
                    return None
                value = args[index]
                index += 1
            if not value.lstrip("+-").isdigit():
                return None
        else:
            return None
    return paths or None


def grep_paths(args):
    """Return the file arguments of a grep command, or None."""
    flags = set("EFGHhiIlLnorRsvwxcqzaU")
    pattern_given = False
    paths = []
    index = 0
    while index < len(args):
        word = args[index]
        index += 1
        if word == "--":
            rest = args[index:]
            if not pattern_given and rest:
                pattern_given = True
                rest = rest[1:]
            paths.extend(rest)
            break
        if not word.startswith("-") or word == "-":
            if word == "-":
                return None
            if pattern_given:
                paths.append(word)
            else:
                pattern_given = True
            continue
        if paths or word.startswith("--"):
            return None
        letters = word[1:]
        while letters:
            letter, letters = letters[0], letters[1:]
            if letter in flags:
                continue
            if letter not in "eABCm":
                return None
            value = letters
            letters = ""
            if not value:
                if index >= len(args):
                    return None
                value = args[index]
                index += 1
            if letter == "e":
                pattern_given = True
            elif not value.isdigit():
                return None
    return paths if pattern_given and paths else None


def sed_paths(args):
    """Return the file arguments of `sed -n <print-only script> <file>...`, or None."""
    import re

    if len(args) >= 2 and args[0] == "-n" and args[1] == "-e":
        args = ["-n"] + args[2:]
    if len(args) < 3 or args[0] != "-n":
        return None
    address = r"(?:\d+|\$|/(?:[^/\\\n]|\\.)*/)"
    command = rf"\s*(?:{address}(?:\s*,\s*{address})?\s*)?p\s*"
    if re.fullmatch(rf"{command}(?:[;\n]{command})*;?\s*", args[1]) is None:
        return None
    paths = args[2:]
    if paths[0] == "--":
        paths = paths[1:]
    if not paths or any(path.startswith("-") for path in paths):
        return None
    return paths


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
