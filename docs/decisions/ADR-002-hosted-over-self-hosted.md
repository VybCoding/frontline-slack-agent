# ADR-002 — Hosted AWS service, not a self-hosted personal agent

**Status:** accepted · **Date:** 2026-08-18

## Context

The 8/7–8/9 refinement asked to stand up a personal agent via **OpenClaw or
Hermes** (Hermes preferred) by end of week. Both are real and both are good at
what they do. Both are also the same shape: a long-lived daemon on hardware you
own, memory in a local SQLite file, with shell execution and filesystem access as
headline features, bridging a dozen messaging platforms into one gateway.

That shape is exactly why they feel like magic at home, and exactly why they
cannot be the answer here.

Frontline is a K-12 platform under Roper Technologies. Student records are
FERPA-governed; the special education and Medicaid billing surfaces carry
HIPAA-adjacent exposure; several states layer on their own statutes. A process
with shell access, a local unencrypted memory store, no audit trail, and a named
executive's credentials in its environment is not a policy problem to be waived.
It is the specific artifact a security review exists to find.

## Decision

Keep everything about the Hermes experience that the CPO is actually asking for.
Change the substrate.

| What he wants | Kept | How |
|---|---|---|
| Always on, no CLI | yes | Slack agent surface, phone-first |
| One conversation, remembers everything | yes | AgentCore Memory, short + long term |
| Reaches all his systems | yes | Connector registry + delegated OAuth |
| Self-improving | yes | Long-term extraction across sessions |
| Fast to stand up | yes | This repo, `make demo` in one command |
| Shell and filesystem access | **no** | Removed. The tool surface is the registry |
| Local SQLite brain on a box | **no** | Managed store, encrypted, in-account |
| Credentials in environment | **no** | Token vault, delegated, refreshed |

The three removals are the entire delta, and none of them is something the CPO asked
for — they are implementation details of the products he named.

## Consequences

- Inference runs on Bedrock inside Frontline's own AWS account. No Anthropic API
  key exists in the deployment; model access is governed by IAM and billed
  through AWS. For a Roper subsidiary this likely clears more review than any
  amount of written policy.
- The agent cannot do arbitrary things. Every capability is a connector someone
  wrote and labelled. That is a real capability ceiling and it is the correct
  trade at this stage.
- Slower than "install Hermes on a box this week." The honest counter is that the
  week saved is borrowed against the review that follows, at interest.

## Note on the timeline

The end-of-week framing was about **momentum**, not about the specific binary.
This repo runs against mocks in one command and needs one Slack app plus one AWS
account to run for real. If the goal was a pilot group holding something by
Friday, that goal survives intact.
