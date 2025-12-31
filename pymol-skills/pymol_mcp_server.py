#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "mcp[cli]>=1.0.0",
# ]
# ///

import socket
import json
import logging
from contextlib import asynccontextmanager
from typing import Optional, Dict, Any, AsyncIterator

from mcp.server.fastmcp import FastMCP, Context

##############################################################################
# LOGGING
##############################################################################

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("PyMOLMCPServer")

##############################################################################
# PYMOL SOCKET CONNECTION
##############################################################################

class PyMOLConnection:
    """Manages socket connection to PyMOL plugin."""

    def __init__(self, host: str = 'localhost', port: int = 9876):
        self.host = host
        self.port = port
        self.sock: Optional[socket.socket] = None

    def connect(self) -> bool:
        """Establish connection to PyMOL socket server."""
        if self.sock:
            return True
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.connect((self.host, self.port))
            logger.info(f"Connected to PyMOL at {self.host}:{self.port}")
            return True
        except Exception as e:
            logger.error(f"Connection error: {e}")
            self.sock = None
            return False

    def disconnect(self) -> None:
        """Close the socket connection."""
        if self.sock:
            try:
                self.sock.close()
            except Exception as e:
                logger.error(f"Disconnect error: {e}")
            finally:
                self.sock = None

    def send_command(self, code: str) -> Dict[str, Any]:
        """
        Sends Python code to PyMOL via the socket plugin and returns a JSON response.

        Response format:
        {
            "status": "success" or "error",
            "result": {
                "executed": bool,
                "output": str or None,
                "error": str or None
            },
            "message": "error message string if any"
        }
        """
        if not self.sock and not self.connect():
            raise ConnectionError("Not connected to PyMOL")

        data = {"type": "pymol_command", "code": code}

        try:
            # Send command
            self.sock.sendall(json.dumps(data).encode('utf-8'))
            self.sock.settimeout(10.0)

            # Receive response
            chunks = []
            while True:
                chunk = self.sock.recv(4096)
                if not chunk:
                    break
                chunks.append(chunk)
                buffer = b''.join(chunks)
                try:
                    response = json.loads(buffer.decode('utf-8'))
                    return response
                except json.JSONDecodeError:
                    continue

            if chunks:
                buffer = b''.join(chunks)
                return json.loads(buffer.decode('utf-8'))

            raise ConnectionError("No response from PyMOL")

        except socket.timeout:
            self.sock = None
            raise TimeoutError("PyMOL response timed out")
        except Exception as e:
            self.sock = None
            raise RuntimeError(f"PyMOL command error: {e}")

# Global connection instance
_global_connection: Optional[PyMOLConnection] = None

def get_pymol_connection() -> PyMOLConnection:
    """Get or create the global PyMOL connection."""
    global _global_connection

    # Test if existing connection is alive
    if _global_connection is not None:
        try:
            _global_connection.send_command("pass")
            return _global_connection
        except:
            try:
                _global_connection.disconnect()
            except:
                pass
            _global_connection = None

    # Create new connection
    if _global_connection is None:
        conn = PyMOLConnection()
        if not conn.connect():
            raise RuntimeError("Could not connect to PyMOL socket.")
        _global_connection = conn

    return _global_connection

##############################################################################
# MCP SERVER SETUP
##############################################################################

@asynccontextmanager
async def server_lifespan(server: FastMCP) -> AsyncIterator[dict]:
    """Lifecycle management for the MCP server."""
    try:
        logger.info("Starting PyMOL MCP server.")
        try:
            get_pymol_connection()
        except Exception as e:
            logger.warning(f"Initial PyMOL connection failure: {e}")
        yield {}
    finally:
        global _global_connection
        if _global_connection:
            _global_connection.disconnect()
            _global_connection = None
        logger.info("PyMOL MCP server shut down.")

mcp = FastMCP("PyMOLMCPServer", lifespan=server_lifespan)

##############################################################################
# MCP TOOLS
##############################################################################

@mcp.tool()
def pymol_command(ctx: Context, command: str) -> str:
    """
    Executes a direct PyMOL command using native PyMOL syntax.
    Returns the output from PyMOL execution.

    Examples:
      - "fetch 1ubq"
      - "show cartoon, all"
      - "color red, chain A"
      - "bg_color white"
      - "zoom all"
    """
    try:
        conn = get_pymol_connection()

        # Wrap command in cmd.do() for execution
        code = f"cmd.do('{command}')"
        response = conn.send_command(code)

        status = response.get("status", "error")
        if status == "success":
            res = response.get("result", {})

            # Handle different response formats
            if isinstance(res, dict):
                output = res.get("output", "")
                error = res.get("error", "")

                if error:
                    return f"Error: {error}"

                # Generate meaningful output for common commands
                if not output or output == command:
                    if command.startswith('fetch'):
                        structure = command.replace('fetch ', '').split()[0]
                        return f"Fetched structure: {structure}"
                    elif command.startswith('show') or command.startswith('hide'):
                        return f"Display updated: {command}"
                    elif command.startswith('color'):
                        return f"Coloring applied: {command}"
                    elif command.startswith('bg_color'):
                        color = command.replace('bg_color ', '').strip()
                        return f"Background color changed to: {color}"
                    else:
                        return f"Command executed: {command}"

                return output
            else:
                # Handle string response (legacy format)
                return str(res) if res else f"Command executed: {command}"
        else:
            msg = response.get("message", "Unknown error")
            return f"Execution failed: {msg}"
    except Exception as e:
        return f"Connection error: {e}"

@mcp.tool()
def pymol_python_api(ctx: Context, python_code: str) -> str:
    """
    Executes PyMOL Python API commands directly.
    Returns the output from PyMOL execution.

    Examples:
      - "cmd.fetch('1ubq')"
      - "cmd.show('cartoon', 'all')"
      - "cmd.color('red', 'chain A')"
      - "cmd.align('mobile', 'target')"
      - Custom Python scripts for complex operations
    """
    try:
        conn = get_pymol_connection()

        # Ensure pymol.cmd is imported in the code
        if 'from pymol import cmd' not in python_code and 'import cmd' not in python_code:
            python_code = f"from pymol import cmd\n{python_code}"

        response = conn.send_command(python_code)

        status = response.get("status", "error")
        if status == "success":
            res = response.get("result", {})

            # Handle different response formats
            if isinstance(res, dict):
                output = res.get("output", "")
                error = res.get("error", "")

                if error:
                    return f"Error: {error}"

                # Generate meaningful output if none provided
                if not output:
                    if 'cmd.fetch(' in python_code:
                        return f"Structure fetched via Python API"
                    elif 'cmd.align(' in python_code or 'cmd.super(' in python_code:
                        return f"Alignment completed via Python API"
                    elif 'cmd.show(' in python_code or 'cmd.hide(' in python_code:
                        return f"Display updated via Python API"
                    elif 'cmd.color(' in python_code:
                        return f"Coloring applied via Python API"
                    elif 'cmd.select(' in python_code:
                        return f"Selection created via Python API"
                    else:
                        return f"Python API command executed"

                return output
            else:
                # Handle string response (legacy format)
                return str(res) if res else f"Python API executed"
        else:
            msg = response.get("message", "Unknown error")
            return f"Execution failed: {msg}"
    except Exception as e:
        return f"Connection error: {e}"

##############################################################################
# ENTRY POINT
##############################################################################

def main():
    mcp.run()

if __name__ == "__main__":
    main()