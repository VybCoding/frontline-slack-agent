# Operations

## Run it locally, right now

No AWS account, no Slack workspace, no Frontline credentials.

```bash
make install
make demo
```

The demo runs a real scenario — a district renewal eight weeks out with an
unhealthy account and reasons scattered across three systems — then prints the
audit log with a redaction summary.

Two tiers, chosen automatically. Without model credentials it drives the
registry through a scripted sequence, proving the identity → connector → audit
path with no LLM. With Bedrock credentials reachable, it runs the real agent
loop.

## Connect a real Slack workspace

1. **Create the app.** api.slack.com/apps → Create New App → From a manifest →
   paste `manifest/slack-app-manifest.yaml`.
2. **Enable Socket Mode** for development. Basic Information → App-Level Tokens →
   generate one with `connections:write`. Set `socket_mode_enabled: true` in the
   manifest.
3. **Install to the workspace.** On Enterprise Grid this needs org admin
   approval; `org_deploy_enabled: true` is already set. Expect this to be the
   slowest step by a wide margin — start it before you need it.
4. **Fill in `.env`:** `SLACK_BOT_TOKEN`, `SLACK_SIGNING_SECRET`,
   `SLACK_APP_TOKEN`, `PRINCIPAL_SLACK_USER_ID`.
5. `make dev`, then DM the app.

Still `FRONTLINE_AGENT_MODE=local` at this point — real Slack, mock upstreams.
A useful intermediate state: the interface is real, nothing can be broken.

## Deploy to AWS

**Prerequisites.** Bedrock model access enabled for Claude in the target region
(it is not on by default). AgentCore available in the account. CDK bootstrapped.

```bash
cd infra
cdk deploy FrontlineAgentAudit     # first, and separately
cdk deploy FrontlineAgent
```

Audit first and on its own, deliberately: it has `RETAIN` and must exist before
anything can write to it. It is also the stack you never destroy.

**After the first deploy**

1. Take `SlackRequestUrl` from the stack output; put it in the manifest as
   `request_url` for both events and interactivity. Set
   `socket_mode_enabled: false`.
2. Put the signing secret and bot token in the `frontline-agent/slack` secret.
3. Create the AgentCore Memory store; set `AGENTCORE_MEMORY_ID`.
4. Register one OAuth2 credential provider per connector in AgentCore Identity,
   with IDs matching the `*_PROVIDER_ID` variables.
5. Set `FRONTLINE_AGENT_MODE=aws`.
6. Narrow the `bedrock-agentcore:*` policy in `agent_stack.py` from `*` to the
   specific memory and gateway ARNs now that they exist. This is left wide on
   purpose so the first deploy works, and it is a real finding if it stays wide.

## Autonomous triggers

Defined in `src/frontline_agent/triggers/catalog.py`, deployed as EventBridge
Scheduler schedules by `cdk deploy FrontlineAgent`. Adding one is an entry in the
catalogue and a redeploy; removing one is deleting it. Disabled triggers are not
deployed at all, so what exists in the account matches what is in the file.

Run one by hand without waiting for its schedule:

```bash
aws lambda invoke --function-name frontline-agent-trigger \
  --payload '{"trigger":"morning-brief"}' --cli-binary-format raw-in-base64-out /dev/stdout
```

A response of `{"posted": false, "reason": "nothing to report"}` is the expected
outcome most mornings. That is the design, not a failure — see
`triggers/base.py`.

Unattended runs are read-only, enforced by filtering the toolset before the loop
starts. If a trigger appears to have written something, that is a bug worth
treating as an incident, and the audit log will name the tool.

## Reading the audit log

Local:

```bash
make audit
```

AWS — the two questions that will actually be asked:

```bash
# Everything irreversible in the last 30 days
aws dynamodb query --table-name frontline-agent-audit --index-name by-risk \
  --key-condition-expression "risk = :r AND #ts > :since" \
  --expression-attribute-names '{"#ts":"timestamp"}' \
  --expression-attribute-values '{":r":{"S":"write_external"},":since":{"S":"2026-07-19"}}'
```

```bash
# Everything that touched regulated data
aws dynamodb query --table-name frontline-agent-audit --index-name by-data-class \
  --key-condition-expression "data_class = :d" \
  --expression-attribute-values '{":d":{"S":"regulated"}}'
```

## Stopping it

There is no kill switch in v1 (ADR-003, and flagged in open-questions). In order
of speed, the available options are:

1. Revoke the principal's consent for one provider in the AgentCore Identity
   vault — surgical, stops one system.
2. Disable event subscriptions in the Slack app — stops new turns, does not stop
   one already running.
3. Set the worker's reserved concurrency to zero — stops everything, including
   turns in flight.

Option 3 is the real answer and it is a console action, not a product feature.
That gap is deliberate and documented, not overlooked.

## Cost

Bounded, not governed. `MAX_TURN_BUDGET_USD` (default $2.00) is a hard ceiling the
SDK enforces by aborting the loop, so a single runaway turn cannot escalate. Raise
it for research-heavy work; lower it while testing.

Beyond that there is nothing: Bedrock spend appears in Cost Explorer but is not
attributed per principal, not capped in aggregate, and not alerted on. Seven
pilot users bounds it in practice, not in policy. Roper's cost-control gate will
need the rest before expansion — see open-questions.

## Terraform

If Frontline standardizes on Terraform, the two CDK stacks port directly: the
audit stack becomes one module with its own state file, the agent stack another
consuming its outputs. Nothing in either stack uses a CDK-only construct without
a Terraform equivalent — that was a constraint on how they were written.
