# ADR-004 — Claude Agent SDK, running on Amazon Bedrock

**Status:** accepted · **Date:** 2026-08-18

## Context

Frontline runs on AWS. The agent needs a tool-calling loop, subagent delegation,
and persistent memory, and it must not create a new data-egress path.

## Decision

Claude Agent SDK (Python) with `CLAUDE_CODE_USE_BEDROCK=1`, models served from
Bedrock in Frontline's own account.

Why this combination:

- **Delegation is native.** `AgentDefinition` subagents map directly onto the
  requirement to route work to specialized Product OS agents. Today they are
  scoped variants defined in `agent/core.py`; when those agents expose A2A or MCP
  endpoints, the definitions become remote references and nothing else changes.
- **Tools are MCP.** The connector registry emits both in-process SDK tools and
  an AgentCore Gateway target manifest from the same definitions, so capabilities
  are shared infrastructure rather than private to this agent's codebase.
- **No new egress.** Inference happens inside the AWS account, under IAM, billed
  through AWS. There is no Anthropic API key anywhere in the deployment.
- **Memory is a first-class concept** rather than context stuffing.

## Consequences

- Model choice is constrained to what Bedrock offers in the deployment region.
  Fine — Claude is the target.
- The SDK's default tool surface includes filesystem and shell. Both are disabled
  (`setting_sources=[]`, and only registry tools in `allowed_tools`). This is
  deliberate and is the enforcement point for ADR-002; a future change that
  loosens `allowed_tools` reopens that decision and should be reviewed as such.
- `permission_mode="bypassPermissions"` implements ADR-003. It is the one line to
  change when the pilot adopts gating, and it is deliberately not buried.
