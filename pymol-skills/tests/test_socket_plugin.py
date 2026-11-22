"""Run code from the bridge through the PyMOL socket plugin with a fake PyMOL `cmd`.

Run with: python3 -m unittest discover -s pymol-skills/tests -p 'test_*.py'
The plugin imports PyMOL only in its dialog, so the test needs no PyMOL.
"""

import contextlib
import importlib.util
import io
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


def load_plugin():
    path = ROOT / 'pymol-mcp-socket-plugin' / '__init__.py'
    spec = importlib.util.spec_from_file_location('pymol_mcp_socket_plugin', path)
    plugin = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(plugin)
    return plugin


class FakeCmd:
    """Stand in for PyMOL's `cmd`: record each command that `do` runs. No call prints output."""

    def __init__(self):
        self.commands = []

    def do(self, command):
        self.commands.append(command)

    def align(self, mobile, target):
        pass

    def count_atoms(self, selection):
        return 0


class SocketPluginTests(unittest.TestCase):
    def setUp(self):
        self.plugin = load_plugin()
        self.cmd = FakeCmd()

    def execute(self, code):
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return self.plugin.execute_code(self.cmd, code)

    def test_code_without_output_gets_empty_output(self):
        command = 'label all, "it\'s"'
        for code in (f'cmd.do({command!r})', "cmd.do('fetch 1ubq')", "cmd.align('mobile', 'target')"):
            with self.subTest(code=code):
                self.assertEqual(self.execute(code), {'executed': True, 'output': '', 'error': ''})
        self.assertEqual(self.cmd.commands, [command, 'fetch 1ubq'])

    def test_failed_assert_returns_an_error(self):
        result = self.execute("assert cmd.count_atoms('1ubq') > 0, 'no atoms in 1ubq'")
        self.assertEqual(result, {'executed': False, 'output': '',
                                  'error': 'Error executing PyMOL command: no atoms in 1ubq'})


if __name__ == '__main__':
    unittest.main()
