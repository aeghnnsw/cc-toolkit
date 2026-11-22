---
name: pymol-setup
description: Set up the PyMOL socket plugin for Antigravity, or diagnose missing PyMOL MCP tools, connection failures, and listener configuration.
---

# Set up PyMOL for Antigravity

## Check prerequisites

Use a local Antigravity conversation on the machine that runs PyMOL. Confirm
that PyMOL and `uv` are installed. The bundled server uses `uv` to provision
Python 3.10 or newer and its MCP dependency. The first launch needs access to
download missing dependencies. The Antigravity process must be able to find
`uv` on `PATH`.

If **PyMOL Skills** is not installed, run this command, then start a new
conversation to load its tools:

```bash
agy plugin install https://github.com/aeghnnsw/cc-toolkit/tree/master/pymol-skills
```

See the package [README](../../README.md) for installation.

## Install the socket plugin

The plugin root, `<plugin-root>`, is two levels above the directory that
holds this `SKILL.md`. Use that installed copy, independent of any Claude
Code or Codex installation or source checkout.

1. Open PyMOL.
2. Select **Plugin > Plugin Manager > Install New Plugin**.
3. Choose `<plugin-root>/pymol-mcp-socket-plugin/__init__.py`.
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

- Missing tools: check that `agy plugin list` shows the plugin as enabled,
  then start a new conversation.
- Missing `uv`: install it using the [official uv instructions](https://docs.astral.sh/uv/getting-started/installation/)
  and ensure the Antigravity process can find it.
- Connection refused: start PyMOL's listener. The bridge uses `localhost:9876`;
  changing only the port in the PyMOL dialog will break the connection.
- Timeout: disconnect any other client. The socket plugin serves one
  persistent connection at a time, including across Claude Code, Codex, and
  Antigravity.
- Remote agent: run the conversation locally on the PyMOL machine.
