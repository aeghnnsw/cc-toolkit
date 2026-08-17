"""Normalize shell commands from supported hook event payloads."""


SHELL_COMMAND_KEYS = {
    "Bash": "command",
    "exec_command": "cmd",
    "run_terminal_command": "command",
}


def get_shell_command(input_data):
    """Return the shell command from a Claude, Codex, or Grok hook event."""
    if not isinstance(input_data, dict):
        return ""

    if "tool_name" in input_data:
        tool_name = input_data.get("tool_name", "")
    else:
        tool_name = input_data.get("toolName", "")

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
