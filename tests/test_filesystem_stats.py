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


@pytest.fixture
def jail(tmp_path: Path) -> tuple[Path, Path]:
    """A sandbox root next to a directory whose contents must never be reachable."""
    root = tmp_path / "root"
    (root / "sub").mkdir(parents=True)
    (root / "a.txt").write_text("a\n")
    (root / "sub" / "b.py").write_text("b = 1\n")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("secret\n")
    return root, outside


async def _call(root: Path, tool: str, **arguments: object) -> tuple[bool, str]:
    async with in_memory_session(build_server(root)) as s:
        out = await call_tool(s, tool, **arguments)
    return bool(out.isError), "\n".join(c.text for c in out.content)


def _link_or_skip(link: Path, target: Path) -> None:
    try:
        link.symlink_to(target, target_is_directory=target.is_dir())
    except OSError as exc:
        pytest.skip(f"cannot create symlinks here: {exc}")


@pytest.mark.parametrize("tool", ["list_directory", "file_summary"])
@pytest.mark.parametrize(
    "rel_path",
    ["..", "../outside", "../outside/secret.txt", "sub/../../outside/secret.txt", "ABSOLUTE"],
)
async def test_path_tools_reject_escapes(jail, tool: str, rel_path: str) -> None:
    root, outside = jail
    if rel_path == "ABSOLUTE":
        rel_path = str(outside / "secret.txt") if tool == "file_summary" else str(outside)
    is_error, text = await _call(root, tool, rel_path=rel_path)
    assert is_error
    assert "escapes sandbox" in text


@pytest.mark.parametrize(
    "pattern",
    ["../*", "../*/*", "../outside/*", "sub/../../outside/*", "**/../../outside/*", "ABSOLUTE"],
)
async def test_find_files_rejects_patterns_that_leave_the_root(jail, pattern: str) -> None:
    root, outside = jail
    if pattern == "ABSOLUTE":
        pattern = str(outside / "*")
    is_error, text = await _call(root, "find_files", pattern=pattern)
    assert is_error
    assert "secret.txt" not in text


async def test_find_files_still_matches_inside_the_root(jail) -> None:
    root, _ = jail
    is_error, text = await _call(root, "find_files", pattern="sub/*.py")
    assert not is_error
    assert text == "sub/b.py"


@pytest.mark.parametrize(
    ("tool", "arguments"),
    [
        ("list_directory", {"rel_path": "link"}),
        ("file_summary", {"rel_path": "link/secret.txt"}),
    ],
)
async def test_path_tools_reject_symlinks_out_of_the_root(jail, tool, arguments) -> None:
    root, outside = jail
    _link_or_skip(root / "link", outside)
    is_error, text = await _call(root, tool, **arguments)
    assert is_error
    assert "escapes sandbox" in text


@pytest.mark.parametrize("pattern", ["link/*", "**/*", "*/*.txt"])
async def test_find_files_skips_matches_behind_symlinks_out_of_the_root(jail, pattern: str) -> None:
    root, outside = jail
    _link_or_skip(root / "link", outside)
    _, text = await _call(root, "find_files", pattern=pattern)
    assert "secret.txt" not in text


async def test_find_files_skips_a_symlink_loop(jail) -> None:
    root, _ = jail
    _link_or_skip(root / "loop", root / "loop")
    is_error, text = await _call(root, "find_files", pattern="*")
    assert not is_error, text
    assert "a.txt" in text.splitlines()
