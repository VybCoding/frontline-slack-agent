#!/usr/bin/env python3
"""End-to-end demo against mocks. No Slack workspace, no Frontline credentials.

Runs in one of two tiers depending on what is available:

  wiring  no model credentials found. Drives the connector registry directly
          through a scripted scenario, then prints the audit log. Proves the
          identity → connector → audit path without an LLM in the loop.

  agent   Bedrock (or an Anthropic key) is reachable. Runs the real agent loop
          and renders the event stream the way the Slack surface would.

The scenario is the same either way, and it is a real one: a renewal is eight
weeks out, the account is unhealthy, and the reasons are spread across three
systems that do not talk to each other. That is the actual job.
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from frontline_agent.audit.log import read_local_audit
from frontline_agent.config import get_settings
from frontline_agent.connectors.registry import get_registry

PRINCIPAL = "U_CPO_DEMO"
SESSION = "demo-session"

QUESTION = (
    "Harbor County's renewal is 10/15 and their health score dropped to 48. "
    "What's actually going on, and what should I do about it?"
)

SCRIPTED = [
    ("slack", "search", {"query": "Harbor County renewal health"}),
    ("salesforce", "get_account", {"account_id": "0018X00002mQ4bB"}),
    ("atlassian", "search_issues", {"jql": 'project in (SPED, ANL) AND status != Done'}),
    ("analytics", "metric", {
        "metric": "feature_adoption_rate",
        "start_date": "2026-05-01",
        "end_date": "2026-07-31",
        "group_by": "district_segment",
    }),
]


def _has_model_credentials() -> bool:
    if os.environ.get("ANTHROPIC_API_KEY"):
        return True
    try:
        import boto3

        return boto3.Session().get_credentials() is not None
    except Exception:
        return False


async def run_wiring() -> None:
    print("── tier: wiring (no model credentials found) " + "─" * 30)
    print(f"\nQuestion: {QUESTION}\n")
    registry = get_registry()

    for connector, tool, args in SCRIPTED:
        spec = registry.find(connector, tool)
        print(f"  → {connector}.{tool}  [risk={spec.risk.value} data={spec.data_class.value}]")
        result = await registry.invoke(
            connector, tool, args, session_id=SESSION, principal=PRINCIPAL
        )
        preview = str(result).replace("\n", " ")[:100]
        print(f"    {preview}…\n")

    print("Every one of those calls resolved a credential from the vault and wrote")
    print("an audit record. Nothing reached a connector without going through both.")


async def run_agent() -> None:
    print("── tier: agent (model credentials found) " + "─" * 34)
    print(f"\nQuestion: {QUESTION}\n")

    from frontline_agent.agent.core import Agent

    agent = Agent(principal=PRINCIPAL, session_id=SESSION)
    async for ev in agent.run(QUESTION):
        match ev.kind:
            case "status":
                print(f"  [{ev.text}]")
            case "tool_start":
                print(f"  → {ev.tool}")
            case "text":
                print(ev.text, end="", flush=True)
            case "error":
                print(f"\n  !! {ev.text}")
            case "done":
                print()


def print_audit() -> None:
    records = read_local_audit()
    if not records:
        return
    print("\n── audit log " + "─" * 62)
    print(f"{'tool':<34} {'risk':<15} {'data':<13} {'ms':>6}")
    print("─" * 74)
    for r in records:
        tool = f"{r['connector']}.{r['tool']}"
        print(f"{tool:<34} {r['risk']:<15} {r['data_class']:<13} {r['duration_ms']:>6}")

    regulated = [r for r in records if r["data_class"] == "regulated"]
    print(f"\n{len(records)} actions. {len(regulated)} touched regulated data.")
    if regulated:
        print("Regulated calls record the request shape only — arguments and results")
        print("are omitted so the audit log never becomes a second copy of the data.")
    print(f"\nFull log: {get_settings().audit_local_path}")


async def main() -> None:
    settings = get_settings()
    if not settings.is_local:
        raise SystemExit("demo only runs with FRONTLINE_AGENT_MODE=local")

    Path(settings.audit_local_path).unlink(missing_ok=True)

    if _has_model_credentials():
        await run_agent()
    else:
        await run_wiring()

    print_audit()


if __name__ == "__main__":
    asyncio.run(main())
