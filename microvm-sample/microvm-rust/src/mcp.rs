use axum::{http::StatusCode, response::IntoResponse, Json};
use schemars::schema_for;
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use thiserror::Error;
use tracing::{debug, error, info, warn};

// --- Error types ---

#[derive(Debug, Error)]
pub enum McpError {
    #[error("unknown method: {0}")]
    MethodNotFound(String),
    #[error("unknown tool: {0}")]
    UnknownTool(String),
    #[error("invalid tool params: {0}")]
    InvalidParams(#[from] serde_json::Error),
    #[error("weather API request failed: {0}")]
    HttpRequest(#[from] reqwest::Error),
}

impl McpError {
    fn code(&self) -> i32 {
        match self {
            Self::MethodNotFound(_) => -32601,
            Self::UnknownTool(_) | Self::InvalidParams(_) => -32602,
            Self::HttpRequest(_) => -32603,
        }
    }
}

// --- JSON-RPC 2.0 types ---

#[derive(Deserialize)]
pub struct JsonRpcRequest {
    pub id: Option<Value>,
    pub method: String,
    pub params: Option<Value>,
}

#[derive(Serialize)]
struct JsonRpcResponse {
    jsonrpc: &'static str,
    id: Value,
    #[serde(skip_serializing_if = "Option::is_none")]
    result: Option<Value>,
    #[serde(skip_serializing_if = "Option::is_none")]
    error: Option<JsonRpcErrorBody>,
}

#[derive(Serialize)]
struct JsonRpcErrorBody {
    code: i32,
    message: String,
}

impl JsonRpcResponse {
    fn success(id: Value, result: Value) -> Self {
        Self { jsonrpc: "2.0", id, result: Some(result), error: None }
    }

    fn from_error(id: Value, err: McpError) -> Self {
        Self {
            jsonrpc: "2.0",
            id,
            result: None,
            error: Some(JsonRpcErrorBody { code: err.code(), message: err.to_string() }),
        }
    }
}

// --- MCP handler ---

pub async fn mcp_handler(Json(req): Json<JsonRpcRequest>) -> impl IntoResponse {
    let id_display = req.id.as_ref().map(|v| v.to_string()).unwrap_or_else(|| "notification".to_string());
    info!(method = %req.method, id = %id_display, "MCP request received");

    // Notifications (no id) don't expect a response
    if req.id.is_none() {
        debug!(method = %req.method, "Handling notification");
        return (
            [(axum::http::header::CONTENT_TYPE, "text/event-stream")],
            String::new(),
        );
    }

    let id = req.id.unwrap();

    let response = match req.method.as_str() {
        "initialize" => {
            debug!("Handling initialize");
            handle_initialize(id)
        }
        "tools/list" => {
            debug!("Handling tools/list");
            handle_tools_list(id)
        }
        "tools/call" => {
            let params = req.params.unwrap_or(json!({}));
            let tool_name = params.get("name").and_then(|v| v.as_str()).unwrap_or("unknown");
            info!(tool = %tool_name, "Handling tools/call");
            handle_tools_call(id, params).await
        }
        other => {
            warn!(method = %other, "Unknown MCP method requested");
            JsonRpcResponse::from_error(id, McpError::MethodNotFound(other.to_string()))
        }
    };

    (
        [(axum::http::header::CONTENT_TYPE, "text/event-stream")],
        format!("data: {}\n\n", serde_json::to_string(&response).unwrap()),
    )
}

pub async fn mcp_get_handler() -> impl IntoResponse {
    StatusCode::METHOD_NOT_ALLOWED
}

fn handle_initialize(id: Value) -> JsonRpcResponse {
    JsonRpcResponse::success(id, json!({
        "protocolVersion": "2025-11-25",
        "capabilities": { "tools": {} },
        "serverInfo": { "name": "microvm-rust-mcp", "version": "1.0.0" }
    }))
}

fn handle_tools_list(id: Value) -> JsonRpcResponse {
    let weather_schema = schema_for!(GetWeatherParams);
    let hourly_schema = schema_for!(GetHourlyParams);
    let geocode_schema = schema_for!(GeocodeParams);

    JsonRpcResponse::success(id, json!({
        "tools": [
            {
                "name": "geocode",
                "description": "Search for a location by name and return its coordinates (latitude, longitude), country, timezone, and population. Use this to resolve city or place names to coordinates before calling get_weather or get_hourly_forecast.",
                "inputSchema": geocode_schema
            },
            {
                "name": "get_weather",
                "description": "Get current weather conditions and daily forecast for a location. Returns temperature, humidity, wind, and weather conditions.",
                "inputSchema": weather_schema
            },
            {
                "name": "get_hourly_forecast",
                "description": "Get hourly weather forecast for a location. Returns detailed hour-by-hour data for temperature, humidity, wind, and conditions.",
                "inputSchema": hourly_schema
            }
        ]
    }))
}

async fn handle_tools_call(id: Value, params: Value) -> JsonRpcResponse {
    let name = params.get("name").and_then(|v| v.as_str()).unwrap_or("");
    let arguments = params.get("arguments").cloned().unwrap_or(json!({}));

    let result = match name {
        "geocode" => {
            let p: GeocodeParams = match serde_json::from_value(arguments) {
                Ok(p) => p,
                Err(e) => {
                    warn!(tool = "geocode", error = %e, "Invalid parameters");
                    return JsonRpcResponse::from_error(id, McpError::InvalidParams(e));
                }
            };
            info!(tool = "geocode", query = %p.name, "Geocoding location");
            fetch_geocode(p).await
        }
        "get_weather" => {
            let p: GetWeatherParams = match serde_json::from_value(arguments) {
                Ok(p) => p,
                Err(e) => {
                    warn!(tool = "get_weather", error = %e, "Invalid parameters");
                    return JsonRpcResponse::from_error(id, McpError::InvalidParams(e));
                }
            };
            info!(tool = "get_weather", lat = %p.latitude, lon = %p.longitude, "Fetching weather");
            fetch_weather(p).await
        }
        "get_hourly_forecast" => {
            let p: GetHourlyParams = match serde_json::from_value(arguments) {
                Ok(p) => p,
                Err(e) => {
                    warn!(tool = "get_hourly_forecast", error = %e, "Invalid parameters");
                    return JsonRpcResponse::from_error(id, McpError::InvalidParams(e));
                }
            };
            info!(tool = "get_hourly_forecast", lat = %p.latitude, lon = %p.longitude, "Fetching hourly forecast");
            fetch_hourly(p).await
        }
        _ => {
            warn!(tool = %name, "Unknown tool requested");
            return JsonRpcResponse::from_error(id, McpError::UnknownTool(name.to_string()));
        }
    };

    match result {
        Ok(text) => {
            debug!(tool = %name, bytes = text.len(), "Tool call succeeded");
            JsonRpcResponse::success(id, json!({
                "content": [{ "type": "text", "text": text }],
                "isError": false
            }))
        }
        Err(e) => {
            error!(tool = %name, error = %e, "Tool call failed");
            JsonRpcResponse::from_error(id, e)
        }
    }
}

// --- Tool parameter types ---

#[derive(Debug, Deserialize, schemars::JsonSchema)]
pub struct GetWeatherParams {
    /// Latitude of the location (e.g., 52.52 for Berlin)
    latitude: f64,
    /// Longitude of the location (e.g., 13.41 for Berlin)
    longitude: f64,
    /// Comma-separated current weather variables (e.g., temperature_2m,wind_speed_10m)
    #[serde(default = "default_current")]
    current: String,
    /// Comma-separated daily weather variables (e.g., temperature_2m_max,temperature_2m_min)
    #[serde(default = "default_daily")]
    daily: String,
    /// Timezone for the response (use 'auto' to detect from coordinates)
    #[serde(default = "default_timezone")]
    timezone: String,
    /// Number of forecast days (1-16)
    #[serde(default = "default_forecast_days")]
    forecast_days: u8,
    /// Temperature unit: 'celsius' or 'fahrenheit'
    #[serde(default = "default_temperature_unit")]
    temperature_unit: String,
}

#[derive(Debug, Deserialize, schemars::JsonSchema)]
pub struct GetHourlyParams {
    /// Latitude of the location
    latitude: f64,
    /// Longitude of the location
    longitude: f64,
    /// Comma-separated hourly variables (e.g., temperature_2m,relative_humidity_2m,wind_speed_10m)
    #[serde(default = "default_hourly")]
    hourly: String,
    /// Timezone for the response
    #[serde(default = "default_timezone")]
    timezone: String,
    /// Number of forecast days (1-16)
    #[serde(default = "default_forecast_days")]
    forecast_days: u8,
    /// Temperature unit: 'celsius' or 'fahrenheit'
    #[serde(default = "default_temperature_unit")]
    temperature_unit: String,
}

#[derive(Debug, Deserialize, schemars::JsonSchema)]
pub struct GeocodeParams {
    /// Name of the city or place to search for (e.g., "Florida", "Tokyo", "Sevilla")
    name: String,
    /// Maximum number of results to return (1-10)
    #[serde(default = "default_geocode_count")]
    count: u8,
    /// Language for result names (e.g., "en", "es", "de")
    #[serde(default = "default_geocode_language")]
    language: String,
}

fn default_geocode_count() -> u8 { 5 }
fn default_geocode_language() -> String { "en".to_string() }

fn default_current() -> String {
    "temperature_2m,relative_humidity_2m,apparent_temperature,wind_speed_10m,wind_direction_10m,weather_code".to_string()
}
fn default_daily() -> String {
    "temperature_2m_max,temperature_2m_min,precipitation_sum,weather_code".to_string()
}
fn default_timezone() -> String { "auto".to_string() }
fn default_forecast_days() -> u8 { 3 }
fn default_temperature_unit() -> String { "celsius".to_string() }
fn default_hourly() -> String {
    "temperature_2m,relative_humidity_2m,wind_speed_10m,weather_code".to_string()
}

// --- Tool implementations ---

async fn fetch_weather(params: GetWeatherParams) -> Result<String, McpError> {
    let url = format!(
        "https://api.open-meteo.com/v1/forecast?latitude={}&longitude={}&current={}&daily={}&timezone={}&forecast_days={}&temperature_unit={}",
        params.latitude, params.longitude, params.current, params.daily,
        params.timezone, params.forecast_days, params.temperature_unit,
    );

    debug!(url = %url, "Requesting Open-Meteo API");
    let resp = reqwest::get(&url).await?;
    let status = resp.status();

    if !status.is_success() {
        let body = resp.text().await.unwrap_or_default();
        error!(status = %status, body = %body, "Open-Meteo API returned error");
        return Ok(format!("Error from Open-Meteo ({status}): {body}"));
    }

    let data: Value = resp.json().await?;
    Ok(format_weather_response(&data, &params.temperature_unit))
}

async fn fetch_hourly(params: GetHourlyParams) -> Result<String, McpError> {
    let url = format!(
        "https://api.open-meteo.com/v1/forecast?latitude={}&longitude={}&hourly={}&timezone={}&forecast_days={}&temperature_unit={}",
        params.latitude, params.longitude, params.hourly,
        params.timezone, params.forecast_days, params.temperature_unit,
    );

    debug!(url = %url, "Requesting Open-Meteo API");
    let resp = reqwest::get(&url).await?;
    let status = resp.status();

    if !status.is_success() {
        let body = resp.text().await.unwrap_or_default();
        error!(status = %status, body = %body, "Open-Meteo API returned error");
        return Ok(format!("Error from Open-Meteo ({status}): {body}"));
    }

    let data: Value = resp.json().await?;
    Ok(format_hourly_response(&data, &params.temperature_unit))
}

async fn fetch_geocode(params: GeocodeParams) -> Result<String, McpError> {
    let url = format!(
        "https://geocoding-api.open-meteo.com/v1/search?name={}&count={}&language={}",
        params.name, params.count, params.language,
    );

    debug!(url = %url, "Requesting Open-Meteo Geocoding API");
    let resp = reqwest::get(&url).await?;
    let data: Value = resp.json().await?;

    let empty = Vec::new();
    let results = data.get("results").and_then(|v| v.as_array()).unwrap_or(&empty);

    if results.is_empty() {
        return Ok(format!("No results found for '{}'", params.name));
    }

    let mut parts = Vec::new();
    parts.push(format!("Geocoding results for '{}':", params.name));
    parts.push(String::new());
    for (i, r) in results.iter().enumerate() {
        let name = r.get("name").and_then(|v| v.as_str()).unwrap_or("?");
        let lat = r.get("latitude").unwrap_or(&Value::Null);
        let lon = r.get("longitude").unwrap_or(&Value::Null);
        let country = r.get("country").and_then(|v| v.as_str()).unwrap_or("?");
        let admin1 = r.get("admin1").and_then(|v| v.as_str()).unwrap_or("");
        let timezone = r.get("timezone").and_then(|v| v.as_str()).unwrap_or("?");
        let population = r.get("population").and_then(|v| v.as_u64()).unwrap_or(0);
        let elevation = r.get("elevation").unwrap_or(&Value::Null);

        let location = if admin1.is_empty() {
            format!("{name}, {country}")
        } else {
            format!("{name}, {admin1}, {country}")
        };

        parts.push(format!("{}. {}", i + 1, location));
        parts.push(format!("   Coordinates: {lat}, {lon}"));
        parts.push(format!("   Timezone: {timezone}"));
        parts.push(format!("   Population: {population}"));
        parts.push(format!("   Elevation: {elevation}m"));
        parts.push(String::new());
    }
    Ok(parts.join("\n"))
}

// --- Response formatting ---

fn wmo_description(code: u64) -> &'static str {
    match code {
        0 => "Clear sky",
        1 => "Mainly clear",
        2 => "Partly cloudy",
        3 => "Overcast",
        45 => "Fog",
        48 => "Depositing rime fog",
        51 => "Light drizzle",
        53 => "Moderate drizzle",
        55 => "Dense drizzle",
        61 => "Slight rain",
        63 => "Moderate rain",
        65 => "Heavy rain",
        66 => "Light freezing rain",
        67 => "Heavy freezing rain",
        71 => "Slight snow fall",
        73 => "Moderate snow fall",
        75 => "Heavy snow fall",
        77 => "Snow grains",
        80 => "Slight rain showers",
        81 => "Moderate rain showers",
        82 => "Violent rain showers",
        85 => "Slight snow showers",
        86 => "Heavy snow showers",
        95 => "Thunderstorm",
        96 => "Thunderstorm with slight hail",
        99 => "Thunderstorm with heavy hail",
        _ => "Unknown",
    }
}

fn format_weather_response(data: &Value, temp_unit: &str) -> String {
    let unit = if temp_unit == "fahrenheit" { "F" } else { "C" };
    let mut parts = Vec::new();

    parts.push(format!(
        "Location: {}N, {}E (elevation: {}m)",
        data["latitude"], data["longitude"], data.get("elevation").unwrap_or(&Value::Null)
    ));
    parts.push(format!("Timezone: {}", data.get("timezone").and_then(|v| v.as_str()).unwrap_or("Unknown")));

    if let Some(current) = data.get("current") {
        let code = current.get("weather_code").and_then(|v| v.as_u64()).unwrap_or(0);
        parts.push(String::new());
        parts.push("Current Conditions:".to_string());
        parts.push(format!("  Condition: {}", wmo_description(code)));
        parts.push(format!("  Temperature: {} {unit}", current.get("temperature_2m").unwrap_or(&Value::Null)));
        parts.push(format!("  Feels like: {} {unit}", current.get("apparent_temperature").unwrap_or(&Value::Null)));
        parts.push(format!("  Humidity: {}%", current.get("relative_humidity_2m").unwrap_or(&Value::Null)));
        parts.push(format!("  Wind: {} km/h", current.get("wind_speed_10m").unwrap_or(&Value::Null)));
        parts.push(format!("  Wind direction: {} degrees", current.get("wind_direction_10m").unwrap_or(&Value::Null)));
    }

    if let Some(daily) = data.get("daily") {
        if let Some(times) = daily.get("time").and_then(|v| v.as_array()) {
            parts.push(String::new());
            parts.push("Daily Forecast:".to_string());
            for (i, time) in times.iter().enumerate() {
                let code = daily.get("weather_code").and_then(|v| v.get(i)).and_then(|v| v.as_u64()).unwrap_or(0);
                let high = daily.get("temperature_2m_max").and_then(|v| v.get(i)).unwrap_or(&Value::Null);
                let low = daily.get("temperature_2m_min").and_then(|v| v.get(i)).unwrap_or(&Value::Null);
                let precip = daily.get("precipitation_sum").and_then(|v| v.get(i)).unwrap_or(&Value::Null);
                parts.push(format!(
                    "  {}: {} | High: {} {unit} | Low: {} {unit} | Precip: {} mm",
                    time.as_str().unwrap_or("?"), wmo_description(code), high, low, precip
                ));
            }
        }
    }

    parts.push(String::new());
    parts.push("Source: Open-Meteo API (https://open-meteo.com)".to_string());
    parts.join("\n")
}

fn format_hourly_response(data: &Value, temp_unit: &str) -> String {
    let unit = if temp_unit == "fahrenheit" { "F" } else { "C" };
    let mut parts = Vec::new();

    parts.push(format!(
        "Location: {}N, {}E",
        data["latitude"], data["longitude"]
    ));
    parts.push(format!("Timezone: {}", data.get("timezone").and_then(|v| v.as_str()).unwrap_or("Unknown")));

    if let Some(hourly) = data.get("hourly") {
        if let Some(times) = hourly.get("time").and_then(|v| v.as_array()) {
            parts.push(String::new());
            parts.push(format!("Hourly Forecast ({} hours):", times.len()));
            for (i, time) in times.iter().enumerate() {
                let temp = hourly.get("temperature_2m").and_then(|v| v.get(i)).unwrap_or(&Value::Null);
                let humidity = hourly.get("relative_humidity_2m").and_then(|v| v.get(i));
                let wind = hourly.get("wind_speed_10m").and_then(|v| v.get(i));
                let code = hourly.get("weather_code").and_then(|v| v.get(i)).and_then(|v| v.as_u64()).unwrap_or(0);

                let mut line = format!(
                    "  {}: {} {unit} | {}",
                    time.as_str().unwrap_or("?"), temp, wmo_description(code)
                );
                if let Some(h) = humidity {
                    line.push_str(&format!(" | Humidity: {}%", h));
                }
                if let Some(w) = wind {
                    line.push_str(&format!(" | Wind: {} km/h", w));
                }
                parts.push(line);
            }
        }
    }

    parts.push(String::new());
    parts.push("Source: Open-Meteo API (https://open-meteo.com)".to_string());
    parts.join("\n")
}
