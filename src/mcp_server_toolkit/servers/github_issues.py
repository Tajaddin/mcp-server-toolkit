"""MCP server: read-only GitHub issue search over the public REST API."""

from __future__ import annotations

import argparse
import os
from typing import Any

import httpx

from mcp_server_toolkit.base import ToolError, ToolkitServer, register_tool

GITHUB_API = "https://api.github.com"


def _client() -> httpx.Client:
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "mcp-server-toolkit/0.1"}
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return httpx.Client(timeout=15.0, headers=headers)


def _format_issue(issue: dict[str, Any]) -> str:
    state = issue.get("state", "?")
    num = issue.get("number")
    title = issue.get("title", "")
    user = (issue.get("user") or {}).get("login", "?")
    url = issue.get("html_url", "")
    return f"#{num} [{state}] {title}\n  by @{user}\n  {url}"


def build_server() -> ToolkitServer:
    server = ToolkitServer(
        name="github-issues",
        description="Read-only GitHub issue search over the public REST API.",
    )

    @register_tool(
        server,
        name="search_issues",
        description=(
            "Search GitHub issues across all public repos using GitHub's query "
            "syntax. Returns up to ``limit`` results, newest first."
        ),
    )
    def search_issues(query: str, limit: int = 10) -> str:
        if not query.strip():
            raise ToolError("query must be non-empty")
        limit = max(1, min(limit, 50))
        with _client() as client:
            resp = client.get(
                f"{GITHUB_API}/search/issues",
                params={"q": query, "per_page": limit, "sort": "created", "order": "desc"},
            )
        if resp.status_code != 200:
            raise ToolError(f"GitHub returned {resp.status_code}: {resp.text[:200]}")
        items = resp.json().get("items", []) or []
        if not items:
            return "(no results)"
        return "\n\n".join(_format_issue(it) for it in items)

    @register_tool(
        server,
        name="get_issue",
        description="Get one issue's title, state, body, and first 5 comments.",
    )
    def get_issue(owner: str, repo: str, number: int) -> str:
        with _client() as client:
            r1 = client.get(f"{GITHUB_API}/repos/{owner}/{repo}/issues/{number}")
            if r1.status_code != 200:
                raise ToolError(f"GitHub returned {r1.status_code}: {r1.text[:200]}")
            issue = r1.json()
            r2 = client.get(
                f"{GITHUB_API}/repos/{owner}/{repo}/issues/{number}/comments",
                params={"per_page": 5},
            )
            comments = r2.json() if r2.status_code == 200 else []
        body = issue.get("body") or "(no body)"
        comment_lines = []
        for c in comments[:5]:
            user = (c.get("user") or {}).get("login", "?")
            comment_lines.append(f"@{user}: {(c.get('body') or '').strip()[:300]}")
        return (
            f"#{issue.get('number')} [{issue.get('state')}] {issue.get('title','')}\n"
            f"by @{(issue.get('user') or {}).get('login','?')}\n\n"
            f"{body[:1500]}\n\n--- comments ({len(comments)}) ---\n"
            + "\n".join(comment_lines)
        )

    @register_tool(
        server,
        name="list_repo_issues",
        description="List open issues on a repo, newest first.",
    )
    def list_repo_issues(owner: str, repo: str, limit: int = 10) -> str:
        limit = max(1, min(limit, 50))
        with _client() as client:
            resp = client.get(
                f"{GITHUB_API}/repos/{owner}/{repo}/issues",
                params={"state": "open", "per_page": limit, "sort": "created", "direction": "desc"},
            )
        if resp.status_code != 200:
            raise ToolError(f"GitHub returned {resp.status_code}: {resp.text[:200]}")
        issues = resp.json()
        issues = [it for it in issues if "pull_request" not in it]
        if not issues:
            return "(no open issues)"
        return "\n\n".join(_format_issue(it) for it in issues)

    return server


def main() -> None:
    parser = argparse.ArgumentParser(description="MCP server: github-issues")
    parser.parse_args()
    server = build_server()
    server.run()


if __name__ == "__main__":
    main()
