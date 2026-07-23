use axum::{extract::Query, http::StatusCode, response::IntoResponse, Json};
use serde::{Deserialize, Serialize};
use thiserror::Error;
use tracing::{debug, error, info};

#[derive(Debug, Error)]
pub enum WeatherError {
    #[error("Open-Meteo API request failed: {0}")]
    HttpRequest(#[from] reqwest::Error),
    #[error("Open-Meteo API error ({status}): {body}")]
    UpstreamError { status: u16, body: String },
}

impl IntoResponse for WeatherError {
    fn into_response(self) -> axum::response::Response {
        let (status, reason) = match &self {
            WeatherError::HttpRequest(_) => (StatusCode::BAD_GATEWAY, self.to_string()),
            WeatherError::UpstreamError { status, .. } => (
                StatusCode::from_u16(*status).unwrap_or(StatusCode::BAD_GATEWAY),
                self.to_string(),
            ),
        };
        error!(error = %reason, "Weather request failed");
        (status, Json(ErrorBody { error: true, reason })).into_response()
    }
}

#[derive(Debug, Serialize)]
struct ErrorBody {
    error: bool,
    reason: String,
}

#[derive(Debug, Deserialize)]
pub struct WeatherQuery {
    pub latitude: f64,
    pub longitude: f64,
    #[serde(default = "default_hourly")]
    pub hourly: String,
    #[serde(default)]
    pub daily: Option<String>,
    #[serde(default)]
    pub current: Option<String>,
    #[serde(default = "default_temperature_unit")]
    pub temperature_unit: String,
    #[serde(default = "default_wind_speed_unit")]
    pub wind_speed_unit: String,
    #[serde(default)]
    pub timezone: Option<String>,
    #[serde(default)]
    pub forecast_days: Option<u8>,
}

fn default_hourly() -> String {
    "temperature_2m".to_string()
}

fn default_temperature_unit() -> String {
    "celsius".to_string()
}

fn default_wind_speed_unit() -> String {
    "kmh".to_string()
}

#[derive(Debug, Serialize, Deserialize)]
pub struct WeatherResponse {
    pub latitude: f64,
    pub longitude: f64,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub elevation: Option<f64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub generationtime_ms: Option<f64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub utc_offset_seconds: Option<i32>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub timezone: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub timezone_abbreviation: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub current: Option<serde_json::Value>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub current_units: Option<serde_json::Value>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub hourly: Option<serde_json::Value>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub hourly_units: Option<serde_json::Value>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub daily: Option<serde_json::Value>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub daily_units: Option<serde_json::Value>,
}

pub async fn get_weather(
    Query(params): Query<WeatherQuery>,
) -> Result<Json<WeatherResponse>, WeatherError> {
    info!(lat = %params.latitude, lon = %params.longitude, "Weather request");

    let mut url = format!(
        "https://api.open-meteo.com/v1/forecast?latitude={}&longitude={}&hourly={}&temperature_unit={}&wind_speed_unit={}",
        params.latitude, params.longitude, params.hourly, params.temperature_unit, params.wind_speed_unit,
    );

    if let Some(daily) = &params.daily {
        url.push_str(&format!("&daily={daily}"));
    }
    if let Some(current) = &params.current {
        url.push_str(&format!("&current={current}"));
    }
    if let Some(timezone) = &params.timezone {
        url.push_str(&format!("&timezone={timezone}"));
    }
    if let Some(forecast_days) = params.forecast_days {
        url.push_str(&format!("&forecast_days={forecast_days}"));
    }

    debug!(url = %url, "Requesting Open-Meteo API");
    let response = reqwest::Client::new().get(&url).send().await?;

    if !response.status().is_success() {
        let status = response.status().as_u16();
        let body = response.text().await.unwrap_or_default();
        return Err(WeatherError::UpstreamError { status, body });
    }

    let weather: WeatherResponse = response.json().await?;
    debug!(lat = %weather.latitude, lon = %weather.longitude, "Weather response received");
    Ok(Json(weather))
}
