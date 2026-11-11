"""Run the helper script of the token connector reference.

The reference holds the helper script that the user saves and that Claude Code
(`headersHelper`) and Codex (`http_headers_helper`) run. The test extracts the
one `#!/bin/sh` block, runs it with stub `uname` and `security` commands and a
temporary HOME, and checks the header JSON and the failure cases.
"""

from __future__ import annotations

import os
import re
import shutil
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
REFERENCE = PLUGIN_ROOT / "references" / "gtd-token-connector.md"
FENCE = re.compile(r"^[ \t]*```sh[ \t]*\n(.*?)^[ \t]*```", re.MULTILINE | re.DOTALL)
SERVICE = "cc-toolkit-supabase-pat"


def helper_block() -> str:
    """Return the one `sh` block of the reference that starts with a shebang, dedented."""
    blocks = [re.sub(r"^   ", "", block, flags=re.MULTILINE)
              for block in FENCE.findall(REFERENCE.read_text(encoding="utf-8"))]
    helpers = [block for block in blocks if block.startswith("#!/bin/sh\n")]
    if len(helpers) != 1:
        raise AssertionError(f"{REFERENCE}: expected 1 helper block, found {len(helpers)}")
    return helpers[0]


class TokenConnectorHelper(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root)
        self.home = self.root / "home"
        self.home.mkdir()
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.helper = self.root / "supabase-mcp-headers.sh"
        self.helper.write_text(helper_block(), encoding="utf-8")
        self.helper.chmod(stat.S_IRWXU)

    def stub(self, name: str, body: str) -> None:
        path = self.bin / name
        path.write_text(f"#!/bin/sh\n{body}\n", encoding="utf-8")
        path.chmod(stat.S_IRWXU)

    def run_helper(self, system: str) -> subprocess.CompletedProcess[str]:
        self.stub("uname", f"echo {system}")
        env = {"HOME": str(self.home), "PATH": f"{self.bin}{os.pathsep}{os.environ['PATH']}"}
        return subprocess.run([str(self.helper)], env=env, capture_output=True, text=True,
                              timeout=30, check=False)

    def test_linux_reads_the_owner_only_file(self) -> None:
        token = self.home / ".config" / "cc-toolkit" / "supabase-pat"
        token.parent.mkdir(parents=True)
        token.write_text("sbp_linux123\n", encoding="utf-8")
        result = self.run_helper("Linux")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, '{"Authorization":"Bearer sbp_linux123"}\n')

    def test_macos_reads_the_keychain_item(self) -> None:
        self.stub("security", f'[ "$1 $2 $3 $4" = "find-generic-password -s {SERVICE} -w" ] '
                              '&& echo sbp_mac456 || exit 44')
        result = self.run_helper("Darwin")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, '{"Authorization":"Bearer sbp_mac456"}\n')

    def test_missing_token_prints_no_header(self) -> None:
        self.stub("security", "exit 44")  # "The specified item could not be found"
        for system in ("Linux", "Darwin"):
            with self.subTest(system=system):
                result = self.run_helper(system)
                self.assertEqual(result.returncode, 1)
                self.assertEqual(result.stdout, "")
                self.assertIn("token", result.stderr)


if __name__ == "__main__":
    unittest.main()
