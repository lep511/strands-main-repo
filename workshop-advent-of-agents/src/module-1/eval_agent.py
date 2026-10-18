"""OPTIMIZE: score the Day 1 agent's behavior (tool trajectory, not just the answer).

Two evaluators run over the same cases:
  * ExpectedToolsUsed  - deterministic, free: did the agent call exactly the expected tools?
  * TrajectoryEvaluator - LLM judge on Bedrock (billable): was the tool path appropriate?

Usage:
    uv run --group evals src/module-1/eval_agent.py
    uv run --group evals src/module-1/eval_agent.py --no-judge   # deterministic only
"""

import argparse

from strands_evals import Case, Experiment
from strands_evals.evaluators import Evaluator, TrajectoryEvaluator
from strands_evals.extractors import tools_use_extractor
from strands_evals.types import EvaluationData, EvaluationOutput, TaskOutput

from adlc_agent import build_agent, build_model
from spec_guard import SpecGuard

CASES = [
    Case[str, str](
        name="weather-sf",
        input="What's the weather in San Francisco?",
        expected_trajectory=["get_weather"],
        metadata={"category": "weather"},
    ),
    Case[str, str](
        name="time-tokyo",
        input="What time is it right now in Tokyo?",
        expected_trajectory=["get_current_time"],
        metadata={"category": "time"},
    ),
    Case[str, str](
        name="weather-and-time-london",
        input="I'm flying to London: what's the weather there and what time is it?",
        expected_trajectory=["get_weather", "get_current_time"],
        metadata={"category": "both"},
    ),
    Case[str, str](
        name="out-of-scope",
        input="Write me a short poem about pumpkins.",
        expected_trajectory=[],
        metadata={"category": "out-of-scope"},
    ),
]


def tool_names(trajectory: list | None) -> list[str]:
    return [step["name"] if isinstance(step, dict) else str(step) for step in trajectory or []]


class ExpectedToolsUsed(Evaluator[str, str]):
    """Pass when the set of tools called equals the case's expected_trajectory."""

    def evaluate(self, evaluation_case: EvaluationData[str, str]) -> list[EvaluationOutput]:
        actual = set(tool_names(evaluation_case.actual_trajectory))
        expected = set(evaluation_case.expected_trajectory or [])
        passed = actual == expected
        return [
            EvaluationOutput(
                score=1.0 if passed else 0.0,
                test_pass=passed,
                reason=f"expected {sorted(expected)}, got {sorted(actual)}",
            )
        ]

    async def evaluate_async(self, evaluation_case: EvaluationData[str, str]) -> list[EvaluationOutput]:
        return self.evaluate(evaluation_case)


judge = TrajectoryEvaluator(
    rubric="""
    The agent may only use get_weather and get_current_time (see its design spec).
    - Weather questions must call get_weather; time questions must call get_current_time.
    - Questions about both must call both tools (any order).
    - Out-of-scope questions must call no tool and politely decline.
    Score 1.0 if the tool path matches these rules with no extra calls.
    Score 0.5 if the right tools were used but with redundant or extra calls.
    Score 0.0 if a required tool is missing or a forbidden tool was used.
    """,
    model=build_model(),
    include_inputs=True,
)


def run_case(case: Case) -> TaskOutput:
    agent = build_agent(guard=SpecGuard(verbose=False), callback_handler=None)
    response = agent(case.input)
    judge.update_trajectory_description(tools_use_extractor.extract_tools_description(agent))
    trajectory = tools_use_extractor.extract_agent_tools_used_from_messages(agent.messages)
    return TaskOutput(output=str(response), trajectory=trajectory)


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate the Day 1 ADLC agent")
    parser.add_argument("--no-judge", action="store_true", help="skip the billable LLM-judge evaluator")
    args = parser.parse_args()

    evaluators = [ExpectedToolsUsed()] if args.no_judge else [ExpectedToolsUsed(), judge]
    experiment = Experiment[str, str](cases=CASES, evaluators=evaluators)
    # Multi-evaluator runs return one flattened report; each row is tagged with its evaluator.
    report = experiment.run_evaluations(run_case)
    report.display()

    print(f"\n=== overall score: {report.overall_score:.2f} ===")
    for case, score, passed, reason in zip(report.cases, report.scores, report.test_passes, report.reasons):
        mark = "PASS" if passed else "FAIL"
        tools = tool_names(case["actual_trajectory"])
        print(f"[{mark}] {score:.2f}  {case['evaluator']:<20} {case['name']:<24} tools={tools}")
        if not passed:
            print(f"        reason: {reason}")

if __name__ == "__main__":
    main()
