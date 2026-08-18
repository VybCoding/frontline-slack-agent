"""Slack rendering.

The interface is not "a chat box that happens to be in Slack." Slack shipped a
real agent surface in 2026 and this uses it:

  assistant.threads.setStatus     a live status line while the agent thinks,
                                  with the actual current step as its text
  chat.startStream / appendStream a streamed reply with task_display_mode set to
  / stopStream                    `timeline`, so tool calls render as a visible
                                  sequence of steps rather than a spinner
  setSuggestedPrompts             up to four openers, refreshed per surface

Why the timeline matters more than it sounds: the pilot runs unrestricted, so the
principal's ability to see what the agent is doing *while* it does it is the only
real-time check that exists. A streamed timeline on a phone is a working
interrupt mechanism. A spinner is not.

Newer streaming methods are called through `api_call` rather than typed helpers
so this does not break on an older slack_sdk. Swap to the typed methods once you
pin a version that has them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import structlog
from slack_sdk.web.async_client import AsyncWebClient

log = structlog.get_logger()

_MAX_CHUNK = 3500


@dataclass
class Stream:
    """A streamed agent reply, rendered as a Slack timeline."""

    client: AsyncWebClient
    channel: str
    thread_ts: str
    recipient_user_id: str
    _ts: str | None = field(default=None, init=False)
    _fallback: list[str] = field(default_factory=list, init=False)

    async def start(self) -> None:
        try:
            response = await self.client.api_call(
                "chat.startStream",
                json={
                    "channel": self.channel,
                    "thread_ts": self.thread_ts,
                    "recipient_user_id": self.recipient_user_id,
                    "task_display_mode": "timeline",
                },
            )
            self._ts = response.get("ts")
        except Exception as exc:
            # Workspace not entitled for streaming, or an older API surface.
            # Fall back to a single post at the end; the agent still works.
            log.debug("stream_unavailable", error=str(exc))
            self._ts = None

    async def step(self, label: str, detail: str = "") -> None:
        """Render one timeline entry — a tool call about to happen."""
        text = f"{label}: {detail}" if detail else label
        await self._append(text[:256], kind="task")

    async def text(self, chunk: str) -> None:
        await self._append(chunk, kind="markdown")

    async def _append(self, content: str, *, kind: str) -> None:
        if self._ts is None:
            self._fallback.append(content)
            return
        payload: dict[str, Any] = {"channel": self.channel, "ts": self._ts}
        if kind == "task":
            payload["chunks"] = [{"type": "task", "text": content}]
        else:
            payload["markdown_text"] = content[:_MAX_CHUNK]
        try:
            await self.client.api_call("chat.appendStream", json=payload)
        except Exception as exc:
            log.debug("stream_append_failed", error=str(exc))
            self._fallback.append(content)

    async def stop(self, blocks: list[dict[str, Any]] | None = None) -> None:
        if self._ts is not None:
            try:
                await self.client.api_call(
                    "chat.stopStream",
                    json={"channel": self.channel, "ts": self._ts},
                )
                if blocks:
                    await self.client.chat_postMessage(
                        channel=self.channel, thread_ts=self.thread_ts, blocks=blocks,
                        text="Action required",
                    )
                return
            except Exception as exc:
                log.debug("stream_stop_failed", error=str(exc))

        body = "\n".join(self._fallback) or "_(no response)_"
        await self.client.chat_postMessage(
            channel=self.channel,
            thread_ts=self.thread_ts,
            text=body[:_MAX_CHUNK],
            blocks=blocks,
        )


async def set_status(client: AsyncWebClient, channel: str, thread_ts: str, status: str) -> None:
    """Set the thinking indicator. Empty string clears it."""
    try:
        await client.api_call(
            "assistant.threads.setStatus",
            json={"channel_id": channel, "thread_ts": thread_ts, "status": status},
        )
    except Exception as exc:
        log.debug("set_status_failed", error=str(exc))


async def set_suggested_prompts(
    client: AsyncWebClient, channel: str, thread_ts: str, prompts: list[tuple[str, str]]
) -> None:
    """Seed up to four openers. Slack caps this at four; extras are dropped."""
    try:
        await client.api_call(
            "assistant.threads.setSuggestedPrompts",
            json={
                "channel_id": channel,
                "thread_ts": thread_ts,
                "prompts": [{"title": t, "message": m} for t, m in prompts[:4]],
            },
        )
    except Exception as exc:
        log.debug("set_suggested_prompts_failed", error=str(exc))


async def set_title(client: AsyncWebClient, channel: str, thread_ts: str, title: str) -> None:
    try:
        await client.api_call(
            "assistant.threads.setTitle",
            json={"channel_id": channel, "thread_ts": thread_ts, "title": title[:120]},
        )
    except Exception as exc:
        log.debug("set_title_failed", error=str(exc))
