"""Run model-config's set_autocompact.sh on settings files in temporary folders.

Each run sets HOME and CLAUDE_CONFIG_DIR to temporary folders, so no run reads or writes the real Claude Code
configuration. Issue #243: a percentage override left beside autoCompactWindow lowered the trigger from about
367,000 to about 152,000 tokens. Every action of the script must remove it (#464).
"""
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / 'skills' / 'model-config' / 'scripts' / 'set_autocompact.sh'
OVERRIDES = {'CLAUDE_AUTOCOMPACT_PCT_OVERRIDE': '40', 'CLAUDE_CODE_AUTO_COMPACT_WINDOW': '500000'}


@unittest.skipUnless(shutil.which('jq'), 'set_autocompact.sh needs jq; install it, for example with brew install jq')
class SetAutocompactTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.config = self.root / 'profile'
        self.config.mkdir()
        self.settings = self.config / 'settings.json'

    def run_script(self, *args, status=0):
        env = {'PATH': os.environ['PATH'], 'HOME': str(self.root / 'home'), 'CLAUDE_CONFIG_DIR': str(self.config),
               'TMPDIR': str(self.root)}
        result = subprocess.run(['bash', str(SCRIPT), *args], env=env, capture_output=True, text=True,
                                timeout=30, check=False)
        self.assertEqual(result.returncode, status, result.stderr)
        return result.stdout

    def write(self, settings):
        self.settings.write_text(json.dumps(settings, indent=2) + '\n', encoding='utf-8')

    def read(self):
        return json.loads(self.settings.read_text(encoding='utf-8'))

    def test_window_removes_both_overrides_and_keeps_other_keys(self):
        self.write({'model': 'claude-opus-5-5', 'env': {**OVERRIDES, 'KEEP': 'v'}, 'statusLine': {'type': 'command'}})
        out = self.run_script('window', '400000')
        self.assertEqual(self.read(), {'model': 'claude-opus-5-5', 'env': {'KEEP': 'v'},
                                       'statusLine': {'type': 'command'}, 'autoCompactWindow': 400000})
        self.assertIn(f'file: {self.settings}', out)
        self.assertIn('removed: env.CLAUDE_AUTOCOMPACT_PCT_OVERRIDE="40"', out)
        self.assertIn('removed: env.CLAUDE_CODE_AUTO_COMPACT_WINDOW="500000"', out)
        self.assertIn('autoCompactWindow: 400000', out)
        self.assertFalse((self.root / 'home').exists(), 'the script used HOME, not CLAUDE_CONFIG_DIR')

    def test_every_action_removes_the_overrides(self):
        expected = {'window': {'autoCompactWindow': 200000}, 'auto': {}, 'off': {'autoCompactEnabled': False},
                    'off-all': {'env': {'DISABLE_COMPACT': '1'}}, 'on': {'autoCompactEnabled': True}}
        for action, settings in expected.items():
            with self.subTest(action=action):
                self.write({'autoCompactWindow': 300000, 'env': dict(OVERRIDES)})
                self.run_script(action, *(['200000'] if action == 'window' else []))
                self.assertEqual(self.read(), {'autoCompactWindow': 300000, **settings} if action not in
                                 ('window', 'auto') else settings)

    def test_on_removes_the_disable_variables(self):
        self.write({'autoCompactEnabled': False, 'env': {'DISABLE_AUTO_COMPACT': '1', 'DISABLE_COMPACT': '1'}})
        out = self.run_script('on')
        self.assertEqual(self.read(), {'autoCompactEnabled': True})
        self.assertIn('removed: env.DISABLE_AUTO_COMPACT="1"', out)
        self.assertIn('env.DISABLE_COMPACT: not set', out)

    def test_off_keeps_the_disable_variables(self):
        self.write({'env': {'DISABLE_AUTO_COMPACT': '1'}})
        self.run_script('off')
        self.assertEqual(self.read(), {'env': {'DISABLE_AUTO_COMPACT': '1'}, 'autoCompactEnabled': False})

    def test_creates_a_missing_file_and_folder(self):
        shutil.rmtree(self.config)
        self.run_script('window', '1000000')
        self.assertEqual(self.read(), {'autoCompactWindow': 1000000})

    def test_explicit_file(self):
        other = self.root / 'other.json'
        self.run_script('--file', str(other), 'off')
        self.assertEqual(json.loads(other.read_text(encoding='utf-8')), {'autoCompactEnabled': False})
        self.assertFalse(self.settings.exists())
        self.assertIn('no change', self.run_script('auto'))
        self.assertFalse(self.settings.exists(), 'a change with no effect created the file')

    def test_same_value_leaves_the_file_unchanged(self):
        text = '{"autoCompactWindow":400000,"model":"m"}\n'
        self.settings.write_text(text, encoding='utf-8')
        self.assertIn('no change', self.run_script('window', '400000'))
        self.assertEqual(self.settings.read_text(encoding='utf-8'), text)

    def test_writes_through_a_symlink(self):
        target = self.root / 'dotfiles-settings.json'
        target.write_text('{"env": {"CLAUDE_AUTOCOMPACT_PCT_OVERRIDE": "40"}}\n', encoding='utf-8')
        target.chmod(0o600)
        self.settings.symlink_to(target)
        self.run_script('window', '400000')
        self.assertTrue(self.settings.is_symlink())
        self.assertEqual(json.loads(target.read_text(encoding='utf-8')), {'autoCompactWindow': 400000})
        self.assertEqual(target.stat().st_mode & 0o777, 0o600)

    def test_rejects_bad_input_and_changes_nothing(self):
        text = '{"env": {"CLAUDE_AUTOCOMPACT_PCT_OVERRIDE": "40"}}\n'
        cases = [('window', '99999'), ('window', '1000001'), ('window', '4e5'), ('window', '0400000'),
                 ('window', '500k'), ('window',), ('maybe',), ()]
        for args in cases:
            with self.subTest(args=args):
                self.settings.write_text(text, encoding='utf-8')
                self.run_script(*args, status=2)
                self.assertEqual(self.settings.read_text(encoding='utf-8'), text)
        for bad in ('{"env": ', '[]', '{"env": "x"}'):
            with self.subTest(settings=bad):
                self.settings.write_text(bad, encoding='utf-8')
                self.run_script('auto', status=2)
                self.assertEqual(self.settings.read_text(encoding='utf-8'), bad)


if __name__ == '__main__':
    unittest.main()
