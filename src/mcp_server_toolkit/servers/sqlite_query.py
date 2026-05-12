"""MCP server: safe read-only SQLite queries."""

from __future__ import annotations

import argparse
import re
import sqlite3
from pathlib import Path

from mcp_server_toolkit.base import ToolError, ToolkitServer, register_tool


_READ_ONLY_RE = re.compile(r"^\s*(SELECT|WITH)\b", re.IGNORECASE)


def _is_read_only(sql: str) -> bool:
    if not _READ_ONLY_RE.search(sql or ""):
        return False
    stripped = sql.strip().rstrip(";").strip()
    return ";" not in stripped


def build_server(db_path: Path, row_limit: int = 100) -> ToolkitServer:
    server = ToolkitServer(
        name="sqlite-query",
        description="Read-only SQLite query interface with row-limit + write-rejection.",
    )
    db_path = db_path.resolve()

    def _connect() -> sqlite3.Connection:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        return conn

    @register_tool(
        server,
        name="list_tables",
        description="List user tables in the configured SQLite database.",
    )
    def list_tables() -> str:
        if not db_path.exists():
            raise ToolError(f"db file not found: {db_path}")
        with _connect() as conn:
            rows = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
            ).fetchall()
        return "\n".join(r["name"] for r in rows) if rows else "(no tables)"

    @register_tool(
        server,
        name="describe_table",
        description="Return columns + types for a single table.",
    )
    def describe_table(name: str) -> str:
        if not name or not re.match(r"^[A-Za-z_][A-Za-z_0-9]*$", name):
            raise ToolError(f"invalid table name: {name!r}")
        if not db_path.exists():
            raise ToolError(f"db file not found: {db_path}")
        with _connect() as conn:
            rows = conn.execute(f"PRAGMA table_info({name})").fetchall()
        if not rows:
            raise ToolError(f"unknown table: {name}")
        return "\n".join(
            f"{r['name']}\t{r['type']}{' PRIMARY KEY' if r['pk'] else ''}" for r in rows
        )

    @register_tool(
        server,
        name="query",
        description=(
            "Run a read-only SQL query (SELECT or WITH ... SELECT). Returns up to "
            f"``{row_limit}`` rows as TSV. Write statements are rejected."
        ),
    )
    def query(sql: str) -> str:
        if not _is_read_only(sql):
            raise ToolError("rejected: only single SELECT/WITH statements are allowed")
        if not db_path.exists():
            raise ToolError(f"db file not found: {db_path}")
        try:
            with _connect() as conn:
                cur = conn.execute(sql)
                rows = cur.fetchmany(row_limit)
                cols = [d[0] for d in cur.description] if cur.description else []
        except sqlite3.Error as exc:
            raise ToolError(f"sqlite error: {exc}") from exc
        if not rows:
            return f"({len(cols)} columns, 0 rows)"
        header = "\t".join(cols)
        body = "\n".join("\t".join(str(r[c]) if r[c] is not None else "" for c in cols) for r in rows)
        truncated = "\n... (truncated)" if len(rows) >= row_limit else ""
        return f"{header}\n{body}{truncated}"

    return server


def main() -> None:
    parser = argparse.ArgumentParser(description="MCP server: sqlite-query")
    parser.add_argument("--db", type=Path, required=True, help="Path to SQLite DB")
    args = parser.parse_args()
    server = build_server(args.db)
    server.run()


if __name__ == "__main__":
    main()
