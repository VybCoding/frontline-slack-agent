"""Edge Lambda — verify, acknowledge, dispatch.

Slack requires a 2xx within three seconds or it retries, and a retried event that
runs a full agent turn means duplicate work and duplicate side effects. So this
function does exactly three things and nothing that can block:

  1. verify the Slack signature (constant-time, with the timestamp window)
  2. short-circuit url_verification and retries
  3. invoke the worker asynchronously and return 200 immediately

Everything expensive happens in handler_worker, which runs on AgentCore Runtime
where an eight-hour session ceiling means a long research turn is not a timeout.

The retry guard is not optional. Slack retries on any non-2xx and on timeout, and
with an unrestricted agent a duplicate turn can mean a duplicate Jira ticket or a
second message sent to a customer.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from typing import Any

import boto3

_lambda = boto3.client("lambda")

WORKER_FUNCTION = os.environ.get("WORKER_FUNCTION_NAME", "frontline-agent-worker")
SIGNING_SECRET = os.environ.get("SLACK_SIGNING_SECRET", "")
_MAX_SKEW_SECONDS = 60 * 5


def handler(event: dict[str, Any], _context: Any) -> dict[str, Any]:
    body = event.get("body") or ""
    headers = {k.lower(): v for k, v in (event.get("headers") or {}).items()}

    if not _verified(body, headers):
        return {"statusCode": 401, "body": "bad signature"}

    payload = json.loads(body)

    if payload.get("type") == "url_verification":
        return {"statusCode": 200, "body": payload["challenge"]}

    # Slack retried. The first delivery is already being worked; do not run twice.
    if headers.get("x-slack-retry-num"):
        return {"statusCode": 200, "body": ""}

    _lambda.invoke(
        FunctionName=WORKER_FUNCTION,
        InvocationType="Event",
        Payload=json.dumps(payload).encode(),
    )
    return {"statusCode": 200, "body": ""}


def _verified(body: str, headers: dict[str, str]) -> bool:
    timestamp = headers.get("x-slack-request-timestamp", "")
    signature = headers.get("x-slack-signature", "")
    if not (timestamp and signature and SIGNING_SECRET):
        return False
    if abs(time.time() - int(timestamp)) > _MAX_SKEW_SECONDS:
        return False

    basestring = f"v0:{timestamp}:{body}".encode()
    expected = "v0=" + hmac.new(
        SIGNING_SECRET.encode(), basestring, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature)
