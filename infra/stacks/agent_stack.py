"""Agent infrastructure.

    Slack ──HTTPS──▶ API Gateway ──▶ events Lambda ──async──▶ worker
                                     (verify, 3s ack)          (agent turn)
                                                                   │
                                              ┌────────────────────┼─────────────┐
                                              ▼                    ▼             ▼
                                        AgentCore            Bedrock        Audit table
                                    Identity / Memory        (Claude)       (PutItem only)
                                        / Gateway

The three-second rule shapes the whole left half of that diagram. Slack retries
any event it does not get a 2xx for within three seconds, and with an
unrestricted agent a retried turn can mean a second Jira ticket or a second
message to a customer. So the edge function verifies and acknowledges, and
never does work.

The worker is a Lambda here for deployability. For long research turns, point
the same handler at AgentCore Runtime instead — eight-hour sessions with per-
session isolation, versus Lambda's fifteen-minute ceiling. The code does not
change; only what invokes it does.
"""

from __future__ import annotations

import aws_cdk as cdk
from aws_cdk import aws_apigateway as apigw
from aws_cdk import aws_dynamodb as dynamodb
from aws_cdk import aws_events as events
from aws_cdk import aws_events_targets as targets
from aws_cdk import aws_iam as iam
from aws_cdk import aws_lambda as lambda_
from aws_cdk import aws_logs as logs
from aws_cdk import aws_scheduler as scheduler
from aws_cdk import aws_secretsmanager as secrets
from constructs import Construct


class AgentStack(cdk.Stack):
    def __init__(
        self, scope: Construct, construct_id: str, *, audit_table: dynamodb.Table, **kwargs
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Slack signing secret and bot token. The connector credentials are NOT
        # here — those live in the AgentCore Identity token vault as
        # user-delegated OAuth grants (ADR-001). This secret holds only what
        # belongs to the app itself rather than to the principal.
        slack_secret = secrets.Secret(
            self,
            "SlackAppSecret",
            secret_name="frontline-agent/slack",
            description="Slack signing secret and bot token for the Frontline Agent.",
        )

        common_env = {
            "FRONTLINE_AGENT_MODE": "aws",
            "AUDIT_TABLE_NAME": audit_table.table_name,
            "CLAUDE_CODE_USE_BEDROCK": "1",
            "AGENTCORE_WORKLOAD_IDENTITY": "frontline-cpo-agent",
            "SLACK_SECRET_ARN": slack_secret.secret_arn,
        }

        code = lambda_.Code.from_asset("../src")

        worker = lambda_.Function(
            self,
            "Worker",
            function_name="frontline-agent-worker",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="frontline_agent.runtime.handler_worker.handler",
            code=code,
            timeout=cdk.Duration.minutes(15),
            memory_size=2048,
            environment=common_env,
            log_retention=logs.RetentionDays.SIX_MONTHS,
        )

        audit_table.grant(worker, "dynamodb:PutItem")
        slack_secret.grant_read(worker)

        worker.add_to_role_policy(
            iam.PolicyStatement(
                actions=["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"],
                resources=["arn:aws:bedrock:*::foundation-model/anthropic.claude-*",
                           "arn:aws:bedrock:*:*:inference-profile/*"],
            )
        )
        worker.add_to_role_policy(
            iam.PolicyStatement(
                actions=[
                    "bedrock-agentcore:GetResourceOauth2Token",
                    "bedrock-agentcore:GetWorkloadAccessToken",
                    "bedrock-agentcore:RetrieveMemoryRecords",
                    "bedrock-agentcore:CreateEvent",
                    "bedrock-agentcore:InvokeAgentRuntime",
                ],
                resources=["*"],  # narrow to specific memory/gateway ARNs once created
            )
        )

        events = lambda_.Function(
            self,
            "Events",
            function_name="frontline-agent-events",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="frontline_agent.runtime.handler_events.handler",
            code=code,
            # Short on purpose. This function must never be the reason Slack
            # waits: it verifies, dispatches, and returns.
            timeout=cdk.Duration.seconds(10),
            memory_size=512,
            environment={**common_env, "WORKER_FUNCTION_NAME": worker.function_name},
            log_retention=logs.RetentionDays.SIX_MONTHS,
        )

        worker.grant_invoke(events)
        slack_secret.grant_read(events)

        api = apigw.LambdaRestApi(
            self,
            "SlackApi",
            handler=events,
            proxy=False,
            deploy_options=apigw.StageOptions(
                stage_name="prod",
                throttling_rate_limit=20,
                throttling_burst_limit=40,
                metrics_enabled=True,
            ),
        )
        api.root.add_resource("slack").add_resource("events").add_method("POST")

        # --- autonomous triggers ------------------------------------------
        # The workload has two entry points, not one: a human message, and a
        # schedule. Same agent, same audit path, different authorization —
        # unattended runs are read-only, enforced in triggers/base.py by
        # filtering the toolset rather than by asking the model nicely.
        trigger_fn = lambda_.Function(
            self,
            "Trigger",
            function_name="frontline-agent-trigger",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="frontline_agent.runtime.handler_trigger.handler",
            code=code,
            timeout=cdk.Duration.minutes(15),
            memory_size=2048,
            environment=common_env,
            log_retention=logs.RetentionDays.SIX_MONTHS,
        )
        audit_table.grant(trigger_fn, "dynamodb:PutItem")
        slack_secret.grant_read(trigger_fn)
        for statement in worker.role.node.try_find_child("DefaultPolicy").document.statements:
            trigger_fn.add_to_role_policy(statement)

        scheduler_role = iam.Role(
            self,
            "SchedulerRole",
            assumed_by=iam.ServicePrincipal("scheduler.amazonaws.com"),
        )
        trigger_fn.grant_invoke(scheduler_role)

        self._add_triggers(trigger_fn, scheduler_role)

        cdk.CfnOutput(
            self,
            "SlackRequestUrl",
            value=f"{api.url}slack/events",
            description="Paste into the Slack app manifest as request_url.",
        )

    def _add_triggers(self, fn: lambda_.Function, role: iam.Role) -> None:
        """One EventBridge entry per trigger in the catalog.

        Scheduled triggers become EventBridge Scheduler schedules; event-driven
        ones become rules. Disabled triggers are skipped entirely rather than
        deployed in a paused state, so what exists in the account matches what is
        in the catalog.
        """
        import sys
        from pathlib import Path

        sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
        from frontline_agent.triggers.catalog import enabled_triggers

        for trigger in enabled_triggers():
            payload = f'{{"trigger": "{trigger.name}"}}'

            if trigger.schedule:
                scheduler.CfnSchedule(
                    self,
                    f"Schedule{trigger.name.title().replace('-', '')}",
                    flexible_time_window=scheduler.CfnSchedule.FlexibleTimeWindowProperty(
                        mode="FLEXIBLE", maximum_window_in_minutes=15
                    ),
                    schedule_expression=trigger.schedule,
                    schedule_expression_timezone="America/New_York",
                    target=scheduler.CfnSchedule.TargetProperty(
                        arn=fn.function_arn, role_arn=role.role_arn, input=payload
                    ),
                )
            else:
                rule = events.Rule(
                    self,
                    f"Rule{trigger.name.title().replace('-', '')}",
                    event_pattern=events.EventPattern(**_to_pattern(trigger.event_pattern)),
                )
                rule.add_target(
                    targets.LambdaFunction(fn, event=events.RuleTargetInput.from_text(payload))
                )


def _to_pattern(pattern: dict) -> dict:
    """EventBridge pattern keys are kebab-case on the wire, snake_case in CDK."""
    return {key.replace("-", "_"): value for key, value in pattern.items()}
