"""Salesforce.

The most regulated surface in the first connector set. Frontline's customers are
K-12 districts, so account and case records sit adjacent to student data and to
the contractual privacy terms districts sign. Every tool here is labelled
REGULATED, which means the audit log records the shape of each call but never
its contents (see audit/log.py).

Note the deliberate asymmetry: reads are broad, writes are narrow. Not because
of a policy gate — the pilot has none — but because a CPO's actual Salesforce
need is understanding, not data entry, and a tool that does not exist cannot be
called by mistake. Narrow the surface before you need to govern it.
"""

from __future__ import annotations

from typing import Any

from ..config import get_settings
from . import _transport
from .base import Connector, DataClass, Risk

connector = Connector(
    name="salesforce",
    description="Customer accounts, opportunities, and support cases for K-12 districts.",
    provider=get_settings().salesforce_provider_id,
)


@connector.tool(
    "soql",
    "Run a read-only SOQL query. Use for account health, renewal exposure, open "
    "cases by district, and opportunity pipeline. Never returns student-level records.",
    {
        "type": "object",
        "properties": {"query": {"type": "string", "description": "SOQL SELECT statement."}},
        "required": ["query"],
    },
    risk=Risk.READ,
    data_class=DataClass.REGULATED,
)
async def soql(args: dict[str, Any], *, token: str | None) -> Any:
    settings = get_settings()
    query = args["query"].strip()
    if not query.upper().startswith("SELECT"):
        raise ValueError("only SELECT statements are permitted through this tool")
    return await _transport.call(
        "salesforce",
        "soql",
        url=f"{settings.salesforce_instance_url}/services/data/v62.0/query",
        token=token,
        params={"q": query},
    )


@connector.tool(
    "get_account",
    "Fetch one district account record with its renewal date, ARR, and health score.",
    {
        "type": "object",
        "properties": {"account_id": {"type": "string"}},
        "required": ["account_id"],
    },
    risk=Risk.READ,
    data_class=DataClass.REGULATED,
)
async def get_account(args: dict[str, Any], *, token: str | None) -> Any:
    settings = get_settings()
    return await _transport.call(
        "salesforce",
        "get_account",
        url=f"{settings.salesforce_instance_url}/services/data/v62.0/sobjects/Account/{args['account_id']}",
        token=token,
    )
