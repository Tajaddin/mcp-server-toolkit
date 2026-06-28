"""MCP server: Xquik X search and trends over the public REST API."""

from __future__ import annotations

import argparse
import os
from collections.abc import Callable
from typing import Any

import httpx

from mcp_server_toolkit.base import ToolError, ToolkitServer, register_tool

XQUIK_API = os.environ.get("XQUIK_API_URL", "https://xquik.com").rstrip("/")

ClientFactory = Callable[[], httpx.Client]


def _client() -> httpx.Client:
    api_key = os.environ.get("XQUIK_API_KEY")
    if not api_key:
        raise ToolError("Set XQUIK_API_KEY before calling Xquik tools.")

    return httpx.Client(
        timeout=30.0,
        headers={
            "Accept": "application/json",
            "User-Agent": "mcp-server-toolkit/0.1",
            "x-api-key": api_key,
        },
    )


def _clean_params(params: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in params.items() if value is not None}


def _request_json(client: httpx.Client, path: str, params: dict[str, Any]) -> dict[str, Any]:
    response = client.get(f"{XQUIK_API}{path}", params=_clean_params(params))
    if response.status_code != 200:
        raise ToolError(f"Xquik returned {response.status_code}: {response.text[:200]}")
    data = response.json()
    if not isinstance(data, dict):
        raise ToolError("Xquik returned an unexpected response shape.")
    return data


def _clamp(value: int, minimum: int, maximum: int) -> int:
    return max(minimum, min(value, maximum))


def _short(value: Any, limit: int = 220) -> str:
    text = "" if value is None else str(value).strip()
    if len(text) <= limit:
        return text
    return f"{text[: limit - 1]}..."


def _format_tweet(tweet: dict[str, Any]) -> str:
    author = tweet.get("author") if isinstance(tweet.get("author"), dict) else {}
    username = author.get("username") or "unknown"
    tweet_id = tweet.get("id") or "unknown"
    created_at = tweet.get("createdAt") or "unknown time"
    metrics = [
        f"likes={tweet[key]}"
        for key in ("likeCount", "retweetCount", "replyCount", "quoteCount")
        if tweet.get(key) is not None
    ]
    url = f"https://x.com/{username}/status/{tweet_id}" if username != "unknown" else ""
    parts = [
        f"{tweet_id} @{username} {created_at}",
        _short(tweet.get("text")),
    ]
    if metrics:
        parts.append(" ".join(metrics))
    if url:
        parts.append(url)
    return "\n".join(part for part in parts if part)


def _format_user(user: dict[str, Any]) -> str:
    username = user.get("username") or "unknown"
    name = user.get("name") or ""
    verified = " verified" if user.get("verified") is True else ""
    followers = f" followers={user['followersCount']}" if user.get("followersCount") is not None else ""
    return f"@{username} {name}{verified}{followers}".strip()


def _format_trend(trend: dict[str, Any]) -> str:
    rank = trend.get("rank") or "?"
    name = trend.get("name") or "(unnamed)"
    description = f" - {trend['description']}" if trend.get("description") else ""
    query = f" query={trend['query']}" if trend.get("query") else ""
    return f"{rank}. {name}{description}{query}"


def build_server(client_factory: ClientFactory = _client) -> ToolkitServer:
    server = ToolkitServer(
        name="xquik-search",
        description="Read X posts, users, and trends through Xquik's public REST API.",
    )

    @register_tool(
        server,
        name="search_tweets",
        description="Search X posts with Xquik. Set XQUIK_API_KEY before calling.",
    )
    def search_tweets(
        query: str,
        query_type: str = "Latest",
        limit: int = 10,
        cursor: str | None = None,
    ) -> str:
        if not query.strip():
            raise ToolError("query must be non-empty")
        if query_type not in {"Latest", "Top"}:
            raise ToolError("query_type must be Latest or Top")

        with client_factory() as client:
            data = _request_json(
                client,
                "/api/v1/x/tweets/search",
                {
                    "q": query,
                    "queryType": query_type,
                    "limit": _clamp(limit, 1, 50),
                    "cursor": cursor,
                },
            )
        tweets = data.get("tweets") or []
        if not tweets:
            return "(no tweets)"
        lines = [_format_tweet(tweet) for tweet in tweets[:50] if isinstance(tweet, dict)]
        if data.get("has_next_page") and data.get("next_cursor"):
            lines.append(f"next_cursor={data['next_cursor']}")
        return "\n\n".join(lines)

    @register_tool(
        server,
        name="search_users",
        description="Search X users with Xquik. Set XQUIK_API_KEY before calling.",
    )
    def search_users(query: str, cursor: str | None = None) -> str:
        if not query.strip():
            raise ToolError("query must be non-empty")

        with client_factory() as client:
            data = _request_json(
                client,
                "/api/v1/x/users/search",
                {"q": query, "cursor": cursor},
            )
        users = data.get("users") or []
        if not users:
            return "(no users)"
        lines = [_format_user(user) for user in users if isinstance(user, dict)]
        if data.get("has_next_page") and data.get("next_cursor"):
            lines.append(f"next_cursor={data['next_cursor']}")
        return "\n".join(lines)

    @register_tool(
        server,
        name="get_trends",
        description="Get X trends by WOEID with Xquik. Set XQUIK_API_KEY before calling.",
    )
    def get_trends(woeid: int = 1, count: int = 10) -> str:
        with client_factory() as client:
            data = _request_json(
                client,
                "/api/v1/x/trends",
                {"woeid": woeid, "count": _clamp(count, 1, 50)},
            )
        trends = data.get("trends") or []
        if not trends:
            return "(no trends)"
        return "\n".join(_format_trend(trend) for trend in trends if isinstance(trend, dict))

    return server


def main() -> None:
    parser = argparse.ArgumentParser(description="MCP server: xquik-search")
    parser.parse_args()
    server = build_server()
    server.run()


if __name__ == "__main__":
    main()
