"""Exercise the installed Codex and Antigravity launches at the MCP stdio boundary.

Run with: python3 -m unittest discover -s pymol-skills/tests -p 'test_*.py'
Requires uv and access to provision the script's declared dependencies.
"""

import contextlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
import unittest


def run_server(command, args, cwd):
    """Start the server, send initialize and tools/list, and return the run.

    stdin stays open until the tools/list response arrives, as it does for an
    MCP client. When stdin closes first, the server can stop before it answers
    a request that it has read.
    """
    messages = [
        {
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05", "capabilities": {},
                "clientInfo": {"name": "pymol-startup-test", "version": "1.0"},
            },
        },
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
    ]
    # A file, not a pipe, takes stderr, so that a long log cannot stall the server.
    with tempfile.TemporaryFile("w+") as stderr:
        process = subprocess.Popen(
            [command, *args], cwd=cwd, text=True,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=stderr,
        )
        # Stop a server that does not answer in time.
        timer = threading.Timer(120, process.kill)
        timer.start()
        lines = []
        try:
            with contextlib.suppress(BrokenPipeError):
                process.stdin.write("".join(json.dumps(message) + "\n" for message in messages))
                process.stdin.flush()
            for line in process.stdout:
                lines.append(line)
                if json.loads(line).get("id") == 2:
                    break
            with contextlib.suppress(BrokenPipeError):
                process.stdin.close()
            lines.append(process.stdout.read())
            returncode = process.wait()
        finally:
            timer.cancel()
            if process.poll() is None:
                process.kill()
                process.wait()
        stderr.seek(0)
        return subprocess.CompletedProcess(process.args, returncode, "".join(lines), stderr.read())


class McpStartupTests(unittest.TestCase):
    def setUp(self):
        source = Path(__file__).resolve().parents[1]
        tmp = tempfile.TemporaryDirectory(prefix="pymol installed package ")
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name) / "pymol-skills"
        shutil.copytree(source, self.root, ignore=shutil.ignore_patterns("__pycache__"))

    def assert_initializes_and_lists_both_tools(self, result):
        self.assertEqual(result.returncode, 0, result.stderr)
        responses = {
            message["id"]: message
            for line in result.stdout.splitlines()
            if "id" in (message := json.loads(line))
        }
        self.assertIn("result", responses.get(1, {}), result.stdout + result.stderr)
        tools = responses[2]["result"]["tools"]
        self.assertEqual({tool["name"] for tool in tools},
                         {"pymol_command", "pymol_python_api"})
        schemas = {tool["name"]: tool["inputSchema"] for tool in tools}
        self.assertIn("command", schemas["pymol_command"]["required"])
        self.assertIn("python_code", schemas["pymol_python_api"]["required"])

    def test_relocated_codex_package_initializes_and_lists_both_tools(self):
        manifest = json.loads((self.root / ".codex-plugin/plugin.json").read_text())
        config = json.loads((self.root / manifest["mcpServers"]).read_text())
        server = config["mcpServers"]["pymol-mcp"]
        result = run_server(server["command"], server["args"], self.root / server["cwd"])
        self.assert_initializes_and_lists_both_tools(result)

    def test_relocated_antigravity_package_initializes_and_lists_both_tools(self):
        # Antigravity reads the root mcp_config.json and expands ${PLUGIN_ROOT}
        # in args, cwd, and env, but not in command.
        config = json.loads((self.root / "mcp_config.json").read_text())
        server = config["mcpServers"]["pymol-mcp"]
        self.assertNotIn("${PLUGIN_ROOT}", server["command"])

        def expand(value):
            return value.replace("${PLUGIN_ROOT}", str(self.root))

        args = [expand(arg) for arg in server["args"]]
        self.assertIn(str(self.root / "pymol_mcp_server.py"), args)
        cwd = expand(server["cwd"])
        self.assertEqual(Path(cwd), self.root)
        result = run_server(server["command"], args, cwd)
        self.assert_initializes_and_lists_both_tools(result)


if __name__ == "__main__":
    unittest.main()
