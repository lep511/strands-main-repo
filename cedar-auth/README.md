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

**Dogwood** extends Cedar with temporal conditions that look back over an agent's recent events. It adds operators like `formerly` (did this happen before?), `since` (has this not happened since that?), `count_within` (how many times?), `sum_within` (how much total?), and `count_distinct_within` (how many different values?). These let you express policies that depend on sequences of actions — prerequisites, rate limits, cumulative caps, and ordering constraints.

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

> **Note:** Dogwood has no official Python package. These two examples implement the temporal evaluation logic in Python while using real Cedar policies via `cedarpy` for point-in-time checks. For verdicts from the real Dogwood engine, see the Local Engine chat below.

### Interactive Chat on the Dogwood Local Engine (`dogwood/local_engine_chat.py`)

A terminal chat (Rich) with a Strands trading-desk agent where every tool call is decided by the real [Dogwood Local Engine](https://github.com/dogwood-policy/dogwood-local-engine), not a Python simulation. The engine runs as `dogwood-server`, a local daemon that keeps the event history durably on disk, so temporal limits survive a restart of the chat. The chat talks to it over two Unix sockets with length-prefixed JSON, so no Rust bindings are needed:

| Socket | Path | Used for |
| --- | --- | --- |
| Data plane | `<dir>/run/dogwood.sock` | Submit events, receive verdicts |
| Control plane | `<dir>/control.sock` | Install policies, status, reset |

**Running it** needs a Rust toolchain (1.85 or newer) for the first build, and Bedrock access for Strands' default model:

```bash
# Terminal 1: build dogwood-server the first time, then run it in the foreground
dogwood/run_dogwood_server.sh

# Terminal 2
uv run python dogwood/local_engine_chat.py
```

If Rust is missing or too old, `run_dogwood_server.sh` explains how to install it with [rustup](https://rustup.rs). It clones `dogwood-local-engine` into `~/.cache/dogwood-local-engine`, serves the state directory `~/.dogwood-chat` (the chat's default), and refuses to start a second server on the same directory. Options: `--dir DIR`, `--rebuild` (pull and rebuild), and `DOGWOOD_SERVER_BIN=/path/to/dogwood-server` to reuse a binary you already built.

Chat options: `--user NAME` (the principal, default `alice`), `--dir DIR` (the server's state directory), `--policies DIR` (where the `.dw` files are), `--reinstall` (install the policies even if the store already runs them).

| Command | What it does |
| --- | --- |
| `/policies` | The policies and the natural-language rule each one encodes |
| `/history` | Every event the harness submitted, with its verdict and the policy that decided it |
| `/status` | What the engine has installed and how many events it has recorded |
| `/user <name>` | Act as another principal; each principal has its own history |
| `/reset` | Clear the temporal history of every policy (asks first) |
| `/new` | Start a new conversation; the engine keeps its history |
| `/help`, `/exit` | Help, and quit (Ctrl-D and Ctrl-C also quit) |

The input line supports arrow keys, line editing, and the up-arrow history of the current session.

**How a tool call is decided.** `DogwoodHarness`, a Strands `InterventionHandler`, plays the harness role from the [Local Engine announcement](https://aws.amazon.com/es/blogs/opensource/introducing-the-dogwood-local-engine-temporal-governance-for-agent-actions/):

1. Before the tool runs, it submits a `request` event and runs the tool only if the verdict is ALLOW.
2. Afterwards it submits a `response` event with the tool's output, or an `error` event if the call was denied or failed. This is the same bookkeeping AgentCore Policy does at the Gateway.
3. Every event of a call carries the Strands `toolUseId` as `input.callId`, so a policy can match a request with its outcome. The tool never sees it.
4. Tools run one at a time (`SequentialToolExecutor`), so a sale never starts before its approval is recorded.

`ApproveSale` asks you, the human operator, to approve the sale in the terminal, so the agent cannot approve its own sales. Each line printed as `dogwood ALLOW …` or `dogwood DENY …` is a verdict from the engine. If an answer appears without such a line, the agent never called the tool.

The agent is **not** told the rules. If it knew them, it would refuse an obvious violation itself and the engine would never decide it. When the engine denies a call, the harness passes the agent the natural-language rule of the policy that decided it, so the agent can explain the denial.

**Policies.** The policy set lives in `dogwood/policies/local_engine_chat/`, one `.dw` file per policy. The chat loads every `.dw` file in that directory:

| `@id` | Effect | Rule | Dogwood feature |
| --- | --- | --- | --- |
| `allow_stock_info` | permit | Anyone may look up market data | Plain Cedar |
| `allow_approval_requests` | permit | Anyone may ask a human to approve a sale | Plain Cedar |
| `sell_with_single_use_approval` | permit | At most 1,000 shares, with a human approval for the same stock and amount within 1h; each approval covers one sale | Cedar + `!A since B` |
| `allow_transfers` | permit | Transfers of a positive amount, unless a limit forbids them | Plain Cedar |
| `rate_limit_transfers` | forbid | No more than 5 transfer attempts per hour, refused ones included | `count_within` |
| `distinct_recipients_limit` | forbid | No more than 3 distinct recipients per hour, among transfers not refused | `count` + guarded negation |
| `dollar_cap` | forbid | No more than $5,000 per hour, among transfers not refused | `sum` + guarded negation |

How the policy files work:

- **Natural-language rule:** each file opens with its rule as a `//` comment, kept next to the policy as the [natural-language authoring post](https://aws.amazon.com/es/blogs/machine-learning/authoring-dogwood-policies-from-natural-language-in-amazon-bedrock-agentcore/) recommends. The first paragraph is the rule that the agent and `/policies` see. Text after a blank `//` line is notes for whoever edits the policy.
- **Refused transfers don't count:** the two money limits count a transfer request unless the same call ended in an `error`. So a refused $40,000 attempt does not use up the hour's budget. Temporal blocks have no arithmetic, so "settled + this amount" cannot be written directly. Instead, the sum of requests that were not refused includes the current one.
- **Installing:** the chat installs the set when the store has no policies, or a different revision of them. Every installed policy is stamped with `@revision("<hash>")`, a hash of the `.dw` files and the action schema. Editing any file, even a comment, reinstalls the set on the next start, and that resets the temporal history.
- **Why a separate directory:** these files are their own set, not `dogwood/policies/*.dw`. Some of those undo these rules when loaded together: `approve_before_sell.dw` permits a sale on any earlier approval, and `anti_spike.dw` forbids the first transfer of every hour.

To change the hourly transfer limit, for example, edit both the number (`total > 5000`) and the rule comment in `dollar_cap.dw`.

> **Security note:** the chat installs policies over the control socket as a demo convenience. `dogwood-server` is only tamper-resistant when it runs as a different, more privileged user than the agent, and an operator installs policy with `dogwood-server policy install`. Without control-socket access the chat still works, but it cannot install, reset, or name the policies behind a verdict.

> **Editing `.dw` files in VS Code:** with the [Cedar extension](https://marketplace.visualstudio.com/items?itemName=cedar-policy.vscode-cedar), add `"files.associations": { "*.dw": "cedar" }` to your settings for syntax highlighting. The extension validates files with the Cedar parser, so `when temporal { … }` blocks show syntax errors even though they are valid Dogwood.

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
│   │   ├── local_engine_chat/       # Policy set of the Local Engine chat, one .dw per policy
│   │   ├── approve_before_sell.dw
│   │   ├── small_and_approved.dw
│   │   ├── rate_limit_transfers.dw
│   │   ├── distinct_recipients_limit.dw
│   │   ├── dollar_cap.dw
│   │   └── anti_spike.dw
│   ├── traces/                      # Event traces for replay
│   ├── stock_trading_agent.py       # Temporal policy simulator
│   ├── trading_agent_with_strands.py # Strands agent + temporal auth
│   ├── local_engine_chat.py         # Interactive chat on the Dogwood Local Engine
│   ├── run_dogwood_server.sh        # Builds (once) and runs dogwood-server
│   └── agentcore_temporal_policies.py # AgentCore Policy integration
├── database_access.py               # Role-based DB access control
├── environment_gating.py            # Block tools by environment
├── rate_limiting.py                 # Limit tool invocations
├── namespaced_policies.py           # Namespace-prefixed policies
├── pyproject.toml
└── README.md
```
