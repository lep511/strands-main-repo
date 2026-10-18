"""Offline tests: delegation flow, session binding, read-only guard and IAM scope. No AWS calls.

Usage:
    uv run --group dev pytest src/module-6 -q
"""

from types import SimpleNamespace

import pytest
from botocore.exceptions import ClientError
from fastapi.testclient import TestClient

import app as web
import policies
from delegation import Delegation
from devops_agent import WRITE_TOOL, ReadOnlyGuard


class FakeIdentity:
    """Stands in for the bedrock-agentcore data plane: a vault keyed by user."""

    def __init__(self):
        self.vault: dict[str, str] = {}
        self.sessions: dict[str, str] = {}  # session_uri -> user who started it
        self.calls: list[tuple] = []

    def get_workload_access_token_for_user_id(self, workloadName, userId):
        self.calls.append(("wat", workloadName, userId))
        return {"workloadAccessToken": f"wat:{workloadName}:{userId}"}

    def get_resource_oauth2_token(self, workloadIdentityToken, forceAuthentication=False, **kwargs):
        user = workloadIdentityToken.split(":")[-1]
        self.calls.append(("token", user, kwargs["oauth2Flow"], tuple(kwargs["scopes"])))
        if user in self.vault and not forceAuthentication:
            return {"accessToken": self.vault[user]}
        session = f"urn:session:{user}:{len(self.sessions)}"
        self.sessions[session] = user
        return {"authorizationUrl": f"https://consent.example/{session}", "sessionUri": session}

    def complete_resource_token_auth(self, sessionUri, userIdentifier):
        if self.sessions.get(sessionUri) != userIdentifier["userId"]:
            raise ClientError({"Error": {"Code": "AccessDeniedException", "Message": "Invalid or expired session"}}, "Complete")
        self.vault[userIdentifier["userId"]] = f"gho_{userIdentifier['userId']}"


@pytest.fixture
def fake(monkeypatch):
    fake = FakeIdentity()
    monkeypatch.setattr(web, "delegation", Delegation(client=fake))
    return fake


def client_as(user: str | None) -> TestClient:
    client = TestClient(web.app, follow_redirects=False)
    if user:
        client.post("/login", data={"username": user})
    return client


# --- delegation ---------------------------------------------------------------------------

def test_first_call_needs_consent_then_token_comes_from_vault(fake):
    d = Delegation(client=fake)
    first = d.token_for("alice")
    assert first.consent_url and not first.token
    d.complete(first.session_uri, "alice")
    assert d.token_for("alice").token == "gho_alice"


def test_tokens_are_per_user(fake):
    d = Delegation(client=fake)
    d.complete(d.token_for("alice").session_uri, "alice")
    assert d.token_for("bob").token is None  # Bob does not inherit Alice's GitHub access


def test_user_federation_flow_and_scopes(fake):
    Delegation(client=fake).token_for("alice")
    (_, user, flow, scopes) = next(c for c in fake.calls if c[0] == "token")
    assert (user, flow) == ("alice", "USER_FEDERATION")
    assert "repo" in scopes


# --- session binding in the app -------------------------------------------------------------

def test_chat_requires_sign_in(fake):
    assert client_as(None).post("/api/chat", json={"prompt": "hi"}).status_code == 401


def test_chat_returns_consent_url_when_vault_is_empty(fake):
    body = client_as("alice").post("/api/chat", json={"prompt": "hi"}).json()
    assert body["consent_url"].startswith("https://consent.example/")


def test_callback_without_signed_in_user_is_rejected(fake):
    session = Delegation(client=fake).token_for("alice").session_uri
    assert client_as(None).get("/oauth2/callback", params={"session_id": session}).status_code == 401
    assert "alice" not in fake.vault


def test_callback_by_a_different_user_is_rejected(fake):
    session = Delegation(client=fake).token_for("alice").session_uri
    response = client_as("bob").get("/oauth2/callback", params={"session_id": session})
    assert response.status_code == 403
    assert not fake.vault


def test_callback_by_the_same_user_binds_the_token(fake):
    session = Delegation(client=fake).token_for("alice").session_uri
    response = client_as("alice").get("/oauth2/callback", params={"session_id": session})
    assert response.status_code == 303 and fake.vault == {"alice": "gho_alice"}


def test_forged_cookie_is_not_a_user(fake):
    client = TestClient(web.app, follow_redirects=False, cookies={web.COOKIE: "alice.deadbeef"})
    assert client.post("/api/chat", json={"prompt": "hi"}).status_code == 401


# --- read-only guard -------------------------------------------------------------------------

READS = ["get_me", "list_issues", "search_code", "issue_read", "pull_request_read", "get_file_contents", "ui_get"]
WRITES = ["create_issue", "update_pull_request", "merge_pull_request", "push_files", "delete_file",
          "add_issue_comment", "request_copilot_review", "fork_repository", "create_or_update_file"]


@pytest.mark.parametrize("name", READS)
def test_read_tools_pass(name):
    event = SimpleNamespace(tool_use={"name": name, "input": {}}, cancel_tool=False)
    ReadOnlyGuard().check(event)
    assert not event.cancel_tool


@pytest.mark.parametrize("name", WRITES)
def test_write_tools_are_cancelled(name):
    assert WRITE_TOOL.search(name)
    event = SimpleNamespace(tool_use={"name": name, "input": {}}, cancel_tool=False)
    ReadOnlyGuard().check(event)
    assert event.cancel_tool


# --- IAM -----------------------------------------------------------------------------------

def test_delegation_policy_is_scoped_to_one_workload_and_provider():
    doc = policies.delegation_policy("123456789012", "us-east-1", "aoa_day06_devops", "github-oauth-provider")
    resources = [r for s in doc["Statement"] for r in ([s["Resource"]] if isinstance(s["Resource"], str) else s["Resource"])]
    assert "*" not in resources
    assert any(r.endswith("workload-identity/aoa_day06_devops") for r in resources)
    assert any(r.endswith("oauth2credentialprovider/github-oauth-provider") for r in resources)
