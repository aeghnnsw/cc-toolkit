#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.8"
# ///

import json
import sys
import re
from pathlib import Path

def is_dangerous_rm_command(command):
    """
    Selective detection of dangerous rm commands.
    Only blocks rm commands with dangerous paths or patterns while allowing explicit removals.
    """
    # Normalize command by removing extra spaces and converting to lowercase
    normalized = ' '.join(command.lower().split())

    # First check if this is an rm command
    if not re.search(r'\brm\s+', normalized):
        return False

    # IMMEDIATELY block any rm command with wildcards (check BEFORE safe patterns)
    # This avoids regex backtracking issues on long paths
    if '*' in command:
        return True

    # Dangerous path patterns that should always be blocked
    dangerous_paths = [
        r'\brm\s+(-\w+\s+)*/$',  # Root directory (rm /, rm -rf /)
        r'\brm\s+(-\w+\s+)*/\s',  # Root directory with space after
        r'~/?$',        # Home directory (exact match)
        r'\s~/\s',      # Home directory path
        r'\$HOME',      # Home environment variable
        r'\.\.',        # Parent directory references
        r'\s\.\s*$',    # Current directory (space dot space/end)
        r'\brm\s+(-\w+\s+)*\.\s*$',  # rm . or rm -rf .
        r'/usr\b',      # System directories
        r'/var\b',
        r'/etc\b',
        r'/bin\b',
        r'/sbin\b',
        r'/lib\b',
        r'/opt\b',
        r'/sys\b',      # Linux system directories
        r'/proc\b',
        r'/dev\b',
        r'/boot\b',
    ]

    # Block rm commands that target dangerous paths
    for path in dangerous_paths:
        if re.search(path, normalized):
            return True

    return False


def main():
    try:
        # Read JSON input from stdin
        input_data = json.load(sys.stdin)

        tool_name = input_data.get('tool_name', '')
        tool_input = input_data.get('tool_input', {})

        # Check for dangerous rm -rf commands
        if tool_name == 'Bash':
            command = tool_input.get('command', '')

            # Block dangerous rm commands while allowing explicit removals
            if is_dangerous_rm_command(command):
                print("BLOCKED: Potentially dangerous rm command detected", file=sys.stderr)
                print("Safe explicit removals like 'rm -rf specific_folder' are allowed", file=sys.stderr)
                sys.exit(2)  # Exit code 2 blocks tool call and shows error to Claude

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
