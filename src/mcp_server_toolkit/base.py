"""Thin wrapper around ``mcp.server.fastmcp.FastMCP``.

Lets the example servers in ``mcp_server_toolkit/servers/`` share a
``ToolkitServer`` base with a tool registry for documentation, plus a uniform
error-handling pattern: success → return ``str``, failure → raise
:class:`ToolError`. FastMCP serializes the string as a TextContent block and
turns the exception into an ``isError: true`` result automatically.
"""

from __future__ import annotations

import logging
from typing import Any

from mcp.server.fastmcp import FastMCP

_logger = logging.getLogger("mcp_server_toolkit")


class ToolError(Exception):
    """Raise from a tool function to signal a user-visible error.

    FastMCP catches this and emits an ``isError: true`` ``CallToolResult``,
    which is the MCP-spec way to signal a tool-level failure as opposed to a
    server-level crash.
    """


class ToolkitServer:
    """Wrap a :class:`FastMCP` instance with a per-tool description registry."""

    def __init__(self, name: str, description: str = "") -> None:
        self.name = name
        self.description = description
        self.mcp: FastMCP = FastMCP(name)
        self._tool_descriptions: list[dict[str, str]] = []

    def tool(self, *args: Any, **kwargs: Any):
        """Re-export of :meth:`FastMCP.tool`."""
        return self.mcp.tool(*args, **kwargs)

    def list_registered_tools(self) -> list[dict[str, str]]:
        return list(self._tool_descriptions)

    def run(self, transport: str = "stdio") -> None:
        self.mcp.run(transport=transport)


def register_tool(server: ToolkitServer, *, name: str, description: str):
    """Decorator: register a tool and record its description on the wrapper."""

    def decorator(fn):
        server._tool_descriptions.append({"name": name, "description": description})
        return server.mcp.tool(name=name, description=description)(fn)

    return decorator
