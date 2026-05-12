"""sqlite-query server tests."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from mcp_server_toolkit import call_tool, in_memory_session
from mcp_server_toolkit.servers.sqlite_query import build_server, _is_read_only


@pytest.fixture
def db(tmp_path: Path) -> Path:
    p = tmp_path / "test.db"
    conn = sqlite3.connect(p)
    conn.executescript(
        """
        CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT, age INTEGER);
        INSERT INTO users VALUES (1, 'alice', 30), (2, 'bob', 42);
        CREATE TABLE orders (id INTEGER PRIMARY KEY, user_id INTEGER, total REAL);
        INSERT INTO orders VALUES (1, 1, 19.99), (2, 1, 7.50);
        """
    )
    conn.close()
    return p


def test_read_only_check_accepts_select() -> None:
    assert _is_read_only("SELECT 1") is True
    assert _is_read_only("  WITH x AS (SELECT 1) SELECT * FROM x") is True


def test_read_only_check_rejects_writes() -> None:
    assert _is_read_only("INSERT INTO x VALUES (1)") is False
    assert _is_read_only("UPDATE x SET y = 1") is False
    assert _is_read_only("DROP TABLE x") is False
    assert _is_read_only("SELECT 1; DROP TABLE x") is False  # statement chaining


async def test_list_tables(db: Path) -> None:
    server = build_server(db)
    async with in_memory_session(server) as s:
        out = await call_tool(s, "list_tables")
        text = out.content[0].text
        assert "orders" in text
        assert "users" in text


async def test_describe_table(db: Path) -> None:
    server = build_server(db)
    async with in_memory_session(server) as s:
        out = await call_tool(s, "describe_table", name="users")
        text = out.content[0].text
        assert "name" in text
        assert "age" in text


async def test_query_returns_tsv(db: Path) -> None:
    server = build_server(db)
    async with in_memory_session(server) as s:
        out = await call_tool(s, "query", sql="SELECT name, age FROM users ORDER BY id")
        text = out.content[0].text
        assert "alice" in text and "30" in text
        assert "bob" in text and "42" in text


async def test_query_rejects_write(db: Path) -> None:
    server = build_server(db)
    async with in_memory_session(server) as s:
        out = await call_tool(s, "query", sql="DELETE FROM users")
        assert out.isError is True or "rejected" in (out.content[0].text or "").lower()


async def test_describe_rejects_invalid_name(db: Path) -> None:
    server = build_server(db)
    async with in_memory_session(server) as s:
        out = await call_tool(s, "describe_table", name="users; DROP")
        assert out.isError is True or "invalid" in (out.content[0].text or "").lower()
