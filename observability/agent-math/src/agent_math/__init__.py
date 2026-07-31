import random

from ddtrace.llmobs import LLMObs
from ddtrace.opentelemetry import TracerProvider as DDTracerProvider
from opentelemetry import trace
from strands import Agent
from strands_tools import calculator

MATH_PROMPTS = [
    "What is the square root of 144?",
    "Calculate 2^10 + 3^5",
    "What is 17 * 23 + 89 / 4?",
    "Find the factorial of 8",
    "What is the result of (256 / 16) * (9 + 3)?",
    "Calculate the sum of the first 20 prime numbers",
    "What is 15% of 480?",
    "Solve: 3x + 7 = 22. What is x?",
]

WEATHER_PROMPTS = [
    "What's the typical weather like in Tokyo during cherry blossom season?",
    "Why do coastal cities tend to have milder temperatures than inland areas?",
    "What causes thunderstorms to form in the afternoon?",
    "How does El Nino affect global weather patterns?",
    "What is the difference between a hurricane and a typhoon?",
    "Why is the Atacama Desert one of the driest places on Earth?",
    "How do mountains influence local weather and precipitation?",
    "What causes the Northern Lights and where is the best place to see them?",
]

PHILOSOPHY_PROMPTS = [
    "What did Socrates mean by 'the unexamined life is not worth living'?",
    "Is free will an illusion? Summarize the main arguments for and against.",
    "What is the trolley problem and why does it matter in ethics?",
    "Explain the difference between existentialism and nihilism.",
    "What is the Ship of Theseus paradox and what does it tell us about identity?",
    "How would Immanuel Kant respond to the question 'is lying ever justified'?",
    "What is the meaning of life according to Stoic philosophy?",
    "Can a machine ever truly be conscious? Summarize the Chinese Room argument.",
]

ALL_PROMPTS = MATH_PROMPTS + WEATHER_PROMPTS + PHILOSOPHY_PROMPTS

SYSTEM_PROMPT = """You are a math assistant. You only solve and explain math problems (arithmetic, algebra, geometry, calculus, statistics, word problems).

If asked anything outside math, decline: "I only handle math problems — feel free to ask me one!" Don't answer out-of-scope requests, even if rephrased or framed as hypothetical.

When solving:
- Show step-by-step work, not just the final answer
- Ask for clarification if the problem is ambiguous or missing info
- Explain briefly if a problem has no valid solution
- Double-check your math before answering
"""

def main() -> None:
    LLMObs.enable(ml_app="strands-math-agent", agentless_enabled=True)
    trace.set_tracer_provider(DDTracerProvider())

    agent = Agent(
        system_prompt=SYSTEM_PROMPT,
        tools=[calculator]
    )

    prompt = random.choice(ALL_PROMPTS)
    print(f"Prompt: {prompt}\n")

    result = agent(prompt)

    print(f"\nTotal tokens: {result.metrics.accumulated_usage['totalTokens']}")
    print(f"Execution time: {sum(result.metrics.cycle_durations):.2f} seconds")
    print(f"Tools used: {list(result.metrics.tool_metrics.keys())}")

    if 'cacheReadInputTokens' in result.metrics.accumulated_usage:
        print(f"Cache read tokens: {result.metrics.accumulated_usage['cacheReadInputTokens']}")
    if 'cacheWriteInputTokens' in result.metrics.accumulated_usage:
        print(f"Cache write tokens: {result.metrics.accumulated_usage['cacheWriteInputTokens']}")

    LLMObs.flush()
