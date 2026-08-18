# Adding a connector

The tool list is not known. That is the honest state of the requirement, so the
repo optimizes for the thing that will actually happen: someone at Frontline
discovers the agent needs a system nobody mentioned, and adds it.

This should take under an hour. Here is the whole job.

## 1. Write the file

`src/frontline_agent/connectors/productboard.py`:

```python
from ..config import get_settings
from . import _transport
from .base import Connector, DataClass, Risk

connector = Connector(
    name="productboard",
    description="Feature requests and customer feedback.",
    provider=get_settings().productboard_provider_id,
)


@connector.tool(
    "search_features",
    "Search feature requests by keyword. Use for demand signal on a theme.",
    {
        "type": "object",
        "properties": {"query": {"type": "string"}},
        "required": ["query"],
    },
    risk=Risk.READ,
    data_class=DataClass.CONFIDENTIAL,
)
async def search_features(args, *, token):
    return await _transport.call(
        "productboard",
        "search_features",
        url=f"{get_settings().productboard_base_url}/features",
        token=token,
        params={"q": args["query"]},
    )
```

That is the entire pattern. `token` arrives already resolved from the vault; you
never handle a credential.

## 2. Choose the labels honestly

This is the only part that requires thought, and it is the part that matters most
later.

**`risk`** — what happens if this fires when it should not?

| | |
|---|---|
| `READ` | Nothing changes anywhere. |
| `WRITE_INTERNAL` | Changes Frontline state. A human can undo it. |
| `WRITE_EXTERNAL` | Leaves the building. Cannot be undone. |

The line is reversibility, not importance. Creating a Jira ticket is
`WRITE_INTERNAL` even in a critical project. Posting in a customer Slack Connect
channel is `WRITE_EXTERNAL` even if it says "hi".

**`data_class`** — what is the *most* sensitive thing this could return, not what
it usually returns.

| | |
|---|---|
| `PUBLIC` | Already outside the company. |
| `INTERNAL` | Ordinary company data. Roadmaps, tickets, docs. |
| `CONFIDENTIAL` | Commercially sensitive. Metrics, pipeline, private channels. |
| `REGULATED` | FERPA / HIPAA-adjacent reach. Student records, IEP data, Medicaid billing. |

`REGULATED` is a reachability test, not a typical-case test. A query endpoint
that *could* return student rows is `REGULATED` even if every query so far has
returned counts. Getting this right is what keeps student data out of the audit
log — records at that class store a digest instead of arguments and results.

Nothing enforces these labels in v1 (see
[ADR-003](decisions/ADR-003-unrestricted-with-audit.md)). They are the instrument
for deciding what to enforce later. A mislabelled tool is invisible to that
decision.

## 3. Register it

In `connectors/registry.py`, `get_registry()`:

```python
from . import productboard
_registry.register(productboard.connector)
```

## 4. Add fixtures

`mocks/fixtures/productboard.search_features.json` — one file per operation,
named `<connector>.<operation>.json`. Synthetic data only; do not paste real
exports into this directory.

Without a fixture, `make demo` fails loudly on that tool rather than silently
reaching for the network. That is intentional.

## 5. Register the credential provider

In AgentCore Identity, create an OAuth2 credential provider named to match
`provider`, then set `PRODUCTBOARD_PROVIDER_ID` in the environment. The first
time the agent calls the tool, the principal gets a one-tap consent link in
Slack. No further action.

## 6. Run the tests

```bash
make test
```

`test_every_tool_declares_risk_and_data_class` will fail if you skipped step 2,
and `test_gateway_target_marks_read_tools_read_only` will fail if the risk label
disagrees with the MCP `readOnlyHint` an external client would act on.

## What you did not have to do

No changes to the agent loop, the Slack layer, the audit writer, the IAM policy,
or the prompt. The tool appears in the agent's toolset on next start, appears in
the Gateway manifest for other agents, and is audited on every call — because
those are properties of the registry, not of your connector.
