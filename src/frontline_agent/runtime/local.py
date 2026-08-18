"""Local dev entry point — Socket Mode.

Socket Mode holds a WebSocket out to Slack, so there is no public endpoint and no
tunnel to run. That makes local development possible from behind a corporate
firewall, which matters if a Frontline engineer picks this up on a managed laptop.

Production does not use Socket Mode: it uses an HTTPS Request URL into API Gateway
(see runtime/handler_events.py). Socket Mode apps also cannot be listed on the
Slack Marketplace, which is irrelevant here — this app is internal by design and
will never be distributed.
"""

from __future__ import annotations

import asyncio
import logging

from ..config import get_settings
from ..slack.app import build_app


async def _run() -> None:
    from slack_bolt.adapter.socket_mode.async_handler import AsyncSocketModeHandler

    settings = get_settings()
    if not settings.slack_app_token:
        raise SystemExit(
            "SLACK_APP_TOKEN is required for Socket Mode.\n"
            "Create it under Basic Information -> App-Level Tokens with connections:write.\n"
            "To try the agent with no Slack workspace at all, run `make demo` instead."
        )

    handler = AsyncSocketModeHandler(build_app(), settings.slack_app_token)
    await handler.start_async()


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    asyncio.run(_run())


if __name__ == "__main__":
    main()
