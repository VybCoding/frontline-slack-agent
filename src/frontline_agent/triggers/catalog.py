"""The standing triggers.

These are deliberately few. Each one is a question he would otherwise have to
remember to ask, phrased the way he would ask it.

Adding a trigger is adding an entry here plus a redeploy. Removing one is
deleting it. That is the whole lifecycle — there is no trigger-management UI, and
there should not be one until somebody asks for it twice.

Times are America/New_York (Wayne, PA).
"""

from __future__ import annotations

from .base import Trigger

TRIGGERS: list[Trigger] = [
    Trigger(
        name="morning-brief",
        schedule="cron(0 11 ? * MON-FRI *)",  # 07:00 ET
        instruction=(
            "Look across Slack, Jira, Salesforce, and product analytics for anything "
            "that changed overnight and that I would want to know before my first "
            "meeting. Renewals inside 90 days whose health score moved, epics that "
            "became blocked, escalations naming me, adoption metrics outside their "
            "usual range. If it is a normal morning, say nothing."
        ),
    ),
    Trigger(
        name="renewal-watch",
        schedule="cron(0 13 ? * MON *)",  # Mondays 09:00 ET
        instruction=(
            "Every district with a renewal inside 90 days: pull the health score, "
            "open case count, and adoption trend. Tell me only about the ones where "
            "the picture got worse since last week, and why."
        ),
    ),
    Trigger(
        name="escalation-watch",
        # Slack events reach this through EventBridge once a forwarder is wired;
        # see docs/open-questions.md. Until then this trigger is inert by design
        # rather than silently broken.
        event_pattern={"source": ["frontline.slack"], "detail-type": ["escalation"]},
        enabled=False,
        instruction=(
            "An escalation was raised. Work out whether it connects to something "
            "already known — an open bug, a district already at risk, a pattern "
            "across accounts. Tell me only if it does, and what the connection is."
        ),
    ),
]


def enabled_triggers() -> list[Trigger]:
    return [t for t in TRIGGERS if t.enabled]


def find(name: str) -> Trigger:
    for trigger in TRIGGERS:
        if trigger.name == name:
            return trigger
    raise KeyError(f"no such trigger: {name}")
