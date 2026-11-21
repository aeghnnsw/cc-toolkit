"""Normalize shell commands from supported hook event payloads."""


SHELL_COMMAND_KEYS = {
    "Bash": "command",
    "exec_command": "cmd",
    "run_terminal_command": "command",
}
ANTIGRAVITY = "antigravity"


def block_status(host):
    """Return the exit status of a script that blocks a tool call on `host`.

    In Antigravity mode, a script blocks with status 3. The root `hooks.json`
    changes 3 to 2, the Antigravity block status, without its "hook failed"
    line. `uv` also exits 2 when it cannot start a script, so the wrappers
    must tell that failure from a block.
    """
    return 3 if host == ANTIGRAVITY else 2


def host_argument(argv):
    """Return the host that `--host <host>` in `argv` names, or None.

    The root `hooks.json` passes `--host antigravity` to each script. The
    Claude Code and Codex hook configurations pass no host to the scripts
    that behave the same on both hosts.
    """
    for index, argument in enumerate(argv[:-1]):
        if argument == "--host":
            return argv[index + 1]
    return None


def _antigravity_shell_command(tool_call):
    """Return `toolCall.args.CommandLine` of an Antigravity `run_command`."""
    if not isinstance(tool_call, dict) or tool_call.get("name") != "run_command":
        return ""
    args = tool_call.get("args", {})
    if not isinstance(args, dict):
        return ""
    command = args.get("CommandLine", "")
    return command if isinstance(command, str) else ""


def get_shell_command(input_data):
    """Return the shell command from a Claude, Codex, Grok, or Antigravity
    hook event."""
    if not isinstance(input_data, dict):
        return ""

    if "tool_name" in input_data:
        tool_name = input_data.get("tool_name", "")
    elif "toolName" in input_data:
        tool_name = input_data.get("toolName", "")
    else:
        # Antigravity sends no tool name; its tool call is in `toolCall`.
        return _antigravity_shell_command(input_data.get("toolCall"))

    if "tool_input" in input_data:
        tool_input = input_data.get("tool_input", {})
    else:
        tool_input = input_data.get("toolInput", {})

    if not isinstance(tool_input, dict):
        return ""

    command_key = SHELL_COMMAND_KEYS.get(tool_name)
    if not command_key:
        return ""

    command = tool_input.get(command_key, "")
    return command if isinstance(command, str) else ""
