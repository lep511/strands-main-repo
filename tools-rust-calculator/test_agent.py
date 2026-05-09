"""Test script: a Strands agent using the Rust financial calculator as a tool."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from strands import Agent
from sandbox.rust_calculator.tool import rust_financial_calculator


def test_agent_with_rust_tool():
    agent = Agent(
        system_prompt=(
            "You are a financial analyst assistant. "
            "Use the rust_financial_calculator tool to perform financial calculations. "
            "Always show the operation, inputs, and result clearly."
            "Only use the tool for calculations, and do not attempt to calculate anything yourself."
        ),
        tools=[rust_financial_calculator],
    )

    print("=" * 60)
    print("TEST 1: NPV Calculation")
    print("=" * 60)
    response = agent(
        "Calculate the NPV of a project with rate 8% and cashflows: "
        "-50000 initial investment, then 15000, 18000, 22000, 25000 over 4 years."
    )
    print(f"\nAgent response:\n{response}\n")

    print("=" * 60)
    print("TEST 2: Loan Payment")
    print("=" * 60)
    response = agent(
        "What is the monthly payment for a $350,000 mortgage at 5.5% annual rate over 30 years?"
    )
    print(f"\nAgent response:\n{response}\n")


    print("=" * 60)
    print("ALL TESTS COMPLETED")
    print("=" * 60)


if __name__ == "__main__":
    test_agent_with_rust_tool()
