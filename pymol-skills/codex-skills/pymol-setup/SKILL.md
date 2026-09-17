---
name: pymol-setup
description: Set up the PyMOL socket plugin for Codex, or diagnose missing PyMOL MCP tools, connection failures, and listener configuration.
---

# Set up PyMOL for Codex

## Check prerequisites

Use a local Codex session on the machine that runs PyMOL. Confirm that PyMOL
and `uv` are installed. The bundled server uses `uv` to provision Python 3.10
or newer and its MCP dependency. The first launch needs access to download
missing dependencies. The Codex process must be able to find `uv` on `PATH`.

Install **PyMOL Skills** from the **cc-toolkit** Codex marketplace if it is
not installed. See the package [README](../../README.md) for installation.
Start a new Codex task after installing the package to load its tools.

## Install the socket plugin

Resolve the installed package root from this skill's location: it is two
levels above the directory containing this `SKILL.md`. Use that installed
copy, independent of any Claude Code installation or source checkout.

1. Open PyMOL.
2. Select **Plugin > Plugin Manager > Install New Plugin**.
3. Choose `pymol-mcp-socket-plugin/__init__.py` under the package root.
4. Complete installation. The PyMOL installer copies the containing package
   directory. Verify that `pymol_mcp_plugin.ui` remains beside `__init__.py`.
5. Open **Plugin > PyMol MCP Socket Plugin** and click **Start Listening**.
6. Confirm **Listening on port 9876**.

If the socket plugin is already installed, use the existing installation.
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
check preserves the molecular scene. Do not treat generic success text as
returned molecular data.

## Troubleshoot

- Missing tools: check that the Codex plugin is installed and enabled, then
  start a new task.
- Missing `uv`: install it using the [official uv instructions](https://docs.astral.sh/uv/getting-started/installation/)
  and ensure the Codex process can find it.
- Connection refused: start PyMOL's listener. The bridge uses `localhost:9876`;
  changing only the port in the PyMOL dialog will break the connection.
- Timeout: disconnect any other client. The socket plugin serves one
  persistent connection at a time, including across Claude Code and Codex.
- Remote Codex host: run the integration locally on the PyMOL machine.
