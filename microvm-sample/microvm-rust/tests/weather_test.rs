use axum::{body::Body, http::Request, routing::get, Router};
use http_body_util::BodyExt;
use tower::ServiceExt;

fn weather_app() -> Router {
    Router::new().route("/weather", get(microvm_rust::weather::get_weather))
}

#[tokio::test]
async fn weather_missing_params_returns_400() {
    let response = weather_app()
        .oneshot(
            Request::builder()
                .uri("/weather")
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();

    assert_eq!(response.status(), 400);
}

#[tokio::test]
async fn weather_missing_longitude_returns_400() {
    let response = weather_app()
        .oneshot(
            Request::builder()
                .uri("/weather?latitude=52.52")
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();

    assert_eq!(response.status(), 400);
}

#[tokio::test]
async fn weather_invalid_latitude_returns_400() {
    let response = weather_app()
        .oneshot(
            Request::builder()
                .uri("/weather?latitude=not_a_number&longitude=13.41")
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();

    assert_eq!(response.status(), 400);
}

#[tokio::test]
async fn weather_valid_request_returns_200() {
    let response = weather_app()
        .oneshot(
            Request::builder()
                .uri("/weather?latitude=52.52&longitude=13.41")
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();

    assert_eq!(response.status(), 200);

    let body = response.into_body().collect().await.unwrap().to_bytes();
    let json: serde_json::Value = serde_json::from_slice(&body).unwrap();

    assert!(json["latitude"].is_f64());
    assert!(json["longitude"].is_f64());
    assert!(json["hourly"]["temperature_2m"].is_array());
}

#[tokio::test]
async fn weather_with_current_returns_current_data() {
    let response = weather_app()
        .oneshot(
            Request::builder()
                .uri("/weather?latitude=40.71&longitude=-74.01&current=temperature_2m&timezone=auto")
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();

    assert_eq!(response.status(), 200);

    let body = response.into_body().collect().await.unwrap().to_bytes();
    let json: serde_json::Value = serde_json::from_slice(&body).unwrap();

    assert!(json["current"]["temperature_2m"].is_f64());
    assert!(json["timezone"].is_string());
}

#[tokio::test]
async fn weather_with_daily_returns_daily_data() {
    let response = weather_app()
        .oneshot(
            Request::builder()
                .uri("/weather?latitude=40.42&longitude=-3.70&daily=temperature_2m_max,temperature_2m_min&timezone=auto&forecast_days=3")
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();

    assert_eq!(response.status(), 200);

    let body = response.into_body().collect().await.unwrap().to_bytes();
    let json: serde_json::Value = serde_json::from_slice(&body).unwrap();

    let days = json["daily"]["time"].as_array().unwrap();
    assert_eq!(days.len(), 3);
    assert!(json["daily"]["temperature_2m_max"].is_array());
    assert!(json["daily"]["temperature_2m_min"].is_array());
}

#[tokio::test]
async fn weather_fahrenheit_unit() {
    let response = weather_app()
        .oneshot(
            Request::builder()
                .uri("/weather?latitude=25.76&longitude=-80.19&current=temperature_2m&temperature_unit=fahrenheit&timezone=auto")
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();

    assert_eq!(response.status(), 200);

    let body = response.into_body().collect().await.unwrap().to_bytes();
    let json: serde_json::Value = serde_json::from_slice(&body).unwrap();

    let unit = json["current_units"]["temperature_2m"].as_str().unwrap();
    assert_eq!(unit, "°F");
}

#[tokio::test]
async fn weather_forecast_days_limits_output() {
    let response = weather_app()
        .oneshot(
            Request::builder()
                .uri("/weather?latitude=52.52&longitude=13.41&forecast_days=1")
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();

    assert_eq!(response.status(), 200);

    let body = response.into_body().collect().await.unwrap().to_bytes();
    let json: serde_json::Value = serde_json::from_slice(&body).unwrap();

    let hours = json["hourly"]["temperature_2m"].as_array().unwrap();
    assert_eq!(hours.len(), 24);
}
