---
name: dynamodb-query
description: Query banking scheduled payments from DynamoDB. Supports querying by account+status, account+date range, status+date (GSI), or all payments for an account.
when_to_use: When the user asks about payments, scheduled transactions, pending or processed payments for a bank account, or needs to look up payment information in DynamoDB.
argument-hint: [query-json]
allowed-tools: Bash(echo * | ${CLAUDE_SKILL_DIR}/scripts/skill_dynamodb_query) Read
---

## Binary check

!`test -x ${CLAUDE_SKILL_DIR}/scripts/skill_dynamodb_query && echo "Binary ready" || echo "ERROR: binary not found"`

## Usage

Pipe JSON to the binary via stdin:

```bash
echo '{"action": "query_by_account_and_status", "account_id": "1001", "status": "SCHEDULED", "limit": 5}' | ${CLAUDE_SKILL_DIR}/scripts/skill_dynamodb_query
```

The table name is read from the `PAYMENTS_TABLE` environment variable. It can also be overridden via the `table_name` field in the JSON input.

## Supported actions

| Action | Description | Required fields |
|--------|-------------|-----------------|
| `query_by_account_and_status` | Payments for an account filtered by status | `account_id`, `status` |
| `query_by_account_and_date_range` | Payments for an account in a date range | `account_id`, `status`, `date_start`, `date_end` |
| `query_by_status_and_date` | All payments across accounts by status and date (GSI) | `status`, `date` |
| `query_all_by_account` | All payments for an account | `account_id` |

## Parameters

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| action | string | yes | One of the supported actions above |
| table_name | string | no | DynamoDB table name (falls back to `PAYMENTS_TABLE` env var) |
| account_id | string | conditional | Bank account ID (e.g. "1001") |
| status | string | conditional | `SCHEDULED`, `PENDING`, or `PROCESSED` |
| date | string | conditional | Date in ISO 8601 (e.g. "2026-05-09") |
| date_start | string | conditional | Range start date (e.g. "2026-05-01") |
| date_end | string | conditional | Range end date (e.g. "2026-06-01") |
| limit | integer | no | Max number of items to return |

## Response

```json
{"success": true, "items": [{"PaymentId": "uuid", "AccountId": "1001", "Status": "SCHEDULED", "ScheduledTime": "2026-05-09T09:00:00Z"}], "count": 1}
```

## Instructions

1. Identify the action from the user's request.
2. Build the JSON input with the required fields for that action.
3. Always include `"limit": 5` unless the user asks for more results.
4. Run: `echo '<json>' | ${CLAUDE_SKILL_DIR}/scripts/skill_dynamodb_query`
5. Present the results clearly to the user.

For full API details, see [references/API.md](references/API.md).
