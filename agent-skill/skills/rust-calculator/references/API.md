# Rust Calculator API Reference

## Binary

- **Name**: `skill_rust_calculator`
- **Location**: `scripts/skill_rust_calculator`
- **Interface**: Reads JSON from stdin, writes JSON to stdout

## Input Schema

All requests are JSON objects with an `operation` field that determines the variant.

### `npv` — Net Present Value

| Field      | Type     | Required | Description                    |
|------------|----------|----------|--------------------------------|
| operation  | string   | yes      | Must be `"npv"`                |
| rate       | float    | yes      | Discount rate (e.g., 0.1 = 10%) |
| cashflows  | float[]  | yes      | Array of cash flows (at least 1) |

**Formula**: `NPV = Σ cashflow[t] / (1 + rate)^t`

### `irr` — Internal Rate of Return

| Field      | Type     | Required | Description                       |
|------------|----------|----------|-----------------------------------|
| operation  | string   | yes      | Must be `"irr"`                   |
| cashflows  | float[]  | yes      | Array of cash flows (at least 2)  |

**Method**: Newton-Raphson iteration (max 1000 iterations, tolerance 1e-9).

### `compound_interest`

| Field                 | Type   | Required | Description                             |
|-----------------------|--------|----------|-----------------------------------------|
| operation             | string | yes      | Must be `"compound_interest"`           |
| principal             | float  | yes      | Initial investment                      |
| rate                  | float  | yes      | Annual interest rate                    |
| periods               | int    | yes      | Number of years                         |
| compounds_per_period  | int    | no       | Compounding frequency per period (default: 1) |

**Formula**: `A = P × (1 + r/n)^(n×t)`

### `loan_payment`

| Field        | Type   | Required | Description                    |
|--------------|--------|----------|--------------------------------|
| operation    | string | yes      | Must be `"loan_payment"`       |
| principal    | float  | yes      | Loan amount                    |
| annual_rate  | float  | yes      | Annual interest rate            |
| months       | int    | yes      | Loan term in months (must be > 0) |

**Formula**: `M = P × r(1+r)^n / ((1+r)^n - 1)` where `r = annual_rate / 12`

### `future_value`

| Field      | Type   | Required | Description                     |
|------------|--------|----------|---------------------------------|
| operation  | string | yes      | Must be `"future_value"`        |
| payment    | float  | yes      | Periodic payment amount         |
| rate       | float  | yes      | Interest rate per period        |
| periods    | int    | yes      | Number of periods               |

**Formula**: `FV = PMT × ((1 + r)^n - 1) / r`

## Output Schema

| Field   | Type         | Description                        |
|---------|--------------|------------------------------------|
| success | boolean      | Whether the computation succeeded  |
| result  | float | null | The computed value (on success)    |
| error   | string | null | Error message (on failure)       |

## Error Cases

- Invalid JSON input
- Empty cashflows for NPV
- Fewer than 2 cashflows for IRR
- IRR does not converge
- `compounds_per_period` is 0
- `months` is 0 for loan payment
