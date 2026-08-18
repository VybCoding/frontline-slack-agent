"""Worker entry point.

Receives an already-verified Slack event envelope and runs the agent turn. Deploy
as a Lambda for short turns, or as the AgentCore Runtime entrypoint for long ones
— the function body is identical either way, which is the point.
"""

from __future__ import annotations

import asyncio
from typing import Any

from slack_sdk.web.async_client import AsyncWebClient

from ..config import get_settings
from ..slack.app import run_turn


def handler(payload: dict[str, Any], _context: Any = None) -> dict[str, Any]:
    asyncio.run(_process(payload))
    return {"ok": True}


async def _process(payload: dict[str, Any]) -> None:
    event = payload.get("event", {})
    if event.get("type") != "message" or event.get("bot_id") or event.get("subtype"):
        return

    settings = get_settings()
    client = AsyncWebClient(token=settings.slack_bot_token)

    await run_turn(
        client=client,
        principal=event["user"],
        channel=event["channel"],
        thread_ts=event.get("thread_ts") or event["ts"],
        text=event.get("text", ""),
        slack_context=None,
    )
