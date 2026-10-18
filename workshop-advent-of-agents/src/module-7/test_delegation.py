"""Deterministic tests: IdP rules, delegation, both vaults, and the tool's user binding.

    uv run --group dev pytest src/module-7 -v
"""

import threading

import boto3
import pytest
from botocore.stub import Stubber
from moto import mock_aws

import delegation
from lab_server import CLIENT_ID, CLIENT_SECRET, IdP, serve
from vault import CURRENT, LocalVault, SecretsManagerVault, VaultAccessDenied, VaultError, secret_name

ALICE, BOB = "alice@example.com", "bob@example.com"


@pytest.fixture
def lab():
    server, idp = serve(port=0)
    yield f"http://127.0.0.1:{server.server_port}", idp
    server.shutdown()


@pytest.fixture
def vault(tmp_path):
    return LocalVault(tmp_path / "vault")


def consent(url, vault, user=ALICE, password="pumpkin"):
    return delegation.grant_offline_consent(user, password, vault, idp_url=url)


def refresh(idp: IdP, token: str, scope: str = "") -> dict:
    return idp.token({"grant_type": "refresh_token", "refresh_token": token, "scope": scope,
                      "client_id": CLIENT_ID, "client_secret": CLIENT_SECRET})


class TestIdP:
    def test_refresh_rotates_and_reuse_revokes_the_family(self, lab, vault):
        url, idp = lab
        consent(url, vault)
        first, _ = vault.read_current(secret_name(ALICE))
        second = refresh(idp, first)["refresh_token"]
        with pytest.raises(ValueError, match="reuse detected"):
            refresh(idp, first)                      # attacker replays the rotated token
        with pytest.raises(ValueError, match="revoked"):
            refresh(idp, second)                     # ...and the legitimate one dies with it

    def test_refresh_can_narrow_but_not_widen_scopes(self, lab, vault):
        url, idp = lab
        consent(url, vault)
        token, _ = vault.read_current(secret_name(ALICE))
        narrowed = refresh(idp, token, "reports:read")
        assert narrowed["scope"] == "reports:read"
        with pytest.raises(ValueError, match="invalid_scope"):
            refresh(idp, narrowed["refresh_token"], "reports:read admin:all")

    def test_downscoped_token_cannot_write_and_sees_only_its_user(self, lab, vault):
        url, idp = lab
        consent(url, vault)
        token = delegation.get_delegated_access_token(ALICE, vault, idp_url=url)["access_token"]
        data = delegation.fetch_reports(token, idp_url=url)
        assert data["user"] == ALICE and all(r["id"].startswith("INC-10") for r in data["reports"])
        with pytest.raises(LookupError, match="403"):
            idp.check(token, "reports:write")

    def test_expired_access_token_is_rejected(self):
        idp = IdP(access_ttl=0)
        token = idp._issue(ALICE, ["reports:read"], "fam", ["reports:read"])["access_token"]
        with pytest.raises(PermissionError, match="401"):
            idp.check(token, "reports:read")

    def test_pkce_verifier_is_enforced(self):
        idp = IdP()
        code = idp.authorize(ALICE, "pumpkin", CLIENT_ID, ["offline_access", "reports:read"], "challenge")
        with pytest.raises(ValueError, match="PKCE"):
            idp.token({"grant_type": "authorization_code", "code": code, "code_verifier": "wrong",
                       "client_id": CLIENT_ID, "client_secret": CLIENT_SECRET})

    def test_wrong_client_secret_is_rejected(self, lab, vault):
        url, idp = lab
        with pytest.raises(PermissionError, match="invalid_client"):
            idp.token({"grant_type": "refresh_token", "refresh_token": "x", "client_id": CLIENT_ID,
                       "client_secret": "guess"})


class TestDelegation:
    def test_exchange_rotates_vault_and_wipes_old_value(self, lab, vault):
        url, _ = lab
        consent(url, vault)
        old, old_id = vault.read_current(secret_name(ALICE))
        token = delegation.get_delegated_access_token(ALICE, vault, idp_url=url)
        new, new_id = vault.read_current(secret_name(ALICE))
        assert token["scope"] == "reports:read" and token["expires_in"] == 900
        assert new != old and new_id != old_id
        stored = vault._load(secret_name(ALICE))
        assert [v["stages"] for v in stored] == [[], [CURRENT]]
        assert stored[0]["value"] is None             # a leaked copy of the vault holds no usable old token

    def test_missing_or_revoked_consent_raises_consent_required(self, lab, vault):
        url, idp = lab
        with pytest.raises(delegation.ConsentRequired, match="no offline consent"):
            delegation.get_delegated_access_token(ALICE, vault, idp_url=url)
        consent(url, vault)
        idp.revoke_user(ALICE)
        with pytest.raises(delegation.ConsentRequired, match="no longer valid"):
            delegation.get_delegated_access_token(ALICE, vault, idp_url=url)

    def test_concurrent_jobs_for_one_user_do_not_trigger_reuse_detection(self, lab, vault):
        url, idp = lab
        consent(url, vault)
        errors = []

        def job():
            try:
                delegation.get_delegated_access_token(ALICE, vault, idp_url=url)
            except Exception as e:  # noqa: BLE001
                errors.append(e)

        threads = [threading.Thread(target=job) for _ in range(4)]
        [t.start() for t in threads]
        [t.join() for t in threads]
        assert errors == []
        assert not any(e["kind"] == "refresh_reuse_detected" for e in idp.events)

    def test_users_are_isolated_in_the_vault(self, lab, vault):
        url, _ = lab
        consent(url, vault, ALICE, "pumpkin")
        consent(url, vault, BOB, "lantern")
        bob_token = delegation.get_delegated_access_token(BOB, vault, idp_url=url)["access_token"]
        assert [r["id"] for r in delegation.fetch_reports(bob_token, idp_url=url)["reports"]] == ["INC-2001"]


class TestLocalVault:
    def test_stale_rotation_is_refused(self, vault):
        vid = vault.write_initial("s", "v1")
        vault.rotate("s", "v2", vid)
        with pytest.raises(VaultError, match="stale"):
            vault.rotate("s", "v3", vid)


@mock_aws
class TestSecretsManagerVault:
    def make(self):
        return SecretsManagerVault(client=boto3.client("secretsmanager", region_name="us-east-1"))

    def test_rotation_moves_awscurrent_and_deprecates_the_old_version(self):
        sm = self.make()
        first = sm.write_initial(secret_name(ALICE), "rt_1")
        second = sm.rotate(secret_name(ALICE), "rt_2", first)
        assert sm.read_current(secret_name(ALICE)) == ("rt_2", second)
        stages = {v["id"]: v["stages"] for v in sm.versions(secret_name(ALICE))}
        assert stages[second[:8]] == [CURRENT]
        assert stages[first[:8]] == []                # no AWSPREVIOUS: the old token is unreachable

    def test_stale_rotation_is_refused(self):
        sm = self.make()
        first = sm.write_initial("s", "rt_1")
        sm.rotate("s", "rt_2", first)
        with pytest.raises(VaultError, match="stale"):
            sm.rotate("s", "rt_3", first)

    def test_reconsent_supersedes_existing_secret(self):
        sm = self.make()
        sm.write_initial("s", "rt_1")
        latest = sm.write_initial("s", "rt_new")
        assert sm.read_current("s") == ("rt_new", latest)

    def test_access_denied_is_a_layer_one_failure(self):
        client = boto3.client("secretsmanager", region_name="us-east-1")
        with Stubber(client) as stub:
            stub.add_client_error("get_secret_value", service_error_code="AccessDeniedException",
                                  service_message="not authorized to perform: secretsmanager:GetSecretValue")
            with pytest.raises(VaultAccessDenied, match="not authorized"):
                SecretsManagerVault(client=client).read_current("s")


def test_the_tool_has_no_user_parameter(vault):
    from overnight_agent import build_agent

    spec = build_agent(vault, callback_handler=None).tool_registry.get_all_tools_config()["fetch_overnight_reports"]
    assert spec["inputSchema"]["json"].get("properties", {}) == {}   # the model cannot choose whose data to read
