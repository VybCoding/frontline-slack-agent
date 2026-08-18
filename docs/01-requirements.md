# Requirements

There is no PRD for this. The existing PM-assistant PRDs cover the PM-focused
Personal Assistant, which is adjacent but not the same product. What exists for
the general-purpose PA is one paragraph of intent plus an implementation
preference. The platform architect's point — the desire is long-known but "never detailed out on
capabilities" — is the accurate summary.

This document is the attempt to detail it. It is derived, not given. Where it
extrapolates, it says so.

## Source material

| Date | Via | Substance |
|---|---|---|
| 7/10 | product leadership, relaying the CPO | Personal Frontline agent acting on his behalf. Slack, not CLI. Access to every system he has access to. Takes action inside applications — documents, prototypes, presentations. Self-improving memory. "Collaborator in chief." Delegates to specialized Product OS agents. |
| 7/10 | the platform architect | Agents should act as scoped service identities, not named users. Flags this as conflicting with the above. Unresolved. |
| 8/7–8/9 | product ops | the CPO wants what he has at home — on-demand general-purpose agent (per the platform architect's characterization). Stand one up via OpenClaw or Hermes, Hermes preferred, by end of week, small pilot group. Explicitly not waiting on the internal agent-platform programme. |
| 8/17 | Hackathon framing | No token limits, C-level audience, unrestricted. Roper compliance and cost controls are the gate before expanding past seven named users. |
| — | platform engineering's tickets | router core and memory. |

## Derived requirements

Each is traced to its source. **[E]** marks extrapolation — a judgment call made
because the source is silent and the build cannot be.

### R1 — Single-principal, identity-scoped

The agent serves one named person and operates with their access.

- **R1.1** Reaches every system the principal can reach. *(7/10)*
- **R1.2** Actions attributable to the agent, not indistinguishable from the
  human. *(the platform architect, 7/10)*
- **R1.3** **[E]** Access granted per system at first need, revocable per system.
  Neither source addresses granularity; a single blanket grant makes R1.2
  unenforceable in practice.

→ Resolved in [ADR-001](decisions/ADR-001-user-delegated-identity.md).

### R2 — Slack is the whole interface

- **R2.1** Conversational. No command line, no flags. *(7/10, 8/7)*
- **R2.2** **[E]** Phone-first. "Remotely on his phone" is the stated usage;
  everything else follows from it — answer length, streaming, suggested prompts,
  no wide tables.
- **R2.3** **[E]** Uses Slack's native agent surface rather than a generic bot.
  Not requested, but the platform capability materially changes what R2.2 can be.

→ [ADR-005](decisions/ADR-005-slack-native-surface.md).

### R3 — Acts, not just drafts

- **R3.1** Write actions inside applications, not read-only. *(7/10)*
- **R3.2** Documents, prototypes, presentations named explicitly. *(7/10)*
  Satisfied by generation rather than integration: the agent writes the content
  and delivers it as a Slack canvas (documents) or an uploaded file (decks). No
  Workspace or M365 connector is required. See `connectors/artifacts.py`.
- **R3.3** Unrestricted in the pilot. *(8/17)*
- **R3.4** **[E]** Every action recorded. R3.3 without this is not a pilot, it is
  an incident waiting for a date.

→ [ADR-003](decisions/ADR-003-unrestricted-with-audit.md).

### R4 — Persistent, self-improving memory

- **R4.1** Context survives across sessions. *(7/10)*
- **R4.2** Improves with use. *(7/10)*
- **R4.3** **[E]** Long-term memory is written by post-session extraction, not by
  the agent editing itself mid-task. An agent that rewrites its own memory during
  a turn drifts toward whatever it just did.

### R5 — Delegation

- **R5.1** Routes to specialized Product OS agents. *(7/10, platform engineering's router tickets)*
- **R5.2** **[E]** Capability definitions are shared infrastructure, not private
  to this agent. R5.1 is impossible otherwise — every agent would reimplement
  every connector.

→ The registry emits an AgentCore Gateway target manifest for exactly this.

### R6 — Autonomy

Added after the 8/18 clarification that the agent should orchestrate *without
constant human intervention*, and that Slack is the interface to an AWS-hosted
workload rather than the workload itself.

- **R6.1** Runs on a schedule and on external events, not only on a human
  message. *(8/18)*
- **R6.2** Slack remains the interface for output. The trigger is separate from
  the interface. **[E]** — the two were stated as one requirement; separating
  them is the design move that makes the rest work.
- **R6.3** **[E]** Unattended runs are read-only, enforced by filtering the
  toolset rather than by instruction. A human message re-enables writes, so
  presence is the authorization and no approval UI is needed.
- **R6.4** **[E]** Silence is the default output. A trigger that always posts
  gets muted, and a muted agent is a dead one.

→ `triggers/`, and [05-hosting-options.md](05-hosting-options.md) for why this is
not a self-hosted daemon.

### R7 — Speed

- **R7.1** Pilot group holding something in days, not quarters. *(8/7)*
- **R7.2** Does not depend on the the internal agent-platform programme delivery path. *(8/7)*

## Explicitly out of scope for v1

Named so that leaving them out is a decision rather than an oversight.

- Multi-user. The architecture is single-principal. Extending to seven users
  means per-principal vault entries and memory namespaces — real work, not a
  config change.
- Approval gates. Deliberate; see ADR-003.
- Kill switch and cost caps. **Known gaps**, not deferred features. See
  [open-questions.md](open-questions.md).
- Prototypes. R3.2 names them alongside documents and presentations, which are
  now covered. A Figma connector is the obvious addition and the shape is proven
  by the five that exist.
- Proactive judgement beyond the trigger catalogue. The agent initiates on
  defined schedules and events (R6); it does not decide on its own that a new
  kind of thing is worth watching. Widening that is a product decision, and the
  audit log will say what to widen it to.

## The tension, stated plainly

R1.1 and R1.2 were recorded as contradictory and left unresolved for five weeks.
They are not contradictory. They were assumed to require the same mechanism, and
they do not — one is about reach, the other about attribution, and delegated
OAuth satisfies both. That resolution is the single most useful output of this
exercise; the code is the demonstration that it works.
