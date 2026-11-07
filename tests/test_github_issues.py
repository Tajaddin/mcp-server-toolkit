"""github-issues server tests, with GitHub replaced by a recording fake."""

from __future__ import annotations

import httpx
import pytest

from mcp_server_toolkit import call_tool, in_memory_session
from mcp_server_toolkit.servers import github_issues


@pytest.fixture
def requested(monkeypatch) -> list[httpx.URL]:
    urls: list[httpx.URL] = []

    def handler(request: httpx.Request) -> httpx.Response:
        urls.append(request.url)
        if request.url.path.endswith("/comments") or request.url.path.endswith("/issues"):
            return httpx.Response(200, json=[])
        return httpx.Response(200, json={"number": 1, "state": "open", "title": "t", "body": "b"})

    monkeypatch.setattr(
        github_issues, "_client", lambda: httpx.Client(transport=httpx.MockTransport(handler))
    )
    return urls


BAD_SEGMENTS = ["..", ".", "", "a/b", "../user", "user/repos?x=", "a#b", "a b", "%2e%2e"]


@pytest.mark.parametrize("field", ["owner", "repo"])
@pytest.mark.parametrize("value", BAD_SEGMENTS)
@pytest.mark.parametrize(
    ("tool", "extra"), [("get_issue", {"number": 1}), ("list_repo_issues", {})]
)
async def test_repo_tools_reject_unsafe_path_segments(requested, tool, extra, field, value) -> None:
    arguments = {"owner": "octocat", "repo": "hello-world", **extra, field: value}
    async with in_memory_session(github_issues.build_server()) as s:
        out = await call_tool(s, tool, **arguments)
    assert out.isError is True
    assert f"invalid {field}" in out.content[0].text
    assert requested == []


async def test_repo_tools_accept_real_names(requested) -> None:
    async with in_memory_session(github_issues.build_server()) as s:
        issue = await call_tool(s, "get_issue", owner="octo-cat", repo="hello_world.js", number=7)
        listing = await call_tool(s, "list_repo_issues", owner="octo-cat", repo="hello_world.js")
    assert not issue.isError and not listing.isError
    assert [u.path for u in requested] == [
        "/repos/octo-cat/hello_world.js/issues/7",
        "/repos/octo-cat/hello_world.js/issues/7/comments",
        "/repos/octo-cat/hello_world.js/issues",
    ]
