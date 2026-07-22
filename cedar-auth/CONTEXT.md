# Cedar Authorization

Cedar Authorization evaluates [Cedar](https://cedarpolicy.com/) policies before each tool call, giving you declarative, identity-aware access control over agent behavior. It ships as a vended intervention handler in both the Python and TypeScript SDKs.

## How it works

The handler sits at the tool-call boundary. When the agent attempts to invoke a tool, Cedar Authorization maps the call to a Cedar authorization request and evaluates your policies. If no `permit` statement matches, the tool call is denied and the agent receives feedback explaining the denial.

| Cedar concept | Maps to | Example |
| --- | --- | --- |
| **Principal** | User identity | `User::"alice@acme.com"` |
| **Action** | Tool name | `Action::"search"` |
| **Resource** | Static (unconstrained) | `Resource::"agent"` |
| **Context.input** | Tool arguments | `{ query: "quarterly report" }` |
| **Context.session** | Invocation metadata | `{ hour_utc: 14, call_count: 3, role: "admin" }` |

The design is fail-closed: if principal identity cannot be resolved, all tool calls are denied.

## Basic usage

Permit specific tools and deny everything else:

- [Python](#tab-panel-1725)
- [TypeScript](#tab-panel-1726)

```python
from strands import Agent, tool
from strands.vended_interventions.cedar import (
    CedarAuthorization,
)

@tool
def search(query: str) -> str:
    """Search for information."""
    return f"Results for: {query}"

@tool
def delete_record(record_id: str) -> str:
    """Delete a record by ID."""
    return f"Deleted {record_id}"

cedar = CedarAuthorization(
    policies=(
        'permit(principal, action == Action::"search",'
        " resource);"
    ),
)

agent = Agent(
    tools=[search, delete_record],
    interventions=[cedar],
)

agent(
    "Search for quarterly reports then delete record 42"
)
# search is permitted; delete_record is denied
# (no matching permit)
```

Cedar uses default-deny semantics. Tools without a matching `permit` statement are automatically blocked.

## Role-based access control

For multi-tenant agents where each request carries user identity, use

`principal_resolver`

to extract the principal from

`invocation_state`

and

`context_enricher`

to forward role information into Cedar context:

- [Python](#tab-panel-1713)
- [TypeScript](#tab-panel-1714)

```python
from strands import Agent, tool
from strands.vended_interventions.cedar import (
    CedarAuthorization,
)

@tool
def search(query: str) -> str:
    """Search for information."""
    return f"Results for: {query}"

@tool
def delete_record(record_id: str) -> str:
    """Delete a record by ID."""
    return f"Deleted {record_id}"

cedar = CedarAuthorization(
    policies="""
      permit(principal, action, resource)
      when { context.session.role == "admin" };

      permit(
        principal,
        action == Action::"search",
        resource
      )
      when { context.session.role == "analyst" };
    """,
    principal_resolver=lambda state: (
        {"type": "User", "id": state["user_id"]}
        if state.get("user_id")
        else None
    ),
    context_enricher=lambda ctx: {
        "role": ctx["invocation_state"].get(
            "role", "none"
        ),
    },
)

agent = Agent(
    tools=[search, delete_record],
    interventions=[cedar],
)

# admin can use any tool
agent(
    "Delete record 42",
    invocation_state={
        "user_id": "alice",
        "role": "admin",
    },
)

# analyst can only search
agent(
    "Delete record 42",
    invocation_state={
        "user_id": "bob",
        "role": "analyst",
    },
)
# denied: no permit for delete_record with "analyst"
```

When

`principal_resolver`

returns

`None`

(no identity found), the handler denies all tool calls for that request.

## Rate limiting

Cedar policies can reference `context.session.call_count`, which tracks how many times each tool has been invoked successfully during the session:

- [Python](#tab-panel-1715)
- [TypeScript](#tab-panel-1716)

```python
from strands import Agent, tool
from strands.vended_interventions.cedar import (
    CedarAuthorization,
)

@tool
def send_email(to: str, body: str) -> str:
    """Send an email."""
    return f"Sent to {to}"

@tool
def search(query: str) -> str:
    """Search for information."""
    return f"Results for: {query}"

cedar = CedarAuthorization(
    policies="""
      permit(
        principal,
        action == Action::"send_email",
        resource
      )
      when { context.session.call_count < 5 };

      permit(
        principal,
        action == Action::"search",
        resource
      );
    """,
)

agent = Agent(
    tools=[send_email, search],
    interventions=[cedar],
)

# send_email permitted for calls 1-4, denied on 5th
# search is unlimited
```

Call counts persist with the agent’s state and survive session reloads. Only successful tool calls increment the counter.

## Schema validation

Pass your tool definitions to catch policy typos at construction time. The handler generates a Cedar schema from tool definitions and validates policies against it:

- [Python](#tab-panel-1717)
- [TypeScript](#tab-panel-1718)

```python
from strands.vended_interventions.cedar import (
    CedarAuthorization,
    ToolDefinition,
)

search_def: ToolDefinition = {
    "name": "search",
    "inputSchema": {
        "type": "object",
        "properties": {
            "query": {"type": "string"}
        },
    },
}

delete_def: ToolDefinition = {
    "name": "delete_record",
    "inputSchema": {
        "type": "object",
        "properties": {
            "record_id": {"type": "string"}
        },
    },
}

# Valid policies pass schema validation
cedar = CedarAuthorization(
    policies="""
      permit(
        principal,
        action == Action::"search",
        resource
      );
      permit(
        principal,
        action == Action::"delete_record",
        resource
      )
      when { context.session.role == "admin" };
    """,
    tools=[search_def, delete_def],
    context_enricher=lambda ctx: {
        "role": ctx["invocation_state"].get(
            "role", "none"
        ),
    },
)

# A typo in the action name raises at construction:
# CedarAuthorization(
#     policies='permit(principal, action == Action::"deleet_record", resource);',
#     tools=[search_def, delete_def],
# )
# raises ValueError: Cedar policy validation failed:
#   unrecognized action "deleet_record"
```

Schema validation integrates with the [`cedar-for-agents`](https://github.com/cedar-policy/cedar-for-agents) ecosystem via `@cedar-policy/mcp-schema-generator-wasm` (TypeScript) and `cedar-policy-mcp-schema-generator` (Python).

## Namespaced policies

When using policy generators like [`cedar-agent-policy-builder`](https://github.com/cedar-policy/cedar-for-agents) that produce namespaced Cedar policies (e.g. `Agent::Action::"search"` instead of `Action::"search"`), set the `namespace` option to match:

- [TypeScript](#tab-panel-1712)

```typescript
import { Agent, tool } from '@strands-agents/sdk'
import { CedarAuthorization } from '@strands-agents/sdk/vended-interventions/cedar'
import { z } from 'zod'

const searchTool = tool({
  name: 'search',
  description: 'Search for information',
  inputSchema: z.object({ query: z.string() }),
  callback: (input) => \`Results for: ${input.query}\`,
})

const cedar = new CedarAuthorization({
  namespace: 'Agent',
  policies: \`
    permit(principal, action == Agent::Action::"search", resource);
  \`,
  tools: [searchTool],
  entities: [{ uid: { type: 'Agent::Resource', id: 'default' }, attrs: {}, parents: [] }],
  principalResolver: (state) => {
    if (!state.user_id) return undefined
    return { type: 'Agent::User', id: String(state.user_id) }
  },
})

const agent = new Agent({
  tools: [searchTool],
  interventions: [cedar],
})

await agent.invoke('Search for reports', {
  invocationState: { user_id: 'alice' },
})
```

When `namespace` is set:

| Cedar concept | Unnamespaced (default) | Namespaced (`namespace: 'Agent'`) |
| --- | --- | --- |
| **Action** | `Action::"search"` | `Agent::Action::"search"` |
| **Resource** | `Resource::"agent"` | `Agent::Resource::"default"` |
| **Default principal** | `User::"anonymous"` | `Agent::User::"anonymous"` |

Schema generation also uses the configured namespace, so `tools` and `namespace` work together correctly.

## Environment gating

Block tools based on deployment context by forwarding environment metadata through

`context_enricher`

:

- [Python](#tab-panel-1719)
- [TypeScript](#tab-panel-1720)

```python
from strands import Agent, tool
from strands.vended_interventions.cedar import (
    CedarAuthorization,
)

@tool
def deploy(version: str) -> str:
    """Deploy the service."""
    return f"Deployed {version}"

cedar = CedarAuthorization(
    policies="""
      permit(
        principal,
        action == Action::"deploy",
        resource
      )
      when {
        context.session has environment &&
        context.session.environment != "production"
      };
    """,
    context_enricher=lambda ctx: {
        "environment": ctx["invocation_state"].get(
            "environment", "unknown"
        ),
    },
)

agent = Agent(
    tools=[deploy],
    interventions=[cedar],
)

# works in staging
agent(
    "Deploy the service",
    invocation_state={"environment": "staging"},
)

# denied in production
agent(
    "Deploy the service",
    invocation_state={"environment": "production"},
)
```

## File-based policies

For production deployments, keep policies in `.cedar` files rather than inline strings:

- [Python](#tab-panel-1721)
- [TypeScript](#tab-panel-1722)

```python
from strands.vended_interventions.cedar import (
    CedarAuthorization,
)

cedar = CedarAuthorization(
    policies="./policies/agent.cedar",
    entities="./policies/entities.json",
)
```

The handler reads and parses files at construction time. Invalid syntax throws immediately.

## Hot reload

Update policies without restarting your agent process:

- [Python](#tab-panel-1723)
- [TypeScript](#tab-panel-1724)

```python
from strands import Agent, tool
from strands.vended_interventions.cedar import (
    CedarAuthorization,
)

@tool
def search(query: str) -> str:
    """Search for information."""
    return f"Results for: {query}"

cedar = CedarAuthorization(
    policies="./policies/agent.cedar",
)

agent = Agent(
    tools=[search],
    interventions=[cedar],
)

# After editing agent.cedar on disk:
cedar.reload()
# Validates new policies before applying.
# Raises ValueError if invalid.
```

`reload()` reads fresh policy, entity, and schema files, validates them, and atomically swaps the active policy set. If validation fails, the previous policies remain in effect and the method throws.

## Context structure

Every authorization request includes a structured context object:

```json
{
  "input": { "query": "quarterly report" },
  "session": {
    "hour_utc": 14,
    "call_count": 3,
    "role": "admin"
  }
}
```

- `context.input` contains the tool’s input arguments, accessible in policies via `context.input.fieldName`
- `context.session.hour_utc` is auto-populated with the current UTC hour (0-23)
- `context.session.call_count` tracks per-tool invocation count
- Additional `context.session` fields come from your
	`context_enricher`

## Error handling

Cedar engine failures (malformed policies, evaluation errors) are always fail-closed: the tool call is denied regardless of configuration.

The

`on_error`

option controls what happens when your user-supplied callbacks (

`principal_resolver`

or

`context_enricher`

) raise an exception:

- `'throw'` (default): re-raises the exception to the caller
- `'deny'`: treats the callback failure as a denial (fail-closed)
- `'proceed'`: allows the tool call despite the callback error (fail-open, use with caution)

## Installation

- [Python](#tab-panel-1710)
- [TypeScript](#tab-panel-1711)

```bash
pip install strands-agents[cedar]
```

Requires `cedarpy` and `cedar-policy-mcp-schema-generator` (installed automatically with the extra).

## Cedar policy syntax

For the full policy language grammar, operators, and built-in functions, see the [Cedar policy language reference](https://docs.cedarpolicy.com/syntax-policy.html).