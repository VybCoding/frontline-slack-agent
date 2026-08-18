"""Product analytics and BI.

This is the connector that answers the brief's real intent — "read-only GET
calls to help feed the AI information to help make sense of the data." It is
read-only by construction: there is no write tool here and there should not be
one. A CPO asking about adoption wants an interpretation, not a mutation.

Metrics come back aggregated. The upstream is expected to be a semantic layer
(Looker/Amplitude/Pendo) rather than a warehouse, so the aggregation boundary is
enforced by the tool the agent can reach, not by the agent's restraint.
"""

from __future__ import annotations

from typing import Any

from ..config import get_settings
from . import _transport
from .base import Connector, DataClass, Risk

connector = Connector(
    name="analytics",
    description="Product usage, adoption, and engagement metrics across Frontline modules.",
    provider=get_settings().analytics_provider_id,
)


@connector.tool(
    "metric",
    "Fetch one aggregated product metric over a time range, optionally split by a "
    "dimension such as module, district segment, or plan tier.",
    {
        "type": "object",
        "properties": {
            "metric": {
                "type": "string",
                "description": "e.g. weekly_active_users, feature_adoption_rate, time_to_value_days",
            },
            "start_date": {"type": "string", "description": "ISO date."},
            "end_date": {"type": "string", "description": "ISO date."},
            "group_by": {"type": "string"},
        },
        "required": ["metric", "start_date", "end_date"],
    },
    risk=Risk.READ,
    data_class=DataClass.CONFIDENTIAL,
)
async def metric(args: dict[str, Any], *, token: str | None) -> Any:
    settings = get_settings()
    return await _transport.call(
        "analytics",
        "metric",
        url=f"{settings.analytics_base_url}/v1/metrics/{args['metric']}",
        token=token,
        params={
            "start": args["start_date"],
            "end": args["end_date"],
            "group_by": args.get("group_by"),
        },
    )


@connector.tool(
    "list_metrics",
    "List the metrics available in the semantic layer, with definitions. Call this "
    "first when unsure what exists rather than guessing a metric name.",
    {"type": "object", "properties": {}},
    risk=Risk.READ,
    data_class=DataClass.INTERNAL,
)
async def list_metrics(args: dict[str, Any], *, token: str | None) -> Any:
    settings = get_settings()
    return await _transport.call(
        "analytics",
        "list_metrics",
        url=f"{settings.analytics_base_url}/v1/metrics",
        token=token,
    )
