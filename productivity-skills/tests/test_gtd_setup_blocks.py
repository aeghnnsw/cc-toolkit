"""Run the gtd-setup step 7 and step 9 shell blocks of every copy in bash and zsh.

Step 7 has one block, which writes the GTD binding. Step 9 has two blocks: a check of the global instruction files, and an append
of the agent-capture rule to one file. The blocks come from SKILL.md, so the
checks cover the text that an agent runs. Each block runs in a new shell with
a temporary HOME, CLAUDE_CONFIG_DIR, and CODEX_HOME. Antigravity's file is
$HOME/.gemini/GEMINI.md.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
COPIES = {
    "claude-code": PLUGIN_ROOT / "skills" / "gtd-setup" / "SKILL.md",
    "codex": PLUGIN_ROOT / "codex-skills" / "gtd-setup" / "SKILL.md",
    "antigravity": PLUGIN_ROOT / "antigravity-skills" / "gtd-setup" / "SKILL.md",
}
SHELLS = {"bash": ["bash", "-c"], "zsh": ["zsh", "-f", "-c"]}  # -f: no user startup files
BASH_FENCE = re.compile(r"^[ \t]*```bash[ \t]*\n(.*?)^[ \t]*```", re.MULTILINE | re.DOTALL)
RULE_LINE = re.compile(r"^rule='(.*)'$", re.MULTILINE)
RULE = (
    "When a task you were given stops and waits on the user, add each waiting item "
    "to the GTD inbox with the `gtd-inbox` skill."
)


PROJECT = "abcdefghijklmnopqrst"  # synthetic values, as in references/gtd-cloud.md
OWNER = "11111111-1111-4111-8111-111111111111"


def step7_block(path: Path) -> str:
    """Return the step 7 block that writes the GTD binding, dedented, with synthetic values."""
    text = path.read_text(encoding="utf-8")
    step = text[text.index("## 7. Write the GTD binding"):text.index("## 8. Verify")]
    blocks = [re.sub(r"^   ", "", block, flags=re.MULTILINE) for block in BASH_FENCE.findall(step)]
    if len(blocks) != 1:
        raise AssertionError(f"{path}: expected 1 bash block in step 7, found {len(blocks)}")
    if "<project-ref>" not in blocks[0] or "<owner-uuid>" not in blocks[0]:
        raise AssertionError(f"{path}: the step 7 block has no <project-ref> or <owner-uuid> placeholder")
    block = blocks[0].replace("<project-ref>", PROJECT).replace("<owner-uuid>", OWNER)
    if re.search(r"<[a-z][a-z-]*>", block):
        raise AssertionError(f"{path}: the step 7 block keeps a placeholder: {block}")
    return block


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
        """Create a new temporary home with Claude Code, Codex, and Antigravity folders."""
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root)
        self.home = self.root / "home"
        self.claude = self.home / ".claude"
        self.codex = self.home / ".codex"
        self.antigravity = self.home / ".gemini"
        for folder in (self.claude, self.codex, self.antigravity, self.home / "real"):
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
        antigravity_md = self.antigravity / "GEMINI.md"

        self.assertEqual(self.states(shell, check),
                         {str(link): "absent", str(agents): "missing", str(antigravity_md): "missing"})

        output = self.run_block(shell, append.replace("<file>", str(antigravity_md)))  # Antigravity's file
        self.assertEqual(output, f"added: {antigravity_md}\n")
        self.assertEqual(antigravity_md.read_text(encoding="utf-8"), f"# GTD agent captures\n\n- {RULE}\n")

        output = self.run_block(shell, append.replace("<file>", str(agents)))  # creates the file
        self.assertEqual(output, f"added: {agents}\n")
        self.assertEqual(agents.read_text(encoding="utf-8"), f"# GTD agent captures\n\n- {RULE}\n")

        output = self.run_block(shell, append.replace("<file>", str(agents)))  # another run added it
        self.assertEqual(output, f"present: {agents}\n")
        self.assertEqual(agents.read_text(encoding="utf-8"), f"# GTD agent captures\n\n- {RULE}\n")

        ended = self.root / "ended.md"  # a file that ends with a newline
        ended.write_text("# Mine\n", encoding="utf-8")
        output = self.run_block(shell, append.replace("<file>", str(ended)))
        self.assertEqual(output, f"added: {ended}\n")
        self.assertEqual(ended.read_text(encoding="utf-8"), f"# Mine\n\n# GTD agent captures\n\n- {RULE}\n")

        output = self.run_block(shell, append.replace("<file>", str(link)))
        self.assertEqual(output, f"added: {link}\n")
        self.assertTrue(link.is_symlink())
        self.assertEqual(real.read_bytes(),
                         f"# Mine \xe9\n- rule one\n\n# GTD agent captures\n\n- {RULE}\n".encode("latin-1"))

        cut = RULE.index(" ", 55)  # wrap at a space, as a text editor does
        wrapped = "- " + RULE[:cut] + "\r\n  " + RULE[cut + 1:] + "\r\n"
        agents.write_text(wrapped, encoding="utf-8")
        self.assertEqual(self.states(shell, check),
                         {str(link): "present", str(agents): "present", str(antigravity_md): "present"})
        output = self.run_block(shell, append.replace("<file>", str(agents)))
        self.assertEqual(output, f"present: {agents}\n")
        self.assertEqual(agents.read_bytes(), wrapped.encode("utf-8"))

        override = self.codex / "AGENTS.override.md"
        override.touch()  # Codex skips an empty override file
        self.assertEqual(self.states(shell, check),
                         {str(link): "present", str(agents): "present", str(antigravity_md): "present"})
        override.write_text("# Override\n", encoding="utf-8")
        self.assertEqual(self.states(shell, check),
                         {str(link): "present", str(override): "absent", str(antigravity_md): "present"})

        no_antigravity = self.root / "no-antigravity"  # a machine without Antigravity
        no_antigravity.mkdir()
        self.assertEqual(self.states(shell, check, HOME=str(no_antigravity)),
                         {str(link): "present", str(override): "absent",
                          str(no_antigravity / ".gemini" / "GEMINI.md"): "no host"})

        shared = self.root / "shared"  # three host paths that are one file
        (shared / ".gemini").mkdir(parents=True)
        (shared / "AGENTS.md").symlink_to(real)
        (shared / ".gemini" / "GEMINI.md").symlink_to(real)
        output = self.run_block(shell, check, CODEX_HOME=str(shared), HOME=str(shared))
        targets = [line.split(" -> ")[1] for line in output.splitlines()]
        self.assertEqual(targets, [str(real.resolve())] * 3)

        broken = self.root / "broken"
        broken.mkdir()
        (broken / "CLAUDE.md").symlink_to(self.root / "gone.md")
        found = self.states(shell, check, CLAUDE_CONFIG_DIR=str(broken),
                            CODEX_HOME=str(self.root / "no-codex"))
        self.assertEqual(found, {str(broken / "CLAUDE.md"): "broken symlink",
                                 str(self.root / "no-codex" / "AGENTS.md"): "no host",
                                 str(antigravity_md): "present"})


class StepSevenBlock(unittest.TestCase):
    """The step 7 block writes a private GTD binding that the renderer accepts."""

    def run_block(self, shell: str, home: Path, block: str) -> None:
        # umask 000: the block itself, not the caller's umask, must make the file private.
        result = subprocess.run([*SHELLS[shell], "umask 000\n" + block],
                                env={"PATH": os.environ["PATH"], "HOME": str(home), "LANG": "en_US.UTF-8"},
                                capture_output=True, text=True, timeout=30, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)

    def check_binding(self, binding: Path) -> None:
        self.assertEqual(binding.stat().st_mode & 0o777, 0o600)
        self.assertEqual(json.loads(binding.read_text(encoding="utf-8")),
                         {"project_id": PROJECT, "owner_id": OWNER})
        renderer = subprocess.run(
            [sys.executable, str(PLUGIN_ROOT / "scripts" / "gtd_sql.py"), "--config", str(binding),
             "read", "--limit", "1"], capture_output=True, text=True, timeout=30, check=False)
        self.assertEqual(renderer.returncode, 0, renderer.stderr)
        self.assertEqual(json.loads(renderer.stdout)["project_id"], PROJECT)

    def test_block_writes_a_private_binding_in_each_shell(self) -> None:
        for copy, path in COPIES.items():
            block = step7_block(path)
            for shell in SHELLS:
                with self.subTest(copy=copy, shell=shell):
                    if shutil.which(SHELLS[shell][0]) is None:
                        self.skipTest(f"{shell} is not installed")
                    home = Path(tempfile.mkdtemp())
                    self.addCleanup(shutil.rmtree, home)
                    binding = home / ".config" / "cc-toolkit" / "gtd.json"
                    self.run_block(shell, home, block)  # no .config folder yet
                    self.check_binding(binding)
                    binding.write_text('{"project_id":"old","owner_id":"old"}\n', encoding="utf-8")
                    binding.chmod(0o644)
                    self.run_block(shell, home, block)  # replaces an existing, readable file
                    self.check_binding(binding)


if __name__ == "__main__":
    unittest.main()
