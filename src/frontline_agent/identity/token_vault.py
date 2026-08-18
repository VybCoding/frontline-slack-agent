"""Credential resolution.

The decision on record is that the agent acts with the principal's access
throughout (ADR-001). The naive reading of that is "put the CPO's tokens in the
environment", which is what a self-hosted personal agent does and what this
deliberately does not do.

Instead, every credential is a *user-delegated OAuth token* held in AgentCore
Identity's token vault:

  - the agent authenticates as a workload identity, which is its own principal
    with its own IAM trail
  - it exchanges that for a token the principal consented to issue, per provider
  - the vault refreshes it; the process never sees a long-lived secret
  - revoking consent for one provider does not require rotating anything else

So downstream systems see the CPO's access, and the audit trail sees the agent.
Both requirements are satisfied at once, which is the thing the original brief
treated as a contradiction.

Local mode swaps in a mock that returns fake tokens so the repo runs with no
AWS account and no real credentials anywhere.
"""

from __future__ import annotations

from ..config import get_settings


class TokenVault:
    async def token_for(self, provider: str | None, *, principal: str) -> str | None:
        raise NotImplementedError  # pragma: no cover - interface


class MockTokenVault(TokenVault):
    """Local mode. Returns a deterministic fake so connectors can be exercised."""

    async def token_for(self, provider: str | None, *, principal: str) -> str | None:
        if provider is None:
            return None
        return f"mock-token::{provider}::{principal}"


class AgentCoreTokenVault(TokenVault):
    """AWS mode.

    Wraps the AgentCore Identity three-legged OAuth flow. On a cache miss the
    service returns an authorization URL rather than a token; that URL is handed
    to the principal in Slack as a one-tap consent link, and the turn resumes
    once consent is granted.

    Verify the client shape against the AgentCore Identity API version you are
    on before first deploy — this is the interface most likely to have moved.
    """

    def __init__(self, workload_identity: str) -> None:
        import boto3

        self._client = boto3.client("bedrock-agentcore")
        self._workload_identity = workload_identity
        self._cache: dict[tuple[str, str], str] = {}

    async def token_for(self, provider: str | None, *, principal: str) -> str | None:
        if provider is None:
            return None

        key = (provider, principal)
        if key in self._cache:
            return self._cache[key]

        response = self._client.get_resource_oauth2_token(
            resourceCredentialProviderName=provider,
            workloadIdentityToken=self._workload_identity,
            userId=principal,
            oauth2Flow="USER_FEDERATION",
        )

        if url := response.get("authorizationUrl"):
            raise ConsentRequired(provider=provider, authorization_url=url)

        token = response["accessToken"]
        self._cache[key] = token
        return token


class ConsentRequired(Exception):
    """Raised when the principal has not yet authorized this provider.

    Caught in the Slack layer and rendered as a consent link rather than an
    error — the first time the agent touches Jira it asks for Jira, and only
    for Jira. Scope creep becomes visible to the principal at the moment it
    happens instead of being bundled into one install-time grant.
    """

    def __init__(self, *, provider: str, authorization_url: str) -> None:
        self.provider = provider
        self.authorization_url = authorization_url
        super().__init__(f"consent required for {provider}")


_vault: TokenVault | None = None


def get_token_vault() -> TokenVault:
    global _vault
    if _vault is None:
        settings = get_settings()
        _vault = (
            MockTokenVault()
            if settings.is_local
            else AgentCoreTokenVault(settings.agentcore_workload_identity)
        )
    return _vault
