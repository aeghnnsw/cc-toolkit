# PyMOL MCP Plugin

PyMOL molecular visualization and analysis tools integrated via MCP server. Enables Claude to directly interact with and control PyMOL through natural language.

## Quick Start

Run `/pymol-skills:setup` for installation instructions.

## Components

- **MCP Server** (`pymol_mcp_server.py`): FastMCP server providing PyMOL tools
- **Socket Plugin** (`pymol-mcp-socket-plugin/`): PyMOL plugin for socket communication
- **Skill** (`skills/pymol-mcp/`): Usage guidance and workflow examples

## Prerequisites

- [PyMOL](https://pymol.org/2/) installed on your system
- [UV](https://docs.astral.sh/uv/getting-started/installation/) package manager

## Attribution

Based on [PyMOL-MCP](https://github.com/vrtejus/pymol-mcp) by vrtejus.

## License

MIT License
