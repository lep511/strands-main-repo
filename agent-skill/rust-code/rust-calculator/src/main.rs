use serde::{Deserialize, Serialize};
use std::io::{self, Read};

#[derive(Deserialize)]
#[serde(tag = "operation")]
enum Request {
    #[serde(rename = "npv")]
    Npv { rate: f64, cashflows: Vec<f64> },
    #[serde(rename = "irr")]
    Irr { cashflows: Vec<f64> },
    #[serde(rename = "compound_interest")]
    CompoundInterest {
        principal: f64,
        rate: f64,
        periods: u32,
        compounds_per_period: Option<u32>,
    },
    #[serde(rename = "loan_payment")]
    LoanPayment {
        principal: f64,
        annual_rate: f64,
        months: u32,
    },
    #[serde(rename = "future_value")]
    FutureValue {
        payment: f64,
        rate: f64,
        periods: u32,
    },
}

#[derive(Serialize)]
struct Response {
    success: bool,
    result: Option<f64>,
    error: Option<String>,
}

impl Response {
    fn ok(value: f64) -> Self {
        Self {
            success: true,
            result: Some(value),
            error: None,
        }
    }

    fn err(msg: &str) -> Self {
        Self {
            success: false,
            result: None,
            error: Some(msg.to_string()),
        }
    }
}

fn npv(rate: f64, cashflows: &[f64]) -> f64 {
    cashflows
        .iter()
        .enumerate()
        .map(|(t, cf)| cf / (1.0 + rate).powi(t as i32))
        .sum()
}

fn irr(cashflows: &[f64]) -> Option<f64> {
    let mut guess = 0.1_f64;
    for _ in 0..1000 {
        let npv_val: f64 = cashflows
            .iter()
            .enumerate()
            .map(|(t, cf)| cf / (1.0 + guess).powi(t as i32))
            .sum();

        let dnpv: f64 = cashflows
            .iter()
            .enumerate()
            .skip(1)
            .map(|(t, cf)| -(t as f64) * cf / (1.0 + guess).powi(t as i32 + 1))
            .sum();

        if dnpv.abs() < 1e-12 {
            return None;
        }

        let new_guess = guess - npv_val / dnpv;
        if (new_guess - guess).abs() < 1e-9 {
            return Some(new_guess);
        }
        guess = new_guess;
    }
    None
}

fn compound_interest(principal: f64, rate: f64, periods: u32, n: u32) -> f64 {
    principal * (1.0 + rate / n as f64).powi((n * periods) as i32)
}

fn loan_payment(principal: f64, annual_rate: f64, months: u32) -> f64 {
    let r = annual_rate / 12.0;
    if r == 0.0 {
        return principal / months as f64;
    }
    principal * r * (1.0 + r).powi(months as i32) / ((1.0 + r).powi(months as i32) - 1.0)
}

fn future_value(payment: f64, rate: f64, periods: u32) -> f64 {
    if rate == 0.0 {
        return payment * periods as f64;
    }
    payment * ((1.0 + rate).powi(periods as i32) - 1.0) / rate
}

fn handle(input: &str) -> Response {
    let request: Request = match serde_json::from_str(input) {
        Ok(r) => r,
        Err(e) => return Response::err(&format!("Invalid input: {e}")),
    };

    match request {
        Request::Npv { rate, cashflows } => {
            if cashflows.is_empty() {
                return Response::err("cashflows must not be empty");
            }
            Response::ok(npv(rate, &cashflows))
        }
        Request::Irr { cashflows } => {
            if cashflows.len() < 2 {
                return Response::err("cashflows must have at least 2 values");
            }
            match irr(&cashflows) {
                Some(r) => Response::ok(r),
                None => Response::err("IRR did not converge"),
            }
        }
        Request::CompoundInterest {
            principal,
            rate,
            periods,
            compounds_per_period,
        } => {
            let n = compounds_per_period.unwrap_or(1);
            if n == 0 {
                return Response::err("compounds_per_period must be > 0");
            }
            Response::ok(compound_interest(principal, rate, periods, n))
        }
        Request::LoanPayment {
            principal,
            annual_rate,
            months,
        } => {
            if months == 0 {
                return Response::err("months must be > 0");
            }
            Response::ok(loan_payment(principal, annual_rate, months))
        }
        Request::FutureValue {
            payment,
            rate,
            periods,
        } => Response::ok(future_value(payment, rate, periods)),
    }
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
    fn test_npv_basic() {
        let result = npv(0.1, &[-1000.0, 300.0, 420.0, 680.0]);
        assert!((result - 130.73).abs() < 0.01);
    }

    #[test]
    fn test_irr_converges() {
        let cashflows = vec![-1000.0, 300.0, 420.0, 680.0];
        let r = irr(&cashflows).unwrap();
        let check: f64 = cashflows
            .iter()
            .enumerate()
            .map(|(t, cf)| cf / (1.0 + r).powi(t as i32))
            .sum();
        assert!(check.abs() < 1e-6);
    }

    #[test]
    fn test_compound_interest() {
        let result = compound_interest(1000.0, 0.05, 10, 12);
        assert!((result - 1647.01).abs() < 0.01);
    }

    #[test]
    fn test_loan_payment() {
        let result = loan_payment(200000.0, 0.06, 360);
        assert!((result - 1199.10).abs() < 0.01);
    }

    #[test]
    fn test_future_value() {
        let result = future_value(500.0, 0.005, 120);
        assert!((result - 81939.67).abs() < 1.0);
    }

    #[test]
    fn test_handle_json() {
        let input = r#"{"operation":"npv","rate":0.1,"cashflows":[-1000,300,420,680]}"#;
        let resp = handle(input);
        assert!(resp.success);
        assert!((resp.result.unwrap() - 130.73).abs() < 0.01);
    }

    #[test]
    fn test_handle_invalid_json() {
        let resp = handle("not json");
        assert!(!resp.success);
        assert!(resp.error.unwrap().contains("Invalid input"));
    }
}
