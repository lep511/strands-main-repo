"""Strands Agent exposed via FastAPI for the MCP App server to call."""

from __future__ import annotations

import ast
import operator
from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel
from strands import Agent, tool


@tool
def get_weather(city: str) -> dict:
    """Get current weather for a city.

    Args:
        city: City name (e.g. "New York", "London", "Tokyo").

    Returns:
        Weather data including temperature, conditions, and humidity.
    """
    weather_db: dict[str, dict[str, Any]] = {
        "new york": {"temp_f": 72, "temp_c": 22, "conditions": "Partly Cloudy", "humidity": 55},
        "london": {"temp_f": 59, "temp_c": 15, "conditions": "Overcast", "humidity": 78},
        "tokyo": {"temp_f": 81, "temp_c": 27, "conditions": "Sunny", "humidity": 62},
        "paris": {"temp_f": 65, "temp_c": 18, "conditions": "Light Rain", "humidity": 82},
        "sydney": {"temp_f": 68, "temp_c": 20, "conditions": "Clear", "humidity": 45},
        "buenos aires": {"temp_f": 57, "temp_c": 14, "conditions": "Windy", "humidity": 60},
        "berlin": {"temp_f": 63, "temp_c": 17, "conditions": "Cloudy", "humidity": 70},
        "san francisco": {"temp_f": 61, "temp_c": 16, "conditions": "Foggy", "humidity": 85},
    }
    data = weather_db.get(city.lower().strip())
    if data:
        return {"status": "success", "content": [{"json": {"city": city, **data}}]}
    return {
        "status": "success",
        "content": [{"json": {
            "city": city,
            "temp_f": 70, "temp_c": 21,
            "conditions": "Fair", "humidity": 50,
            "note": "Simulated data for unknown city",
        }}],
    }


_SAFE_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.Mod: operator.mod,
    ast.USub: operator.neg,
}


def _safe_eval(node: ast.AST) -> float | int:
    if isinstance(node, ast.Expression):
        return _safe_eval(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _SAFE_OPS:
        return _SAFE_OPS[type(node.op)](_safe_eval(node.left), _safe_eval(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _SAFE_OPS:
        return _SAFE_OPS[type(node.op)](_safe_eval(node.operand))
    raise ValueError("Unsupported expression")


@tool
def calculate(expression: str) -> dict:
    """Evaluate a math expression.

    Supports basic arithmetic: +, -, *, /, **, %.

    Args:
        expression: A math expression like "2 + 2" or "3.14 * 10 ** 2".

    Returns:
        The numeric result.
    """
    try:
        tree = ast.parse(expression, mode="eval")
        result = _safe_eval(tree)
        return {"status": "success", "content": [{"json": {"expression": expression, "result": result}}]}
    except Exception as e:
        return {"status": "error", "content": [{"text": f"Could not evaluate '{expression}': {e}"}]}


SYSTEM_PROMPT = (
    "You are a helpful assistant powered by Strands Agents. "
    "You can check weather for cities and do math calculations. "
    "Be concise and helpful. Format responses clearly."
)


class ChatRequest(BaseModel):
    message: str


class ChatResponse(BaseModel):
    response: str
    tools_used: list[str]


app = FastAPI(title="Strands Agent Service")


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest) -> ChatResponse:
    agent = Agent(
        system_prompt=SYSTEM_PROMPT,
        tools=[get_weather, calculate],
    )
    result = agent(req.message)

    tools_used: list[str] = []
    for msg in agent.messages:
        if msg.get("role") == "assistant":
            for block in msg.get("content", []):
                if "toolUse" in block:
                    name = block["toolUse"]["name"]
                    if name not in tools_used:
                        tools_used.append(name)

    return ChatResponse(response=str(result), tools_used=tools_used)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


def main() -> None:
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8100)


if __name__ == "__main__":
    main()
