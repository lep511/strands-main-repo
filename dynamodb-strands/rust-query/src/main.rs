use aws_sdk_dynamodb::error::SdkError;
use aws_sdk_dynamodb::types::AttributeValue;
use aws_sdk_dynamodb::Client;
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::io::{self, Read};

fn format_sdk_error<E: std::fmt::Debug, R: std::fmt::Debug>(err: &SdkError<E, R>) -> String {
    match err {
        SdkError::ServiceError(e) => format!("{:?}", e.err()),
        SdkError::TimeoutError(_) => "Request timed out".to_string(),
        SdkError::DispatchFailure(e) => format!("Connection error: {:?}", e),
        _ => format!("{:?}", err),
    }
}

fn short_error_message(raw: &str) -> String {
    if let Some(start) = raw.find("message: Some(\"") {
        let msg_start = start + 15;
        if let Some(end) = raw[msg_start..].find("\")") {
            return raw[msg_start..msg_start + end].to_string();
        }
    }
    raw.to_string()
}

#[derive(Deserialize)]
struct Request {
    action: Action,
    #[serde(default)]
    table_name: Option<String>,
    #[serde(default)]
    account_id: Option<String>,
    #[serde(default)]
    status: Option<String>,
    #[serde(default)]
    date: Option<String>,
    #[serde(default)]
    date_start: Option<String>,
    #[serde(default)]
    date_end: Option<String>,
    #[serde(default)]
    limit: Option<usize>,
}

#[derive(Deserialize)]
#[serde(rename_all = "snake_case")]
enum Action {
    QueryByAccountAndStatus,
    QueryByAccountAndDateRange,
    QueryByStatusAndDate,
    QueryAllByAccount,
}

#[derive(Serialize)]
struct Response {
    success: bool,
    #[serde(skip_serializing_if = "Option::is_none")]
    items: Option<Vec<HashMap<String, String>>>,
    #[serde(skip_serializing_if = "Option::is_none")]
    count: Option<usize>,
    #[serde(skip_serializing_if = "Option::is_none")]
    error: Option<String>,
}

impl Response {
    fn ok(items: Vec<HashMap<String, String>>) -> Self {
        let count = items.len();
        Self {
            success: true,
            items: Some(items),
            count: Some(count),
            error: None,
        }
    }

    fn err(msg: &str) -> Self {
        Self {
            success: false,
            items: None,
            count: None,
            error: Some(msg.to_string()),
        }
    }
}

fn extract_string(val: &AttributeValue) -> String {
    match val {
        AttributeValue::S(s) => s.clone(),
        AttributeValue::N(n) => n.clone(),
        other => format!("{:?}", other),
    }
}

const RELEVANT_FIELDS: &[&str] = &[
    "PaymentId",
    "AccountId",
    "Status",
    "ScheduledTime",
    "TransactionId",
    "ProcessedAt",
];

fn items_to_maps(
    items: &[HashMap<String, AttributeValue>],
) -> Vec<HashMap<String, String>> {
    items
        .iter()
        .map(|item| {
            item.iter()
                .filter(|(k, _)| RELEVANT_FIELDS.contains(&k.as_str()))
                .map(|(k, v)| (k.clone(), extract_string(v)))
                .collect()
        })
        .collect()
}

/// PK = a#{account_id}, SK begins_with p#{status}
async fn query_by_account_and_status(
    client: &Client,
    table: &str,
    account_id: &str,
    status: &str,
) -> Result<Vec<HashMap<String, AttributeValue>>, String> {
    let resp = client
        .query()
        .table_name(table)
        .key_condition_expression("PK = :pk AND begins_with(SK, :sk_prefix)")
        .expression_attribute_values(":pk", AttributeValue::S(format!("a#{}", account_id)))
        .expression_attribute_values(
            ":sk_prefix",
            AttributeValue::S(format!("p#{}#", status.to_uppercase())),
        )
        .send()
        .await
        .map_err(|e| short_error_message(&format_sdk_error(&e)))?;

    Ok(resp.items().to_vec())
}

/// PK = a#{account_id}, SK BETWEEN p#{status}#{date_start} AND p#{status}#{date_end}
async fn query_by_account_and_date_range(
    client: &Client,
    table: &str,
    account_id: &str,
    status: &str,
    date_start: &str,
    date_end: &str,
) -> Result<Vec<HashMap<String, AttributeValue>>, String> {
    let resp = client
        .query()
        .table_name(table)
        .key_condition_expression("PK = :pk AND SK BETWEEN :sk_start AND :sk_end")
        .expression_attribute_values(":pk", AttributeValue::S(format!("a#{}", account_id)))
        .expression_attribute_values(
            ":sk_start",
            AttributeValue::S(format!("p#{}#{}", status.to_uppercase(), date_start)),
        )
        .expression_attribute_values(
            ":sk_end",
            AttributeValue::S(format!("p#{}#{}~", status.to_uppercase(), date_end)),
        )
        .send()
        .await
        .map_err(|e| short_error_message(&format_sdk_error(&e)))?;

    Ok(resp.items().to_vec())
}

/// GSI StatusIndex: PK = Status, SK begins_with date
async fn query_by_status_and_date(
    client: &Client,
    table: &str,
    status: &str,
    date: &str,
) -> Result<Vec<HashMap<String, AttributeValue>>, String> {
    let resp = client
        .query()
        .table_name(table)
        .index_name("StatusIndex")
        .key_condition_expression("#s = :status AND begins_with(ScheduledTime, :date)")
        .expression_attribute_names("#s", "Status")
        .expression_attribute_values(":status", AttributeValue::S(status.to_uppercase()))
        .expression_attribute_values(":date", AttributeValue::S(date.to_string()))
        .send()
        .await
        .map_err(|e| short_error_message(&format_sdk_error(&e)))?;

    Ok(resp.items().to_vec())
}

/// PK = a#{account_id} (all items for an account)
async fn query_all_by_account(
    client: &Client,
    table: &str,
    account_id: &str,
) -> Result<Vec<HashMap<String, AttributeValue>>, String> {
    let resp = client
        .query()
        .table_name(table)
        .key_condition_expression("PK = :pk")
        .expression_attribute_values(":pk", AttributeValue::S(format!("a#{}", account_id)))
        .send()
        .await
        .map_err(|e| short_error_message(&format_sdk_error(&e)))?;

    Ok(resp.items().to_vec())
}

fn resolve_table_name(request_table: &Option<String>) -> Option<String> {
    request_table
        .clone()
        .or_else(|| std::env::var("PAYMENTS_TABLE").ok())
}

async fn handle(input: &str) -> Response {
    let request: Request = match serde_json::from_str(input) {
        Ok(r) => r,
        Err(e) => return Response::err(&format!("Invalid input: {}", e)),
    };

    let table = match resolve_table_name(&request.table_name) {
        Some(t) => t,
        None => return Response::err("table_name not provided and PAYMENTS_TABLE env var not set"),
    };

    let config = aws_config::load_defaults(aws_config::BehaviorVersion::latest()).await;
    let client = Client::new(&config);

    let result = match request.action {
        Action::QueryByAccountAndStatus => {
            let account_id = match &request.account_id {
                Some(id) => id,
                None => return Response::err("account_id is required"),
            };
            let status = match &request.status {
                Some(s) => s,
                None => return Response::err("status is required (SCHEDULED, PENDING, or PROCESSED)"),
            };
            query_by_account_and_status(&client, &table, account_id, status).await
        }
        Action::QueryByAccountAndDateRange => {
            let account_id = match &request.account_id {
                Some(id) => id,
                None => return Response::err("account_id is required"),
            };
            let status = match &request.status {
                Some(s) => s,
                None => return Response::err("status is required"),
            };
            let date_start = match &request.date_start {
                Some(d) => d,
                None => return Response::err("date_start is required (ISO 8601, e.g. 2026-02-01)"),
            };
            let date_end = match &request.date_end {
                Some(d) => d,
                None => return Response::err("date_end is required (ISO 8601, e.g. 2026-03-01)"),
            };
            query_by_account_and_date_range(&client, &table, account_id, status, date_start, date_end).await
        }
        Action::QueryByStatusAndDate => {
            let status = match &request.status {
                Some(s) => s,
                None => return Response::err("status is required (SCHEDULED, PENDING, or PROCESSED)"),
            };
            let date = match &request.date {
                Some(d) => d,
                None => return Response::err("date is required (e.g. 2026-02-05)"),
            };
            query_by_status_and_date(&client, &table, status, date).await
        }
        Action::QueryAllByAccount => {
            let account_id = match &request.account_id {
                Some(id) => id,
                None => return Response::err("account_id is required"),
            };
            query_all_by_account(&client, &table, account_id).await
        }
    };

    match result {
        Ok(items) => {
            let mapped = items_to_maps(&items);
            let limited = match request.limit {
                Some(n) => mapped.into_iter().take(n).collect(),
                None => mapped,
            };
            Response::ok(limited)
        }
        Err(e) => Response::err(&e),
    }
}

#[tokio::main]
async fn main() {
    let mut input = String::new();
    io::stdin().read_to_string(&mut input).unwrap_or_default();

    let response = handle(input.trim()).await;
    println!("{}", serde_json::to_string(&response).unwrap());
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_invalid_json() {
        let rt = tokio::runtime::Runtime::new().unwrap();
        let resp = rt.block_on(handle("not json"));
        assert!(!resp.success);
        assert!(resp.error.unwrap().contains("Invalid input"));
    }

    #[test]
    fn test_missing_account_id() {
        let rt = tokio::runtime::Runtime::new().unwrap();
        let input = r#"{"action": "query_by_account_and_status", "table_name": "test", "status": "SCHEDULED"}"#;
        let resp = rt.block_on(handle(input));
        assert!(!resp.success);
        assert!(resp.error.unwrap().contains("account_id is required"));
    }

    #[test]
    fn test_missing_status() {
        let rt = tokio::runtime::Runtime::new().unwrap();
        let input = r#"{"action": "query_by_account_and_status", "table_name": "test", "account_id": "1001"}"#;
        let resp = rt.block_on(handle(input));
        assert!(!resp.success);
        assert!(resp.error.unwrap().contains("status is required"));
    }

    #[test]
    fn test_missing_date_range() {
        let rt = tokio::runtime::Runtime::new().unwrap();
        let input = r#"{"action": "query_by_account_and_date_range", "table_name": "test", "account_id": "1001", "status": "SCHEDULED"}"#;
        let resp = rt.block_on(handle(input));
        assert!(!resp.success);
        assert!(resp.error.unwrap().contains("date_start is required"));
    }
}
