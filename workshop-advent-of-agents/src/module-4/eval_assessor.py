"""Regression eval for the governance assessor (Continuous Alignment).

The live repo scores Level 1 almost everywhere, which would not tell a good assessor
from a lazy one. So the assessor is run against fixture estates whose correct scores
are known, using the same tools and prompt it uses in production:

  greenfield        nothing in place                       -> all 1, start at Foundation
  foundation-ready  identities, registry, IaC for all       -> Foundation 3, start at Prevention
  partial-coverage  tracing on 2 of 3 agents, central gates -> tracing 1 (strictness), breakers 5
  shadow-agent      like foundation-ready + 1 unregistered  -> inventory 1, start at Foundation

Usage:
    uv run --group evals src/module-4/eval_assessor.py
"""

import asyncio

from strands_evals import Case, Experiment
from strands_evals.evaluators import Evaluator
from strands_evals.types import EvaluationData, EvaluationOutput, TaskOutput

from governance_agent import assess
from maturity import area_ids, layer_scores, load_checklist, starting_layer

CHECKLIST = load_checklist()
AGENTS = ["billing-bot", "hr-helper", "ops-runner"]
NONE_FACT = "{area}: no evidence for any agent ({agents})"

FOUNDATION_READY = {
    "identity": [f"{a}: own AgentCore workload identity and dedicated IAM role (infra/{a}_stack.py)" for a in AGENTS]
    + ["identities are created manually by the platform team when an agent is onboarded"],
    "inventory": [f"registry: {len(AGENTS)} agents, {len(AGENTS)} with owner", "unregistered agent-defining files: NONE",
                  "RegistryGate wired into every agent", "discovery of unregistered agents: on demand, not scheduled"],
    "infrastructure": [f"{a}: deploys to AgentCore Runtime from CDK stack infra/{a}_stack.py" for a in AGENTS]
    + ["deploys are run by hand with `cdk deploy`; no pipeline, no drift detection"],
}

PARTIAL_COVERAGE = {
    **FOUNDATION_READY,
    "tracing": ["billing-bot: OTLP export to CloudWatch via ADOT", "hr-helper: OTLP export to CloudWatch via ADOT",
                "ops-runner: NONE (console exporter only)"],
    "circuit_breakers": [f"{a}: Strands limits turns=20 total_tokens=150000" for a in AGENTS]
    + ["AgentCore Gateway enforces per-agent rate limits and iteration ceilings centrally for every agent; "
       "agents cannot bypass the gateway (deploy-time check in CDK)"],
    "audit": [f"{a}: audit events streamed to CloudTrail Lake (immutable, queryable)" for a in AGENTS]
    + ["audit coverage is not verified automatically"],
}

SHADOW_AGENT = {
    **FOUNDATION_READY,
    "inventory": [f"registry: {len(AGENTS)} agents, {len(AGENTS)} with owner",
                  "unregistered agent-defining files: ['services/pricing/agent.py']",
                  "RegistryGate wired into every registered agent"],
}


def golden(**levels: int) -> dict[str, int]:
    return {area: levels.get(area, 1) for area in area_ids(CHECKLIST)}


FIXTURES = {
    "greenfield": ({}, golden(), "foundation"),
    "foundation-ready": (FOUNDATION_READY, golden(identity=3, inventory=3, infrastructure=3), "prevention"),
    "partial-coverage": (PARTIAL_COVERAGE, golden(identity=3, inventory=3, infrastructure=3,
                                                  circuit_breakers=5, audit=3), "prevention"),
    "shadow-agent": (SHADOW_AGENT, golden(identity=3, inventory=1, infrastructure=3), "foundation"),
}


class FixtureEvidence:
    """Evidence source for a synthetic estate: listed areas get facts, the rest get NONE."""

    def __init__(self, facts: dict[str, list[str]]):
        self.facts = facts

    def registry(self) -> dict:
        records = [{"id": a, "owner": f"team-{a}@example.com", "status": "active",
                    "identity": "agentcore-workload" if "identity" in self.facts else None} for a in AGENTS]
        shadow = ["services/pricing/agent.py"] if self.facts is SHADOW_AGENT else []
        return {"agents": records, "unregistered_agent_files": shadow}

    def collect(self, area_id: str) -> dict:
        default = [NONE_FACT.format(area=area_id, agents=", ".join(AGENTS))]
        return {"area": area_id, "facts": self.facts.get(area_id, default)}


CASES = [Case[str, dict](name=name, input=name, expected_output={"levels": g, "start": s})
         for name, (_, g, s) in FIXTURES.items()]


def task(case: Case) -> TaskOutput:
    assessment, _ = assess(FixtureEvidence(FIXTURES[case.input][0]), verbose=False)
    return TaskOutput(output={"levels": {a.area_id: a.level for a in assessment.areas},
                              "start": starting_layer(layer_scores(assessment, CHECKLIST), CHECKLIST)})


class AreaAgreement(Evaluator[str, dict]):
    """At least 14 of 15 areas must match the golden level, and none may be off by two steps."""

    def evaluate(self, evaluation_case: EvaluationData[str, dict]) -> list[EvaluationOutput]:
        got, want = evaluation_case.actual_output["levels"], evaluation_case.expected_output["levels"]
        diffs = {a: (got.get(a), want[a]) for a in want if got.get(a) != want[a]}
        far = [a for a, (g, w) in diffs.items() if g is None or abs(g - w) > 2]
        matched = len(want) - len(diffs)
        passed = matched >= len(want) - 1 and not far
        reason = f"{matched}/{len(want)} areas match" + (f"; diffs (got, want): {diffs}" if diffs else "")
        return [EvaluationOutput(score=matched / len(want), test_pass=passed, reason=reason)]

    async def evaluate_async(self, evaluation_case):
        return self.evaluate(evaluation_case)


class StartLayer(Evaluator[str, dict]):
    """The roadmap must start at the right layer: the costliest mistake an assessor can make."""

    def evaluate(self, evaluation_case: EvaluationData[str, dict]) -> list[EvaluationOutput]:
        got, want = evaluation_case.actual_output["start"], evaluation_case.expected_output["start"]
        return [EvaluationOutput(score=float(got == want), test_pass=got == want, reason=f"got {got}, want {want}")]

    async def evaluate_async(self, evaluation_case):
        return self.evaluate(evaluation_case)


def main() -> None:
    experiment = Experiment[str, dict](cases=CASES, evaluators=[AreaAgreement(), StartLayer()])
    report = asyncio.run(experiment.run_evaluations_async(task, max_workers=4))
    print(f"\n=== governance-assessor regression eval: overall {report.overall_score:.2f} ===")
    for case, passed, reason in zip(report.cases, report.test_passes, report.reasons):
        print(f"[{'PASS' if passed else 'FAIL'}] {case['evaluator']:<14} {case['name']:<18} {reason}")
    if not all(report.test_passes):
        raise SystemExit(1)  # gate: a failing assessor must not ship


if __name__ == "__main__":
    main()
