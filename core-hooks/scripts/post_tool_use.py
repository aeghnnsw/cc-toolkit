#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.8"
# ///

import json
import sys

from hook_logs import append_log, host_log_dir
from hook_payload import host_argument

def main():
    try:
        # Read JSON input from stdin
        input_data = json.load(sys.stdin)

        directory = host_log_dir(host_argument(sys.argv[1:]), input_data)
        if directory is not None:
            append_log('post_tool_use.jsonl', input_data, directory)

        sys.exit(0)

    except json.JSONDecodeError:
        # Handle JSON decode errors gracefully
        sys.exit(0)
    except Exception:
        # Exit cleanly on any other error
        sys.exit(0)

if __name__ == '__main__':
    main()
