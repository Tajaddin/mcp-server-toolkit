"""MCP server exposing sandboxed read-only filesystem stat operations."""

from __future__ import annotations

import argparse
import os
import stat as _stat
from datetime import datetime, timezone
from pathlib import Path

from mcp_server_toolkit.base import ToolError, ToolkitServer, register_tool


def build_server(root: Path, max_entries: int = 200) -> ToolkitServer:
    server = ToolkitServer(
        name="filesystem-stats",
        description="Sandboxed read-only filesystem stats over a single root.",
    )
    root = root.resolve()

    def _resolve_in_sandbox(rel: str) -> Path:
        path = (root / rel).resolve()
        if root != path and root not in path.parents:
            raise ToolError(f"path escapes sandbox: {rel!r}")
        return path

    @register_tool(
        server,
        name="list_directory",
        description=(
            "List entries of a directory under the sandbox root. Returns name, "
            "type, size_bytes, and modified time for each entry. ``rel_path`` "
            "is relative to the sandbox root."
        ),
    )
    def list_directory(rel_path: str = ".") -> str:
        target = _resolve_in_sandbox(rel_path)
        if not target.exists():
            raise ToolError(f"not found: {rel_path}")
        if not target.is_dir():
            raise ToolError(f"not a directory: {rel_path}")
        rows = []
        for i, entry in enumerate(sorted(target.iterdir())):
            if i >= max_entries:
                rows.append(f"... ({sum(1 for _ in target.iterdir()) - max_entries} more)")
                break
            st = entry.stat()
            mt = datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).isoformat()
            kind = "dir" if entry.is_dir() else "file"
            rows.append(f"{entry.name}\t{kind}\t{st.st_size}\t{mt}")
        return "\n".join(rows) if rows else "(empty)"

    @register_tool(
        server,
        name="file_summary",
        description=(
            "Return size, suffix, and (for text files <= 1 MB) line count for one "
            "file under the sandbox root."
        ),
    )
    def file_summary(rel_path: str) -> str:
        target = _resolve_in_sandbox(rel_path)
        if not target.exists():
            raise ToolError(f"not found: {rel_path}")
        if not target.is_file():
            raise ToolError(f"not a file: {rel_path}")
        st = target.stat()
        line_count: int | None = None
        if st.st_size <= 1_000_000:
            try:
                with target.open("rb") as f:
                    line_count = sum(1 for _ in f)
            except (OSError, UnicodeDecodeError):
                line_count = None
        return (
            f"size_bytes={st.st_size}\nsuffix={target.suffix}\n"
            f"line_count={'n/a' if line_count is None else line_count}\n"
            f"mode={_stat.filemode(st.st_mode)}"
        )

    @register_tool(
        server,
        name="find_files",
        description=(
            "Find files matching a glob pattern under the sandbox root. "
            "``max_depth`` caps recursion; ``limit`` caps the number of returned "
            "paths."
        ),
    )
    def find_files(pattern: str, max_depth: int = 5, limit: int = 50) -> str:
        if max_depth < 1 or max_depth > 20:
            raise ToolError("max_depth must be in [1, 20]")
        if limit < 1 or limit > 1000:
            raise ToolError("limit must be in [1, 1000]")
        matches: list[str] = []
        root_parts = len(root.parts)
        for path in root.rglob(pattern):
            try:
                path.relative_to(root)
            except ValueError:
                continue
            if len(path.parts) - root_parts > max_depth:
                continue
            matches.append(str(path.relative_to(root)).replace(os.sep, "/"))
            if len(matches) >= limit:
                break
        return "\n".join(matches) if matches else "(no matches)"

    return server


def main() -> None:
    parser = argparse.ArgumentParser(description="MCP server: filesystem-stats")
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="Sandbox root")
    args = parser.parse_args()
    server = build_server(args.root)
    server.run()


if __name__ == "__main__":
    main()
