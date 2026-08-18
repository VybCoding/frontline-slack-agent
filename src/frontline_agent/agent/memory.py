"""Persistent memory.

"Self-improving memory" was one of four explicit requirements and is the one most
often faked. Faking it looks like stuffing the last N turns into context. Real
memory means two stores with different lifetimes:

  short term  the current conversation, so a follow-up question makes sense
  long term   durable facts about how this principal works — which metrics they
              actually care about, how they want things phrased, who owns what,
              what they have already decided and do not want re-litigated

AgentCore Memory provides both, with the long-term store populated by extraction
strategies that run after a session rather than by the agent writing to itself
mid-turn. That ordering matters: an agent that edits its own memory during a task
will drift toward whatever it just did.

Local mode keeps both in a JSON file so the behaviour is observable without AWS.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..config import get_settings

_LOCAL_STORE = Path(".memory/store.json")


class Memory:
    async def recall(self, principal: str, query: str) -> str | None:
        raise NotImplementedError  # pragma: no cover

    async def record(self, principal: str, session_id: str, turns: list[dict[str, Any]]) -> None:
        raise NotImplementedError  # pragma: no cover


class LocalMemory(Memory):
    def __init__(self, path: Path = _LOCAL_STORE) -> None:
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)
        if not self._path.exists():
            self._path.write_text(json.dumps({"facts": {}, "sessions": {}}))

    def _load(self) -> dict[str, Any]:
        return json.loads(self._path.read_text())

    async def recall(self, principal: str, query: str) -> str | None:
        facts = self._load()["facts"].get(principal, [])
        if not facts:
            return None
        return "\n".join(f"- {fact}" for fact in facts[-20:])

    async def record(self, principal: str, session_id: str, turns: list[dict[str, Any]]) -> None:
        store = self._load()
        store["sessions"].setdefault(principal, {})[session_id] = turns
        self._path.write_text(json.dumps(store, indent=2, default=str))

    async def learn(self, principal: str, fact: str) -> None:
        """Explicit teaching: 'remember that I always want X'."""
        store = self._load()
        store["facts"].setdefault(principal, []).append(fact)
        self._path.write_text(json.dumps(store, indent=2, default=str))


class AgentCoreMemory(Memory):
    """AWS mode.

    Verify `retrieve_memory_records` / `create_event` against the AgentCore
    Memory API version in your account before first deploy.
    """

    def __init__(self, memory_id: str) -> None:
        import boto3

        self._client = boto3.client("bedrock-agentcore")
        self._memory_id = memory_id

    async def recall(self, principal: str, query: str) -> str | None:
        response = self._client.retrieve_memory_records(
            memoryId=self._memory_id,
            namespace=f"principal/{principal}",
            searchCriteria={"searchQuery": query, "topK": 20},
        )
        records = response.get("memoryRecordSummaries", [])
        if not records:
            return None
        return "\n".join(f"- {r['content']['text']}" for r in records)

    async def record(self, principal: str, session_id: str, turns: list[dict[str, Any]]) -> None:
        self._client.create_event(
            memoryId=self._memory_id,
            actorId=principal,
            sessionId=session_id,
            payload=[{"conversational": {"role": t["role"], "content": {"text": t["text"]}}}
                     for t in turns],
        )


_memory: Memory | None = None


def get_memory() -> Memory:
    global _memory
    if _memory is None:
        settings = get_settings()
        _memory = (
            LocalMemory() if settings.is_local else AgentCoreMemory(settings.agentcore_memory_id)
        )
    return _memory
