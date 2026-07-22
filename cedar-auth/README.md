# Cedar Authorization Examples

## What is Cedar?

[Cedar](https://cedarpolicy.com/) is an open-source policy language created by AWS for defining and enforcing fine-grained authorization decisions. It uses a declarative syntax where you write `permit` and `forbid` statements that evaluate principals, actions, resources, and context to determine access. Cedar follows **default-deny** semantics: if no `permit` policy matches a request, it is automatically denied.

## How it works with Strands Agents

The `CedarAuthorization` handler sits at the tool-call boundary. When an agent attempts to invoke a tool, the handler maps the call to a Cedar authorization request and evaluates your policies. If no `permit` statement matches, the tool call is denied and the agent receives feedback explaining the denial.

| Cedar concept | Maps to | Example |
| --- | --- | --- |
| **Principal** | User identity | `User::"alice@acme.com"` |
| **Action** | Tool name | `Action::"search"` |
| **Resource** | Static (unconstrained) | `Resource::"agent"` |
| **Context.input** | Tool arguments | `{ query: "quarterly report" }` |
| **Context.session** | Invocation metadata | `{ hour_utc: 14, call_count: 3, role: "admin" }` |

## Installation

```bash
pip install strands-agents[cedar]
```

Or using uv:

```bash
uv add "strands-agents[cedar]"
```

## Examples

### Database Access Control (`database_access.py`)

Demonstrates role-based access control for database operations using a policy loaded from a `.cedar` file.

- **Admin** (`alice`): full access to query, insert, and delete
- **Analyst** (`bob`): read-only access (only `query_database` permitted)
- **No identity**: all operations denied

Policy file: `policies/database_access.cedar`

```bash
uv run python database_access.py
```

### Environment Gating (`environment_gating.py`)

Blocks tools based on deployment context. The `deploy` tool is permitted in staging but denied in production.

```bash
uv run python environment_gating.py
```

### Rate Limiting (`rate_limiting.py`)

Uses `context.session.call_count` to limit how many times a tool can be invoked. The `send_email` tool is capped at 4 calls; `search` is unlimited.

```bash
uv run python rate_limiting.py
```

### Namespaced Policies (`namespaced_policies.py`)

Shows how to use namespace-prefixed Cedar policies (e.g. `Agent::Action::"search"`) as produced by policy generators like `cedar-agent-policy-builder`. Includes a custom `NamespacedCedarAuthorization` handler with schema validation.

```bash
uv run python namespaced_policies.py
```

## Cedar Policy Syntax Quick Reference

```rust
// Allow a specific action
permit(
  principal,
  action == Action::"query_database",
  resource
);

// Allow based on role
permit(principal, action, resource)
when { context.session.role == "admin" };

// Rate limit a tool
permit(principal, action == Action::"send_email", resource)
when { context.session.call_count < 5 };

// Environment gating
permit(principal, action == Action::"deploy", resource)
when {
  context.session has environment &&
  context.session.environment != "production"
};
```

For the full policy language grammar, see the [Cedar policy language reference](https://docs.cedarpolicy.com/syntax-policy.html).

## Project Structure

```
cedar-auth/
├── policies/
│   └── database_access.cedar   # File-based Cedar policy
├── database_access.py          # Role-based DB access control
├── environment_gating.py       # Block tools by environment
├── rate_limiting.py            # Limit tool invocations
├── namespaced_policies.py      # Namespace-prefixed policies
├── pyproject.toml
└── README.md
```
