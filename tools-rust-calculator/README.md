# Rust Financial Calculator — Strands Agent Tool

A high-performance financial calculator written in Rust, exposed as a [Strands Agents](https://github.com/strands-agents/sdk-python) tool. The agent sends JSON over stdin to a compiled Rust binary and gets results back, combining Rust's speed with Python's agent orchestration.

## Supported Operations

| Operation | Description | Key Parameters |
|---|---|---|
| `npv` | Net Present Value | `rate`, `cashflows` |
| `irr` | Internal Rate of Return | `cashflows` |
| `compound_interest` | Compound Interest | `principal`, `rate`, `periods`, `compounds_per_period` |
| `loan_payment` | Monthly Loan Payment | `principal`, `annual_rate`, `months` |
| `future_value` | Future Value of Annuity | `payment`, `rate`, `periods` |

## Prerequisites

- Python 3.13+
- Rust toolchain (`rustup`)
- [uv](https://docs.astral.sh/uv/) package manager

## Setup

```bash
# Build the Rust binary
cargo build --release

# Install Python dependencies
uv sync
```

## Usage

### As a Strands Agent Tool

```python
from strands import Agent
from tool import rust_financial_calculator

agent = Agent(
    system_prompt="You are a financial analyst assistant.",
    tools=[rust_financial_calculator],
)

agent("Calculate the NPV with rate 8% and cashflows: -50000, 15000, 18000, 22000, 25000")
```

### Rust Binary Directly

```bash
echo '{"operation":"npv","rate":0.1,"cashflows":[-1000,300,420,680]}' | ./target/release/rust_calculator
# {"success":true,"result":130.73...}
```

## Running Tests

```bash
# Rust unit tests
cargo test

# Agent integration test
python test_agent.py
```

## Project Structure

```
.
├── Cargo.toml         # Rust dependencies
├── src/main.rs        # Rust calculator (NPV, IRR, etc.)
├── tool.py            # Strands @tool wrapper
├── test_agent.py      # Agent integration test
└── pyproject.toml     # Python project config
```
