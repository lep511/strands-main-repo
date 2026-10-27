from strands import Agent, tool
from strands.vended_tools import http_request
import logging

logging.basicConfig(level=logging.INFO)


@tool
def calculate(expression: str) -> str:
    """Evaluate a math expression and return the result.

    Args:
        expression: A Python math expression to evaluate (e.g. "100 * 20.45").

    Returns:
        The result of the calculation as a string.
    """
    result = eval(expression)  # noqa: S307
    return str(result)


agent = Agent(
    tools=[
        http_request,
        calculate,
    ],
    system_prompt="""You are a helpful currency exchange assistant.
    When asked about exchange rates or currency conversions, use the Frankfurt API:
    - Latest rates:  https://api.frankfurter.dev/v1/latest?base=<BASE>&symbols=<TARGET>
    - Convert amount: https://api.frankfurter.dev/v1/latest?amount=<AMOUNT>&from=<BASE>&to=<TARGET>
    where <BASE> and <TARGET> are ISO 4217 currency codes (e.g. USD, EUR, GBP, JPY, MXN).
    Always show the exchange rate used and the final converted amount.
    Use the calculate tool for any arithmetic such as multiplying amounts by rates or comparing totals.""",
)

result = agent("How much is 154850 USD in Pounds and how much percent is depreaceted?")
print("\n\n")
