# ADR-001 — The agent acts with the principal's access, via delegated OAuth

**Status:** accepted · **Date:** 2026-08-18

## Context

The CPO's requirement, relayed 7/10, is an agent with "access to every system he has
access to," acting on his behalf. The platform architect's objection the same day is that the internal agent platform's
design principle is that agents act as **scoped service identities, not as named
users**. This was recorded as the core unresolved tension and never settled.

It reads as a contradiction. It is better understood as two requirements that
were assumed to need the same mechanism.

- The CPO's requirement is about **reach**: the agent must not be blind to things he
  can see, or it fails at the first real question.
- The platform architect's requirement is about **attribution**: when something happens, the record
  must show that an agent did it, so it can be audited, rate-limited, and killed.

Those are separable. What makes them look inseparable is the implementation
everyone pictures: paste the executive's token into the agent's config. That
satisfies reach and destroys attribution, because every downstream log now shows
a human doing things at 3am.

## Decision

The agent authenticates as its own **workload identity**, and holds
**user-delegated OAuth tokens** for each connected system in Amazon Bedrock
AgentCore Identity's token vault.

Per call:

1. The agent proves it is the workload identity (IAM).
2. It exchanges that for a token the principal consented to issue, scoped to one
   provider.
3. The upstream system sees the principal's access.
4. The audit record captures both — `principal` and `workload_identity` are
   separate fields, always.

Consent is requested **per provider at the moment of first need**, surfaced in
Slack as a one-tap link. The agent does not receive a blanket grant at install
time; access expands visibly, and each grant is revocable on its own.

## Consequences

**Good**

- Both requirements are met without either side conceding, which is the outcome
  the discovery exercise was looking for.
- No long-lived credential is ever in the process, in an env var, or in a repo.
  The vault refreshes.
- Revoking the agent's Salesforce access does not require rotating its Jira
  access, or anything else.
- Attribution survives. "Who did this" has an answer that is a machine.

**Costs**

- A first-use consent interruption per provider. Deliberate: it is the moment the
  principal learns what the agent is reaching for. It also makes scope creep
  visible to the person best placed to object.
- Depends on AgentCore Identity. `identity/token_vault.py` isolates it behind one
  interface; a Secrets Manager + custom OAuth broker implementation is roughly a
  day's work if that dependency is unacceptable.
- The write scopes on the Slack user token remain a genuine impersonation
  surface: `chat:write` as the principal produces messages that look like the
  principal wrote them. Kept because "draft and send my reply" was an explicit
  ask, but this is the single most reviewable line in the manifest.

## Alternatives rejected

**Bot token only.** Clean attribution, no impersonation. Fails the reach
requirement outright — the agent sees only channels it is invited to.

**The principal's raw user token in configuration.** What a self-hosted personal
agent does. Meets the letter of the brief and fails every review it will face.

**Service account with union-of-scopes access.** Attribution is clean but the
agent ends up with *more* access than the principal, not less, and the blast
radius of a prompt injection becomes the whole workspace.
