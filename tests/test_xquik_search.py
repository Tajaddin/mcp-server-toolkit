"""xquik-search server tests via mocked HTTP."""

from __future__ import annotations

import httpx

from mcp_server_toolkit import call_tool, in_memory_session, list_tools
from mcp_server_toolkit.servers.xquik_search import build_server


def _factory(handler):
    def create_client() -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(handler))

    return create_client


async def test_list_tools_returns_three() -> None:
    server = build_server(_factory(lambda request: httpx.Response(500)))
    async with in_memory_session(server) as session:
        tools = await list_tools(session)
        names = {tool.name for tool in tools}
        assert names == {"search_tweets", "search_users", "get_trends"}


async def test_search_tweets_formats_results() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/x/tweets/search"
        assert request.url.params["q"] == "mcp"
        return httpx.Response(
            200,
            json={
                "tweets": [
                    {
                        "id": "123",
                        "text": "MCP example",
                        "createdAt": "2026-06-28T00:00:00Z",
                        "likeCount": 4,
                        "author": {"username": "xquik"},
                    }
                ],
                "has_next_page": True,
                "next_cursor": "cursor-1",
            },
        )

    server = build_server(_factory(handler))
    async with in_memory_session(server) as session:
        out = await call_tool(session, "search_tweets", query="mcp", limit=5)
        text = out.content[0].text
        assert "123 @xquik" in text
        assert "MCP example" in text
        assert "next_cursor=cursor-1" in text


async def test_search_users_formats_results() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/x/users/search"
        assert request.url.params["q"] == "xquik"
        return httpx.Response(
            200,
            json={
                "users": [
                    {
                        "username": "xquik",
                        "name": "Xquik",
                        "verified": True,
                        "followersCount": 100,
                    }
                ],
                "has_next_page": False,
                "next_cursor": None,
            },
        )

    server = build_server(_factory(handler))
    async with in_memory_session(server) as session:
        out = await call_tool(session, "search_users", query="xquik")
        assert "@xquik Xquik verified followers=100" in out.content[0].text


async def test_get_trends_formats_results() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/x/trends"
        assert request.url.params["woeid"] == "1"
        return httpx.Response(
            200,
            json={
                "trends": [
                    {
                        "rank": 1,
                        "name": "#AI",
                        "description": "Artificial intelligence discussions",
                        "query": "%23AI",
                    }
                ],
                "count": 1,
                "woeid": 1,
            },
        )

    server = build_server(_factory(handler))
    async with in_memory_session(server) as session:
        out = await call_tool(session, "get_trends", count=1)
        text = out.content[0].text
        assert "1. #AI" in text
        assert "query=%23AI" in text


async def test_tool_errors_are_user_visible() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "unauthenticated"})

    server = build_server(_factory(handler))
    async with in_memory_session(server) as session:
        out = await call_tool(session, "search_tweets", query="mcp")
        assert out.isError is True or "Xquik returned 401" in (out.content[0].text or "")
