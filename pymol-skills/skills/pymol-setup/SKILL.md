---
name: pymol-setup
description: This skill should be used when the user asks to "set up PyMOL", "install PyMOL plugin", "configure PyMOL socket", "PyMOL setup instructions", or needs help installing and configuring the PyMOL MCP socket plugin for use with Claude Code.
---

Print the following setup instructions to the user:

## PyMOL MCP Plugin Setup

### Step 1: Install PyMOL Socket Plugin

1. Open PyMOL
2. Go to **Plugin > Plugin Manager > Install New Plugin**
3. Click **Choose file...** and select:
   ```
   ~/.claude/plugins/pymol-skills/pymol-mcp-socket-plugin/__init__.py
   ```
4. Click **OK** to install

### Step 2: Start the Socket Listener

Each time you want to use PyMOL with Claude:

1. Open PyMOL
2. Go to **Plugin > PyMOL MCP Socket Plugin > Start Listening**
3. You should see "Listening on port 9876" in the status

### Step 3: Use PyMOL Commands

Now you can use natural language to control PyMOL:
- "Load protein 1UBQ and show as cartoon"
- "Color chain A red and chain B blue"
- "Align structure1 to structure2"

### Troubleshooting

- **Connection refused**: Make sure PyMOL plugin is listening before using Claude
- **Plugin not found**: Reinstall the socket plugin in PyMOL
