"""Run the gtd-setup step 9 shell blocks of both copies in bash and zsh.

Step 9 has two blocks: a check of the global instruction files, and an append
of the agent-capture rule to one file. The blocks come from SKILL.md, so the
checks cover the text that an agent runs. Each block runs in a new shell with
a temporary HOME, CLAUDE_CONFIG_DIR, and CODEX_HOME.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
COPIES = {
    "claude-code": PLUGIN_ROOT / "skills" / "gtd-setup" / "SKILL.md",
    "codex": PLUGIN_ROOT / "codex-skills" / "gtd-setup" / "SKILL.md",
}
SHELLS = {"bash": ["bash", "-c"], "zsh": ["zsh", "-f", "-c"]}  # -f: no user startup files
BASH_FENCE = re.compile(r"^[ \t]*```bash[ \t]*\n(.*?)^[ \t]*```", re.MULTILINE | re.DOTALL)
RULE_LINE = re.compile(r"^rule='(.*)'$", re.MULTILINE)
RULE = (
    "When a task you were given stops and waits on the user, add each waiting item "
    "to the GTD inbox with the `gtd-inbox` skill."
)


def step9_blocks(path: Path) -> tuple[str, str]:
    """Return the check block and the append block of step 9, dedented."""
    text = path.read_text(encoding="utf-8")
    step = text[text.index("## 9. Turn on agent captures"):text.index("## 10. Report")]
    blocks = [re.sub(r"^   ", "", block, flags=re.MULTILINE) for block in BASH_FENCE.findall(step)]
    if len(blocks) != 2:
        raise AssertionError(f"{path}: expected 2 bash blocks in step 9, found {len(blocks)}")
    return blocks[0], blocks[1]


class StepNineBlocks(unittest.TestCase):
    def make_home(self) -> None:
        """Create a new temporary home with Claude Code and Codex folders."""
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root)
        self.home = self.root / "home"
        self.claude = self.home / ".claude"
        self.codex = self.home / ".codex"
        for folder in (self.claude, self.codex, self.home / "real"):
            folder.mkdir(parents=True)

    def run_block(self, shell: str, block: str, **env: str) -> str:
        values = {"PATH": os.environ["PATH"], "HOME": str(self.home), "LANG": "en_US.UTF-8",
                  "CLAUDE_CONFIG_DIR": str(self.claude), "CODEX_HOME": str(self.codex)}
        values.update(env)
        result = subprocess.run([*SHELLS[shell], block], env=values, capture_output=True,
                                text=True, timeout=30, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout

    def states(self, shell: str, check: str, **env: str) -> dict[str, str]:
        """Map each checked path to its state word."""
        found = {}
        for line in self.run_block(shell, check, **env).splitlines():
            state, _, rest = line.partition(": ")
            found[rest.split(" -> ")[0]] = state
        return found

    def test_rule_text_is_the_same_in_every_block(self) -> None:
        for copy, path in COPIES.items():
            for block in step9_blocks(path):
                with self.subTest(copy=copy):
                    self.assertEqual(RULE_LINE.findall(block), [RULE])

    def test_blocks_in_each_shell(self) -> None:
        for copy, path in COPIES.items():
            check, append = step9_blocks(path)
            for shell in SHELLS:
                with self.subTest(copy=copy, shell=shell):
                    if shutil.which(SHELLS[shell][0]) is None:
                        self.skipTest(f"{shell} is not installed")
                    self.make_home()
                    self.check_flow(shell, check, append)

    def check_flow(self, shell: str, check: str, append: str) -> None:
        real = self.home / "real" / "CLAUDE.md"
        real.write_bytes(b"# Mine \xe9\n- rule one")  # Latin-1 byte, no final newline
        link = self.claude / "CLAUDE.md"
        link.symlink_to(real)
        agents = self.codex / "AGENTS.md"

        self.assertEqual(self.states(shell, check), {str(link): "absent", str(agents): "missing"})

        self.run_block(shell, append.replace("<file>", str(agents)))  # creates the file
        self.assertEqual(agents.read_text(encoding="utf-8"), f"# GTD agent captures\n\n- {RULE}\n")

        self.run_block(shell, append.replace("<file>", str(link)))
        self.assertTrue(link.is_symlink())
        self.assertEqual(real.read_bytes(),
                         f"# Mine \xe9\n- rule one\n\n# GTD agent captures\n\n- {RULE}\n".encode("latin-1"))

        cut = RULE.index(" ", 55)  # wrap at a space, as a text editor does
        wrapped = "- " + RULE[:cut] + "\r\n  " + RULE[cut + 1:] + "\r\n"
        agents.write_text(wrapped, encoding="utf-8")
        self.assertEqual(self.states(shell, check), {str(link): "present", str(agents): "present"})

        override = self.codex / "AGENTS.override.md"
        override.touch()  # Codex skips an empty override file
        self.assertEqual(self.states(shell, check), {str(link): "present", str(agents): "present"})
        override.write_text("# Override\n", encoding="utf-8")
        self.assertEqual(self.states(shell, check), {str(link): "present", str(override): "absent"})

        shared = self.root / "shared"  # two host paths that are one file
        shared.mkdir()
        (shared / "AGENTS.md").symlink_to(real)
        output = self.run_block(shell, check, CODEX_HOME=str(shared))
        targets = {line.split(" -> ")[1] for line in output.splitlines()}
        self.assertEqual(targets, {str(real.resolve())})

        broken = self.root / "broken"
        broken.mkdir()
        (broken / "CLAUDE.md").symlink_to(self.root / "gone.md")
        found = self.states(shell, check, CLAUDE_CONFIG_DIR=str(broken),
                            CODEX_HOME=str(self.root / "no-codex"))
        self.assertEqual(found, {str(broken / "CLAUDE.md"): "broken symlink",
                                 str(self.root / "no-codex" / "AGENTS.md"): "no host"})


if __name__ == "__main__":
    unittest.main()
