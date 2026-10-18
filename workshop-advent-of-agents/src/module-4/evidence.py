"""Deterministic, read-only evidence collectors, one per checklist area.

The assessor agent never browses the repo freely: it calls these functions, which
return short facts with file references. Code evidence is collected per registered
agent (from its `source` directory); estate-wide signals (IaC, CI, drills) are
collected from the repository root.
"""

import json
import re
import subprocess
import time
from pathlib import Path

import estate_registry

REPO_ROOT = estate_registry.REPO_ROOT
DRILL_RESULT = estate_registry.HERE / "drill_result.json"
SKIP_DIRS = estate_registry.VENDOR_DIRS | {".git", ".saif-data", ".pytest_cache"}


def _files(root: Path, suffixes: tuple[str, ...] = (".py",)) -> list[Path]:
    return [p for p in sorted(root.rglob("*")) if p.is_file() and p.suffix in suffixes
            and not SKIP_DIRS.intersection(p.relative_to(REPO_ROOT).parts)]


def _grep(pattern: str, root: Path, suffixes: tuple[str, ...] = (".py",)) -> list[str]:
    rx = re.compile(pattern, re.IGNORECASE)
    hits = []
    for path in _files(root, suffixes):
        if path.name.startswith("test_") or path.name == "evidence.py":
            continue  # tests and this file mention every pattern without implementing it
        for n, line in enumerate(path.read_text(errors="ignore").splitlines(), 1):
            if rx.search(line):
                hits.append(f"{path.relative_to(REPO_ROOT)}:{n}")
                break  # one reference per file is enough evidence
    return hits


def _per_agent(pattern: str, suffixes: tuple[str, ...] = (".py",)) -> list[str]:
    facts = []
    for agent in estate_registry.agents():
        hits = _grep(pattern, REPO_ROOT / agent["source"], suffixes)
        facts.append(f"{agent['id']}: {', '.join(hits) if hits else 'NONE'}")
    return facts


def _estate_files(patterns: list[str]) -> list[str]:
    found = []
    for pattern in patterns:
        found += [str(p.relative_to(REPO_ROOT)) for p in REPO_ROOT.rglob(pattern)
                  if not SKIP_DIRS.intersection(p.relative_to(REPO_ROOT).parts)]
    return sorted(set(found))


def _scheduled_ci() -> list[str]:
    workflows = _estate_files([".github/workflows/*.yml", ".github/workflows/*.yaml", "buildspec*.yml"])
    return [w for w in workflows if "schedule" in (REPO_ROOT / w).read_text()] or ["NONE"]


def _drill() -> str:
    if not DRILL_RESULT.exists():
        return "no containment drill has been run (drill_result.json missing)"
    d = json.loads(DRILL_RESULT.read_text())
    age_days = (time.time() - d["finished_at"]) / 86400
    return (f"last drill on '{d['agent_id']}': time_to_contain={d['time_to_contain_s']:.2f}s, "
            f"passed={d['passed']}, new invocation refused={d['new_invocation_refused']}, {age_days:.1f} days ago")


def _git_history(paths: list[str]) -> list[str]:
    facts = []
    for p in paths:
        try:
            out = subprocess.run(["git", "log", "--oneline", "--", p], cwd=REPO_ROOT,
                                 capture_output=True, text=True, timeout=10).stdout.strip()
        except (OSError, subprocess.TimeoutExpired):
            out = ""
        facts.append(f"{p}: {len(out.splitlines())} commits")
    return facts


def collect(area_id: str) -> dict:
    """Return the evidence for one checklist area as a list of facts."""
    registry = estate_registry.agents()
    facts: list[str]
    match area_id:
        case "identity":
            facts = [f"{a['id']}: identity={a['identity']}" for a in registry]
            facts += ["workload identity code: " + "; ".join(_per_agent(r"agentcore.?identity|workload.?identity"))]
            facts.append("all agents authenticate to Bedrock with the default boto3 credential chain (developer credentials)")
        case "inventory":
            facts = [f"registry {estate_registry.REGISTRY_PATH.name}: {len(registry)} agents, "
                     f"{sum(1 for a in registry if a.get('owner'))} with owner"]
            shadow = estate_registry.unregistered_sources()
            facts.append(f"unregistered agent-defining files: {shadow or 'NONE'}")
            facts.append("registration enforced at runtime (RegistryGate): " + "; ".join(_per_agent(r"RegistryGate")))
            facts.append("discovery of unregistered agents: available on demand (estate_registry.py discover), not scheduled")
        case "infrastructure":
            iac = _estate_files(["*.tf", "cdk.json", "template.yaml", "template.yml", "agentcore.json", "Dockerfile"])
            facts = [f"IaC / deployment files: {iac or 'NONE'}", f"CI pipelines: {_estate_files(['.github/workflows/*'] ) or 'NONE'}",
                     "local AgentCore-compatible server: " + "; ".join(_per_agent(r"BedrockAgentCoreApp"))]
        case "prompt_shielding":
            facts = ["Bedrock Guardrails: " + "; ".join(_per_agent(r"guardrail_id|guardrailIdentifier")),
                     "untrusted-content isolation: " + "; ".join(_per_agent(r"UntrustedContentFilter|untrusted_"))]
        case "data_leaks":
            facts = ["output sanitizer / domain allowlist: " + "; ".join(_per_agent(r"sanitize_output|ALLOWED_LINK_DOMAINS")),
                     "PII masking: " + "; ".join(_per_agent(r"\bpii\b|redact|anonymi[sz]e")),
                     "tool-argument allowlists: " + "; ".join(_per_agent(r"COMPANY_DOMAIN|Allowed tools"))]
        case "circuit_breakers":
            facts = ["invocation limits (turns/tokens): " + "; ".join(_per_agent(r"limits\s*=|LIMITS\b")),
                     "tool-call budgets: " + "; ".join(_per_agent(r"LimitToolCounts|max_tool")),
                     "gateway rate limiting: NONE (no AgentCore Gateway in front of any agent)"]
        case "tracing":
            facts = ["Strands telemetry setup: " + "; ".join(_per_agent(r"StrandsTelemetry")),
                     "OTLP export to a backend: " + "; ".join(_per_agent(r"setup_otlp_exporter|OTEL_EXPORTER_OTLP")),
                     "ADOT / CloudWatch: " + "; ".join(_per_agent(r"aws-opentelemetry-distro|opentelemetry-instrument|cloudwatch"))]
        case "anomalies":
            facts = ["metric alarms / anomaly detection: " + "; ".join(_per_agent(r"put_metric_alarm|anomaly_detector|AnomalyDetector")),
                     "token usage captured per call: " + "; ".join(_per_agent(r"accumulated_usage|inputTokens"))]
        case "audit":
            facts = ["audit logging: " + "; ".join(_per_agent(r"AuditLog|audit_log")),
                     "immutable store: " + "; ".join(_per_agent(r"object.?lock|cloudtrail")),
                     "audit sinks are local files (audit.jsonl), mutable and per-machine"]
        case "containment":
            facts = ["single-agent revocation (RegistryGate/ContainmentWatch): " + "; ".join(_per_agent(r"RegistryGate|ContainmentWatch")),
                     "credential revocation: no per-agent IAM role exists to revoke", _drill()]
        case "threat_alerts":
            facts = ["GuardDuty / Security Hub: " + "; ".join(_per_agent(r"guardduty|securityhub|security_hub"))]
        case "playbooks":
            playbooks = _estate_files(["PLAYBOOK*.md", "postmortem*.md", "POSTMORTEM*.md"])
            facts = [f"playbooks / postmortem templates: {playbooks or 'NONE'}", _drill(),
                     f"scheduled drills: {_scheduled_ci()}"]
        case "drift":
            facts = ["eval suites: " + "; ".join(_per_agent(r"strands_evals")),
                     f"scheduled CI runs: {_scheduled_ci()}"]
        case "red_teaming":
            facts = ["adversarial / injection suites: " + "; ".join(_per_agent(r"attack|redteam|injection")),
                     f"scheduled CI runs: {_scheduled_ci()}"]
        case "policy_updates":
            specs = _estate_files(["DESIGN_SPEC.md", "checklist.yaml", "agent_registry.yaml", "saif_controls.py"])
            facts = [f"versioned policy artifacts: {specs}", *_git_history(specs),
                     f"postmortems: {_estate_files(['postmortems/*.md']) or 'NONE'}"]
        case _:
            raise ValueError(f"unknown area '{area_id}'")
    return {"area": area_id, "facts": facts}


if __name__ == "__main__":
    import yaml

    checklist = yaml.safe_load((estate_registry.HERE / "checklist.yaml").read_text())
    for layer in checklist["layers"]:
        for area in layer["areas"]:
            print(f"\n## {layer['id']}/{area['id']}")
            for fact in collect(area["id"])["facts"]:
                print(f"  - {fact}")
