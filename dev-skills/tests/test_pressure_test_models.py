"""Run the critic-model shell blocks of both pressure-test copies in bash and zsh.

Each check runs the Setup block of a copy, then other blocks of the same copy,
each in a new shell as the agent runs them, and reads the critic model file in
the work directory. The blocks come from SKILL.md, so the checks cover the text
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
    def run_block(self, shell: str, block: str, workdir: str = "") -> str:
        """Run one block in a new shell and return its stdout; fail on a non-zero exit."""
        result = subprocess.run([*SHELLS[shell], block.replace("<workdir>", workdir)], cwd=self.temp,
                                env=self.env, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout

    def setup_copy(self, copy: str, shell: str) -> tuple[str, Path]:
        """Run the Setup block of a copy; return the SKILL.md text and the work directory."""
        path = COPIES[copy][0]
        text = path.read_text(encoding="utf-8")
        block = first_block(text, "Setup").replace("<skill-dir>", str(path.parent))
        self.assertTrue(block, f"{copy}: no bash block under Setup")
        match = WORKDIR_LINE.search(self.run_block(shell, block))
        self.assertIsNotNone(match, f"{copy}: Setup printed no workdir line")
        return text, Path(match.group(1))

    def model(self, workdir: Path) -> str:
        return (workdir / "model").read_text(encoding="utf-8").strip()

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.temp = directory.name
        # mktemp -d in Setup creates the work directory under TMPDIR, so the cleanup removes it.
        self.env = dict(os.environ, TMPDIR=self.temp, CLAUDE_PLUGIN_ROOT=str(PLUGIN_ROOT))

    def require(self, shell: str) -> None:
        if shutil.which(shell) is None:
            self.skipTest(f"{shell} is not installed")

    def test_setup_starts_on_the_primary_model(self):
        for copy, shell, models in CASES:
            with self.subTest(copy=copy, shell=shell):
                self.require(shell)
                _, workdir = self.setup_copy(copy, shell)
                self.assertEqual(self.model(workdir), models["primary"])

    def test_critic_model_block_chooses_the_fallback_model(self):
        for copy, shell, models in CASES:
            with self.subTest(copy=copy, shell=shell):
                self.require(shell)
                text, workdir = self.setup_copy(copy, shell)
                block = first_block(text, "Critic model")
                self.assertTrue(block, f"{copy}: no bash block under Critic model")
                self.run_block(shell, block, str(workdir))
                self.assertEqual(self.model(workdir), models["fallback"])

    def test_flag_switch_moves_to_the_other_allowed_model(self):
        for copy, shell, models in CASES:
            for start, other in (("primary", "fallback"), ("fallback", "primary")):
                with self.subTest(copy=copy, shell=shell, start=start):
                    self.require(shell)
                    text, workdir = self.setup_copy(copy, shell)
                    if start == "fallback":
                        self.run_block(shell, first_block(text, "Critic model"), str(workdir))
                    block = first_block(text, "Flags")
                    self.assertTrue(block, f"{copy}: no bash block under Flags")
                    self.run_block(shell, block, str(workdir))
                    self.assertEqual(self.model(workdir), models[other])


if __name__ == "__main__":
    unittest.main()
