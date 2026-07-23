use axum::{body::Body, http::Request};
use microvm_rust::{AppState, SharedState};
use std::sync::Arc;
use tokio::sync::RwLock;
use tower::ServiceExt;

fn hooks_app() -> (microvm_rust::hooks::HooksRouter, SharedState) {
    let state: SharedState = Arc::new(RwLock::new(AppState::new()));
    let router = microvm_rust::hooks::router(state.clone());
    (router, state)
}

const PREFIX: &str = "/aws/lambda-microvms/runtime/v1";

#[tokio::test]
async fn ready_hook_returns_200_and_sets_status() {
    let (app, state) = hooks_app();

    let response = app
        .oneshot(
            Request::builder()
                .method("POST")
                .uri(format!("{PREFIX}/ready"))
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();

    assert_eq!(response.status(), 200);

    let s = state.read().await;
    assert_eq!(s.status, "ready");
}

#[tokio::test]
async fn validate_hook_returns_200() {
    let (app, _) = hooks_app();

    let response = app
        .oneshot(
            Request::builder()
                .method("POST")
                .uri(format!("{PREFIX}/validate"))
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();

    assert_eq!(response.status(), 200);
}

#[tokio::test]
async fn run_hook_sets_running_and_extracts_microvm_id() {
    let (app, state) = hooks_app();

    let payload = serde_json::json!({"microvmId": "microvm-abc-123"});

    let response = app
        .oneshot(
            Request::builder()
                .method("POST")
                .uri(format!("{PREFIX}/run"))
                .header("content-type", "application/json")
                .body(Body::from(serde_json::to_vec(&payload).unwrap()))
                .unwrap(),
        )
        .await
        .unwrap();

    assert_eq!(response.status(), 200);

    let s = state.read().await;
    assert_eq!(s.status, "running");
    assert_eq!(s.microvm_id, Some("microvm-abc-123".to_string()));
}

#[tokio::test]
async fn run_hook_works_without_body() {
    let (app, state) = hooks_app();

    let response = app
        .oneshot(
            Request::builder()
                .method("POST")
                .uri(format!("{PREFIX}/run"))
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();

    assert_eq!(response.status(), 200);

    let s = state.read().await;
    assert_eq!(s.status, "running");
    assert_eq!(s.microvm_id, None);
}

#[tokio::test]
async fn suspend_hook_sets_suspended() {
    let (app, state) = hooks_app();

    let response = app
        .oneshot(
            Request::builder()
                .method("POST")
                .uri(format!("{PREFIX}/suspend"))
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();

    assert_eq!(response.status(), 200);

    let s = state.read().await;
    assert_eq!(s.status, "suspended");
}

#[tokio::test]
async fn resume_hook_sets_running() {
    let state: SharedState = Arc::new(RwLock::new(AppState {
        microvm_id: Some("microvm-test".to_string()),
        status: "suspended".to_string(),
    }));
    let app = microvm_rust::hooks::router(state.clone());

    let response = app
        .oneshot(
            Request::builder()
                .method("POST")
                .uri(format!("{PREFIX}/resume"))
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();

    assert_eq!(response.status(), 200);

    let s = state.read().await;
    assert_eq!(s.status, "running");
}

#[tokio::test]
async fn terminate_hook_sets_terminating() {
    let (app, state) = hooks_app();

    let response = app
        .oneshot(
            Request::builder()
                .method("POST")
                .uri(format!("{PREFIX}/terminate"))
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();

    assert_eq!(response.status(), 200);

    let s = state.read().await;
    assert_eq!(s.status, "terminating");
}

#[tokio::test]
async fn lifecycle_sequence_ready_run_suspend_resume_terminate() {
    let state: SharedState = Arc::new(RwLock::new(AppState::new()));

    let steps = ["ready", "run", "suspend", "resume", "terminate"];
    let expected = ["ready", "running", "suspended", "running", "terminating"];

    for (hook, expected_status) in steps.iter().zip(expected.iter()) {
        let app = microvm_rust::hooks::router(state.clone());
        let response = app
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri(format!("{PREFIX}/{hook}"))
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();

        assert_eq!(response.status(), 200, "Hook /{hook} failed");

        let s = state.read().await;
        assert_eq!(
            s.status, *expected_status,
            "After /{hook}, expected status '{expected_status}', got '{}'",
            s.status
        );
    }
}
