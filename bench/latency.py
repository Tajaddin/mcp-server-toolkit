"""Measure tool round-trip latency over the in-memory MCP transport."""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mcp_server_toolkit import call_tool, in_memory_session
from mcp_server_toolkit.servers.filesystem_stats import build_server as build_fs
from mcp_server_toolkit.servers.sqlite_query import build_server as build_sql


def quantile(samples_ns: list[int], q: float) -> int:
    if not samples_ns:
        return 0
    s = sorted(samples_ns)
    return s[int(q * (len(s) - 1))]


def summary(label: str, samples_ns: list[int]) -> dict:
    return {
        "label": label,
        "n": len(samples_ns),
        "mean_us": round(sum(samples_ns) / len(samples_ns) / 1000, 2),
        "p50_us": round(quantile(samples_ns, 0.50) / 1000, 2),
        "p95_us": round(quantile(samples_ns, 0.95) / 1000, 2),
        "p99_us": round(quantile(samples_ns, 0.99) / 1000, 2),
        "max_us": round(max(samples_ns) / 1000, 2),
    }


async def bench_filesystem(n: int) -> dict:
    server = build_fs(Path(__file__).resolve().parents[1])
    samples: list[int] = []
    async with in_memory_session(server) as s:
        # warmup
        for _ in range(50):
            await call_tool(s, "list_directory", rel_path=".")
        for _ in range(n):
            t0 = time.perf_counter_ns()
            await call_tool(s, "list_directory", rel_path=".")
            samples.append(time.perf_counter_ns() - t0)
    return summary("filesystem.list_directory", samples)


async def bench_sqlite(n: int, tmpdb: Path) -> dict:
    import sqlite3

    conn = sqlite3.connect(tmpdb)
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS k (id INTEGER PRIMARY KEY, v TEXT);
        INSERT OR IGNORE INTO k VALUES (1, 'one'), (2, 'two'), (3, 'three');
        """
    )
    conn.close()
    server = build_sql(tmpdb)
    samples: list[int] = []
    async with in_memory_session(server) as s:
        for _ in range(50):
            await call_tool(s, "query", sql="SELECT * FROM k")
        for _ in range(n):
            t0 = time.perf_counter_ns()
            await call_tool(s, "query", sql="SELECT * FROM k")
            samples.append(time.perf_counter_ns() - t0)
    return summary("sqlite.query", samples)


async def main_async(args) -> int:
    fs = await bench_filesystem(args.n)
    tmp_db = Path("bench/_bench.db")
    sql = await bench_sqlite(args.n, tmp_db)
    if tmp_db.exists():
        try:
            tmp_db.unlink()
        except PermissionError:
            pass  # Windows file lock — gitignore handles it
    out = {
        "n_per_op": args.n,
        "results": [fs, sql],
        "p99_under_50ms": fs["p99_us"] < 50_000 and sql["p99_us"] < 50_000,
    }
    Path(args.out).write_text(json.dumps(out, indent=2), encoding="utf-8")

    print(f"{'op':<32} {'mean':>10} {'p50':>10} {'p95':>10} {'p99':>10} {'max':>10}  (us)")
    for r in (fs, sql):
        print(
            f"{r['label']:<32} {r['mean_us']:>10.2f} {r['p50_us']:>10.2f} "
            f"{r['p95_us']:>10.2f} {r['p99_us']:>10.2f} {r['max_us']:>10.2f}"
        )
    print(f"\nTarget: p99 < 50,000 µs (50 ms) for every op")
    print(f"Result: {'PASS' if out['p99_under_50ms'] else 'FAIL'}")
    print(f"Wrote {args.out}")
    return 0


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    except Exception:
        pass
    p = argparse.ArgumentParser()
    p.add_argument("-n", type=int, default=2000)
    p.add_argument("--out", type=str, default="bench/latency_results.json")
    args = p.parse_args()
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    sys.exit(main())
