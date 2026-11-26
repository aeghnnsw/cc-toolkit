"""Call the bridge tools against a fake PyMOL socket plugin on a free local port.

Run with: python3 -m unittest discover -s pymol-skills/tests -p 'test_*.py'
The test replaces the `mcp` package with a stub, so it needs neither uv nor the MCP dependency.
test_mcp_startup.py covers the MCP wiring of the real server.
"""

import importlib.util
import json
import logging
from pathlib import Path
import socket
import sys
import threading
import types
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]


def require_local_bind():
    """Raise one error that names the sandbox and the fix when a bind to 127.0.0.1 is denied.

    The Claude Code sandbox denies the bind of the fake socket plugin with PermissionError,
    "Operation not permitted". The check fails instead of skipping, because a skip prints OK
    and can pass as a local test run.
    """
    try:
        socket.create_server(('127.0.0.1', 0)).close()
    except PermissionError as error:
        raise RuntimeError(
            f'a sandbox blocks a bind to 127.0.0.1 ({error}), and these tests need it. Run the '
            'pymol-skills suite again outside the sandbox: python3 dev-skills/scripts/run_suite.py '
            '-- <suite command>, in Claude Code with dangerouslyDisableSandbox on the Bash call.'
        ) from None


def setUpModule():
    # In a sandbox that denies the bind, one error with the fix replaces an error for each test.
    require_local_bind()


def load_bridge():
    """Import pymol_mcp_server.py with a stub FastMCP whose tool decorator returns the function."""
    class FastMCP:
        def __init__(self, *args, **kwargs):
            pass

        def tool(self):
            return lambda function: function

    fastmcp = types.ModuleType('mcp.server.fastmcp')
    fastmcp.FastMCP, fastmcp.Context = FastMCP, object
    stubs = {'mcp': types.ModuleType('mcp'), 'mcp.server': types.ModuleType('mcp.server'),
             'mcp.server.fastmcp': fastmcp}
    with mock.patch.dict(sys.modules, stubs):
        spec = importlib.util.spec_from_file_location('pymol_mcp_server', ROOT / 'pymol_mcp_server.py')
        bridge = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(bridge)
    bridge.logger.setLevel(logging.WARNING)
    return bridge


class FakeSocketPlugin:
    """Answer each request as the PyMOL socket plugin does, and record its code.

    Code that does not compile gets the plugin's error result. Other code gets `output`.
    """

    def __init__(self):
        self.server = socket.create_server(('127.0.0.1', 0))
        self.port = self.server.getsockname()[1]
        self.codes = []
        self.output = ''
        self.thread = threading.Thread(target=self.serve, daemon=True)
        self.thread.start()

    def serve(self):
        client, _ = self.server.accept()
        with client:
            buffer = b''
            while data := client.recv(4096):
                buffer += data
                try:
                    code = json.loads(buffer)['code']
                except json.JSONDecodeError:
                    continue
                buffer = b''
                self.codes.append(code)
                try:
                    compile(code, '<mcp>', 'exec')
                    result = {'executed': True, 'output': self.output, 'error': ''}
                except SyntaxError as error:
                    result = {'executed': False, 'output': '',
                              'error': f'Error executing PyMOL command: {error}'}
                client.sendall(json.dumps({'status': 'success', 'result': result}).encode())

    def close(self):
        self.server.close()


class BridgeToolTests(unittest.TestCase):
    def setUp(self):
        self.bridge = load_bridge()
        self.plugin = FakeSocketPlugin()
        self.addCleanup(self.plugin.close)
        self.bridge._global_connection = self.bridge.PyMOLConnection(port=self.plugin.port)
        self.addCleanup(self.bridge._global_connection.disconnect)

    def test_command_with_a_single_quote_reaches_pymol_intact(self):
        command = 'label all, "it\'s"'
        self.plugin.output = 'PyMOL result'
        self.assertEqual(self.bridge.pymol_command(None, command), 'PyMOL result')
        received = []
        exec(self.plugin.codes[-1], {'cmd': types.SimpleNamespace(do=received.append)})
        self.assertEqual(received, [command])

    def test_empty_output_gives_a_neutral_message(self):
        # The plugin's output is empty, so success text such as "Fetched structure" would be invented.
        for tool, request in ((self.bridge.pymol_command, 'fetch 1ubq'),
                              (self.bridge.pymol_python_api, "cmd.align('mobile', 'target')")):
            with self.subTest(request=request):
                self.assertEqual(tool(None, request), f'PyMOL returned no output for: {request}')


class LocalBindCheckTests(unittest.TestCase):
    def test_denied_bind_raises_one_error_with_the_sandbox_and_the_fix(self):
        # The Claude Code sandbox denies the bind with errno 1, "Operation not permitted".
        denied = PermissionError(1, 'Operation not permitted')
        with mock.patch('socket.create_server', side_effect=denied), \
                self.assertRaises(RuntimeError) as raised:
            require_local_bind()

        message = str(raised.exception)
        self.assertRegex(message, r'^a sandbox blocks a bind to 127\.0\.0\.1 \(\[Errno 1\] '
                                  r'Operation not permitted\), and these tests need it\.')
        self.assertIn('outside the sandbox: python3 dev-skills/scripts/run_suite.py --', message)


if __name__ == '__main__':
    unittest.main()
