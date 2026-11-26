"""Report at once that a sandbox blocks ps, for the test modules that need ps.

The Claude Code sandbox blocks running /bin/ps: starting it raises
PermissionError, "Operation not permitted". Each test module that starts ps
calls require_ps() from setUpModule. In the sandbox, unittest then reports one
error for each such module, with the cause and the fix, and runs none of its
tests. The check fails instead of skipping, because a skip prints OK and can
pass as a local test run. A missing ps is another case, which the modules'
own guards handle.
"""

from __future__ import annotations

import os
import subprocess


def require_ps() -> None:
    """Raise one error that names the sandbox and the fix when ps cannot start."""
    try:
        subprocess.run(["ps", "-o", "pid=", "-p", str(os.getpid())], capture_output=True)
    except PermissionError as error:
        raise RuntimeError(
            f"a sandbox blocks ps ({error}), and these tests need it. Run the dev-skills "
            "suite again outside the sandbox: python3 dev-skills/scripts/run_suite.py -- "
            "<suite command>, in Claude Code with dangerouslyDisableSandbox on the Bash call."
        ) from None
