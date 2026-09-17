# PyMOL MCP Plugin

Control a local PyMOL session from Claude Code or Codex through MCP.
Both hosts use the same Python bridge and PyMOL socket plugin.

## Prerequisites

- [PyMOL](https://pymol.org/2/) with its graphical plugin manager.
- [uv](https://docs.astral.sh/uv/getting-started/installation/) on the host's `PATH`.
- Access to download missing Python and MCP dependencies on first launch.
- PyMOL and the MCP server on the same machine.

## Codex installation

Add the marketplace if it is not already configured:

```bash
codex plugin marketplace add aeghnnsw/cc-toolkit
```

If it is already configured, refresh it before installing the new plugin:

```bash
codex plugin marketplace upgrade cc-toolkit
```

Install the plugin:

```bash
codex plugin add pymol-skills@cc-toolkit
```

Start a new Codex task. Ask to use `pymol-setup` to configure the socket
plugin, then use `pymol-mcp` to control PyMOL. The Codex manifest declares
`codex-skills/` and `mcp-config.codex.json`. Codex resolves the MCP `cwd`
relative to the installed package root. The bridge runs from that directory;
it does not need a Claude Code installation or a source checkout.

## Claude Code installation

Install `pymol-skills@cc-toolkit` from the Claude Code marketplace. Ask to
use `pymol-setup` for socket installation guidance. Claude Code retains its
own manifest, skills, and MCP configuration.

## Socket setup

1. In PyMOL, open **Plugin > Plugin Manager > Install New Plugin**.
2. Select `pymol-mcp-socket-plugin/__init__.py` from the installed package.
   The installer copies the package directory, including the required
   `pymol_mcp_plugin.ui` file.
3. Open **Plugin > PyMol MCP Socket Plugin** and click **Start Listening**.
4. Confirm **Listening on port 9876**.

Use the existing socket plugin if it is already installed. The bridge always
connects to `localhost:9876`. Start the listener again after restarting PyMOL.
The listener serves one client at a time. Disconnect another Codex or Claude
Code MCP client before connecting a new one.

## Tools

- `pymol_command`: native PyMOL commands.
- `pymol_python_api`: Python API commands using `cmd`.

Ask: "Load protein 1UBQ and show it as a cartoon."
For a check that preserves the scene, use `pymol_python_api` with
`assert isinstance(cmd.get_names(), list)`.

## Components

- `pymol_mcp_server.py`: shared stdio MCP server.
- `pymol-mcp-socket-plugin/`: shared PyMOL socket plugin and Qt interface.
- `skills/`: Claude Code guidance.
- `codex-skills/`: Codex guidance.

## Attribution

Based on [PyMOL-MCP](https://github.com/vrtejus/pymol-mcp) by vrtejus.

## License

MIT License
