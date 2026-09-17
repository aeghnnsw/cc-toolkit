---
name: pymol-mcp
description: Control PyMOL through MCP when the user wants to visualize molecular structures, align structures, measure geometry, or export molecular images.
---

# PyMOL MCP

Use the installed PyMOL MCP tools to operate the user's running PyMOL session.
PyMOL and the MCP server must run on the same machine. The socket plugin must
show **Listening on port 9876**. If setup is incomplete, follow
[PyMOL setup](../pymol-setup/SKILL.md).

## Tools

Find the tools by their exposed names; Codex can add a plugin namespace.

- `pymol_command(command)`: execute native PyMOL syntax, such as
  `show cartoon, all` or `color red, chain A`.
- `pymol_python_api(python_code)`: execute Python using the existing `cmd`
  object, such as `cmd.align('mobile', 'target')`. Prefer this tool when
  commands contain quotes or require multiple steps.

Act on the objects and selections the user requests. Preserve the current
session unless the requested operation requires changing it. Use absolute
paths when loading local structures or saving results. Those paths belong
to the machine running PyMOL.

For a new protein visualization, use the Python API:

```python
cmd.fetch('1ubq')
cmd.show('cartoon', '1ubq')
cmd.color('cyan', '1ubq')
cmd.zoom('1ubq')
```

To verify the connection without changing molecular objects or the view:

```python
assert isinstance(cmd.get_names(), list)
assert isinstance(cmd.count_atoms(), int)
assert len(cmd.get_view()) == 18
```

Read the returned text. The server can report execution or connection errors
as ordinary text. A completed tool call alone does not prove success. The
socket plugin may return a generic success message instead of Python values
or printed output; report only what the response establishes.

## Connection recovery

- Connection refused: open PyMOL and start its socket listener on port 9876.
- Timeout: the listener serves one client at a time. Disconnect the other
  MCP client, including a Claude Code session, then reconnect from Codex.
- Missing tools or failed server launch: follow the setup skill and check
  that `uv` is available to the local Codex process.
