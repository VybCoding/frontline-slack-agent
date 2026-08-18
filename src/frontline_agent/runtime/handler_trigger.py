"""Entry point for autonomous runs.

Invoked by EventBridge Scheduler (cron triggers) or EventBridge rules (event
triggers) with `{"trigger": "<name>"}`. Runs the agent unattended, then posts to
the principal's DM — unless the agent decided there was nothing worth saying, in
which case nothing is posted and the run is silent.

The thread it posts into is an ordinary DM thread, so his reply resumes the
normal interactive path with writes re-enabled. There is no separate approval
mechanism to build or maintain: presence *is* the authorization.
"""

from __future__ import annotations

import asyncio
from typing import Any

from slack_sdk.web.async_client import AsyncWebClient

from ..agent.core import Agent
from ..config import get_settings
from ..triggers.base import NOTHING_TO_REPORT
from ..triggers.catalog import find


def handler(event: dict[str, Any], _context: Any = None) -> dict[str, Any]:
    return asyncio.run(_run(event["trigger"]))


async def _run(trigger_name: str) -> dict[str, Any]:
    settings = get_settings()
    trigger = find(trigger_name)
    principal = settings.principal_slack_user_id

    agent = Agent(principal=principal, session_id=f"trigger:{trigger_name}")

    collected: list[str] = []
    async for ev in agent.run(trigger.instruction, unattended=True):
        if ev.kind == "text":
            collected.append(ev.text)
        elif ev.kind == "error":
            collected.append(f":warning: {ev.text}")

    body = "".join(collected).strip()

    if not body or NOTHING_TO_REPORT in body:
        return {"trigger": trigger_name, "posted": False, "reason": "nothing to report"}

    client = AsyncWebClient(token=settings.slack_bot_token)
    await client.chat_postMessage(
        channel=principal,
        text=body,
        blocks=[
            {"type": "section", "text": {"type": "mrkdwn", "text": body[:2900]}},
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": (
                            f"_{trigger.name} · you weren't asked, so I only looked. "
                            "Reply here and I can act._"
                        ),
                    }
                ],
            },
        ],
    )
    return {"trigger": trigger_name, "posted": True}
