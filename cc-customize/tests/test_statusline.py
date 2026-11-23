"""Run statusline-setup's statusline script and its setup blocks in temporary folders.

Each run sets HOME, CLAUDE_CONFIG_DIR, and TMPDIR to temporary folders, so no run reads or writes the real
Claude Code configuration or statusline state. Line 2 measures context against the auto-compact trigger: the
window minus a 20,000-token summary reserve and a 13,000-token margin (#536).
"""
import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[1]
SKILL = PLUGIN / 'skills' / 'statusline-setup' / 'SKILL.md'
SCRIPT = PLUGIN / 'skills' / 'statusline-setup' / 'scripts' / 'statusline-command.sh'
SAMPLE = {'session_id': 'test', 'context_window': {'context_window_size': 1000000, 'total_input_tokens': 113800}}
SHELLS = {'bash': ['bash', '-c'], 'zsh': ['zsh', '-f', '-c']}  # -f: no user startup files


def first_block(title):
    """Return the first bash block under the level-3 heading of SKILL.md that starts with title."""
    text = SKILL.read_text(encoding='utf-8')
    heading = re.search(rf'^### {re.escape(title)}\b.*$', text, re.MULTILINE)
    end = heading and re.compile(r'^##', re.MULTILINE).search(text, heading.end())
    match = end and re.search(r'^```bash\n(.*?)^```', text[heading.end():end.start()], re.MULTILINE | re.DOTALL)
    if not match:
        raise AssertionError(f'{SKILL}: no bash block under ### {title}')
    return match.group(1)


@unittest.skipUnless(shutil.which('jq'), 'statusline-command.sh needs jq; install it, for example with brew install jq')
class StatuslineTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.config = self.root / 'profile'
        self.config.mkdir()
        self.env = {'PATH': os.environ['PATH'], 'HOME': str(self.root / 'home'),
                    'CLAUDE_CONFIG_DIR': str(self.config), 'TMPDIR': str(self.root)}

    def write_settings(self, settings):
        (self.config / 'settings.json').write_text(json.dumps(settings) + '\n', encoding='utf-8')

    def run_script(self, **env):
        result = subprocess.run(['bash', str(SCRIPT)], input=json.dumps(SAMPLE), env={**self.env, **env},
                                capture_output=True, text=True, timeout=30, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        lines = result.stdout.splitlines()
        self.assertEqual(len(lines), 3, result.stdout)
        return lines

    def run_block(self, shell, title):
        """Run the first bash block of a SKILL.md step in a new shell, as the agent runs it, and return stdout."""
        env = {**self.env, 'CLAUDE_PLUGIN_ROOT': str(PLUGIN)}
        result = subprocess.run([*SHELLS[shell], first_block(title)], cwd=self.root, env=env, capture_output=True,
                                text=True, timeout=30, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout

    def test_context_limit_is_the_auto_compact_trigger(self):
        self.write_settings({'autoCompactWindow': 400000})
        self.assertIn('(113.8K/367.0K)', self.run_script()[1])
        self.assertIn('(113.8K/152.0K)', self.run_script(CLAUDE_AUTOCOMPACT_PCT_OVERRIDE='40')[1])

    def test_setup_blocks_install_and_check_the_script(self):
        command = f'bash "{self.config}/statusline-command.sh"'
        for shell in SHELLS:
            with self.subTest(shell=shell):
                if shutil.which(shell) is None:
                    self.skipTest(f'{shell} is not installed')
                self.write_settings({})
                self.run_block(shell, 'Step 1')
                self.assertIn('FAIL: cannot read statusLine.command from', self.run_block(shell, 'Step 3'))
                self.write_settings({'statusLine': {'type': 'command', 'command': command},
                                     'autoCompactWindow': 400000})
                out = self.run_block(shell, 'Step 3')
                self.assertNotIn('FAIL', out)
                lines = out.splitlines()
                self.assertEqual(len(lines), 4, out)
                self.assertEqual(lines[0], command)
                self.assertIn('(113.8K/367.0K)', lines[2])


if __name__ == '__main__':
    unittest.main()
