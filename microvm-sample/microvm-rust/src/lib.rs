pub mod hooks;
pub mod mcp;
pub mod weather;

use axum::Json;
use serde::Serialize;
use std::sync::Arc;
use tokio::sync::RwLock;

#[derive(Debug, Clone, Serialize)]
pub struct AppState {
    pub microvm_id: Option<String>,
    pub status: String,
}

impl AppState {
    pub fn new() -> Self {
        Self {
            microvm_id: None,
            status: "initializing".to_string(),
        }
    }
}

pub type SharedState = Arc<RwLock<AppState>>;

#[derive(Serialize)]
pub struct HealthResponse {
    pub status: String,
    pub microvm_id: Option<String>,
}

pub async fn health(state: axum::extract::State<SharedState>) -> Json<HealthResponse> {
    let app_state = state.read().await;
    Json(HealthResponse {
        status: app_state.status.clone(),
        microvm_id: app_state.microvm_id.clone(),
    })
}

#[derive(Serialize)]
pub struct MemoryResponse {
    pub total_kb: u64,
    pub available_kb: u64,
    pub used_kb: u64,
    pub usage_percent: f64,
}

pub async fn memory() -> Json<MemoryResponse> {
    let (total, available) = read_meminfo();
    let used = total.saturating_sub(available);
    let usage_percent = if total > 0 {
        (used as f64 / total as f64) * 100.0
    } else {
        0.0
    };
    Json(MemoryResponse {
        total_kb: total,
        available_kb: available,
        used_kb: used,
        usage_percent,
    })
}

fn read_meminfo() -> (u64, u64) {
    let content = std::fs::read_to_string("/proc/meminfo").unwrap_or_default();
    let mut total = 0u64;
    let mut available = 0u64;
    for line in content.lines() {
        if line.starts_with("MemTotal:") {
            total = parse_meminfo_value(line);
        } else if line.starts_with("MemAvailable:") {
            available = parse_meminfo_value(line);
        }
    }
    (total, available)
}

fn parse_meminfo_value(line: &str) -> u64 {
    line.split_whitespace()
        .nth(1)
        .and_then(|v| v.parse().ok())
        .unwrap_or(0)
}
