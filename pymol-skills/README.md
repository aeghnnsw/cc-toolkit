# PyMOL MCP Plugin

PyMOL molecular visualization and analysis tools integrated via MCP server. Enables Claude to directly interact with and control PyMOL through natural language.

## Prerequisites

- [PyMOL](https://pymol.org/2/) installed on your system
- [Claude Code](https://claude.ai/code) or Claude Desktop
- [UV](https://docs.astral.sh/uv/getting-started/installation/) package manager

## Installation

### Step 1: Install PyMOL Socket Plugin

1. Open PyMOL
2. Go to **Plugin > Plugin Manager > Install New Plugin**
3. Click **Choose file...** and select `pymol-mcp-socket-plugin/__init__.py`
4. Click **OK** to install

To activate: **Plugin > PyMOL MCP Socket Plugin > Start Listening**

### Step 2: Enable the Plugin

The MCP server is automatically available when this plugin is installed in Claude Code.

## Usage

1. **Start PyMOL** and activate the plugin (Plugin > PyMOL MCP Socket Plugin > Start Listening)
2. **Open Claude Code** - PyMOL tools will be available
3. **Use natural language** to control PyMOL:
   - "Load PDB 1UBQ and display it as cartoon"
   - "Color the protein by secondary structure"
   - "Show the active site residues as sticks"

## MCP Tools

- `pymol_command`: Execute direct PyMOL commands (e.g., `fetch 1ubq`, `show cartoon`)
- `pymol_python_api`: Execute PyMOL Python API commands (e.g., `cmd.fetch('1ubq')`)

## Troubleshooting

- **No connection**: Ensure PyMOL plugin shows "Listening on port 9876" before using Claude
- **Tools not appearing**: Restart Claude Code after plugin installation

## Attribution

Based on [PyMOL-MCP](https://github.com/vrtejus/pymol-mcp) by vrtejus.

## License

MIT License
