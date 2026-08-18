# Where the agent should run

The stated preference is to run something like Hermes on a company PC at home,
interfacing with Slack and orchestrating without constant human intervention.
This document takes that seriously, says what it would actually buy, says what it
would cost, and recommends something else — while conceding the one situation in
which it is the right call.

The short version: **the requirement is real, the mechanism is wrong, and the gap
between them is about a week.**

---

## 1. What is actually being asked for

Two requirements arrived in one sentence and have been treated as one ever since:

- **Slack is the interface.** How he talks to it.
- **It works without constant human intervention.** When it runs.

These are independent. Slack being the interface says nothing about what wakes
the agent up. Conflating them is what makes a self-hosted daemon look necessary —
if the only way to get autonomy is a process that runs on its own, and the only
process you can stand up this week is one on your own machine, then the machine
follows from the autonomy.

It doesn't. Autonomy is a trigger, and triggers are cheap.

## 2. What the PC route actually buys

Stated fairly, because it is not a bad idea and dismissing it as one would be
dishonest.

1. **Autonomy out of the box.** Heartbeat daemon, scheduled tasks, wakes up on
   its own. This is the genuine want.
2. **Universal access by brute force.** Logged-in browser sessions, VPN, SSO
   cookies, apps with no API at all. If he can click it, the agent can click it.
   No connector to write, no integration to specify — which matters enormously
   when nobody has enumerated the systems yet.
3. **Zero integration work.** No OAuth provider registration, no app manifest,
   no scopes.
4. **No procurement, no security review, no admin approval.** It is his machine.

Points 3 and 4 are the real reason this option keeps coming up, and they are
worth naming: **the sanctioned path has lead times, and this one has none.**
That is not recklessness — it is a reasonable response to a real constraint, and
it is what makes the option attractive. Any recommendation that does not compete
on time-to-value will lose to it, and should.

## 3. The threat model, corrected

The intuition that source-code access is the thing to protect is understandable
and, here, misleading. It suggests that a machine without repo access is a
low-risk machine. The opposite is closer to true.

**What matters on that machine is not code. It is sessions.** A CPO's browser
holds live authenticated sessions into Salesforce, the product admin console,
analytics, and email. That set reaches district contracts and student-adjacent
records *directly* — no build step, no repository, no deploy. Measured by reach
into regulated data, it is a more dangerous machine than a developer's laptop,
not a safer one. The FERPA-relevant data was never in the source tree.

With that corrected, four risks are structural rather than configurable.

### 3.1 Prompt injection has an unbounded blast radius

This is the sharp edge and the one most often waved past.

An agent of this kind reads Slack messages, emails, Jira tickets, and web pages.
All of those are untrusted input, and all of them can contain instructions. An
agent with shell access and his credentials that reads untrusted content is,
functionally, a remote code execution path reachable by anyone who can email him
or post in a shared Slack Connect channel.

This is the characteristic failure mode of the product category rather than a
hypothetical. The useful question is not "will the model be fooled" but "what can
it reach when it is." On AWS with a fixed connector registry, the answer is the
declared tools and nothing else. With shell access on an endpoint, the answer is
everything the machine can reach.

### 3.2 Attribution cannot be recovered

Everything the agent does is recorded, everywhere downstream, as him. Salesforce,
Jira, Slack, email — every log shows a human.

There is no configuration that fixes this. It is a property of using his
credentials directly, and it is precisely what the platform architect's
scoped-identity principle exists to prevent.

The consequence is evidentiary rather than procedural. In a FERPA context, "who
accessed this record, when, and why" is a question with legal weight, and an
answer of "his account, repeatedly, overnight" opens an investigation rather than
closing one. There is no way to establish afterward which actions were his and
which were the agent's, because the distinction was never captured.

### 3.3 Data leaves the corporate boundary

Model calls go out over a home network to whatever provider the daemon is
pointed at. No DLP, no egress logging, no retention control, no data-processing
agreement covering it. Bedrock-in-account exists specifically so this does not
happen; running on a PC opts out of it by construction.

### 3.4 It cannot serve the pilot group

The ask was a small pilot — seven named users. A PC-hosted agent serves one
person. Seven users means seven unmanaged daemons on seven endpoints, each with a
different configuration, none observable centrally.

**This is the argument worth leading with**, because it is not a security
objection at all. The approach cannot serve the group the pilot was defined
around, which is a scoping fact rather than a matter of risk appetite.

### 3.5 The ordinary operational ones

- **Endpoint policy.** A persistent process running shell at boot with outbound
  WebSockets will either trip EDR or require an exception. The exception is the
  worse outcome, because it converts a personal setup into something the
  organization now owns.
- **Availability.** "Always-on collaborator" becomes "on when the laptop is
  open." He is now operating infrastructure, and he is the only one who can
  restart it.

---

## 4. The five routes

| | Time to first use | Autonomy | Attribution | Blast radius | Serves 7 users |
|---|---|---|---|---|---|
| **A** Hermes on his PC | days | full | none | unbounded | no |
| **B** Hermes on a managed VM | ~3 days | full | none | unbounded, contained | poorly |
| **C** This scaffold, Slack-triggered | ~1 week | none | full | bounded | yes |
| **D** This scaffold + triggers | ~1 week | full | full | bounded | yes |
| **E** Slackbot MCP Client | ~2 days | none | partial | bounded | yes |

### A — Hermes / OpenClaw on the company PC

Covered above. **Not recommended under any timeline.** The disqualifier is not
the risk register; it is 3.4.

### B — The same software on a company-managed VM

The honest middle, and it deserves better than a strawman.

**For:** it is the software he asked for, so it wins on preference and on
familiarity. Moving it to a managed instance removes the endpoint-policy conflict
entirely, puts it behind a corporate network boundary, makes it monitorable,
gives it real uptime, and lets somebody other than him restart it. Standing one
up is genuinely about three days.

**Against:** it moves the box without changing the model. Still a single-user
daemon. Still local SQLite for memory. Still shell access, so 3.1 is unchanged.
Still credentials in environment, so 3.2 is unchanged. Still one user, so 3.4 is
unchanged. What improves is containment and observability — real gains, but they
address the least severe items on the list.

**Use it when:** speed genuinely dominates and there is a hard date. See §6.

### C — This scaffold as originally built

Slack message in, agent turn, response out. Delegated OAuth, bounded tools, full
audit.

**Against:** no autonomy at all. Fails the actual requirement. Listed only
because it is what existed before this document, and the delta to D is the point.

### D — This scaffold plus triggers  ← **recommended**

C, plus EventBridge Scheduler and event rules as a second entry point into the
same workload.

- A schedule fires. The agent runs with a standing instruction — *"every weekday
  at seven, check renewals inside ninety days against health score and open
  cases."*
- The run is **read-only, enforced structurally**: `allowed_tools` is filtered to
  `risk == READ` before the loop starts, so write tools are absent from the
  model's toolset rather than merely discouraged.
- If nothing clears the bar for interrupting him, nothing is posted. Silence is
  the normal output.
- If something does, it lands in his DM with what it proposes to do.
- **His reply resumes the interactive path, where writes are allowed again.**

That last line is the whole design. Presence is the authorization. There is no
approval workflow, no buttons, no second UI — he replies to a message, which is
what he was going to do anyway. The gate is invisible because it is just the
conversation.

**For:** satisfies both halves of the requirement. Attribution intact. Blast
radius bounded to declared tools even during unattended runs, and narrower then
than during interactive ones. Scales to seven users and beyond. Survives review.

**Against:** the systems it can reach are the systems somebody wrote a connector
for. That is a real ceiling and the honest counter to point 2 in §2 — brute-force
access via a logged-in browser genuinely covers things an API connector does not.
The mitigation is that adding a connector is under an hour
([03-adding-a-connector.md](03-adding-a-connector.md)), and that the set of
systems a CPO actually needs is small and knowable.

Also against: it needs Bedrock enabled, AgentCore available, and Enterprise Grid
app approval. The last is the long pole and is outside engineering's control.

### E — Slackbot MCP Client

Slack calls *your* MCP server; Slackbot's own model does the orchestration. No
app runtime, no three-second acknowledgement problem, tool confirmation built in,
about two days of work.

**Disqualified by the requirement.** You do not own the loop, so there is no
custom memory and no subagent delegation; tools must answer within sixty seconds;
and third-party tool calls require the user to authorize **every single
invocation**. That is the precise opposite of "without constant human
intervention."

Worth keeping in view as a fast way to expose Frontline capabilities to Slackbot
for *other* people later. It is not the personal agent.

---

## 5. Recommendation

**Build D.** It is the only route that satisfies both halves of the requirement
while remaining defensible, and it is roughly a week — not meaningfully slower
than B once app approval is running in parallel, which it can be from day one.

Sequenced:

1. **Today.** Start Enterprise Grid app approval and the Bedrock model-access
   request. Both are queues, neither needs code, and either will become the
   critical path if left until it is needed.
2. **Days 1–3.** Deploy C against his account with two or three connectors.
   Interactive only. He is using something real by mid-week.
3. **Days 4–5.** Enable the morning brief and renewal watch. Autonomy arrives
   read-only, which is the version nobody has to argue about.
4. **Week 2+.** Widen connectors based on what he actually reaches for, using the
   audit log rather than a planning meeting. Decide on gating using the
   accumulated `risk` and `data_class` evidence
   ([ADR-003](decisions/ADR-003-unrestricted-with-audit.md)).

## 6. If speed truly dominates

If there is a hard date this week and D cannot make it, **B is the fallback, not
A** — and only with all four of the following:

- A company-managed instance in a VPC, not an endpoint. Not his laptop.
- **No regulated systems.** No Salesforce, no student-adjacent data, no
  production admin console. Jira, Confluence, and Slack only.
- A **written decommission date**, because a temporary agent with credentials is
  the single most reliable way to acquire a permanent one nobody owns.
- Its own service account rather than his personal credentials. This costs some
  reach and recovers most of §3.2, which is the item that cannot be fixed later.

The failure mode to avoid is not moving fast. It is moving fast, having it work,
and finding a year later that it is load-bearing and nobody owns it.
