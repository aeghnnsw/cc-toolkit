"""Exercise the installed Codex launch at the MCP stdio boundary.

Run with: python3 -m unittest discover -s pymol-skills/tests -p 'test_*.py'
Requires uv and access to provision the script's declared dependencies.
"""

import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


class McpStartupTests(unittest.TestCase):
    def test_relocated_package_initializes_and_lists_both_tools(self):
        source = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory(prefix="pymol installed package ") as tmp:
            root = Path(tmp) / "pymol-skills"
            shutil.copytree(source, root, ignore=shutil.ignore_patterns("__pycache__"))
            manifest = json.loads((root / ".codex-plugin/plugin.json").read_text())
            config = json.loads((root / manifest["mcpServers"]).read_text())
            server = config["mcpServers"]["pymol-mcp"]
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
            result = subprocess.run(
                [server["command"], *server["args"]],
                cwd=root / server["cwd"],
                input="".join(json.dumps(message) + "\n" for message in messages),
                text=True, capture_output=True, timeout=120,
            )
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


if __name__ == "__main__":
    unittest.main()
