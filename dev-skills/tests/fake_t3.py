"""A fake t3 CLI of T3 Code for the repo-cleanup tests.

The tests put a `t3` wrapper that runs this file first on PATH, or name the
wrapper with T3CODE_CLI_PATH. It answers `t3 thread list --json --project P`
and `t3 thread show --json --messages 1 T` from the JSON file that
FAKE_T3_DATA names, and appends each argument list to the file that
FAKE_T3_LOG names. The errors copy those of the t3 CLI that T3 Code ships.
Any other command fails.

The data file has these optional keys:

- "fail": [exit status, message]; every command prints the message and exits.
- "sleep": seconds to wait before the answer.
- "projects": the rows of `thread list` by project path. A string value
  prints as it is, in place of JSON. A path that is not a key gets the error
  for a folder outside every T3 Code project.
- "threads": the output of `thread show` by thread id.
"""

from __future__ import annotations

import json
import os
import sys
import time


def option(args: list[str], name: str) -> str | None:
    return args[args.index(name) + 1] if name in args[:-1] else None


def main() -> int:
    args = sys.argv[1:]
    with open(os.environ["FAKE_T3_LOG"], "a", encoding="utf-8") as log:
        log.write(json.dumps(args) + "\n")
    with open(os.environ["FAKE_T3_DATA"], encoding="utf-8") as handle:
        data = json.load(handle)
    time.sleep(data.get("sleep", 0))
    if "fail" in data:
        print(data["fail"][1], file=sys.stderr)
        return data["fail"][0]
    if args[:2] == ["thread", "list"] and "--json" in args:
        project = option(args, "--project")
        if project not in data.get("projects", {}):
            print(f"No T3 Code project matches '{project}'. Pass a project id or a path inside "
                  "a project.", file=sys.stderr)
            return 1
        rows = data["projects"][project]
        print(rows if isinstance(rows, str) else json.dumps(rows))
        return 0
    if args[:2] == ["thread", "show"] and "--json" in args:
        thread = args[-1]
        if thread not in data.get("threads", {}):
            print(f"Thread {thread} is no longer available.", file=sys.stderr)
            return 1
        print(json.dumps(data["threads"][thread]))
        return 0
    print(f"fake t3: unsupported command: {' '.join(args)}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
