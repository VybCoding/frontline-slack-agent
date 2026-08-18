# Open questions

Everything here is either unknown to me, unresolved by the source material, or a
deliberate gap. Listing them is the point — a scaffold that pretends these are
settled is worse than useless, because it hides where the work is.

Ordered by how much they would change the build.

---

## Blocking before the pilot expands past the named users

### 1. There is no kill switch

ADR-003 accepts unrestricted operation on the basis that the audit log and the
streamed timeline are the controls. Neither stops a turn in progress. The nearest
available action is setting the worker's reserved concurrency to zero, which is a
console operation, not a product feature.

**What it needs:** a `/stop` affordance in Slack that sets a flag the agent loop
checks between tool calls, plus a global disable. Perhaps a day of work. It is
listed as blocking because "we ran it unrestricted with no way to stop it" is a
sentence that ends a pilot.

### 2. Cost is bounded per turn, but not governed

A hard per-turn ceiling exists — `max_turn_budget_usd`, default $2.00, enforced by
the SDK, which aborts the loop when spend crosses it. That bounds the single worst
case: a runaway loop on an unrestricted agent.

It is not cost governance. Still missing: per-session and per-principal
attribution, an aggregate cap, and alerting. Roper's cost-control gate is
explicitly named as a precondition for expansion past the named users, and a
per-turn ceiling will not satisfy it.

**What it needs:** token counts and cost recorded on each audit record (available
from the SDK's `ResultMessage`), a rolling budget per principal, and a CloudWatch
alarm. The audit table is already the right place to put all three.

### 3. Retention and access policy for the audit log

The table has `RETAIN` and streams to a versioned S3 bucket. Nobody has said for
how long, who may read it, or whether it needs S3 Object Lock. It contains a
record of an executive's activity, which makes it sensitive in a second,
non-obvious way: it is a surveillance artifact as well as a compliance one.

**Decision needed from:** Legal and Security, jointly. Not an engineering call.

---

## Unknowns about Frontline's environment

I have no visibility into any of these. Each has a real chance of changing the
architecture.

### 4. Is AgentCore available and permitted in the account?

The whole identity model rests on AgentCore Identity. `identity/token_vault.py`
isolates it behind one interface, and a Secrets Manager + custom OAuth broker
implementation is roughly a day — but if the answer is no, that day should be
spent before anything else.

### 5. Is Bedrock model access enabled for Claude in the region?

Not on by default. Requires an account-level request. Blocks the first real run.

### 6. Enterprise Grid app approval — who, and how long?

`org_deploy_enabled: true` is set, but installing a custom app with user scopes
on Grid needs org admin approval, and `search:read` plus `chat:write` on a user
token is the kind of request that gets a second look. **Start this before
anything else.** It is the longest-lead item and it is entirely out of
engineering's hands.

### 7. Is the Real-Time Search API entitled for the workspace?

RTS is the correct retrieval path — permission-aware, no data export, built for
this. It went closed beta in 2025 with GA signalled for early 2026, so it is
plausibly available now, but entitlement per workspace is unverified. Until
confirmed, `connectors/slack_search.py` uses `search.messages`, which works and
is the documented fallback.

### 8. Do the specialized Product OS agents expose anything callable?

R5 says the PA delegates to them. platform engineering's router tickets
(six tickets) suggest this is being built
separately. Today's subagents are locally-defined scoped variants — real, but not
the real thing.

**What I need to know:** do those agents expose A2A endpoints, MCP servers, or
HTTP APIs? Each answer is a different integration and only one of them is
trivial.

### 9. What is the actual tool list?

The connectors here are inferences. Atlassian and analytics are near-certain for
a CPO. Salesforce is inferred from Frontline being Roper-owned with Slack in the
stack.

**Resolved since first draft:** Workspace/M365 is not needed. Documents and
presentations are *generated* rather than integrated — the agent writes the
content and delivers it as a Slack canvas or an uploaded PPTX
(`connectors/artifacts.py`). This is better than a Workspace connector for the
phone-first case, since a canvas is readable and editable in place.

**Partly resolved:** the target machine has internal source access, so a `code`
connector is now built — read-only search, file read, and merged-PR history. It
is the highest-ceiling capability in the set, because a CPO normally receives the
product through three layers of summary.

Still unaddressed: **prototypes.** R3.2 names them and reading code does not
produce one. The hosted answer is AgentCore Code Interpreter — ephemeral sandbox,
repo clone, no push credentials — which is a few days of work and has not been
done. It is the largest remaining capability gap and the one most likely to be
raised, since a persistent daemon with a checkout can do it today.

Also unaddressed: whatever Frontline uses that an outsider would never guess.

---

## Design questions I answered by judgment

Flagged because reasonable people would answer differently, and because if any of
these is wrong it is better to find out from this list than from the code.

### 10. Slack `chat:write` on the user token

Retained, because "draft and send my reply" was explicitly asked for. It is
genuine impersonation — messages appear as if the principal wrote them. It is the
single most reviewable line in the manifest and the first thing I would remove if
Security pushed back on anything.

### 11. Salesforce writes are absent

Reads are broad; there are no write tools. Not a policy gate — a decision that a
CPO's Salesforce need is understanding, not data entry, and that a tool which
does not exist cannot fire by mistake. If the CPO wants to update an opportunity
from Slack, this is wrong and should be revisited.

### 12. Analytics is read-only by construction

Same reasoning, held more firmly. I would argue against ever adding a write tool
here.

### 13. Single-principal architecture

Built for one person, per the brief. The pilot is seven. Extending means
per-principal vault entries and memory namespaces — real work, and better done
deliberately than by accident when the second user is added.

### 14. Slack context is stored in process memory

`slack/app.py` keeps last-known surface per user in a module-level dict. Correct
for Socket Mode; **wrong for Lambda**, where scale-out means it is not shared. It
needs a DynamoDB item with a TTL before the AWS path is used in anger. Marked in
the code.

### 15. Trigger catalogue is a guess

Autonomy is built (R6) but *what* it watches is three entries in
`triggers/catalog.py`: a morning brief, a weekly renewal sweep, and an
escalation hook. Those are inferences about what a CPO wants noticed.

The escalation trigger is **disabled** because it needs a Slack-to-EventBridge
forwarder that does not exist — a small Lambda subscribed to the relevant
channels that emits an EventBridge event. Shipped inert rather than silently
broken.

The right way to fix the catalogue is not a workshop; it is to run the two
scheduled triggers for a fortnight and let him say what he wishes it had told
him.

### 16. The code connector's safety depends on the OAuth grant, not just the code

There are no write tools, which handles the agent. It does not handle the
credential: if the registered GitHub provider is given a token with push scope,
that scope exists whether or not this codebase uses it, and anything else holding
the same grant can use it.

**Register the provider with read scope only.** This is a five-minute
configuration decision with a supply-chain-sized consequence, which is a bad
ratio to leave undocumented.

### 17. Unattended read-only is enforced at the toolset, not the credential

During an autonomous run the agent receives only `risk == READ` tools, so it
cannot write. But the *delegated tokens it holds* still carry write scope,
because they are the same grants used for interactive turns.

The enforcement is therefore in-process. A sufficiently novel failure — a bug in
the filter, a connector mislabelled `READ` — would not be caught by anything
downstream. The stronger form is a second set of read-scoped OAuth grants used
only for unattended runs, so the credential itself cannot write.

Worth doing before autonomy expands past the two scheduled triggers. Not worth
doing before then.

---

## API surfaces to verify before first deploy

Written against documented behaviour, not against a live account. Each is
isolated to one file:

- AgentCore Identity `get_resource_oauth2_token` shape —
  `identity/token_vault.py`. Most likely to have moved.
- AgentCore Memory `retrieve_memory_records` / `create_event` — `agent/memory.py`.
- AgentCore Gateway target manifest schema — `connectors/registry.py`.
- Slack streaming methods, called via `api_call` rather than typed helpers so an
  older `slack_sdk` does not break the build — `slack/surface.py`.
- `canvases.create` / `canvases.access_set` and `files_upload_v2` shapes —
  `connectors/artifacts.py`. Both need `canvases:write` and `files:write`, which
  are in the manifest but widen the approval request.
- Claude Agent SDK version pinning — `pyproject.toml` floors it rather than
  pinning; pin it before production.
