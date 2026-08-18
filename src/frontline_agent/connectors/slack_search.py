"""Slack retrieval.

Deliberately not conversations.history. Since 29 May 2025 non-Marketplace apps
are throttled on conversations.history and conversations.replies to roughly one
request per minute returning fifteen messages — an internal app is by definition
non-Marketplace, so any design that pages through channel history to build
context will stall on the first real question.

Retrieval goes through search instead, which is both faster and correctly
scoped: search runs with the principal's user token and therefore returns only
what the principal can already see. The permission model is inherited rather
than reimplemented.

Where the Real-Time Search API is entitled for the workspace, point `_search` at
it instead — same contract, better recall, purpose-built for this. See
docs/open-questions.md.
"""

from __future__ import annotations

from typing import Any

from ..config import get_settings
from .base import Connector, DataClass, Risk

connector = Connector(
    name="slack",
    description="Search and read Slack as the principal, plus post on their behalf.",
    provider="slack-user",
)


def _client(token: str | None):
    from slack_sdk.web.async_client import AsyncWebClient

    settings = get_settings()
    return AsyncWebClient(token=token or settings.slack_user_token)


@connector.tool(
    "search",
    "Search Slack messages the principal has access to. Prefer this over reading "
    "channel history. Supports Slack search modifiers: in:#channel, from:@user, "
    "before:YYYY-MM-DD, after:YYYY-MM-DD.",
    {
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "count": {"type": "integer", "default": 20},
        },
        "required": ["query"],
    },
    risk=Risk.READ,
    data_class=DataClass.CONFIDENTIAL,
)
async def search(args: dict[str, Any], *, token: str | None) -> Any:
    settings = get_settings()
    if settings.is_local:
        from . import _transport

        return await _transport.call("slack", "search")

    response = await _client(token).search_messages(
        query=args["query"], count=args.get("count", 20)
    )
    matches = response.get("messages", {}).get("matches", [])
    return [
        {
            "channel": m.get("channel", {}).get("name"),
            "user": m.get("username"),
            "text": m.get("text"),
            "ts": m.get("ts"),
            "permalink": m.get("permalink"),
        }
        for m in matches
    ]


@connector.tool(
    "read_thread",
    "Read one specific thread by channel ID and parent timestamp. Rate-limited "
    "upstream — use for a thread the principal is looking at, not for bulk reading.",
    {
        "type": "object",
        "properties": {
            "channel_id": {"type": "string"},
            "thread_ts": {"type": "string"},
        },
        "required": ["channel_id", "thread_ts"],
    },
    risk=Risk.READ,
    data_class=DataClass.CONFIDENTIAL,
)
async def read_thread(args: dict[str, Any], *, token: str | None) -> Any:
    settings = get_settings()
    if settings.is_local:
        from . import _transport

        return await _transport.call("slack", "read_thread")

    response = await _client(token).conversations_replies(
        channel=args["channel_id"], ts=args["thread_ts"], limit=15
    )
    return [{"user": m.get("user"), "text": m.get("text"), "ts": m.get("ts")}
            for m in response.get("messages", [])]


@connector.tool(
    "post_message",
    "Post a message to a channel or DM as the principal. This is visible to other "
    "people immediately and cannot be unsent.",
    {
        "type": "object",
        "properties": {
            "channel": {"type": "string"},
            "text": {"type": "string"},
            "thread_ts": {"type": "string"},
        },
        "required": ["channel", "text"],
    },
    risk=Risk.WRITE_EXTERNAL,
    data_class=DataClass.CONFIDENTIAL,
)
async def post_message(args: dict[str, Any], *, token: str | None) -> Any:
    settings = get_settings()
    if settings.is_local:
        return {"ok": True, "simulated": True, **args}

    response = await _client(token).chat_postMessage(
        channel=args["channel"], text=args["text"], thread_ts=args.get("thread_ts")
    )
    return {"ok": response.get("ok"), "ts": response.get("ts")}
