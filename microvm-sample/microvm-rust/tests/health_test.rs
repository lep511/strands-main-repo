use axum::{body::Body, http::Request, routing::get, Router};
use http_body_util::BodyExt;
use microvm_rust::{AppState, SharedState};
use std::sync::Arc;
use tokio::sync::RwLock;
use tower::ServiceExt;

fn app() -> Router {
    let state: SharedState = Arc::new(RwLock::new(AppState::new()));
    Router::new()
        .route("/health", get(microvm_rust::health))
        .with_state(state)
}

fn app_with_running_state() -> Router {
    let state: SharedState = Arc::new(RwLock::new(AppState {
        microvm_id: Some("microvm-test-123".to_string()),
        status: "running".to_string(),
    }));
    Router::new()
        .route("/health", get(microvm_rust::health))
        .with_state(state)
}

#[tokio::test]
async fn health_returns_200() {
    let response = app()
        .oneshot(Request::builder().uri("/health").body(Body::empty()).unwrap())
        .await
        .unwrap();

    assert_eq!(response.status(), 200);
}

#[tokio::test]
async fn health_returns_initializing_on_start() {
    let response = app()
        .oneshot(Request::builder().uri("/health").body(Body::empty()).unwrap())
        .await
        .unwrap();

    let body = response.into_body().collect().await.unwrap().to_bytes();
    let json: serde_json::Value = serde_json::from_slice(&body).unwrap();

    assert_eq!(json["status"], "initializing");
    assert_eq!(json["microvm_id"], serde_json::Value::Null);
}

#[tokio::test]
async fn health_returns_running_with_microvm_id() {
    let response = app_with_running_state()
        .oneshot(Request::builder().uri("/health").body(Body::empty()).unwrap())
        .await
        .unwrap();

    let body = response.into_body().collect().await.unwrap().to_bytes();
    let json: serde_json::Value = serde_json::from_slice(&body).unwrap();

    assert_eq!(json["status"], "running");
    assert_eq!(json["microvm_id"], "microvm-test-123");
}
