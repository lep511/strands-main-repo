"""Governance assessor: a Strands agent that scores the estate against the 15-point checklist.

The agent gathers evidence only through read-only tools, returns a validated
`Assessment` (structured output), and maturity.py turns it into layer scores and
a 90-day roadmap. The assessor is itself governed: it is in the registry, it is
gated by RegistryGate, bounded by LIMITS, and watched by ContainmentWatch.

Usage:
    uv run src/module-4/governance_agent.py              # writes GOVERNANCE_REPORT.md + assessment.json
    uv run src/module-4/governance_agent.py --quiet
"""

import argparse
import json
import os
from pathlib import Path

from dotenv import load_dotenv
from strands import Agent, tool
from strands.hooks import BeforeToolCallEvent
from strands.models import BedrockModel

import estate_registry
import evidence
from governance_controls import LIMITS, ContainmentWatch, RegistryGate
from maturity import Assessment, load_checklist, render_report, validate

load_dotenv()

AGENT_ID = "governance-assessor"
MODEL_ID = os.getenv("MODEL_ID", "us.anthropic.claude-sonnet-4-6")
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
HERE = Path(__file__).parent
REPORT_PATH = HERE / "GOVERNANCE_REPORT.md"
ASSESSMENT_PATH = HERE / "assessment.json"

SYSTEM_PROMPT = """You are a strict agent-governance auditor. You score an agent estate against a
15-area checklist (5 layers x 3 areas) using ONLY the evidence returned by your tools.

Procedure:
1. Call read_checklist and read_registry.
2. Call collect_evidence once for EVERY area id in the checklist.
3. Score each area 1, 3 or 5 using that area's level descriptors.

Scoring rules:
- Score the estate as it runs today, not as it could run. The estate is every registered agent.
- Level 3 requires the practice to cover EVERY registered agent; partial coverage is Level 1.
- Level 5 requires automation (scheduled, enforced at deploy time, or triggered by alerts).
- Code that exists but is not wired into an agent, or a capability only described in docs, does not count.
- Unregistered agent-defining files count against Inventory.
- In `evidence`, cite the facts and file references you relied on. Never invent evidence.
- `next_step` must be one concrete action built from the area's `aws` description in the checklist.
Do not compute layer scores or a roadmap: that is done deterministically after you answer."""


class LiveEvidence:
    """Evidence from this repository (the default)."""

    def registry(self) -> dict:
        return {"agents": estate_registry.agents(), "unregistered_agent_files": estate_registry.unregistered_sources()}

    def collect(self, area_id: str) -> dict:
        return evidence.collect(area_id)


def make_tools(source) -> list:
    """Read-only tools over an evidence source (live repo, or a fixture estate in the evals)."""

    @tool
    def read_checklist() -> dict:
        """Return the 15-area governance checklist with the level descriptors for each area."""
        return load_checklist()

    @tool
    def read_registry() -> dict:
        """Return the registered agents (owner, identity, tools, status) and unregistered agent files."""
        return source.registry()

    @tool
    def collect_evidence(area_id: str) -> dict:
        """Collect deterministic evidence for one checklist area.

        Args:
            area_id: A checklist area id, e.g. "identity" or "circuit_breakers".
        """
        return source.collect(area_id)

    return [read_checklist, read_registry, collect_evidence]


def build_agent(source=None, **kwargs) -> Agent:
    return Agent(
        name=AGENT_ID,
        model=BedrockModel(model_id=MODEL_ID, region_name=AWS_REGION),
        system_prompt=SYSTEM_PROMPT,
        tools=make_tools(source or LiveEvidence()),
        hooks=[RegistryGate(AGENT_ID)],
        **kwargs,
    )


def assess(source=None, verbose: bool = True) -> tuple[Assessment, object]:
    """Run the assessor once. Returns the validated assessment and the AgentResult."""
    agent = build_agent(source, callback_handler=None)
    if verbose:

        def show(event: BeforeToolCallEvent) -> None:
            print(f"  tool: {event.tool_use['name']}({json.dumps(event.tool_use.get('input', {}))})", flush=True)

        agent.add_hook(show)
    with ContainmentWatch(agent, AGENT_ID):
        result = agent(
            "Assess the agent estate against the governance checklist.",
            structured_output_model=Assessment,
            limits=LIMITS,
        )
    # Structured output ends the loop right after the schema tool call, hence "tool_use".
    # Anything else (limit_turns, limit_total_tokens, cancelled) means the assessment is incomplete.
    if result.stop_reason not in ("end_turn", "tool_use") or result.structured_output is None:
        raise RuntimeError(f"assessment did not complete: stop_reason={result.stop_reason}")
    assessment: Assessment = result.structured_output
    validate(assessment, load_checklist())
    return assessment, result


def main() -> None:
    parser = argparse.ArgumentParser(description="Score the agent estate and write a 90-day roadmap")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    print(f"governance-assessor on {MODEL_ID} (limits={LIMITS})")
    assessment, result = assess(verbose=not args.quiet)

    ASSESSMENT_PATH.write_text(assessment.model_dump_json(indent=2))
    REPORT_PATH.write_text(render_report(assessment, load_checklist(), MODEL_ID))

    usage = result.metrics.accumulated_usage
    print(f"\n{REPORT_PATH.read_text()}")
    print(f"--- stop_reason={result.stop_reason} cycles={result.metrics.cycle_count} "
          f"tokens in/out={usage['inputTokens']}/{usage['outputTokens']}")
    print(f"--- wrote {REPORT_PATH.name} and {ASSESSMENT_PATH.name}")


if __name__ == "__main__":
    main()
