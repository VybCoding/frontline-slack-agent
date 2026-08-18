"""Connector registry — the one place tools become visible to the agent.

Emits two projections of the same set:

  as_sdk_tools()      in-process tools for the Claude Agent SDK, wrapped so that
                      every invocation is credential-resolved and audited.
  as_gateway_targets() an AgentCore Gateway target manifest, so the same tools can
                      be published as MCP and reused by the other Product OS
                      agents rather than reimplemented per agent.

The second projection is the reason the registry exists as a separate layer
instead of tools being defined inline against the SDK. the CPO's requirement is
that his agent delegates to specialized agents; that only works if capability
definitions are shared infrastructure, not private to one agent's codebase.
"""

from __future__ import annotations

import time
from typing import Any

from ..audit.log import AuditRecord, get_audit_log
from ..identity.token_vault import get_token_vault
from .base import Connector, Risk, ToolSpec


class Registry:
    def __init__(self) -> None:
        self._connectors: dict[str, Connector] = {}

    def register(self, connector: Connector) -> None:
        if connector.name in self._connectors:
            raise ValueError(f"connector already registered: {connector.name}")
        self._connectors[connector.name] = connector

    @property
    def connectors(self) -> list[Connector]:
        return list(self._connectors.values())

    def find(self, connector: str, tool: str) -> ToolSpec:
        for spec in self._connectors[connector].tools:
            if spec.name == tool:
                return spec
        raise KeyError(f"no such tool: {connector}.{tool}")

    async def invoke(
        self,
        connector: str,
        tool: str,
        args: dict[str, Any],
        *,
        session_id: str,
        principal: str,
    ) -> Any:
        """Call a tool with credentials resolved and the call recorded.

        Nothing calls a connector handler directly. This is the choke point where
        the audit record is written, which is what makes "unrestricted, log
        everything" an actual position rather than an absence of one.
        """
        spec = self.find(connector, tool)
        vault = get_token_vault()
        audit = get_audit_log()

        token = await vault.token_for(spec.provider, principal=principal) if spec.provider else None

        started = time.monotonic()
        error: str | None = None
        result: Any = None
        try:
            result = await spec.handler(args, token=token)
            return result
        except Exception as exc:  # recorded, then re-raised
            error = f"{type(exc).__name__}: {exc}"
            raise
        finally:
            await audit.write(
                AuditRecord.build(
                    session_id=session_id,
                    principal=principal,
                    connector=connector,
                    tool=tool,
                    risk=spec.risk,
                    data_class=spec.data_class,
                    provider=spec.provider,
                    args=args,
                    result=result,
                    error=error,
                    duration_ms=int((time.monotonic() - started) * 1000),
                )
            )

    def as_sdk_tools(
        self, *, session_id: str, principal: str, read_only: bool = False
    ) -> list[Any]:
        """Wrap every registered tool as a Claude Agent SDK tool.

        `read_only` drops every non-READ tool from the returned set. Unattended
        runs use it (see triggers/base.py): a write tool the model never receives
        is a write tool it cannot call, which is a stronger guarantee than any
        instruction in a prompt.
        """
        from claude_agent_sdk import tool as sdk_tool

        wrapped: list[Any] = []
        for connector in self._connectors.values():
            for spec in connector.tools:
                if read_only and spec.risk is not Risk.READ:
                    continue
                wrapped.append(
                    self._wrap(sdk_tool, connector.name, spec, session_id, principal)
                )
        return wrapped

    def _wrap(self, sdk_tool: Any, connector_name: str, spec: ToolSpec, session_id: str, principal: str) -> Any:
        qualified = spec.qualified_name(connector_name)
        # Risk and data class go into the description so they land in the model's
        # context. The agent is not gated, but it is informed — it can say
        # "this touches student records" before it acts, which is most of the
        # value a confirmation dialog would have provided anyway.
        description = (
            f"{spec.description}\n"
            f"[risk={spec.risk.value} data={spec.data_class.value} system={connector_name}]"
        )

        @sdk_tool(qualified, description, spec.input_schema)
        async def _tool(args: dict[str, Any]) -> dict[str, Any]:
            value = await self.invoke(
                connector_name, spec.name, args, session_id=session_id, principal=principal
            )
            return {"content": [{"type": "text", "text": _render(value)}]}

        return _tool

    def as_gateway_targets(self) -> dict[str, Any]:
        """AgentCore Gateway target manifest.

        Feed this to `agentcore gateway create-target` so the same tool set is
        reachable over MCP by other agents. Shape follows the Gateway inline
        OpenAPI/Lambda target schema; verify against the current API version
        before applying (see docs/open-questions.md).
        """
        return {
            "targets": [
                {
                    "name": connector.name,
                    "description": connector.description,
                    "credentialProviderId": connector.provider,
                    "tools": [
                        {
                            "name": spec.qualified_name(connector.name),
                            "description": spec.description,
                            "inputSchema": spec.input_schema,
                            "annotations": {
                                # Gateway/Slackbot MCP clients use readOnlyHint to
                                # decide whether a call needs user confirmation.
                                "readOnlyHint": spec.risk.value == "read",
                                "x-frontline-risk": spec.risk.value,
                                "x-frontline-data-class": spec.data_class.value,
                            },
                        }
                        for spec in connector.tools
                    ],
                }
                for connector in self._connectors.values()
            ]
        }


def _render(value: Any) -> str:
    import json

    if isinstance(value, str):
        return value
    return json.dumps(value, indent=2, default=str)


_registry: Registry | None = None


def get_registry() -> Registry:
    global _registry
    if _registry is None:
        _registry = Registry()
        from . import analytics, artifacts, atlassian, code, slack_search

        _registry.register(atlassian.connector)
        _registry.register(artifacts.connector)
        _registry.register(code.connector)
        _registry.register(analytics.connector)
        _registry.register(slack_search.connector)
        try:
            from . import salesforce

            _registry.register(salesforce.connector)
        except ImportError:  # optional dependency not installed
            pass
    return _registry
