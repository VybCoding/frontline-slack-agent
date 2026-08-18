# Frontline Personal Agent

Slack is the human interface to an agent workload hosted in Frontline's own AWS
account, acting on the principal's behalf. It answers when spoken to, and it
works on a schedule when nobody is watching. It runs on Amazon Bedrock, holds the
principal's access under its own identity, and records everything it does.

```bash
make install
make demo
```

That runs end to end against synthetic data. No AWS account, no Slack workspace,
no Frontline credential. It exists so you can see the thing work before deciding
whether to invest in it.

---

## What this is, and what it isn't

**It is** a working scaffold and the PRD that was missing. Every architectural
decision is written down with its reasoning and its cost, so the parts you
disagree with are easy to find and change.

**It isn't** finished. Section [*What is deliberately missing*](#what-is-deliberately-missing)
is not a disclaimer — it is the most useful page here, and the gaps are named
because naming them is the job.

**Start with** [docs/05-hosting-options.md](docs/05-hosting-options.md) if the
question on your mind is *why not just run Hermes on a laptop.* That is the most
consequential decision in the package and it gets a document of its own.

---

## The problem this was built against

The requirement arrived as intent rather than specification: one paragraph
relayed on 7/10, plus an implementation preference from 8/7. The platform
architect's read is the useful one — the desire is long-known but *"never
detailed out on capabilities."* The existing PM-assistant PRDs cover an adjacent
product, not this one.

That is a normal starting condition for an ambitious internal request, and it is
the condition this repo is built for.

So the first deliverable is not code. It is
[**docs/01-requirements.md**](docs/01-requirements.md) — every requirement traced
to its source, with extrapolations marked `[E]` so you can see exactly where I
guessed and overrule me.

### The tension that was left unresolved

Recorded on 7/10 and open ever since:

> The CPO wants an agent with access to every system **he** has access to, acting on
> his behalf. The platform architect's principle is that agents act as **scoped service identities,
> not as named users**.

These read as contradictory, and were left open as such. They are not — they
were assumed to require the same mechanism.

- The CPO's requirement is about **reach** — an agent blind to what he can see fails
  at the first real question.
- The platform architect's requirement is about **attribution** — when something happens, the record
  must show a machine did it.

They only conflict under one implementation: pasting the executive's token into
the agent's config. That satisfies reach and destroys attribution, and it is what
a self-hosted personal agent does by default.

**The resolution is delegated OAuth.** The agent authenticates as its own
workload identity, then exchanges that for user-delegated tokens held in Amazon
Bedrock AgentCore Identity's vault. Upstream systems see the principal's access.
The audit trail sees the agent. `principal` and `workload_identity` are separate
fields on every record, always.

Consent is per-system and requested at the moment of first need, as a one-tap
link in Slack — so access expands visibly, and each grant is revocable on its own.

Full reasoning: [ADR-001](docs/decisions/ADR-001-user-delegated-identity.md).

### On Hermes and OpenClaw

The 8/7 ask was to stand one of these up, Hermes preferred. Both are good at what
they do. Both are also the same shape: a daemon on hardware you own, memory in a
local SQLite file, shell and filesystem access as headline features.

That shape is why they feel like magic at home, and why it does not transfer.
Frontline is K-12 under Roper. Student records are FERPA-governed; special
education and Medicaid billing carry HIPAA-adjacent exposure. A process with
shell access, an unencrypted local memory store, no audit trail, and an
executive's credentials in its environment is unlikely to clear review in that
context — and reasonably so.

**So this keeps the Hermes experience and changes the substrate.** Always on, one
conversation, remembers everything, reaches all his systems, self-improving —
all kept. Shell access, local SQLite brain, and credentials-in-environment —
removed. None of those three is something the CPO asked for; they are implementation
details of the products he named.

[ADR-002](docs/decisions/ADR-002-hosted-over-self-hosted.md) has the full
comparison.

---

## What you need to fill in

Everything below is a value only Frontline can supply. Nothing else is required.

### Slack — create the app from `manifest/slack-app-manifest.yaml`

| Variable | Where it comes from | Notes |
|---|---|---|
| `SLACK_BOT_TOKEN` | OAuth & Permissions | `xoxb-` |
| `SLACK_SIGNING_SECRET` | Basic Information | request verification |
| `SLACK_APP_TOKEN` | Basic Information → App-Level Tokens | `xapp-`, dev only |
| `PRINCIPAL_SLACK_USER_ID` | the principal's Slack member ID | `U…` |
| `SLACK_USER_TOKEN` | **leave empty in AWS mode** | vault-issued; local dev only |

> **Start the Enterprise Grid app approval first.** It is the longest-lead item
> and it is entirely out of engineering's hands. A custom app requesting
> `search:read` and `chat:write` on a *user* token will get a second look.

### AWS

| Variable | Notes |
|---|---|
| `AWS_REGION` | must have Claude enabled on Bedrock — **not on by default** |
| `AGENTCORE_MEMORY_ID` | after creating the Memory store |
| `AGENTCORE_WORKLOAD_IDENTITY` | defaults to `frontline-cpo-agent` |
| `AUDIT_TABLE_NAME` | from the `FrontlineAgentAudit` stack output |

No Anthropic API key. Inference runs on Bedrock in Frontline's account, governed
by IAM and billed through AWS.

### Connectors

For each: register an OAuth2 credential provider in AgentCore Identity, then set
its ID. **No connector secrets go in the environment** — tokens are delegated,
vaulted, and refreshed.

| Variable | System |
|---|---|
| `ATLASSIAN_PROVIDER_ID` + `ATLASSIAN_SITE_URL` | Jira + Confluence |
| `SALESFORCE_PROVIDER_ID` + `SALESFORCE_INSTANCE_URL` | Salesforce |
| `ANALYTICS_PROVIDER_ID` + `ANALYTICS_BASE_URL` | product analytics / BI |

Those four are **inferences**, not requirements — see
[open question 9](docs/open-questions.md). Adding a system you actually use is
about forty lines and under an hour:
[docs/03-adding-a-connector.md](docs/03-adding-a-connector.md).

Full runbook: [docs/04-operations.md](docs/04-operations.md).

---

## How it works

```
Slack ──▶ API Gateway ──▶ events Lambda ──async──▶ worker ──▶ Claude Agent SDK
   ▲                      verify · 3s ack                          │
   │                                                               ▼
   │   EventBridge ──────────unattended, read-only──────▶  Connector registry
   │   schedule/event                                   (the only way out, ever)
   │                                                          │        │
   └───────── findings, silence by default ──────┐            │        │
                                  delegated token│◀───────────┘        │
                                       from vault│         one audit ◀─┘
                                                            record per call
```

Five things are doing the real work.

**Two entry points, one workload.** A human message and a schedule reach the
same agent through the same connectors and the same audit path. What differs is
authorization: interactive turns are unrestricted because someone is watching;
unattended turns are read-only because nobody is — enforced by filtering the
toolset before the loop starts, so write tools are *absent* rather than
discouraged. If a scheduled run finds something worth acting on, it says what it
would do and stops. **His reply resumes the interactive path, where writes are
allowed again.** Presence is the authorization, so there is no approval workflow,
no buttons, and no second interface to learn.

Silence is the normal output. A trigger that posts every day gets muted, and a
muted agent is a dead one.

**The registry is a choke point, not a convenience.** There is no code path from
the agent to an upstream system that skips `Registry.invoke`. Credential
resolution and audit are structural — a connector author cannot forget them.

**Every tool carries a risk and a data class.** `read` / `write_internal` /
`write_external`, and `public` / `internal` / `confidential` / `regulated`.
Nothing enforces these in v1. They exist so that after a few weeks of real use
there is *evidence* for what should be gated, instead of gates designed by people
who have not watched it work yet.

**The three-second rule shapes the deployment.** Slack retries anything it does
not get a 2xx for in three seconds, and a retried turn on an unrestricted agent
means a duplicate ticket or a second message to a customer. The edge function
verifies, drops retries, dispatches, returns. It never does work.

**The Slack surface is the 2026 agent surface, not a bot in a DM.**
`features.agent_view`, streamed replies with `task_display_mode: timeline` so tool
calls render as a live sequence, `app_context_changed` so *"summarize this and
draft a reply"* resolves with no arguments, suggested prompts, thread titles.
On a phone, a streamed timeline is a working interrupt. A spinner is not.

**Documents are generated, not integrated.** No Workspace or M365 connector.
The agent writes the content and delivers it as a Slack **canvas** for anything
text-shaped — editable in place, shareable, readable on a phone with no download
— or an uploaded **PPTX** for decks. That covers "documents, prototypes,
presentations" without adding a third-party surface holding Frontline data.

Detail: [docs/02-architecture.md](docs/02-architecture.md).

### One constraint worth knowing about

Since 29 May 2025, non-Marketplace Slack apps are throttled on
`conversations.history` and `conversations.replies` to roughly **one request per
minute returning fifteen messages**. An internal app is non-Marketplace
permanently.

Any design that pages channel history to build context stalls on the first real
question. Retrieval here goes through **search** instead — faster, and correctly
scoped, since it runs on the principal's token and returns only what they can
already see. The permission model is inherited rather than reimplemented.

---

## Decisions

Five, each with its costs written down.

| | |
|---|---|
| [ADR-001](docs/decisions/ADR-001-user-delegated-identity.md) | Delegated OAuth resolves the reach-vs-attribution tension |
| [ADR-002](docs/decisions/ADR-002-hosted-over-self-hosted.md) | Hosted AWS service, not a self-hosted personal agent |
| [ADR-003](docs/decisions/ADR-003-unrestricted-with-audit.md) | Unrestricted pilot; the audit log is the control |
| [ADR-004](docs/decisions/ADR-004-claude-agent-sdk-on-bedrock.md) | Claude Agent SDK on Bedrock |
| [ADR-005](docs/decisions/ADR-005-slack-native-surface.md) | Slack's agent surface, not a chat box in Slack |

Plus one memo that is not a decision record because the decision isn't mine:
[**docs/05-hosting-options.md**](docs/05-hosting-options.md) — five hosting
routes for the agent workload, what a self-hosted daemon on a company PC actually
buys, why source-code access is the wrong thing to be protecting, and the one
scenario where the fast option is the right call.

### Why unrestricted

The hackathon framing is explicit — no limits, speed over governance maturity.
The instinct is to add approval gates anyway. That instinct is wrong here, for
one reason: **nobody knows what to gate yet.**

Gates designed before anyone has watched the agent work will be wrong in both
directions, and they will be defended afterward because they are already built.

So the pilot runs open, and the audit log is built as a control rather than as
logging: one record per call, `PutItem`-only for the agent's role, a separate
stack with `RETAIN` so tearing down the agent cannot erase its history, and two
indexes because two questions will be asked — *what irreversible things happened*
and *what touched regulated data*.

Calls labelled `regulated` store a digest and a byte count instead of arguments
and results, so the audit log never becomes a second copy of student data. There
is a test for that.

---

## What is deliberately missing

Read this section before the code.

**Blocking before the pilot grows past its named users**

1. **No kill switch.** Nothing stops a turn in flight. The nearest action is
   setting worker concurrency to zero — a console operation, not a feature. About
   a day of work, and worth doing before the pilot widens.
2. **Cost is bounded, not governed.** A hard $2.00 per-turn ceiling is enforced
   by the SDK, which bounds a runaway loop. There is still no per-principal
   attribution, aggregate cap, or alerting — and Roper's cost gate needs those.
3. **No retention policy on the audit log.** It records an executive's activity,
   which makes it a surveillance artifact as well as a compliance one. Legal and
   Security decide this, not engineering.

**Unknown to me**

Whether AgentCore is permitted in the account · whether Bedrock has Claude
enabled · how long Grid app approval takes · whether the Real-Time Search API is
entitled · whether the Product OS agents expose A2A, MCP, or HTTP · **what the
actual tool list is**, and what the trigger catalogue should watch. The
escalation trigger ships **disabled** because it needs a Slack-to-EventBridge
forwarder that doesn't exist — inert by design rather than silently broken.

**Judgment calls that could reasonably go the other way**

`chat:write` on the user token is real impersonation and is the first thing I
would remove under pushback · Salesforce and analytics have no write tools by
choice · the architecture is single-principal while the pilot is seven · Slack
context lives in process memory, which is correct for Socket Mode and **wrong for
Lambda** · unattended read-only is enforced at the toolset, while the delegated
tokens themselves still carry write scope.

All sixteen, with reasoning: [docs/open-questions.md](docs/open-questions.md).

---

## Repository

```
src/frontline_agent/
  connectors/base.py      the contract — read this first
  connectors/registry.py  the choke point
  audit/log.py            the control
  identity/token_vault.py delegated OAuth
  agent/core.py           the loop and subagents
  triggers/base.py        why unattended runs are read-only
  slack/                  surface, blocks, handlers
  runtime/                socket mode · edge lambda · worker · trigger
infra/                    CDK — audit stack and agent stack
mocks/fixtures/           synthetic data; local mode never hits the network
manifest/                 Slack app manifest
docs/                     requirements · architecture · hosting options ·
                          operations · decisions · open questions
```

```bash
make demo     # end to end against mocks, no credentials
make dev      # against a real Slack workspace via Socket Mode
make test     # 20 tests — the audit log and the read-only guarantee
make audit    # read the local action log
make synth    # render CloudFormation without deploying
make deploy   # audit stack first, then the agent
```

---

## A note on the timeline

The 8/7 ask was a pilot group holding something by end of week. That goal
survives: this runs in one command against mocks, and needs one Slack app plus
one AWS account to run for real. The week was never the problem. The problem was
that nobody had written down what the thing was supposed to do — which is why
[docs/01-requirements.md](docs/01-requirements.md) is the first file, and the
code is the demonstration that the requirements hold together.
