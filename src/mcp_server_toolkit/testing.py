"""In-memory test harness: spin up a real ClientSession talking to a real
FastMCP server over an in-process memory transport.

This is the fast path for both unit tests and the latency benchmark — no
subprocess, no JSON-over-stdio roundtrip, no fixture flakiness.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

from mcp.client.session import ClientSession
from mcp.shared.memory import create_connected_server_and_client_session

from mcp_server_toolkit.base import ToolkitServer


@asynccontextmanager
async def in_memory_session(server: ToolkitServer):
    """Yield an initialized :class:`ClientSession` connected to ``server``."""
    async with create_connected_server_and_client_session(
        server.mcp._mcp_server
    ) as client_session:
        yield client_session


async def list_tools(session: ClientSession) -> list[Any]:
    """Return the tools advertised by the connected server."""
    result = await session.list_tools()
    return list(result.tools)


async def call_tool(session: ClientSession, tool_name: str, /, **arguments: Any) -> Any:
    """Call a tool by name and return the result object the SDK produces.

    ``tool_name`` is positional-only so callers can pass ``name=...`` as a
    tool argument without it colliding with the helper's own parameter.
    """
    return await session.call_tool(tool_name, arguments=arguments)
