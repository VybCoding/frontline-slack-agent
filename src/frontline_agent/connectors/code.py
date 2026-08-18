"""Source code — read-only.

This connector exists because of a specific finding: the machine being considered
for a self-hosted daemon has access to internal source. That is simultaneously
the strongest argument yet *for* the local route and the one that escalates its
risk from "broad" to "supply chain" (see docs/05-hosting-options.md §3.6).

The resolution is that the *benefit* is separable from the *mechanism*. A CPO
does not need shell access to a checkout in order to get grounded answers about
how a product actually behaves. They need to be able to read the code and search
it. That is this connector, and it is deliberately incapable of anything else.

## Why there are no write tools, and should not be

A tool that does not exist cannot be called by a confused model, a prompt
injection, or a bad afternoon. Given that this connector reaches the source of
software running in roughly ten thousand school districts, the cost of a write
capability is not "someone has to revert a commit" — it is that a successful
injection through any channel the agent reads (Slack, email, a Jira ticket, a
web page) becomes a path into the build.

Read-only removes that entirely rather than mitigating it.

## What this deliberately does not cover

Building a prototype. R3.2 asks for prototypes and reading code does not produce
one. The hosted answer is a sandbox — AgentCore Code Interpreter gives ephemeral,
isolated execution with a repo clone and no push credentials. That is a
deliberate next step, not an oversight; see docs/open-questions.md.
"""

from __future__ import annotations

from typing import Any

from ..config import get_settings
from . import _transport
from .base import Connector, DataClass, Risk

connector = Connector(
    name="code",
    description="Read and search internal source repositories. Read-only by design.",
    provider=get_settings().github_provider_id,
)

_API = "https://api.github.com"


@connector.tool(
    "search",
    "Search internal source code. Use when a question about product behaviour is "
    "better answered by what the code does than by what a ticket says it does. "
    "Supports GitHub code-search qualifiers such as repo:, path:, and language:.",
    {
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "limit": {"type": "integer", "default": 15},
        },
        "required": ["query"],
    },
    risk=Risk.READ,
    data_class=DataClass.CONFIDENTIAL,
)
async def search(args: dict[str, Any], *, token: str | None) -> Any:
    settings = get_settings()
    return await _transport.call(
        "code",
        "search",
        url=f"{_API}/search/code",
        token=token,
        params={
            "q": f"{args['query']} org:{settings.github_org}",
            "per_page": args.get("limit", 15),
        },
    )


@connector.tool(
    "read_file",
    "Read one file from a repository at a given ref. Use after search to see the "
    "actual implementation rather than reasoning from a snippet.",
    {
        "type": "object",
        "properties": {
            "repo": {"type": "string", "description": "Repository name, without the org prefix."},
            "path": {"type": "string"},
            "ref": {"type": "string", "default": "main"},
        },
        "required": ["repo", "path"],
    },
    risk=Risk.READ,
    data_class=DataClass.CONFIDENTIAL,
)
async def read_file(args: dict[str, Any], *, token: str | None) -> Any:
    settings = get_settings()
    return await _transport.call(
        "code",
        "read_file",
        url=f"{_API}/repos/{settings.github_org}/{args['repo']}/contents/{args['path']}",
        token=token,
        params={"ref": args.get("ref", "main")},
    )


@connector.tool(
    "recent_changes",
    "List recently merged pull requests for a repository. Use to answer 'what "
    "actually shipped' and to connect a behaviour change to the change that caused it.",
    {
        "type": "object",
        "properties": {
            "repo": {"type": "string"},
            "limit": {"type": "integer", "default": 20},
        },
        "required": ["repo"],
    },
    risk=Risk.READ,
    data_class=DataClass.INTERNAL,
)
async def recent_changes(args: dict[str, Any], *, token: str | None) -> Any:
    settings = get_settings()
    return await _transport.call(
        "code",
        "recent_changes",
        url=f"{_API}/repos/{settings.github_org}/{args['repo']}/pulls",
        token=token,
        params={"state": "closed", "sort": "updated", "direction": "desc",
                "per_page": args.get("limit", 20)},
    )
