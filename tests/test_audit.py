"""The audit log is the only control in the v1 pilot (ADR-003), so it gets the
tests. Each of these asserts a property someone will eventually be asked to
prove in a review.
"""

from __future__ import annotations

import pytest

from frontline_agent.audit.log import AuditRecord, read_local_audit
from frontline_agent.connectors.base import DataClass, Risk
from frontline_agent.connectors.registry import get_registry


def _record(data_class: DataClass, args: dict) -> AuditRecord:
    return AuditRecord.build(
        session_id="s", principal="U1", connector="c", tool="t",
        risk=Risk.READ, data_class=data_class, provider="p",
        args=args, result={"secret": "value"}, error=None, duration_ms=1,
    )


def test_regulated_calls_omit_arguments_and_results():
    """A FERPA review must not find student data inside the audit table."""
    record = _record(DataClass.REGULATED, {"student_id": "12345"})
    assert record.args is None
    assert record.result_summary is None
    # Volume is still observable — you can see that data moved, not what it was.
    assert record.result_bytes > 0


def test_non_regulated_calls_retain_arguments():
    record = _record(DataClass.INTERNAL, {"jql": "project = ABS"})
    assert record.args == {"jql": "project = ABS"}
    assert record.result_summary is not None


def test_args_digest_is_stable_and_present_even_when_redacted():
    """Identical calls correlate across records without storing the arguments."""
    a = _record(DataClass.REGULATED, {"student_id": "12345"})
    b = _record(DataClass.REGULATED, {"student_id": "12345"})
    c = _record(DataClass.REGULATED, {"student_id": "99999"})
    assert a.args_digest == b.args_digest != c.args_digest


def test_record_separates_principal_from_workload_identity():
    """The whole argument in ADR-001: acting *for* someone is not acting *as* them."""
    record = _record(DataClass.INTERNAL, {})
    assert record.principal == "U1"
    assert record.workload_identity == "frontline-cpo-agent"


@pytest.mark.asyncio
async def test_every_tool_call_writes_exactly_one_record(tmp_path, monkeypatch):
    from frontline_agent.audit import log as log_module
    from frontline_agent.config import get_settings

    path = tmp_path / "audit.jsonl"
    monkeypatch.setattr(log_module, "_log", log_module.JsonlAuditLog(str(path)))
    get_settings.cache_clear()

    registry = get_registry()
    await registry.invoke(
        "analytics", "list_metrics", {}, session_id="s", principal="U1"
    )
    assert len(read_local_audit(str(path))) == 1


@pytest.mark.asyncio
async def test_failed_calls_are_still_recorded(tmp_path, monkeypatch):
    """A tool that raises is exactly the call you most want in the log."""
    from frontline_agent.audit import log as log_module

    path = tmp_path / "audit.jsonl"
    monkeypatch.setattr(log_module, "_log", log_module.JsonlAuditLog(str(path)))

    registry = get_registry()
    with pytest.raises(ValueError):
        await registry.invoke(
            "salesforce", "soql", {"query": "DELETE FROM Account"},
            session_id="s", principal="U1",
        )
    records = read_local_audit(str(path))
    assert len(records) == 1
    assert records[0]["error"].startswith("ValueError")
