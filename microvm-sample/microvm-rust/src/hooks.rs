use axum::{extract::State, routing::post, Json, Router};
use serde::Deserialize;
use tracing::info;

use crate::SharedState;

pub type HooksRouter = Router;

const PREFIX: &str = "/aws/lambda-microvms/runtime/v1";

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
struct RunPayload {
    microvm_id: Option<String>,
    #[serde(flatten)]
    _extra: serde_json::Value,
}

async fn ready(State(state): State<SharedState>) -> axum::http::StatusCode {
    info!("Hook /ready called - application is initialized");
    let mut s = state.write().await;
    s.status = "ready".to_string();
    axum::http::StatusCode::OK
}

async fn validate() -> axum::http::StatusCode {
    info!("Hook /validate called - snapshot validated");
    axum::http::StatusCode::OK
}

async fn run(
    State(state): State<SharedState>,
    body: Option<Json<RunPayload>>,
) -> axum::http::StatusCode {
    info!("Hook /run called - MicroVM started from snapshot");

    let mut s = state.write().await;
    s.status = "running".to_string();

    if let Some(Json(payload)) = body {
        if let Some(id) = payload.microvm_id {
            info!(microvm_id = %id, "Received microvm_id from run payload");
            s.microvm_id = Some(id);
        }
    }

    let instance_entropy: u64 = rand::random();
    info!(entropy = instance_entropy, "Generated per-instance entropy");

    axum::http::StatusCode::OK
}

async fn resume(State(state): State<SharedState>) -> axum::http::StatusCode {
    info!("Hook /resume called - MicroVM resumed from suspend");
    let mut s = state.write().await;
    s.status = "running".to_string();
    axum::http::StatusCode::OK
}

async fn suspend(State(state): State<SharedState>) -> axum::http::StatusCode {
    info!("Hook /suspend called - preparing to suspend");
    let mut s = state.write().await;
    s.status = "suspended".to_string();
    axum::http::StatusCode::OK
}

async fn terminate(State(state): State<SharedState>) -> axum::http::StatusCode {
    info!("Hook /terminate called - shutting down");
    let mut s = state.write().await;
    s.status = "terminating".to_string();
    axum::http::StatusCode::OK
}

pub fn router(state: SharedState) -> HooksRouter {
    Router::new()
        .route(&format!("{PREFIX}/ready"), post(ready))
        .route(&format!("{PREFIX}/validate"), post(validate))
        .route(&format!("{PREFIX}/run"), post(run))
        .route(&format!("{PREFIX}/resume"), post(resume))
        .route(&format!("{PREFIX}/suspend"), post(suspend))
        .route(&format!("{PREFIX}/terminate"), post(terminate))
        .with_state(state)
}
