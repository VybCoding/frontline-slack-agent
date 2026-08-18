"""Contract tests for the connector layer.

These are the tests that keep the registry honest as Frontline adds systems it
has not told us about yet.
"""

from __future__ import annotations

import pytest

from frontline_agent.connectors.base import DataClass, Risk
from frontline_agent.connectors.registry import get_registry


def test_every_tool_declares_risk_and_data_class():
    """Enforced here rather than by convention, because the labels are what a
    future control layer will key on. A tool with no label is invisible to it."""
    for connector in get_registry().connectors:
        assert connector.tools, f"{connector.name} registered no tools"
        for spec in connector.tools:
            assert isinstance(spec.risk, Risk)
            assert isinstance(spec.data_class, DataClass)
            assert spec.description.strip()
            assert spec.input_schema.get("type") == "object"


def test_analytics_is_read_only_by_construction():
    """A CPO asking about adoption wants an interpretation, not a mutation."""
    analytics = next(c for c in get_registry().connectors if c.name == "analytics")
    assert all(spec.risk is Risk.READ for spec in analytics.tools)


def test_salesforce_tools_are_all_regulated():
    """Customer records sit adjacent to student data; the label drives redaction."""
    sf = next(c for c in get_registry().connectors if c.name == "salesforce")
    assert all(spec.data_class is DataClass.REGULATED for spec in sf.tools)


def test_gateway_target_marks_read_tools_read_only():
    """readOnlyHint is what an MCP client uses to decide whether to prompt.
    Getting it wrong means either nuisance prompts or silent writes."""
    targets = get_registry().as_gateway_targets()["targets"]
    tools = [t for target in targets for t in target["tools"]]
    assert tools
    for tool in tools:
        expected = tool["annotations"]["x-frontline-risk"] == "read"
        assert tool["annotations"]["readOnlyHint"] is expected


@pytest.mark.asyncio
async def test_soql_rejects_non_select():
    registry = get_registry()
    with pytest.raises(ValueError):
        await registry.invoke(
            "salesforce", "soql", {"query": "UPDATE Account SET Name='x'"},
            session_id="s", principal="U1",
        )


@pytest.mark.asyncio
async def test_local_mode_never_touches_the_network(monkeypatch):
    """The demo must be runnable on a plane. If a fixture is missing the call
    fails loudly rather than silently reaching for the internet."""
    import httpx

    def explode(*args, **kwargs):
        raise AssertionError("local mode attempted a network call")

    monkeypatch.setattr(httpx.AsyncClient, "request", explode)
    result = await get_registry().invoke(
        "atlassian", "search_issues", {"jql": "project = ABS"},
        session_id="s", principal="U1",
    )
    assert result["total"] == 4
