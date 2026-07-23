use axum::{routing::{get, post}, Json, Router};
use microvm_rust::{health, hooks, mcp, memory, weather, AppState, SharedState};
use serde::Serialize;
use std::sync::Arc;
use tokio::sync::RwLock;
use tracing::info;

#[derive(Serialize)]
struct HelloResponse {
    message: String,
    instance_id: String,
}

async fn hello(state: axum::extract::State<SharedState>) -> Json<HelloResponse> {
    let app_state = state.read().await;
    let instance_id = app_state
        .microvm_id
        .clone()
        .unwrap_or_else(|| "unknown".to_string());
    Json(HelloResponse {
        message: "Hello from Rust MicroVM!".to_string(),
        instance_id,
    })
}

#[tokio::main]
async fn main() {
    tracing_subscriber::fmt()
        .with_env_filter("info")
        .init();

    let state: SharedState = Arc::new(RwLock::new(AppState::new()));

    let app_router = Router::new()
        .route("/", get(hello))
        .route("/health", get(health))
        .route("/memory", get(memory))
        .route("/weather", get(weather::get_weather))
        .with_state(state.clone());

    let hooks_router = hooks::router(state.clone());

    let mcp_router = Router::new()
        .route("/mcp", post(mcp::mcp_handler).get(mcp::mcp_get_handler));

    let app_handle = tokio::spawn(async move {
        let listener = tokio::net::TcpListener::bind("0.0.0.0:8080").await.unwrap();
        info!("Application server listening on port 8080");
        axum::serve(listener, app_router).await.unwrap();
    });

    let hooks_handle = tokio::spawn(async move {
        let listener = tokio::net::TcpListener::bind("0.0.0.0:9000").await.unwrap();
        info!("Lifecycle hooks server listening on port 9000");
        axum::serve(listener, hooks_router).await.unwrap();
    });

    let mcp_handle = tokio::spawn(async move {
        let listener = tokio::net::TcpListener::bind("0.0.0.0:8081").await.unwrap();
        info!("MCP server listening on port 8081 at /mcp");
        axum::serve(listener, mcp_router).await.unwrap();
    });

    tokio::select! {
        r = app_handle => { if let Err(e) = r { tracing::error!("App server error: {e}"); } }
        r = hooks_handle => { if let Err(e) = r { tracing::error!("Hooks server error: {e}"); } }
        r = mcp_handle => { if let Err(e) = r { tracing::error!("MCP server error: {e}"); } }
    }
}
