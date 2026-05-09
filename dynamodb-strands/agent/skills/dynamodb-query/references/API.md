# DynamoDB Query API Reference

## Binary

- **Name**: `skill_dynamodb_query`
- **Location**: `scripts/skill_dynamodb_query`
- **Interface**: Reads JSON from stdin, writes JSON to stdout

## Configuration

The table name is resolved in this order:
1. `table_name` field in the JSON input (if provided)
2. `PAYMENTS_TABLE` environment variable

## Input Schema

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| action | string | yes | The query action to perform |
| table_name | string | no | DynamoDB table name override |
| account_id | string | conditional | Bank account ID |
| status | string | conditional | Payment status: `SCHEDULED`, `PENDING`, or `PROCESSED` |
| date | string | conditional | Single date (ISO 8601, e.g. `2026-05-09`) |
| date_start | string | conditional | Range start date |
| date_end | string | conditional | Range end date |
| limit | integer | no | Max items to return (no default, returns all if omitted) |

## Actions

### query_by_account_and_status

Returns payments for a specific account filtered by status.

**Required**: `account_id`, `status`

**DynamoDB pattern**: `PK = a#{account_id}` AND `SK begins_with p#{status}#`

```json
{"action": "query_by_account_and_status", "account_id": "1001", "status": "SCHEDULED", "limit": 5}
```

### query_by_account_and_date_range

Returns payments for an account within a date range for a given status.

**Required**: `account_id`, `status`, `date_start`, `date_end`

**DynamoDB pattern**: `PK = a#{account_id}` AND `SK BETWEEN p#{status}#{date_start} AND p#{status}#{date_end}`

```json
{"action": "query_by_account_and_date_range", "account_id": "1001", "status": "SCHEDULED", "date_start": "2026-05-01", "date_end": "2026-06-01", "limit": 10}
```

### query_by_status_and_date

Returns all payments across all accounts for a specific status and date. Uses the GSI `StatusIndex`.

**Required**: `status`, `date`

**DynamoDB pattern**: GSI `StatusIndex` — `Status = {status}` AND `ScheduledTime begins_with {date}`

```json
{"action": "query_by_status_and_date", "status": "PENDING", "date": "2026-05-09", "limit": 5}
```

### query_all_by_account

Returns all payments for an account regardless of status.

**Required**: `account_id`

**DynamoDB pattern**: `PK = a#{account_id}`

```json
{"action": "query_all_by_account", "account_id": "1001", "limit": 10}
```

## Output Schema

| Field | Type | Description |
|-------|------|-------------|
| success | boolean | Whether the query succeeded |
| items | array \| null | List of payment objects (on success) |
| count | integer \| null | Number of items returned |
| error | string \| null | Error message (on failure) |

### Item fields

| Field | Type | Always present | Description |
|-------|------|----------------|-------------|
| PaymentId | string | yes | Unique payment UUID |
| AccountId | string | yes | Bank account ID |
| Status | string | yes | `SCHEDULED`, `PENDING`, or `PROCESSED` |
| ScheduledTime | string | yes | ISO 8601 datetime |
| TransactionId | string | no | Only on `PROCESSED` payments |
| ProcessedAt | string | no | Only on `PROCESSED` payments |

## Error Cases

- Invalid JSON input
- Missing required field for the chosen action
- Table not found (`PAYMENTS_TABLE` not set and `table_name` not provided)
- DynamoDB service errors (table doesn't exist, permissions, etc.)

## Examples

```bash
# Scheduled payments for account 1001 (max 3)
echo '{"action":"query_by_account_and_status","account_id":"1001","status":"SCHEDULED","limit":3}' | ./scripts/skill_dynamodb_query
# -> {"success":true,"items":[{"PaymentId":"...","AccountId":"1001","Status":"SCHEDULED","ScheduledTime":"2026-05-09T09:00:00Z"},...],"count":3}

# All pending payments for today across all accounts
echo '{"action":"query_by_status_and_date","status":"PENDING","date":"2026-05-09","limit":5}' | ./scripts/skill_dynamodb_query
# -> {"success":true,"items":[...],"count":5}

# Processed payments for account 1002
echo '{"action":"query_by_account_and_status","account_id":"1002","status":"PROCESSED","limit":5}' | ./scripts/skill_dynamodb_query
# -> {"success":true,"items":[{"PaymentId":"...","AccountId":"1002","Status":"PROCESSED","ScheduledTime":"...","TransactionId":"...","ProcessedAt":"..."},...],"count":5}
```
