"""The connector contract.

This is the load-bearing file in the repo. Frontline's tool list is not known
yet, so the scaffold does not try to enumerate it — it defines the shape a tool
must have, and makes the shape carry the metadata that a governance decision
will later need.

Every tool declares three things beyond its function signature:

  risk        what kind of blast radius the call has
  data_class  the most sensitive class of data the call can return or touch
  provider    which OAuth credential provider in the token vault it draws on

None of these gate anything in v1 — the pilot runs unrestricted by decision
(ADR-003). They are recorded on every invocation so that after a few weeks of
real use there is a factual basis for deciding what *should* be gated, instead
of a guess made before anyone had used it. The metadata is the discovery
instrument; the controls come later and are cheap to add because the labels
already exist.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class Risk(StrEnum):
    """Blast radius of a tool call."""

    READ = "read"
    """Retrieval only. Cannot change state anywhere."""

    WRITE_INTERNAL = "write_internal"
    """Changes state in a Frontline-controlled system. Reversible by a human."""

    WRITE_EXTERNAL = "write_external"
    """Leaves the building — external email, customer-visible record, public post.
    Not reversible. The first control anyone will want is on this tier."""


class DataClass(StrEnum):
    """Most sensitive class of data a tool can surface.

    Frontline is a K-12 platform, so the regulated tier is not theoretical:
    student records fall under FERPA, and the special-education and Medicaid
    billing surfaces carry HIPAA-adjacent exposure. A tool that can reach
    student-level data is labelled REGULATED even if it usually returns
    aggregates.
    """

    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    REGULATED = "regulated"


ToolHandler = Callable[..., Awaitable[Any]]


@dataclass(frozen=True, slots=True)
class ToolSpec:
    """One callable capability exposed to the agent."""

    name: str
    description: str
    input_schema: dict[str, Any]
    handler: ToolHandler
    risk: Risk
    data_class: DataClass
    provider: str | None = None
    """OAuth credential provider ID in the token vault. None = no credential needed."""

    def qualified_name(self, connector: str) -> str:
        return f"{connector}__{self.name}"


@dataclass
class Connector:
    """A group of tools sharing one upstream system and one credential.

    Adding a system to the agent means adding one of these and registering it.
    See docs/06-adding-a-connector.md — it is roughly forty lines of work.
    """

    name: str
    description: str
    provider: str
    tools: list[ToolSpec] = field(default_factory=list)

    def tool(
        self,
        name: str,
        description: str,
        input_schema: dict[str, Any],
        *,
        risk: Risk,
        data_class: DataClass,
    ) -> Callable[[ToolHandler], ToolHandler]:
        """Decorator registering a handler as a tool on this connector."""

        def decorator(handler: ToolHandler) -> ToolHandler:
            self.tools.append(
                ToolSpec(
                    name=name,
                    description=description,
                    input_schema=input_schema,
                    handler=handler,
                    risk=risk,
                    data_class=data_class,
                    provider=self.provider,
                )
            )
            return handler

        return decorator
