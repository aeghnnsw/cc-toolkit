"""Run claude-prompt-config's install_prompt.sh in temporary folders.

Each run sets HOME and CLAUDE_CONFIG_DIR to temporary folders, so no run reads or writes the real Claude Code
configuration. The script must show the lines that the new file drops before it writes, and keep the
"# GTD agent captures" section that gtd-setup step 9 adds (#464).
"""
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1] / 'skills' / 'claude-prompt-config'
SCRIPT = SKILL / 'scripts' / 'install_prompt.sh'
ASSET = (SKILL / 'assets' / 'global-claude-md.md').read_text(encoding='utf-8')
RULE = ('- When a task you were given stops and waits on the user, add each waiting item to the GTD inbox with '
        'the `gtd-inbox` skill.\n')
GTD_SECTION = '# GTD agent captures\n\n' + RULE  # the text that gtd-setup step 9 appends after a blank line
OLD = '# My rules\n\n- Keep my custom rule.\n\n' + GTD_SECTION


class InstallPromptTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.config = self.root / 'profile'
        self.target = self.config / 'CLAUDE.md'

    def run_script(self, *args, status=0):
        env = {'PATH': os.environ['PATH'], 'HOME': str(self.root / 'home'), 'CLAUDE_CONFIG_DIR': str(self.config),
               'TMPDIR': str(self.root)}
        result = subprocess.run(['bash', str(SCRIPT), *args], env=env, capture_output=True, text=True,
                                timeout=30, check=False)
        self.assertEqual(result.returncode, status, result.stderr)
        self.assertFalse((self.root / 'home').exists(), 'the script used HOME, not CLAUDE_CONFIG_DIR')
        return result.stdout.splitlines()

    def write_target(self, text):
        self.config.mkdir(exist_ok=True)
        self.target.write_text(text, encoding='utf-8')

    def backups(self):
        return sorted(self.config.glob('CLAUDE.md.bak-*'))

    def test_preview_shows_dropped_lines_and_writes_nothing(self):
        self.write_target(OLD)
        out = self.run_script()
        self.assertEqual(out, [f'target: {self.target}', 'keep: # GTD agent captures', 'drop: # My rules',
                               'drop: - Keep my custom rule.'])
        self.assertEqual(self.target.read_text(encoding='utf-8'), OLD)
        self.assertEqual(self.backups(), [])

    def test_apply_backs_up_and_keeps_the_agent_capture_section(self):
        self.write_target(OLD)
        out = self.run_script('--apply')
        self.assertIn('drop: - Keep my custom rule.', out)
        self.assertEqual(self.target.read_text(encoding='utf-8'), ASSET + '\n' + GTD_SECTION)
        [backup] = self.backups()
        self.assertEqual(backup.read_text(encoding='utf-8'), OLD)
        self.assertEqual(out[-2:], [f'backup: {backup}', f'wrote: {self.target}'])
        self.assertEqual(self.run_script('--apply'), [f'target: {self.target}', 'keep: # GTD agent captures',
                                                      'unchanged'])
        self.assertEqual(len(self.backups()), 1)

    def test_a_moved_section_is_not_dropped(self):
        self.write_target(GTD_SECTION + '\n' + ASSET)
        out = self.run_script()
        self.assertEqual(out, [f'target: {self.target}', 'keep: # GTD agent captures'])

    def test_new_file(self):
        self.assertEqual(self.run_script(), [f'target: {self.target}', 'new file'])
        self.assertFalse(self.config.exists())
        self.assertEqual(self.run_script('--apply'), [f'target: {self.target}', 'new file',
                                                      f'wrote: {self.target}'])
        self.assertEqual(self.target.read_text(encoding='utf-8'), ASSET)

    def test_file_without_the_section_gets_the_asset(self):
        self.write_target('# Old\n\n- Old rule.\n')
        self.run_script('--apply')
        self.assertEqual(self.target.read_text(encoding='utf-8'), ASSET)

    def test_asset_with_the_section_is_not_doubled(self):
        asset = self.root / 'asset.md'
        asset.write_text('# Rules\n\n' + GTD_SECTION, encoding='utf-8')
        self.write_target(OLD)
        out = self.run_script('--apply', '--asset', str(asset))
        self.assertNotIn('keep: # GTD agent captures', out)
        self.assertEqual(self.target.read_text(encoding='utf-8'), asset.read_text(encoding='utf-8'))

    def test_writes_through_a_symlink(self):
        real = self.root / 'dotfiles-CLAUDE.md'
        real.write_text(OLD, encoding='utf-8')
        self.config.mkdir()
        self.target.symlink_to(real)
        self.run_script('--apply')
        self.assertTrue(self.target.is_symlink())
        self.assertEqual(real.read_text(encoding='utf-8'), ASSET + '\n' + GTD_SECTION)

    def test_broken_symlink_and_bad_arguments_change_nothing(self):
        self.config.mkdir()
        self.target.symlink_to(self.root / 'missing.md')
        self.run_script('--apply', status=2)
        self.assertFalse((self.root / 'missing.md').exists())
        self.target.unlink()
        for args in (['--force'], ['--asset'], ['--asset', str(self.root / 'none.md')]):
            with self.subTest(args=args):
                self.run_script(*args, status=2)
                self.assertFalse(self.target.exists())


if __name__ == '__main__':
    unittest.main()
