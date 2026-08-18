"""Autonomous triggers — the agent working when nobody asked it to.

The original scaffold conflated two requirements that arrived in one sentence:
Slack is the *interface*, and the agent should work *without constant human
intervention*. Those are different things. Slack being how he talks to it says
nothing about what wakes it up.

So triggers are a separate entry point into the same workload. A trigger fires,
the agent runs, and if it has something worth saying it says it in Slack. The
interface never changed; the trigger did.

## Autonomy policy

An unattended run is **read-only, enforced structurally**. `allowed_tools` is
filtered to `risk == READ` before the loop starts, so a write tool is not merely
discouraged — it is absent from the model's toolset and cannot be called.

This is where the risk labels stop being documentation. Interactive turns are
unrestricted because a human is watching (ADR-003); unattended turns are
read-only because nobody is. The same label drives both, which is why it was
worth putting on every tool before anything enforced it.

When the agent finds something that warrants action, it describes exactly what it
would do and asks. His reply lands in the thread as an ordinary message, which
resumes the normal interactive path — where writes are allowed again, because he
is now present. The approval is a reply, not a gate: no buttons, no workflow, no
new UI to learn.

## Silence

A trigger that always posts becomes noise, and noise gets muted, and a muted
agent is a dead agent. So an unattended run that finds nothing worth an
interruption returns the sentinel below and nothing is posted at all.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

NOTHING_TO_REPORT = "NOTHING_TO_REPORT"

UNATTENDED_PROMPT = f"""
# You were not asked

You woke on a trigger. Nobody is waiting for this, and nobody is watching you
work. Two things follow.

**You cannot change anything.** Your toolset contains only read tools right now.
That is enforced, not advisory. If something needs doing, describe precisely what
you would do — the system, the action, the specific values — and stop. Your
principal will reply, and you will be able to act then.

**Interrupting costs something.** He did not ask for this, so the bar for saying
anything is whether he would be worse off not knowing before the next time he
opens Slack on his own. Routine variance is not news. A number moving within its
usual range is not news.

If nothing clears that bar, reply with exactly `{NOTHING_TO_REPORT}` and nothing
else. Silence is the correct output most of the time, and it is what keeps this
worth having.

When something does clear the bar: lead with it in one sentence, give the two or
three facts that establish it, then say what you propose. Under 150 words.
"""


@dataclass(frozen=True, slots=True)
class Trigger:
    """One reason the agent might wake up."""

    name: str
    instruction: str
    """The standing question. Written as if he had asked it himself."""

    schedule: str | None = None
    """EventBridge cron/rate expression. `None` for event-driven triggers."""

    event_pattern: dict[str, Any] | None = field(default=None)
    """EventBridge event pattern. `None` for scheduled triggers."""

    enabled: bool = True

    def __post_init__(self) -> None:
        if not (self.schedule or self.event_pattern):
            raise ValueError(f"trigger {self.name} has neither schedule nor event pattern")
