"""The agent loop.

Claude Agent SDK on Bedrock. Two things here are non-obvious and load-bearing.

First, tools are built per session rather than once at import. Each session
carries the principal and session ID into every tool call, which is what makes
the audit record complete without threading context through every handler.

Second, the loop emits a typed event stream rather than returning a string. The
Slack layer consumes that stream and renders it as a live timeline — plan, tool
calls, then prose. Keeping the rendering out of here means the same agent can be
driven by the Slack surface, the demo script, or a test with no changes.

Subagents are declared for delegation. Today they are scoped variants of this
agent; when Frontline's Product OS agents expose A2A or MCP endpoints, these
definitions get replaced with remote references and nothing else changes.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any, Literal

from ..config import get_settings
from ..connectors.registry import get_registry
from ..identity.token_vault import ConsentRequired
from .memory import get_memory
from .prompt import build_system_prompt


@dataclass(frozen=True, slots=True)
class AgentEvent:
    kind: Literal["status", "tool_start", "tool_end", "text", "consent", "error", "done"]
    text: str = ""
    tool: str = ""
    payload: dict[str, Any] | None = None


SUBAGENTS = {
    "roadmap-analyst": {
        "description": "Deep analysis of roadmap state, delivery risk, and epic health "
                       "across Jira. Use when a question needs more than a single query.",
        "prompt": "You analyze delivery data. Be quantitative. Identify the two or three "
                  "things that actually explain the picture and ignore the rest.",
        "tools": ["mcp__frontline__atlassian__search_issues"],
        "model": "sonnet",
    },
    "account-analyst": {
        "description": "Customer health, renewal exposure, and account narrative. Use for "
                       "questions about specific districts or segments.",
        "prompt": "You analyze customer health. Connect usage data to commercial risk. "
                  "Never copy student-level records into your output.",
        "tools": [
            "mcp__frontline__salesforce__soql",
            "mcp__frontline__salesforce__get_account",
            "mcp__frontline__analytics__metric",
        ],
        "model": "sonnet",
    },
}


class Agent:
    def __init__(self, *, principal: str, session_id: str | None = None) -> None:
        self.principal = principal
        self.session_id = session_id or str(uuid.uuid4())
        self._settings = get_settings()
        self._configure_bedrock()

    def _configure_bedrock(self) -> None:
        """Route the SDK at Bedrock so inference stays inside Frontline's account.

        Set before the SDK client is constructed. With this on, model calls are
        governed by IAM and billed through AWS — no Anthropic API key exists
        anywhere in the deployment.
        """
        s = self._settings
        os.environ.setdefault("CLAUDE_CODE_USE_BEDROCK", s.claude_code_use_bedrock)
        os.environ.setdefault("AWS_REGION", s.aws_region)
        os.environ.setdefault("ANTHROPIC_MODEL", s.anthropic_model)

    async def run(
        self,
        message: str,
        *,
        context: dict[str, Any] | None = None,
        unattended: bool = False,
    ) -> AsyncIterator[AgentEvent]:
        """One turn.

        `unattended=True` is an autonomous run — nobody asked, nobody is watching.
        The toolset is filtered to read-only before the loop starts and the
        operating brief is extended accordingly. See triggers/base.py for why the
        two modes differ.
        """
        from claude_agent_sdk import (
            AgentDefinition,
            AssistantMessage,
            ClaudeAgentOptions,
            ClaudeSDKClient,
            ResultMessage,
            TextBlock,
            ToolResultBlock,
            ToolUseBlock,
            create_sdk_mcp_server,
        )

        memory = get_memory()
        registry = get_registry()

        yield AgentEvent(kind="status", text="Recalling context")
        recalled = await memory.recall(self.principal, message)

        tools = registry.as_sdk_tools(
            session_id=self.session_id, principal=self.principal, read_only=unattended
        )
        server = create_sdk_mcp_server(name="frontline", version="0.1.0", tools=tools)

        options = ClaudeAgentOptions(
            system_prompt=build_system_prompt(recalled, unattended=unattended),
            mcp_servers={"frontline": server},
            allowed_tools=[f"mcp__frontline__{t.name}" for t in tools],
            agents={
                name: AgentDefinition(
                    description=spec["description"],
                    prompt=spec["prompt"],
                    tools=spec["tools"],
                    model=spec["model"],
                )
                for name, spec in SUBAGENTS.items()
            },
            # No filesystem, no shell. The agent's whole surface is the connector
            # registry. This is the single biggest difference from the self-hosted
            # personal-agent pattern the brief pointed at — see ADR-002.
            permission_mode="bypassPermissions",
            setting_sources=[],
            # Per-turn spend ceiling. ADR-003 accepts an unrestricted agent;
            # it does not accept an unbounded one.
            max_budget_usd=self._settings.max_turn_budget_usd,
        )

        prompt = _with_context(message, context)
        turns: list[dict[str, Any]] = [{"role": "user", "text": message}]
        collected: list[str] = []

        try:
            async with ClaudeSDKClient(options=options) as client:
                await client.query(prompt)
                yield AgentEvent(kind="status", text="Working")

                async for msg in client.receive_response():
                    if isinstance(msg, AssistantMessage):
                        for block in msg.content:
                            if isinstance(block, TextBlock):
                                collected.append(block.text)
                                yield AgentEvent(kind="text", text=block.text)
                            elif isinstance(block, ToolUseBlock):
                                yield AgentEvent(
                                    kind="tool_start",
                                    tool=_pretty_tool(block.name),
                                    payload=dict(block.input or {}),
                                )
                            elif isinstance(block, ToolResultBlock):
                                yield AgentEvent(kind="tool_end", tool=_pretty_tool(""))
                    elif isinstance(msg, ResultMessage):
                        break
        except ConsentRequired as exc:
            yield AgentEvent(
                kind="consent",
                text=exc.provider,
                payload={"authorization_url": exc.authorization_url},
            )
            return
        except Exception as exc:
            yield AgentEvent(kind="error", text=f"{type(exc).__name__}: {exc}")
            return

        turns.append({"role": "assistant", "text": "".join(collected)})
        await memory.record(self.principal, self.session_id, turns)
        yield AgentEvent(kind="done")


def _with_context(message: str, context: dict[str, Any] | None) -> str:
    """Fold Slack's ambient context into the prompt.

    `app_context_changed` tells us what the principal is looking at right now.
    Passing it means "summarize this" resolves without them naming a channel —
    the single highest-leverage thing Slack gives an agent that a chat box does not.
    """
    if not context:
        return message
    lines = [f"{k}: {v}" for k, v in context.items() if v]
    if not lines:
        return message
    return f"{message}\n\n<slack_context>\n" + "\n".join(lines) + "\n</slack_context>"


def _pretty_tool(name: str) -> str:
    return name.removeprefix("mcp__frontline__").replace("__", " · ") if name else ""
