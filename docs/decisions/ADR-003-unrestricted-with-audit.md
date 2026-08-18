# ADR-003 — The v1 pilot runs unrestricted; the audit log is the control

**Status:** accepted · **Date:** 2026-08-18

## Context

The hackathon framing is explicit: no token limits, C-level audience, speed over
governance maturity. The independent diagnosis notes that manifest enforcement,
kill-switch, and cost metering are all absent from the internal agent platform, and that this build
trades those controls for speed knowingly.

The instinct is to add approval gates anyway. That instinct is wrong here, for a
reason worth writing down: **nobody knows what to gate yet.** the platform architect's standing
point is that the capability set has never been detailed. Gates designed before
anyone has watched the agent work will be wrong in both directions — blocking the
useful and waving through the dangerous — and they will be defended afterward
because they are already built.

## Decision

Run the pilot unrestricted. Make the audit log a real control rather than logging.

Concretely:

- Every tool invocation goes through one choke point (`Registry.invoke`). There
  is no path from the agent to a connector that skips it.
- Each record carries `principal`, `workload_identity`, `risk`, `data_class`,
  `provider`, arguments, a result summary, duration, and any error.
- Records for `data_class=regulated` store a digest and a byte count instead of
  arguments and results, so the log never becomes a second copy of student data.
- The table is `PutItem`-only for the agent's role. No update, no delete. An
  agent that can edit its own history does not have one.
- The audit stack has `RETAIN` removal policy and lives in a separate stack from
  the agent, so tearing down the agent cannot erase what it did.
- Two GSIs exist because two questions will be asked: *what irreversible things
  happened* (`by-risk`) and *what touched regulated data* (`by-data-class`).

Every tool is labelled with risk and data class **now**, even though nothing
enforces those labels. The labels are the instrument. After a few weeks of real
use there is a factual basis for deciding what should be gated — and because the
labels already exist, adding the gate is a conditional in one function.

## Consequences

- A bad turn can send a real message or file a real ticket. Accepted, at pilot
  scale, with a named principal who can see it happen in the timeline.
- The streamed timeline (see ADR-005) is the real-time complement: the principal
  watches tool calls as they happen and can stop a turn. That is a weaker control
  than pre-approval and a stronger one than nothing.
- There is no kill switch in v1. The nearest thing is disabling the Slack app or
  revoking a provider's consent in the vault. **This is the largest known gap** —
  see `docs/open-questions.md`.
- Cost is capped per turn (`max_turn_budget_usd`, default $2.00, enforced by the
  SDK) but not governed: no per-principal attribution, no aggregate cap, no
  alerting. Unrestricted was the decision; unbounded was not, and the per-turn
  ceiling is the minimum that distinguishes the two. Second largest gap.

## Revisit when

Any of: the pilot expands past the seven named users; the first `write_external`
action surprises someone; Roper compliance asks for a control matrix. All three
are likely inside a quarter, and the audit log is what makes the resulting
conversation evidence-based instead of theoretical.
