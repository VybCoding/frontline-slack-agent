"""Unattended runs are the one place where the risk labels enforce something.

These tests assert that the enforcement is structural — the model does not
receive write tools during an autonomous run — rather than a prompt instruction
that a sufficiently confident model could talk itself out of.
"""

from __future__ import annotations

import pytest

from frontline_agent.agent.prompt import build_system_prompt
from frontline_agent.connectors.base import Risk
from frontline_agent.connectors.registry import get_registry
from frontline_agent.triggers.base import NOTHING_TO_REPORT, Trigger
from frontline_agent.triggers.catalog import TRIGGERS, enabled_triggers, find


def test_read_only_filter_removes_every_write_tool():
    registry = get_registry()
    all_specs = [spec for c in registry.connectors for spec in c.tools]
    writes = [s for s in all_specs if s.risk is not Risk.READ]

    assert writes, "test is vacuous if nothing can write"

    kept = registry.as_sdk_tools(session_id="s", principal="U1", read_only=True)
    dropped = len(all_specs) - len(kept)
    assert dropped == len(writes)


def test_interactive_runs_keep_every_tool():
    registry = get_registry()
    all_specs = [spec for c in registry.connectors for spec in c.tools]
    assert len(registry.as_sdk_tools(session_id="s", principal="U1")) == len(all_specs)


def test_unattended_prompt_carries_the_silence_sentinel():
    """A trigger that always posts becomes noise, and noise gets muted."""
    prompt = build_system_prompt(unattended=True)
    assert NOTHING_TO_REPORT in prompt
    assert NOTHING_TO_REPORT not in build_system_prompt()


def test_unattended_prompt_still_contains_the_base_brief():
    """The extension must not replace the operating brief."""
    prompt = build_system_prompt(unattended=True)
    assert "Chief Product Officer of Frontline Education" in prompt
    assert "FERPA" in prompt


def test_every_trigger_has_a_firing_condition():
    for trigger in TRIGGERS:
        assert trigger.schedule or trigger.event_pattern


def test_trigger_without_any_condition_is_rejected():
    with pytest.raises(ValueError):
        Trigger(name="broken", instruction="do a thing")


def test_disabled_triggers_are_not_deployed():
    """Inert by design beats silently broken — the escalation trigger waits on a
    Slack-to-EventBridge forwarder that does not exist yet."""
    assert any(not t.enabled for t in TRIGGERS)
    assert all(t.enabled for t in enabled_triggers())


def test_catalog_lookup():
    assert find("morning-brief").schedule
    with pytest.raises(KeyError):
        find("no-such-trigger")
