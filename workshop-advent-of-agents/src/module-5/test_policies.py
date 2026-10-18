"""Offline checks of the agent identity's IAM documents. No AWS calls.

Usage:
    uv run --group dev --group deploy pytest src/module-5 -q
"""

import importlib.util
from pathlib import Path

import pytest

import policies

ACCOUNT, REGION, AGENT = "123456789012", "us-east-1", "aoa_day05_weather"
DATA_PREFIXES = ("athena:", "glue:", "s3:")


def actions(doc: dict) -> set[str]:
    return {a for s in doc["Statement"] for a in ([s["Action"]] if isinstance(s["Action"], str) else s["Action"])}


def test_trust_policy_admits_only_agentcore_for_this_agent():
    (statement,) = policies.trust_policy(ACCOUNT, REGION, AGENT)["Statement"]
    assert statement["Principal"] == {"Service": "bedrock-agentcore.amazonaws.com"}
    assert statement["Condition"]["StringEquals"]["aws:SourceAccount"] == ACCOUNT
    assert statement["Condition"]["ArnLike"]["aws:SourceArn"].endswith(f":runtime/{AGENT}-*")


def test_baseline_grants_no_data_access():
    granted = actions(policies.baseline_policy(ACCOUNT, REGION, AGENT))
    assert not [a for a in granted if a.startswith(DATA_PREFIXES)]


def test_baseline_workload_token_is_scoped_to_this_agent():
    doc = policies.baseline_policy(ACCOUNT, REGION, AGENT)
    (statement,) = [s for s in doc["Statement"] if s.get("Sid") == "OwnWorkloadIdentityOnly"]
    assert all("workload-identity-directory/default" in r for r in statement["Resource"])
    assert any(r.endswith(f"workload-identity/{AGENT}-*") for r in statement["Resource"])
    assert "bedrock-agentcore:GetWorkloadAccessTokenForUserId" not in statement["Action"]


def test_grant_is_least_privilege():
    doc = policies.athena_read_policy(ACCOUNT, REGION, "my-bucket", "aoa-day05", "sample_data")
    for statement in doc["Statement"]:
        resources = statement["Resource"] if isinstance(statement["Resource"], list) else [statement["Resource"]]
        assert "*" not in resources, statement["Sid"]
    granted = actions(doc)
    assert not {"s3:PutObject"} - granted  # needs to write query results...
    assert not [a for a in granted if a.startswith("s3:Delete") or a.startswith("glue:Create")]
    writes = [s for s in doc["Statement"] if "s3:PutObject" in s["Action"]]
    assert all(s["Resource"].endswith("/athena-results/*") for s in writes)  # ...but only there


def _load_agent():
    spec = importlib.util.spec_from_file_location("day5_agent", Path(__file__).parent / "agent" / "main.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    ("sql", "allowed"),
    [
        ("SELECT * FROM cities_weather", True),
        ("  with t as (select 1) select * from t", True),
        ("DESCRIBE cities_weather", True),
        ("DROP TABLE cities_weather", False),
        ("INSERT INTO cities_weather VALUES ('x','y',1,'z')", False),
        ("CREATE TABLE stolen AS SELECT * FROM cities_weather", False),
    ],
)
def test_agent_sql_guard(sql, allowed):
    assert bool(_load_agent().READ_ONLY_SQL.match(sql)) is allowed
