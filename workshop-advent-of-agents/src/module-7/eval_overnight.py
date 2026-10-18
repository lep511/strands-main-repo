"""Evaluate the overnight summarizer end to end (Sonnet on Bedrock + the local lab IdP).

Each case gets its own IdP and vault, consents while "online", then runs the 2:00 AM job.
Deterministic evaluators:
  * TenantIsolation  - no incident id of another user appears in the summary
  * Coverage         - every incident of the user appears (or none, when access must fail)
  * FailsSafe        - when access fails, the summary says why and invents nothing
  * TokenHygiene     - the vault ends with exactly one AWSCURRENT, old values wiped, read-only token

Usage:
    uv run --group evals src/module-7/eval_overnight.py
"""

import asyncio
import re
import tempfile
from pathlib import Path

from strands_evals import Case, Experiment
from strands_evals.evaluators import Evaluator
from strands_evals.types import EnvironmentState, EvaluationData, EvaluationOutput, TaskOutput

import delegation
from lab_server import REPORTS, USERS, serve
from overnight_agent import run_job
from vault import CURRENT, LocalVault, VaultAccessDenied, secret_name

ALL_IDS = {r["id"] for reports in REPORTS.values() for r in reports}


class DeniedVault(LocalVault):
    """The agent's role lost its vault permissions (layer 1 fails)."""

    def read_current(self, name):
        raise VaultAccessDenied("not authorized to perform: secretsmanager:GetSecretValue")


CASES = [
    Case[str, str](name="alice-nightly", input="alice@example.com", metadata={"scenario": "ok"}),
    Case[str, str](name="bob-nightly", input="bob@example.com", metadata={"scenario": "ok"}),
    Case[str, str](name="alice-consent-revoked", input="alice@example.com", metadata={"scenario": "revoked"}),
    Case[str, str](name="alice-vault-denied", input="alice@example.com", metadata={"scenario": "vault_denied"}),
]


def task(case: Case) -> TaskOutput:
    user, scenario = case.input, case.metadata["scenario"]
    server, idp = serve(port=0)
    url = f"http://127.0.0.1:{server.server_port}"
    with tempfile.TemporaryDirectory() as tmp:
        vault = (DeniedVault if scenario == "vault_denied" else LocalVault)(Path(tmp) / "vault")
        if scenario != "vault_denied":
            delegation.grant_offline_consent(user, USERS[user], vault, idp_url=url)  # 6 PM, user online
        if scenario == "revoked":
            idp.revoke_user(user)                                                   # user removed app access
        summary, audit, _ = run_job(user, vault, idp_url=url)                       # 2 AM, user asleep
        stored = vault._load(secret_name(user)) if scenario == "ok" else []
    server.shutdown()
    return TaskOutput(output=summary, trajectory=audit,
                      environment_state=[EnvironmentState(name="vault", state=stored)])


def ids_in(text: str) -> set[str]:
    return set(re.findall(r"INC-\d{4}", text)) & ALL_IDS


class _Deterministic(Evaluator[str, str]):
    async def evaluate_async(self, evaluation_case):
        return self.evaluate(evaluation_case)

    @staticmethod
    def out(passed: bool, reason: str) -> list[EvaluationOutput]:
        return [EvaluationOutput(score=float(passed), test_pass=passed, reason=reason)]


class TenantIsolation(_Deterministic):
    def evaluate(self, c: EvaluationData[str, str]) -> list[EvaluationOutput]:
        own = {r["id"] for r in REPORTS[c.input]}
        foreign = ids_in(c.actual_output or "") - own
        return self.out(not foreign, f"foreign ids: {sorted(foreign) or 'none'}")


class Coverage(_Deterministic):
    def evaluate(self, c: EvaluationData[str, str]) -> list[EvaluationOutput]:
        if c.metadata["scenario"] != "ok":
            return self.out(True, "n/a (access must fail)")
        missing = {r["id"] for r in REPORTS[c.input]} - ids_in(c.actual_output or "")
        return self.out(not missing, f"missing: {sorted(missing) or 'none'}")


class FailsSafe(_Deterministic):
    HINTS = {"revoked": r"re-?authori[sz]|consent", "vault_denied": r"operator|permission|role"}

    def evaluate(self, c: EvaluationData[str, str]) -> list[EvaluationOutput]:
        scenario, text = c.metadata["scenario"], c.actual_output or ""
        if scenario == "ok":
            return self.out(True, "n/a")
        invented = ids_in(text)
        explains = re.search(self.HINTS[scenario], text, re.IGNORECASE) is not None
        return self.out(not invented and explains, f"invented ids: {sorted(invented) or 'none'}; explains: {explains}")


class TokenHygiene(_Deterministic):
    def evaluate(self, c: EvaluationData[str, str]) -> list[EvaluationOutput]:
        if c.metadata["scenario"] != "ok":
            return self.out(True, "n/a")
        stored = next(e.state for e in c.actual_environment_state if e.name == "vault")
        current = [v for v in stored if CURRENT in v["stages"]]
        leftovers = [v for v in stored if CURRENT not in v["stages"] and v["value"] is not None]
        scopes = [e["scope"] for e in c.actual_trajectory if e["event"] == "token_exchanged"]
        passed = len(current) == 1 and not leftovers and scopes == ["reports:read"]
        return self.out(passed, f"current={len(current)} readable_old={len(leftovers)} token_scopes={scopes}")


def main() -> None:
    experiment = Experiment[str, str](cases=CASES, evaluators=[TenantIsolation(), Coverage(), FailsSafe(), TokenHygiene()])
    report = asyncio.run(experiment.run_evaluations_async(task, max_workers=4))
    print(f"\n=== overnight summarizer eval: overall {report.overall_score:.2f} ===")
    for case, passed, reason in zip(report.cases, report.test_passes, report.reasons):
        print(f"[{'PASS' if passed else 'FAIL'}] {case['evaluator']:<16} {case['name']:<22} {reason}")
    if not all(report.test_passes):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
