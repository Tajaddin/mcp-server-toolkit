# mcp-server-toolkit

> Reusable framework for building **Model Context Protocol (MCP) servers** for Claude, plus four production-shaped example servers: filesystem-stats, github-issues, sqlite-query, xquik-search. In-memory test harness with **p99 tool round-trip = 8.2 ms** (target was 50 ms).

[![License](https://img.shields.io/badge/license-MIT-blue)](LICENSE) [![Tests](https://img.shields.io/badge/tests-12%20passing-brightgreen)](#tests) [![Python](https://img.shields.io/badge/python-3.10%2B-blue)]()

## What this is

MCP is Anthropic's standard for letting LLMs call tools running on your machine. Every MCP server starts with the same boilerplate: a `FastMCP` instance, a few tool decorators, a stdio entrypoint. This project bundles:

* A thin `ToolkitServer` wrapper with a tool description registry + uniform `ToolError` error-handling pattern
* An in-memory test harness so your tools are unit-testable via a real `ClientSession` — **no subprocess, no JSON-over-stdio flakiness**
* **Four example servers** ready to install:
  * `mcp-filesystem-stats` - sandboxed `list_directory` / `file_summary` / `find_files`
  * `mcp-github-issues` - read-only public GitHub issue search via REST
  * `mcp-sqlite-query` - read-only SQLite with write-statement rejection
  * `mcp-xquik-search` - X post, user, and trend research via Xquik

## Hero benchmark

In-memory tool round-trip latency over 2000 iterations on a single thread (filesystem `list_directory` on a small dir + sqlite `SELECT * FROM k`).

| Tool round-trip | Mean | p50 | p95 | **p99** | Max |
|---|---:|---:|---:|---:|---:|
| `filesystem.list_directory` | 4.02 ms | 3.80 ms | 5.81 ms | **8.21 ms** | 14.49 ms |
| `sqlite.query` | 4.08 ms | 3.78 ms | 6.61 ms | **8.69 ms** | 12.55 ms |

Target: every op's p99 < 50 ms. **PASS** (~6× under budget).

The in-memory transport is the same `ClientSession` Claude would use over stdio, just connected to the server via `mcp.shared.memory.create_connected_server_and_client_session`. Reproduce: `python bench/latency.py`.

## Quickstart

```bash
pip install -e ".[dev]"
```

```python
import asyncio
from pathlib import Path
from mcp_server_toolkit import call_tool, in_memory_session, list_tools
from mcp_server_toolkit.servers.filesystem_stats import build_server

async def main():
    server = build_server(Path("."))
    async with in_memory_session(server) as session:
        tools = await list_tools(session)
        print([t.name for t in tools])
        # ['list_directory', 'file_summary', 'find_files']

        result = await call_tool(session, "file_summary", rel_path="README.md")
        print(result.content[0].text)

asyncio.run(main())
```

Or run any of the example servers as a real MCP subprocess for Claude Desktop:

```bash
pip install -e .
# In Claude Desktop's mcp settings, add:
#   "command": "mcp-filesystem-stats",
#   "args": ["--root", "/path/to/sandbox"]
```

## Writing your own server

```python
from mcp_server_toolkit import ToolError, ToolkitServer, register_tool

server = ToolkitServer(name="my-server", description="example")

@register_tool(server, name="echo", description="Return the input string unchanged.")
def echo(text: str) -> str:
    if not text:
        raise ToolError("text must be non-empty")
    return text

if __name__ == "__main__":
    server.run()
```

Tool authors:

* Return a plain `str` for success.
* Raise `ToolError("...")` for user-visible failures (the SDK emits `isError: true`).
* Let any other exception bubble — FastMCP turns it into a generic server error.

## Four example servers

### `filesystem-stats`

Sandboxed read-only filesystem access — confined to a `--root` you supply at launch. Path-traversal attempts (`../../etc`) are rejected.

| Tool | Args | What it returns |
|---|---|---|
| `list_directory` | `rel_path` | TSV: name, type, size_bytes, mtime |
| `file_summary` | `rel_path` | size, suffix, line count (for ≤1MB text), mode bits |
| `find_files` | `pattern`, `max_depth`, `limit` | matching relative paths under the root |

### `github-issues`

Read-only public-repo issue search. Unauth GitHub allows 60 req/hr; set `GITHUB_TOKEN` to lift to 5000.

| Tool | Args | What it returns |
|---|---|---|
| `search_issues` | `query`, `limit` | top N issues matching GitHub search syntax |
| `get_issue` | `owner`, `repo`, `number` | title, body, first 5 comments |
| `list_repo_issues` | `owner`, `repo`, `limit` | open issues newest-first |

### `sqlite-query`

Strict read-only SQLite. Only `SELECT` / `WITH ... SELECT` accepted; statement chaining via `;` is rejected. Connection opens in `mode=ro` so even a regex bypass can't write.

| Tool | Args | What it returns |
|---|---|---|
| `list_tables` | — | user tables (excludes `sqlite_*`) |
| `describe_table` | `name` | columns + types + PK marker |
| `query` | `sql` | TSV of up to 100 rows |

### `xquik-search`

Read X posts, users, and trends through Xquik's public REST API. Set `XQUIK_API_KEY` before calling tools.

| Tool | Args | What it returns |
|---|---|---|
| `search_tweets` | `query`, `query_type`, `limit`, `cursor` | matching posts plus pagination cursor |
| `search_users` | `query`, `cursor` | matching profiles plus pagination cursor |
| `get_trends` | `woeid`, `count` | trending topics for a region |

## Tests

```bash
pip install -e ".[dev]"
pytest -q
```

```
12 passed
```

Each server has an in-memory test suite that exercises:
* tool listing (advertised tools match the registry)
* happy-path tool calls
* error paths (path escape, invalid table name, write statement, missing file)

## Project layout

```
.
├── src/mcp_server_toolkit/
│   ├── __init__.py
│   ├── base.py             # ToolkitServer + ToolError + register_tool decorator
│   ├── testing.py          # in_memory_session, list_tools, call_tool
│   └── servers/
│       ├── filesystem_stats.py
│       ├── github_issues.py
│       └── sqlite_query.py
├── tests/                  # pytest-asyncio cases
└── bench/
    ├── latency.py
    └── latency_results.json
```

## Limitations

**Resource and prompt support not yet wrapped.** MCP has three primitive types (tools, resources, prompts). The toolkit only wraps tools right now — adding resources/prompts is straightforward but not yet done.

**No multi-server orchestrator.** Each example is a standalone server. A natural v0.2 would be a "router" that aggregates multiple toolkit servers under a single MCP endpoint.

**`github_issues` is rate-limited without `GITHUB_TOKEN`.** Heavy use during a Claude session will hit the 60 req/hr unauth limit. Set the env var to use the 5000 req/hr authenticated tier.

## License

MIT — see [LICENSE](LICENSE).
