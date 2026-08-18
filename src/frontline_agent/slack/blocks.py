"""Block Kit builders.

Slack's 2026 block set (alert, card, data table, container) means the agent's
non-prose output can be Slack-native — no companion web app to build, secure, and
get through review. That is a governance win as much as a UX one: one fewer
surface holding Frontline data.
"""

from __future__ import annotations

from typing import Any


def consent_prompt(provider: str, authorization_url: str) -> list[dict[str, Any]]:
    """Shown the first time the agent needs a system the principal has not yet
    authorized. Consent is per-provider and happens at the moment of need, so
    the principal sees the scope of access expanding as it expands rather than
    granting everything once at install."""
    return [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"I need your authorization for *{provider}* before I can do that.\n"
                    "This grants me your access to that system only — nothing else changes."
                ),
            },
        },
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": f"Authorize {provider}"},
                    "url": authorization_url,
                    "style": "primary",
                    "action_id": "authorize_provider",
                }
            ],
        },
    ]


def error(message: str) -> list[dict[str, Any]]:
    return [
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": f":warning: {message}"},
        }
    ]


def action_receipt(tool: str, risk: str, summary: str) -> list[dict[str, Any]]:
    """Posted after an irreversible action.

    The pilot has no pre-approval gate by decision. A receipt is the honest
    substitute: the principal cannot stop it beforehand, but they always know
    it happened, in the same place they asked for it.
    """
    icon = ":outbox_tray:" if risk == "write_external" else ":pencil2:"
    return [
        {
            "type": "context",
            "elements": [{"type": "mrkdwn", "text": f"{icon} `{tool}` — {summary}"}],
        }
    ]


DEFAULT_PROMPTS: list[tuple[str, str]] = [
    ("What needs me today", "What across Jira, Salesforce, and Slack actually needs my attention today?"),
    ("Brief me on an account", "Give me the current picture on Harbor County Schools — usage, cases, renewal risk."),
    ("Adoption trend", "How is feature adoption trending by district segment over the last three months?"),
    ("Draft from this thread", "Summarize the thread I'm looking at and draft a follow-up I can send."),
]
