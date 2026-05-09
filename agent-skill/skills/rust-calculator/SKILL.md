---
name: rust-calculator
description: Financial calculator powered by a Rust binary. Computes NPV, IRR, compound interest, loan payments, and future value.
when_to_use: When the user asks to calculate NPV, IRR, internal rate of return, compound interest, loan payments, monthly payments, future value of annuities, or any time-value-of-money computation.
argument-hint: [operation-json]
allowed-tools: Bash(echo * | ${CLAUDE_SKILL_DIR}/scripts/skill_rust_calculator) Read
---

## Binary check

!`test -x ${CLAUDE_SKILL_DIR}/scripts/skill_rust_calculator && echo "Binary ready" || echo "ERROR: binary not found"`

## Usage

Pipe JSON to the binary via stdin:

```bash
echo '{"operation": "npv", "rate": 0.1, "cashflows": [-1000, 300, 420, 680]}' | ${CLAUDE_SKILL_DIR}/scripts/skill_rust_calculator
```

## Operations

| Operation | Required fields |
|-----------|----------------|
| `npv` | `rate` (float), `cashflows` (float[]) |
| `irr` | `cashflows` (float[], min 2) |
| `compound_interest` | `principal`, `rate`, `periods`, optional `compounds_per_period` |
| `loan_payment` | `principal`, `annual_rate`, `months` |
| `future_value` | `payment`, `rate`, `periods` |

## Response

```json
{"success": true, "result": 130.73, "error": null}
```

## Instructions

1. Build the JSON input with the correct `operation` field.
2. Run: `echo '<json>' | ${CLAUDE_SKILL_DIR}/scripts/skill_rust_calculator`
3. Present the result clearly, with units and context.

For full API details and formulas, see [references/API.md](references/API.md).
