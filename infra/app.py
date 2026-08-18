#!/usr/bin/env python3
"""CDK entry point.

Two stacks, split on lifecycle rather than on component:

  AuditStack   the record of what the agent did. Longer retention than the agent
               itself, separate deletion policy, and it must survive the agent
               being torn down and rebuilt. Deploy it first; destroy it last.

  AgentStack   everything that runs.

Terraform note: if Frontline standardizes on Terraform (common across Roper
portfolio companies), the module boundaries here port directly — AuditStack maps
to one module with its own state, AgentStack to another consuming its outputs.
Nothing in these stacks uses a CDK-only construct that lacks a Terraform
equivalent, which was a constraint on how they were written, not an accident.
"""

import os

import aws_cdk as cdk
from stacks.agent_stack import AgentStack
from stacks.audit_stack import AuditStack

app = cdk.App()

env = cdk.Environment(
    account=os.environ.get("CDK_DEFAULT_ACCOUNT"),
    region=os.environ.get("CDK_DEFAULT_REGION", "us-east-1"),
)

audit = AuditStack(app, "FrontlineAgentAudit", env=env)
AgentStack(app, "FrontlineAgent", audit_table=audit.table, env=env)

app.synth()
