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

## Cedar vs Dogwood

Cedar and Dogwood solve different layers of the authorization problem for AI agents:

| | Cedar | Dogwood |
| --- | --- | --- |
| **Scope** | Point-in-time decisions | Decisions over sequences of events |
| **Sees** | The current request only | The current request + recent event history |
| **Strengths** | Fast, analyzable via automated reasoning, deterministic | Temporal conditions, rate limits, ordering constraints |
| **Syntax** | `when { ... }` | `when temporal { ... }` (superset of Cedar) |
| **Use cases** | Role checks, input validation, environment gating | "Approve before sell", sliding-window rate limits, dollar caps |
| **Compatibility** | — | Any valid Cedar policy is a valid Dogwood policy |

**Cedar** evaluates each authorization request in isolation. It can check who is making the request, what tool they're calling, and what arguments they're passing — but it cannot see what happened before. This makes it ideal for role-based access control, input validation, and environment gating.

**Dogwood** extends Cedar with temporal conditions that look back over an agent's recent events. It adds operators like `formerly` (did this happen before?), `count_within` (how many times?), `sum_within` (how much total?), and `count_distinct_within` (how many different values?). These let you express policies that depend on sequences of actions — prerequisites, rate limits, cumulative caps, and ordering constraints.

Because Dogwood is a superset of Cedar, existing Cedar policies work without modification. You only add `when temporal { ... }` clauses when you need history-dependent checks.

Dogwood is based on [Metric First-Order Temporal Logic](https://dl.acm.org/doi/10.1145/2699444) (MFOTL) from the runtime verification discipline. It is open source under Apache 2.0: [github.com/dogwood-policy/dogwood](https://github.com/dogwood-policy/dogwood).

### Example: Cedar (point-in-time)

```
// Permit small sales — no history needed
permit (principal, action == Action::"SellShares", resource)
when { context.input.shares <= 100 };
```

### Example: Dogwood (temporal)

```
// Permit a sale only if approval came back granted within the last hour
permit (principal, action == AgentCore::Action::"SellShares", resource)
when temporal {
    formerly within 1h AgentCore::Action::"ApproveSale"::response{
        input.stock: context.input.stock,
        input.shares: context.input.shares,
        output.approved: true
    }
};
```

## Dogwood Examples (`dogwood/`)

The `dogwood/` directory contains examples demonstrating Dogwood's temporal policy concepts applied to a stock trading agent.

### Temporal Policy Simulator (`dogwood/stock_trading_agent.py`)

A standalone simulator that replays event traces against Dogwood policies, demonstrating all key temporal operators without LLM calls:

| Operator | Policy file | What it enforces |
| --- | --- | --- |
| `formerly` | `approve_before_sell.dw` | Sales require prior approval within 1h |
| Cedar + `temporal` | `small_and_approved.dw` | Shares <= 100 AND recently approved |
| `count_within` | `rate_limit_transfers.dw` | Max 5 transfers per hour |
| `count_distinct_within` | `distinct_recipients_limit.dw` | Max 3 distinct recipients per hour |
| `sum_within` | `dollar_cap.dw` | Max $5,000 transferred per hour |
| `bind` | `anti_spike.dw` | No single transfer larger than settled total |

```bash
uv run python dogwood/stock_trading_agent.py
```

### Strands Agent with Temporal Authorization (`dogwood/trading_agent_with_strands.py`)

A real Strands agent that layers Dogwood-style temporal checks on top of Cedar point-in-time policies. Cedar handles basic authorization while a custom `DogwoodTemporalAuthorization` intervention handler enforces history-dependent rules:

- `formerly` — SellShares requires a prior ApproveSale response
- `count_within` — Max 5 Transfer requests per hour
- `sum_within` — Max $5,000 total transferred per hour

```bash
uv run python dogwood/trading_agent_with_strands.py
```

> **Note:** Dogwood's Rust-based reference interpreter is not yet available as a Python package. These examples implement the temporal evaluation logic in Python while using real Cedar policies via `cedarpy` for point-in-time checks.

### AgentCore Integration (`dogwood/agentcore_temporal_policies.py`)

Shows how to deploy Dogwood temporal policies on **Amazon Bedrock AgentCore Policy**, where the Gateway evaluates policies at the boundary on every tool call. Includes:

- Complete AgentCore CLI workflow (create project, gateway, policy engine, deploy)
- 7 temporal policies: approve-before-sell, rate limiting, cumulative budget, one-time approval, cool-down
- boto3 SDK example for invoking tools with the `x-amzn-bedrock-agentcore-policy-session-id` header
- curl examples for testing

AgentCore handles event tracking automatically — you supply a session ID and the Gateway records request/response/error events per session. Temporal conditions evaluate against that session history.

```bash
uv run python dogwood/agentcore_temporal_policies.py
```

Key differences from the local simulator:
- Temporal policies use `definition.policy.statement` (not `definition.cedar`) in the `create-policy` API
- Every temporal predicate must include `eventResource: resource` to scope to the gateway
- Action names follow the `<TargetName>___<tool_name>` convention
- Session-based rate limits reset when a new session starts (caller controls session ID)

## Project Structure

```
cedar-auth/
├── policies/
│   └── database_access.cedar       # File-based Cedar policy
├── dogwood/
│   ├── policies/                    # Dogwood temporal policies (.dw)
│   │   ├── approve_before_sell.dw
│   │   ├── small_and_approved.dw
│   │   ├── rate_limit_transfers.dw
│   │   ├── distinct_recipients_limit.dw
│   │   ├── dollar_cap.dw
│   │   └── anti_spike.dw
│   ├── traces/                      # Event traces for replay
│   ├── stock_trading_agent.py       # Temporal policy simulator
│   ├── trading_agent_with_strands.py # Strands agent + temporal auth
│   └── agentcore_temporal_policies.py # AgentCore Policy integration
├── database_access.py               # Role-based DB access control
├── environment_gating.py            # Block tools by environment
├── rate_limiting.py                 # Limit tool invocations
├── namespaced_policies.py           # Namespace-prefixed policies
├── pyproject.toml
└── README.md
```
