use axum::{body::Body, http::Request, routing::post, Router};
use http_body_util::BodyExt;
use microvm_rust::mcp;
use tower::ServiceExt;

fn mcp_app() -> Router {
    Router::new().route("/mcp", post(mcp::mcp_handler).get(mcp::mcp_get_handler))
}

fn mcp_request(body: serde_json::Value) -> Request<Body> {
    Request::builder()
        .method("POST")
        .uri("/mcp")
        .header("Host", "localhost")
        .header("Content-Type", "application/json")
        .header("Accept", "application/json, text/event-stream")
        .body(Body::from(serde_json::to_vec(&body).unwrap()))
        .unwrap()
}

fn parse_sse_data(raw: &str) -> serde_json::Value {
    for line in raw.lines() {
        if let Some(data) = line.strip_prefix("data: ") {
            if let Ok(v) = serde_json::from_str(data) {
                return v;
            }
        }
    }
    serde_json::from_str(raw).unwrap_or_default()
}

#[tokio::test]
async fn mcp_initialize_returns_protocol_version() {
    let app = mcp_app();

    let body = serde_json::json!({
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-11-25",
            "capabilities": {},
            "clientInfo": {"name": "test", "version": "1.0"}
        }
    });

    let response = app.oneshot(mcp_request(body)).await.unwrap();
    assert_eq!(response.status(), 200);

    let raw = String::from_utf8(
        response.into_body().collect().await.unwrap().to_bytes().to_vec(),
    )
    .unwrap();
    let json = parse_sse_data(&raw);

    assert_eq!(json["result"]["protocolVersion"], "2025-11-25");
    assert!(json["result"]["serverInfo"]["name"].is_string());
}

#[tokio::test]
async fn mcp_tools_list_returns_both_tools() {
    let app = mcp_app();

    let body = serde_json::json!({
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/list",
        "params": {}
    });

    let response = app.oneshot(mcp_request(body)).await.unwrap();
    assert_eq!(response.status(), 200);

    let raw = String::from_utf8(
        response.into_body().collect().await.unwrap().to_bytes().to_vec(),
    )
    .unwrap();
    let json = parse_sse_data(&raw);

    let tools = json["result"]["tools"].as_array().unwrap();
    let tool_names: Vec<&str> = tools
        .iter()
        .map(|t| t["name"].as_str().unwrap())
        .collect();

    assert!(tool_names.contains(&"get_weather"), "Missing get_weather tool");
    assert!(
        tool_names.contains(&"get_hourly_forecast"),
        "Missing get_hourly_forecast tool"
    );
}

#[tokio::test]
async fn mcp_tools_list_has_valid_schemas() {
    let app = mcp_app();

    let body = serde_json::json!({
        "jsonrpc": "2.0",
        "id": 3,
        "method": "tools/list",
        "params": {}
    });

    let response = app.oneshot(mcp_request(body)).await.unwrap();
    let raw = String::from_utf8(
        response.into_body().collect().await.unwrap().to_bytes().to_vec(),
    )
    .unwrap();
    let json = parse_sse_data(&raw);

    let tools = json["result"]["tools"].as_array().unwrap();
    for tool in tools {
        let schema = &tool["inputSchema"];
        let name = tool["name"].as_str().unwrap();
        assert_eq!(schema["type"], "object", "Tool {name} schema type must be object");

        let required = schema["required"].as_array().unwrap();
        match name {
            "get_weather" | "get_hourly_forecast" => {
                assert!(required.iter().any(|r| r == "latitude"), "Tool {name} must require latitude");
                assert!(required.iter().any(|r| r == "longitude"), "Tool {name} must require longitude");
            }
            "geocode" => {
                assert!(required.iter().any(|r| r == "name"), "Tool {name} must require name");
            }
            _ => {}
        }
    }
}

#[tokio::test]
async fn mcp_tool_call_get_weather_returns_data() {
    let app = mcp_app();

    let body = serde_json::json!({
        "jsonrpc": "2.0",
        "id": 4,
        "method": "tools/call",
        "params": {
            "name": "get_weather",
            "arguments": {
                "latitude": 35.68,
                "longitude": 139.69,
                "forecast_days": 1
            }
        }
    });

    let response = app.oneshot(mcp_request(body)).await.unwrap();
    assert_eq!(response.status(), 200);

    let raw = String::from_utf8(
        response.into_body().collect().await.unwrap().to_bytes().to_vec(),
    )
    .unwrap();
    let json = parse_sse_data(&raw);

    let content = json["result"]["content"].as_array().unwrap();
    assert!(!content.is_empty());

    let text = content[0]["text"].as_str().unwrap();
    assert!(text.contains("Current Conditions"), "Response should contain current conditions");
    assert!(text.contains("Open-Meteo"), "Response should contain source attribution");
}

#[tokio::test]
async fn mcp_tool_call_get_hourly_returns_data() {
    let app = mcp_app();

    let body = serde_json::json!({
        "jsonrpc": "2.0",
        "id": 5,
        "method": "tools/call",
        "params": {
            "name": "get_hourly_forecast",
            "arguments": {
                "latitude": 52.52,
                "longitude": 13.41,
                "forecast_days": 1
            }
        }
    });

    let response = app.oneshot(mcp_request(body)).await.unwrap();
    assert_eq!(response.status(), 200);

    let raw = String::from_utf8(
        response.into_body().collect().await.unwrap().to_bytes().to_vec(),
    )
    .unwrap();
    let json = parse_sse_data(&raw);

    let content = json["result"]["content"].as_array().unwrap();
    assert!(!content.is_empty());

    let text = content[0]["text"].as_str().unwrap();
    assert!(text.contains("Hourly Forecast"), "Response should contain hourly forecast data");
    assert!(text.contains("Open-Meteo"), "Response should contain source attribution");
}

#[tokio::test]
async fn mcp_tool_call_invalid_tool_returns_error() {
    let app = mcp_app();

    let body = serde_json::json!({
        "jsonrpc": "2.0",
        "id": 6,
        "method": "tools/call",
        "params": {
            "name": "nonexistent_tool",
            "arguments": {}
        }
    });

    let response = app.oneshot(mcp_request(body)).await.unwrap();

    let raw = String::from_utf8(
        response.into_body().collect().await.unwrap().to_bytes().to_vec(),
    )
    .unwrap();
    let json = parse_sse_data(&raw);

    assert!(
        json["error"].is_object(),
        "Calling nonexistent tool should return an error"
    );
}

#[tokio::test]
async fn mcp_get_request_returns_method_not_allowed_or_info() {
    let app = mcp_app();

    let request = Request::builder()
        .method("GET")
        .uri("/mcp")
        .header("Host", "localhost")
        .body(Body::empty())
        .unwrap();

    let response = app.oneshot(request).await.unwrap();
    let status = response.status().as_u16();
    assert!(
        status == 405 || status == 200,
        "GET /mcp should return 405 or 200, got {status}"
    );
}
