---
name: pymol-setup
version: 1.0.1
description: Set up the PyMOL socket plugin for Claude Code, or diagnose missing PyMOL MCP tools, connection failures, and listener configuration.
---

# Set up PyMOL for Claude Code

## Check prerequisites

Use a local Claude Code session on the machine that runs PyMOL. Confirm
that PyMOL and `uv` are installed. The bundled server uses `uv` to provision
Python 3.10 or newer and its MCP dependency. The first launch needs access to
download missing dependencies. The Claude Code process must be able to find
`uv` on `PATH`.

Install **PyMOL Skills** from the **cc-toolkit** marketplace if it is
not installed. See the package [README](../../README.md) for installation.
Start a new Claude Code session after installing the package to load its tools.

## Install the socket plugin

Use the installed copy of this plugin, `${CLAUDE_PLUGIN_ROOT}`, independent
of any Codex or Antigravity installation or source checkout.

1. Open PyMOL.
2. Select **Plugin > Plugin Manager > Install New Plugin**.
3. Choose `${CLAUDE_PLUGIN_ROOT}/pymol-mcp-socket-plugin/__init__.py`.
4. Complete installation. The PyMOL installer copies the containing package
   directory. Verify that `pymol_mcp_plugin.ui` remains beside `__init__.py`.
5. Open **Plugin > PyMol MCP Socket Plugin** and click **Start Listening**.
6. Confirm **Listening on port 9876**.

If the socket plugin is already installed, use the existing installation
unless [Verify](#verify) shows that it is outdated.
If its interface fails to open because the UI file is missing, reinstall
from the complete bundled directory. Restarting PyMOL may require starting
its listener again. Preserve any unsaved session before restarting.

## Verify

Discover `pymol_python_api` and call it with:

```python
assert isinstance(cmd.get_names(), list)
assert len(cmd.get_view()) == 18
```

Success requires a response without a connection or execution error. This
check preserves the molecular scene. With a current socket plugin, the
response is `PyMOL returned no output for: ...`. Generic success text, such
as `Python API command executed`, comes from an outdated socket plugin:
reinstall it as above, then restart PyMOL.

## Troubleshoot

- Missing tools: check that the Claude Code plugin is installed and
  enabled, then start a new session.
- Missing `uv`: install it using the [official uv instructions](https://docs.astral.sh/uv/getting-started/installation/)
  and ensure the Claude Code process can find it.
- Connection refused: start PyMOL's listener. The bridge uses `localhost:9876`;
  changing only the port in the PyMOL dialog will break the connection.
- Timeout: disconnect any other client. The socket plugin serves one
  persistent connection at a time, including across Claude Code, Codex, and
  Antigravity.
- Remote Claude Code session: run the integration locally on the PyMOL
  machine.
