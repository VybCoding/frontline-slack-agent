"""The audit log.

The pilot runs unrestricted (ADR-003), which means this file is the only control
in the system. It is therefore written as a control, not as logging: append-only,
structured, complete, and capturing enough that a reviewer six weeks from now can
answer "what did this thing actually do, on whose authority, to what data?"
without reading a transcript.

Three things are recorded that ordinary tool logging leaves out:

  principal + workload    who it acted for AND what identity it acted as. Those
                          are different, and the distinction is the whole
                          argument in docs/03-identity-and-access.md.
  data_class              so exposure can be measured by sensitivity tier rather
                          than by call count.
  args_digest             arguments are hashed rather than stored when the tool
                          is labelled REGULATED, so the log itself never becomes
                          a secondary store of student data.

Retention and access to this table are a compliance decision, not an engineering
one — see docs/open-questions.md.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ..config import get_settings
from ..connectors.base import DataClass, Risk

_MAX_RESULT_SUMMARY = 512


@dataclass(frozen=True, slots=True)
class AuditRecord:
    record_id: str
    timestamp: str
    session_id: str
    principal: str
    workload_identity: str
    connector: str
    tool: str
    risk: str
    data_class: str
    provider: str | None
    args_digest: str
    args: dict[str, Any] | None
    result_summary: str | None
    result_bytes: int
    error: str | None
    duration_ms: int

    @classmethod
    def build(
        cls,
        *,
        session_id: str,
        principal: str,
        connector: str,
        tool: str,
        risk: Risk,
        data_class: DataClass,
        provider: str | None,
        args: dict[str, Any],
        result: Any,
        error: str | None,
        duration_ms: int,
    ) -> AuditRecord:
        settings = get_settings()
        serialized = json.dumps(args, sort_keys=True, default=str)
        regulated = data_class is DataClass.REGULATED

        rendered = "" if result is None else json.dumps(result, default=str)

        return cls(
            record_id=str(uuid.uuid4()),
            timestamp=datetime.now(UTC).isoformat(),
            session_id=session_id,
            principal=principal,
            workload_identity=settings.agentcore_workload_identity,
            connector=connector,
            tool=tool,
            risk=risk.value,
            data_class=data_class.value,
            provider=provider,
            args_digest=hashlib.sha256(serialized.encode()).hexdigest()[:16],
            # Regulated calls record the shape of the request, never its content.
            args=None if regulated else args,
            result_summary=None if regulated else rendered[:_MAX_RESULT_SUMMARY] or None,
            result_bytes=len(rendered),
            error=error,
            duration_ms=duration_ms,
        )


class AuditLog:
    async def write(self, record: AuditRecord) -> None:  # pragma: no cover - interface
        raise NotImplementedError


class JsonlAuditLog(AuditLog):
    """Local mode. One JSON object per line, appended, never rewritten."""

    def __init__(self, path: str) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)

    async def write(self, record: AuditRecord) -> None:
        with self._path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(asdict(record), default=str) + "\n")


class DynamoAuditLog(AuditLog):
    """AWS mode.

    Partition on session so a conversation reads back in order; the table is
    configured write-only for the agent's execution role (PutItem, no
    UpdateItem/DeleteItem) so the agent cannot edit its own history. A stream is
    enabled for archival to S3; the delivery itself is not wired yet, because the
    archive format depends on a retention decision nobody has made.
    See infra/stacks/audit_stack.py and docs/open-questions.md.
    """

    def __init__(self, table_name: str) -> None:
        import boto3

        self._table = boto3.resource("dynamodb").Table(table_name)

    async def write(self, record: AuditRecord) -> None:
        item = {k: v for k, v in asdict(record).items() if v is not None}
        self._table.put_item(Item=item)


_log: AuditLog | None = None


def get_audit_log() -> AuditLog:
    global _log
    if _log is None:
        settings = get_settings()
        _log = (
            JsonlAuditLog(settings.audit_local_path)
            if settings.is_local
            else DynamoAuditLog(settings.audit_table_name)
        )
    return _log


def read_local_audit(path: str | None = None) -> list[dict[str, Any]]:
    """Read back the local log. Used by tests and `make audit`."""
    target = Path(path or get_settings().audit_local_path)
    if not target.exists():
        return []
    return [json.loads(line) for line in target.read_text().splitlines() if line.strip()]
