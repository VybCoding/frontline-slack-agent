"""Jira + Confluence.

Chosen as a first connector because two of the four things the CPO asked for land
here directly: "draft documents" is Confluence, and "delegate work to the teams
that own it" is Jira. Both are also low-regulatory-risk, which makes this the
right place to prove the pattern before pointing it at anything student-facing.
"""

from __future__ import annotations

from typing import Any

from ..config import get_settings
from . import _transport
from .base import Connector, DataClass, Risk

connector = Connector(
    name="atlassian",
    description="Jira issues and Confluence pages for the Frontline product org.",
    provider=get_settings().atlassian_provider_id,
)


@connector.tool(
    "search_issues",
    "Search Jira with a JQL query. Use for roadmap state, sprint contents, "
    "blockers, and anything scoped to a team or epic.",
    {
        "type": "object",
        "properties": {
            "jql": {"type": "string", "description": "JQL query string."},
            "limit": {"type": "integer", "default": 25},
        },
        "required": ["jql"],
    },
    risk=Risk.READ,
    data_class=DataClass.INTERNAL,
)
async def search_issues(args: dict[str, Any], *, token: str | None) -> Any:
    settings = get_settings()
    return await _transport.call(
        "atlassian",
        "search_issues",
        url=f"{settings.atlassian_site_url}/rest/api/3/search",
        token=token,
        params={"jql": args["jql"], "maxResults": args.get("limit", 25)},
    )


@connector.tool(
    "get_page",
    "Fetch a Confluence page by ID, including its body as storage-format HTML.",
    {
        "type": "object",
        "properties": {"page_id": {"type": "string"}},
        "required": ["page_id"],
    },
    risk=Risk.READ,
    data_class=DataClass.INTERNAL,
)
async def get_page(args: dict[str, Any], *, token: str | None) -> Any:
    settings = get_settings()
    return await _transport.call(
        "atlassian",
        "get_page",
        url=f"{settings.atlassian_site_url}/wiki/api/v2/pages/{args['page_id']}",
        token=token,
        params={"body-format": "storage"},
    )


@connector.tool(
    "create_page",
    "Create a Confluence page. Use for drafting specs, briefs, and summaries. "
    "Always place drafts in the principal's personal space unless told otherwise.",
    {
        "type": "object",
        "properties": {
            "space_key": {"type": "string"},
            "title": {"type": "string"},
            "body_html": {"type": "string", "description": "Confluence storage format."},
            "parent_id": {"type": "string"},
        },
        "required": ["space_key", "title", "body_html"],
    },
    risk=Risk.WRITE_INTERNAL,
    data_class=DataClass.INTERNAL,
)
async def create_page(args: dict[str, Any], *, token: str | None) -> Any:
    settings = get_settings()
    return await _transport.call(
        "atlassian",
        "create_page",
        method="POST",
        url=f"{settings.atlassian_site_url}/wiki/api/v2/pages",
        token=token,
        json_body={
            "spaceId": args["space_key"],
            "title": args["title"],
            "parentId": args.get("parent_id"),
            "body": {"representation": "storage", "value": args["body_html"]},
        },
    )


@connector.tool(
    "create_issue",
    "Create a Jira issue. Use when the principal asks to file, assign, or track work.",
    {
        "type": "object",
        "properties": {
            "project_key": {"type": "string"},
            "summary": {"type": "string"},
            "description": {"type": "string"},
            "issue_type": {"type": "string", "default": "Task"},
            "assignee_account_id": {"type": "string"},
        },
        "required": ["project_key", "summary"],
    },
    risk=Risk.WRITE_INTERNAL,
    data_class=DataClass.INTERNAL,
)
async def create_issue(args: dict[str, Any], *, token: str | None) -> Any:
    settings = get_settings()
    return await _transport.call(
        "atlassian",
        "create_issue",
        method="POST",
        url=f"{settings.atlassian_site_url}/rest/api/3/issue",
        token=token,
        json_body={
            "fields": {
                "project": {"key": args["project_key"]},
                "summary": args["summary"],
                "description": args.get("description", ""),
                "issuetype": {"name": args.get("issue_type", "Task")},
            }
        },
    )
