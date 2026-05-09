"""Strands @tool wrapper for the Rust financial calculator binary."""

import json
import subprocess
from pathlib import Path
from typing import Any

from strands import tool

BINARY_PATH = Path(__file__).parent / "target" / "release" / "rust_calculator"


@tool
def rust_financial_calculator(operation: str, params: dict) -> dict:
    """High-performance financial calculator implemented in Rust.

    Supported operations:
    - npv: Net Present Value. Params: rate (float), cashflows (list of floats)
    - irr: Internal Rate of Return. Params: cashflows (list of floats)
    - compound_interest: Compound interest. Params: principal, rate, periods, compounds_per_period (optional, default 1)
    - loan_payment: Monthly loan payment. Params: principal, annual_rate, months
    - future_value: Future value of annuity. Params: payment, rate, periods

    Args:
        operation: One of "npv", "irr", "compound_interest", "loan_payment", "future_value"
        params: Dictionary of parameters specific to the operation

    Returns:
        Dictionary with 'success' (bool), 'result' (float or None), 'error' (str or None)
    """
    if not BINARY_PATH.exists():
        return {
            "success": False,
            "result": None,
            "error": f"Binary not found at {BINARY_PATH}. Run: cargo build --release",
        }

    payload = {"operation": operation, **params}

    try:
        proc = subprocess.run(
            [str(BINARY_PATH)],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            timeout=30,
        )
    except subprocess.TimeoutExpired:
        return {"success": False, "result": None, "error": "Calculation timed out"}
    except OSError as e:
        return {"success": False, "result": None, "error": f"Failed to execute binary: {e}"}

    if proc.returncode != 0:
        return {
            "success": False,
            "result": None,
            "error": f"Process exited with code {proc.returncode}: {proc.stderr}",
        }

    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {"success": False, "result": None, "error": f"Invalid output: {proc.stdout}"}
