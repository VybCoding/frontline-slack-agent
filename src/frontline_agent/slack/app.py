"""Slack event handling.

Bolt for Python in async mode. The same `build_app()` backs three entry points —
Socket Mode for local dev, a Lambda handler for AWS, and the demo script — so
behaviour cannot drift between what you test and what ships.

Three events matter:

  app_home_opened     the principal opened the agent DM. Seed suggested prompts.
  app_context_changed they navigated somewhere. Remember it; this is the ambient
                      context that makes "summarize this" work with no arguments.
  message.im          they said something. Run the agent.

Note what is absent: no slash commands, no @-mentions in channels. The brief said
conversational, phone-first, no CLI. A slash command with flags is a CLI wearing
a Slack costume.
"""

from __future__ import annotations

import structlog
from slack_bolt.async_app import AsyncApp

from ..agent.core import Agent, AgentEvent
from ..config import get_settings
from . import blocks, surface

log = structlog.get_logger()

# Last-known surface per user, populated by app_context_changed. In AWS mode this
# should be a DynamoDB item with a TTL rather than process memory — a Lambda that
# scales out will not share this dict. Flagged in docs/open-questions.md.
_context: dict[str, dict[str, str]] = {}


def build_app() -> AsyncApp:
    settings = get_settings()
    app = AsyncApp(
        token=settings.slack_bot_token or "xoxb-local",
        signing_secret=settings.slack_signing_secret or "local",
        # Bolt re-verifies signatures; in AWS the edge Lambda has already done it.
        request_verification_enabled=bool(settings.slack_signing_secret),
        process_before_response=True,
    )

    @app.event("app_home_opened")
    async def on_home_opened(event, client):
        if event.get("tab") != "messages":
            return
        await surface.set_suggested_prompts(
            client, event["channel"], event.get("thread_ts", ""), blocks.DEFAULT_PROMPTS
        )

    @app.event("app_context_changed")
    async def on_context_changed(event, context):
        user = event.get("user_id") or context.get("user_id", "")
        payload = event.get("context", {})
        _context[user] = {
            "channel_id": payload.get("channel_id", ""),
            "thread_ts": payload.get("thread_ts", ""),
            "team_id": payload.get("team_id", ""),
        }
        log.info("context_changed", user=user, **_context[user])

    @app.event("message")
    async def on_message(event, client, logger):
        if event.get("subtype") or event.get("bot_id"):
            return
        if event.get("channel_type") not in ("im", "channel", "group"):
            return

        user = event["user"]
        channel = event["channel"]
        thread_ts = event.get("thread_ts") or event["ts"]
        text = event.get("text", "").strip()
        if not text:
            return

        await run_turn(
            client=client,
            principal=user,
            channel=channel,
            thread_ts=thread_ts,
            text=text,
            slack_context=_context.get(user),
        )

    @app.action("authorize_provider")
    async def on_authorize(ack):
        await ack()

    return app


async def run_turn(
    *,
    client,
    principal: str,
    channel: str,
    thread_ts: str,
    text: str,
    slack_context: dict[str, str] | None = None,
) -> None:
    """One request → one streamed reply. Shared by every entry point."""
    agent = Agent(principal=principal, session_id=f"{channel}:{thread_ts}")
    stream = surface.Stream(
        client=client, channel=channel, thread_ts=thread_ts, recipient_user_id=principal
    )
    await stream.start()

    trailing: list[dict] = []
    first_text = True

    try:
        async for ev in agent.run(text, context=slack_context):
            await _render(ev, client, stream, channel, thread_ts, trailing)
            if ev.kind == "text" and first_text:
                first_text = False
                await surface.set_title(client, channel, thread_ts, text)
    finally:
        await surface.set_status(client, channel, thread_ts, "")
        await stream.stop(trailing or None)


async def _render(
    ev: AgentEvent, client, stream: surface.Stream, channel: str, thread_ts: str, trailing: list
) -> None:
    match ev.kind:
        case "status":
            await surface.set_status(client, channel, thread_ts, ev.text)
        case "tool_start":
            await stream.step(ev.tool, _summarize_args(ev.payload))
        case "text":
            await stream.text(ev.text)
        case "consent":
            trailing.extend(
                blocks.consent_prompt(ev.text, (ev.payload or {}).get("authorization_url", ""))
            )
        case "error":
            trailing.extend(blocks.error(ev.text))
        case _:
            pass


def _summarize_args(payload: dict | None) -> str:
    """One short line describing what a tool was called with.

    Kept deliberately terse — the timeline is read on a phone, and a wall of JSON
    defeats the point of showing the steps at all.
    """
    if not payload:
        return ""
    for key in ("query", "jql", "metric", "title", "summary", "page_id", "account_id"):
        if key in payload:
            return str(payload[key])[:120]
    return ", ".join(list(payload)[:3])
