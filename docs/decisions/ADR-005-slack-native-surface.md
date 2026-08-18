# ADR-005 — Use Slack's agent surface, not a chat box in Slack

**Status:** accepted · **Date:** 2026-08-18

## Context

"Slack as the interface, conversational, no CLI" is easy to satisfy badly: a bot
that accepts a message and posts a reply technically qualifies. Slack shipped a
purpose-built agent surface in 2026 that does considerably more, and the phone-
first constraint makes the difference material rather than cosmetic.

## Decision

Opt into the full surface.

| Capability | Why it earns its place here |
|---|---|
| `features.agent_view` | Dedicated agent DM, split view beside a channel, top-nav entry. Without it this is a bot in a DM. |
| `app_context_changed` | Tells the agent what the principal is *currently looking at*. "Summarize this and draft a reply" resolves with no arguments. Highest-leverage event on the platform. |
| `chat.startStream` + `task_display_mode: timeline` | Tool calls render as a live sequence. On a phone this is the difference between a spinner and a working interrupt. Given ADR-003, it is also the only real-time check that exists. |
| `assistant.threads.setStatus` | A status line carrying the actual current step, not "thinking…". |
| `setSuggestedPrompts` | Four openers. Solves cold start for an executive who will not compose a careful prompt on a phone. |
| `setTitle` | Threads become a navigable history instead of a wall of DMs. |
| Block Kit 2026 blocks | Cards, data tables, alerts. Structured output stays inside Slack — no companion web app to build, secure, and get reviewed. One fewer surface holding Frontline data. |
| No slash commands | A slash command with flags is a CLI wearing a Slack costume. The brief explicitly ruled that out. |

## Consequence worth flagging: the retrieval constraint

Since 29 May 2025, non-Marketplace apps are throttled on `conversations.history`
and `conversations.replies` to roughly **one request per minute returning fifteen
messages**. An internal app is non-Marketplace by definition and will never be
listed, so this applies permanently.

Any design that pages channel history to build context stalls on the first real
question. Retrieval therefore goes through **search** (`search:read`, user token),
which is faster and correctly scoped — it returns only what the principal can
already see, so the permission model is inherited rather than reimplemented.
`conversations.replies` is retained for the single specific thread the principal
is looking at, which is one call, not a crawl.

Where the **Real-Time Search API** is entitled for the workspace, point
`connectors/slack_search.py` at it — same contract, better recall, purpose-built
for exactly this. See `docs/open-questions.md`.

## Consequences

- Streaming methods are called via `api_call` rather than typed helpers so the
  app does not break on an older `slack_sdk`. Swap once a version is pinned.
- Every streaming path degrades to a single posted message if the workspace is
  not entitled. The agent works either way; it is just less pleasant to watch.
- Socket Mode for local dev only. Socket Mode apps cannot be Marketplace-listed,
  which is irrelevant for an app that is internal by design.
