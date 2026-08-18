"""Runtime configuration.

Two modes, one code path:

  local  mock connectors, mock token vault, JSONL audit. Runs with no AWS account
         and no Frontline credentials. This is what `make demo` uses.
  aws    AgentCore Identity / Memory / Gateway, live connectors, DynamoDB audit.

Everything downstream branches on `settings.mode` and nothing else.
"""

from __future__ import annotations

from enum import StrEnum
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Mode(StrEnum):
    LOCAL = "local"
    AWS = "aws"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    mode: Mode = Mode.LOCAL

    # Slack
    slack_bot_token: str = ""
    slack_signing_secret: str = ""
    slack_app_token: str = ""
    slack_user_token: str = ""
    principal_slack_user_id: str = ""

    # Model
    claude_code_use_bedrock: str = "1"
    aws_region: str = "us-east-1"
    anthropic_model: str = "us.anthropic.claude-opus-4-5-20251101-v1:0"
    # Hard ceiling per turn. The SDK aborts the loop when spend crosses this.
    # Not full cost governance (see docs/open-questions.md) but it does bound
    # the single worst case: a runaway loop on an unrestricted agent.
    max_turn_budget_usd: float = 2.00

    # AgentCore
    agentcore_memory_id: str = ""
    agentcore_gateway_url: str = ""
    agentcore_workload_identity: str = "frontline-cpo-agent"

    # Audit
    audit_table_name: str = "frontline-agent-audit"
    audit_local_path: str = ".audit/actions.jsonl"

    # Connectors
    atlassian_provider_id: str = "atlassian-oauth"
    atlassian_site_url: str = ""
    salesforce_provider_id: str = "salesforce-oauth"
    salesforce_instance_url: str = ""
    analytics_provider_id: str = "analytics-oauth"
    analytics_base_url: str = ""

    @property
    def is_local(self) -> bool:
        return self.mode is Mode.LOCAL


@lru_cache
def get_settings() -> Settings:
    return Settings()
