use serde::{Deserialize, Serialize};
use std::io::{self, Read};

#[derive(Deserialize)]
struct Request {
    value: f64,
    from: Unit,
    to: Unit,
}

#[derive(Deserialize, Serialize, Clone, Copy, PartialEq)]
#[serde(rename_all = "snake_case")]
enum Unit {
    Meter,
    Kilometer,
    Centimeter,
    Millimeter,
    Mile,
    Yard,
    Foot,
    Inch,
}

impl Unit {
    fn to_meters(self, value: f64) -> f64 {
        match self {
            Unit::Meter => value,
            Unit::Kilometer => value * 1000.0,
            Unit::Centimeter => value / 100.0,
            Unit::Millimeter => value / 1000.0,
            Unit::Mile => value * 1609.344,
            Unit::Yard => value * 0.9144,
            Unit::Foot => value * 0.3048,
            Unit::Inch => value * 0.0254,
        }
    }

    fn from_meters(self, value: f64) -> f64 {
        match self {
            Unit::Meter => value,
            Unit::Kilometer => value / 1000.0,
            Unit::Centimeter => value * 100.0,
            Unit::Millimeter => value * 1000.0,
            Unit::Mile => value / 1609.344,
            Unit::Yard => value / 0.9144,
            Unit::Foot => value / 0.3048,
            Unit::Inch => value / 0.0254,
        }
    }

    fn abbreviation(self) -> &'static str {
        match self {
            Unit::Meter => "m",
            Unit::Kilometer => "km",
            Unit::Centimeter => "cm",
            Unit::Millimeter => "mm",
            Unit::Mile => "mi",
            Unit::Yard => "yd",
            Unit::Foot => "ft",
            Unit::Inch => "in",
        }
    }
}

#[derive(Serialize)]
struct Response {
    success: bool,
    result: Option<f64>,
    from_unit: Option<&'static str>,
    to_unit: Option<&'static str>,
    error: Option<String>,
}

impl Response {
    fn ok(value: f64, from: Unit, to: Unit) -> Self {
        Self {
            success: true,
            result: Some(value),
            from_unit: Some(from.abbreviation()),
            to_unit: Some(to.abbreviation()),
            error: None,
        }
    }

    fn err(msg: &str) -> Self {
        Self {
            success: false,
            result: None,
            from_unit: None,
            to_unit: None,
            error: Some(msg.to_string()),
        }
    }
}

fn convert(value: f64, from: Unit, to: Unit) -> f64 {
    to.from_meters(from.to_meters(value))
}

fn handle(input: &str) -> Response {
    let request: Request = match serde_json::from_str(input) {
        Ok(r) => r,
        Err(e) => return Response::err(&format!("Invalid input: {e}")),
    };

    if request.value < 0.0 {
        return Response::err("value must be non-negative");
    }

    let result = convert(request.value, request.from, request.to);
    Response::ok(result, request.from, request.to)
}

fn main() {
    let mut input = String::new();
    io::stdin().read_to_string(&mut input).unwrap_or_default();

    let response = handle(input.trim());
    println!("{}", serde_json::to_string(&response).unwrap());
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_km_to_miles() {
        let result = convert(10.0, Unit::Kilometer, Unit::Mile);
        assert!((result - 6.21371).abs() < 0.001);
    }

    #[test]
    fn test_feet_to_meters() {
        let result = convert(6.0, Unit::Foot, Unit::Meter);
        assert!((result - 1.8288).abs() < 0.001);
    }

    #[test]
    fn test_inches_to_cm() {
        let result = convert(12.0, Unit::Inch, Unit::Centimeter);
        assert!((result - 30.48).abs() < 0.001);
    }

    #[test]
    fn test_miles_to_km() {
        let result = convert(1.0, Unit::Mile, Unit::Kilometer);
        assert!((result - 1.609344).abs() < 0.001);
    }

    #[test]
    fn test_same_unit() {
        let result = convert(42.0, Unit::Meter, Unit::Meter);
        assert!((result - 42.0).abs() < 0.001);
    }

    #[test]
    fn test_handle_json() {
        let input = r#"{"value": 5, "from": "kilometer", "to": "mile"}"#;
        let resp = handle(input);
        assert!(resp.success);
        assert!((resp.result.unwrap() - 3.10686).abs() < 0.001);
    }

    #[test]
    fn test_handle_negative() {
        let input = r#"{"value": -1, "from": "meter", "to": "foot"}"#;
        let resp = handle(input);
        assert!(!resp.success);
        assert!(resp.error.unwrap().contains("non-negative"));
    }

    #[test]
    fn test_handle_invalid_json() {
        let resp = handle("not json");
        assert!(!resp.success);
        assert!(resp.error.unwrap().contains("Invalid input"));
    }
}
