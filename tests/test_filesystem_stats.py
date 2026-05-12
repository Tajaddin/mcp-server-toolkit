"""filesystem-stats server tests via in-memory MCP transport."""

from __future__ import annotations

from pathlib import Path

import pytest

from mcp_server_toolkit import call_tool, in_memory_session, list_tools
from mcp_server_toolkit.servers.filesystem_stats import build_server


@pytest.fixture
def sandbox(tmp_path: Path) -> Path:
    (tmp_path / "a.txt").write_text("line 1\nline 2\n")
    (tmp_path / "b.py").write_text("print('hello')\n")
    (tmp_path / "subdir").mkdir()
    (tmp_path / "subdir" / "c.md").write_text("# title\nbody\n")
    return tmp_path


async def test_list_tools_returns_three(sandbox: Path) -> None:
    server = build_server(sandbox)
    async with in_memory_session(server) as s:
        tools = await list_tools(s)
        names = {t.name for t in tools}
        assert names == {"list_directory", "file_summary", "find_files"}


async def test_list_directory_includes_files_and_subdir(sandbox: Path) -> None:
    server = build_server(sandbox)
    async with in_memory_session(server) as s:
        out = await call_tool(s, "list_directory", rel_path=".")
        text = out.content[0].text
        assert "a.txt" in text
        assert "b.py" in text
        assert "subdir" in text


async def test_file_summary_returns_line_count(sandbox: Path) -> None:
    server = build_server(sandbox)
    async with in_memory_session(server) as s:
        out = await call_tool(s, "file_summary", rel_path="a.txt")
        text = out.content[0].text
        assert "line_count=2" in text
        assert "suffix=.txt" in text


async def test_path_escape_is_rejected(sandbox: Path) -> None:
    server = build_server(sandbox)
    async with in_memory_session(server) as s:
        out = await call_tool(s, "list_directory", rel_path="../../../etc")
        # Either marked isError or the content includes the sandbox-escape message.
        assert out.isError is True or "escape" in (out.content[0].text or "").lower()


async def test_find_files_glob(sandbox: Path) -> None:
    server = build_server(sandbox)
    async with in_memory_session(server) as s:
        out = await call_tool(s, "find_files", pattern="*.py")
        text = out.content[0].text
        assert "b.py" in text
