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
    """Stand in for PyMOL's `cmd`: `do` writes each command to the open log, as PyMOL logs a command.
    No call prints output."""

    def __init__(self):
        self.log = None
        self.commands = []

    def log_open(self, path):
        self.log = path

    def log_close(self):
        self.log = None

    def do(self, command):
        self.commands.append(command)
        if self.log:
            with open(self.log, 'a') as log:
                log.write(command + '\n')

    def align(self, mobile, target):
        pass


class SocketPluginTests(unittest.TestCase):
    def setUp(self):
        self.plugin = load_plugin()
        self.cmd = FakeCmd()

    def execute(self, code):
        with contextlib.redirect_stdout(io.StringIO()):
            return self.plugin.execute_code(self.cmd, code)

    def test_code_without_output_gets_empty_output(self):
        command = 'label all, "it\'s"'
        for code in (f'cmd.do({command!r})', "cmd.do('fetch 1ubq')", "cmd.align('mobile', 'target')"):
            with self.subTest(code=code):
                self.assertEqual(self.execute(code), {'executed': True, 'output': '', 'error': ''})
        self.assertEqual(self.cmd.commands, [command, 'fetch 1ubq'])


if __name__ == '__main__':
    unittest.main()
