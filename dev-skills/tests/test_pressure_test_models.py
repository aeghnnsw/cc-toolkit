"""Run the critic-model shell blocks of both pressure-test copies in bash and zsh.

Each check runs the Setup block of a copy, then its Critic model block, its
Flags block, or both, each in a new shell as the agent runs them, and reads the critic model
file in the work directory. The blocks come from SKILL.md, so the checks cover the text
that an agent runs. The expected models come from allowed-models.json.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
ALLOWED_MODELS = json.loads((PLUGIN_ROOT.parent / "allowed-models.json").read_text(encoding="utf-8"))
# Each copy calls a critic from the model family of the other host.
COPIES = {
    "claude-code": (PLUGIN_ROOT / "skills" / "pressure-test" / "SKILL.md", "gpt"),
    "codex": (PLUGIN_ROOT / "codex-skills" / "pressure-test" / "SKILL.md", "claude"),
}
SHELLS = {"bash": ["bash", "-c"], "zsh": ["zsh", "-f", "-c"]}  # -f: no user startup files
CASES = [(copy, shell, ALLOWED_MODELS[family]) for copy, (_, family) in COPIES.items() for shell in SHELLS]
BASH_FENCE = re.compile(r"^[ \t]*```bash[ \t]*\n(.*?)^[ \t]*```", re.MULTILINE | re.DOTALL)
WORKDIR_LINE = re.compile(r"^workdir: (.+)$", re.MULTILINE)


def section(text: str, title: str) -> str:
    """Return the text under the level-2 heading that starts with title, ignoring case, or ""."""
    match = re.search(rf"^## {re.escape(title)}\b.*$", text, re.MULTILINE | re.IGNORECASE)
    if not match:
        return ""
    end = re.compile(r"^## ", re.MULTILINE).search(text, match.end())
    return text[match.end():end.start() if end else len(text)]


def first_block(text: str, title: str) -> str:
    """Return the first bash block under a level-2 heading, or "" when there is none."""
    match = BASH_FENCE.search(section(text, title))
    return match.group(1) if match else ""


class CriticModelBlockTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.temp = directory.name
        # mktemp -d in Setup creates the work directory under TMPDIR, so the cleanup removes it.
        self.env = dict(os.environ, TMPDIR=self.temp, CLAUDE_PLUGIN_ROOT=str(PLUGIN_ROOT))

    def require_shell(self, shell: str) -> None:
        """Skip the current subtest when the shell is not installed."""
        if shutil.which(shell) is None:
            self.skipTest(f"{shell} is not installed")

    def run_block(self, shell: str, block: str, workdir: str = "") -> str:
        """Run one block in a new shell and return its stdout; fail on a non-zero exit."""
        result = subprocess.run([*SHELLS[shell], block.replace("<workdir>", workdir)], cwd=self.temp,
                                env=self.env, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout

    def run_named_block(self, copy: str, text: str, shell: str, title: str, workdir: Path) -> None:
        """Run the first bash block under a heading of the copy; fail when the heading has none."""
        block = first_block(text, title)
        self.assertTrue(block, f"{copy}: no bash block under {title}")
        self.run_block(shell, block, str(workdir))

    def start_pressure_test(self, copy: str, shell: str, start: str) -> tuple[str, Path]:
        """Run the Setup block of a copy, and the Critic model block when start is "fallback".

        Return the SKILL.md text and the work directory.
        """
        path = COPIES[copy][0]
        text = path.read_text(encoding="utf-8")
        block = first_block(text, "Setup").replace("<skill-dir>", str(path.parent))
        self.assertTrue(block, f"{copy}: no bash block under Setup")
        match = WORKDIR_LINE.search(self.run_block(shell, block))
        self.assertIsNotNone(match, f"{copy}: Setup printed no workdir line")
        workdir = Path(match.group(1))
        if start == "fallback":
            self.run_named_block(copy, text, shell, "Critic model", workdir)
        return text, workdir

    def critic_model(self, workdir: Path) -> str:
        """Return the model in the critic model file of a work directory."""
        return (workdir / "model").read_text(encoding="utf-8").strip()

    def test_pressure_test_starts_on_the_primary_or_the_chosen_fallback_model(self):
        for copy, shell, models in CASES:
            for start in ("primary", "fallback"):
                with self.subTest(copy=copy, shell=shell, start=start):
                    self.require_shell(shell)
                    _, workdir = self.start_pressure_test(copy, shell, start)
                    self.assertEqual(self.critic_model(workdir), models[start])

    def test_flag_switch_moves_to_the_other_allowed_model(self):
        for copy, shell, models in CASES:
            for start, other in (("primary", "fallback"), ("fallback", "primary")):
                with self.subTest(copy=copy, shell=shell, start=start):
                    self.require_shell(shell)
                    text, workdir = self.start_pressure_test(copy, shell, start)
                    self.run_named_block(copy, text, shell, "Flags", workdir)
                    self.assertEqual(self.critic_model(workdir), models[other])


if __name__ == "__main__":
    unittest.main()
