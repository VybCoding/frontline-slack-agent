"""Shared HTTP transport for connectors.

In `local` mode every request is served from mocks/fixtures/ instead of the
network, keyed by connector and operation. That is what lets the repo be cloned
and run end-to-end before anyone has a Frontline credential — the agent reasons
over realistic data, the audit log fills up, and the Slack surface behaves
exactly as it will in production.

Fixtures are obviously synthetic. Do not replace them with real exports; see
docs/open-questions.md on test data.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx

from ..config import get_settings

_FIXTURES = Path(__file__).resolve().parents[3] / "mocks" / "fixtures"


class UpstreamError(RuntimeError):
    pass


async def call(
    connector: str,
    operation: str,
    *,
    method: str = "GET",
    url: str | None = None,
    token: str | None = None,
    params: dict[str, Any] | None = None,
    json_body: dict[str, Any] | None = None,
) -> Any:
    settings = get_settings()

    if settings.is_local:
        return _fixture(connector, operation)

    if not url:
        raise UpstreamError(f"{connector}.{operation}: no URL configured")

    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.request(
            method, url, headers=headers, params=params, json=json_body
        )
        if response.status_code >= 400:
            raise UpstreamError(
                f"{connector}.{operation} -> {response.status_code}: {response.text[:200]}"
            )
        return response.json()


def _fixture(connector: str, operation: str) -> Any:
    path = _FIXTURES / f"{connector}.{operation}.json"
    if not path.exists():
        raise UpstreamError(
            f"no fixture for {connector}.{operation} — add {path.name} to mocks/fixtures/"
        )
    return json.loads(path.read_text())
