"""Offline token delegation: consent once while online, refresh headlessly at 2:00 AM.

Two layers of identity:
  layer 1  the agent's own identity opens the vault (LocalVault: file permissions;
           SecretsManagerVault: the agent's IAM role / AgentCore workload identity)
  layer 2  the user's vaulted refresh token is exchanged at the IdP for a short-lived,
           down-scoped access token that can only see that user's data
"""

import base64
import hashlib
import json
import os
import secrets
import urllib.error
import urllib.parse
import urllib.request

from vault import VaultError, secret_name

IDP_URL = os.getenv("IDP_URL", "http://127.0.0.1:8765")
CLIENT_ID = os.getenv("OAUTH_CLIENT_ID", "overnight-summarizer")
# Kept in the environment only to show the raw OAuth exchange, exactly as the original
# notes; in production vault it too, or let AgentCore Identity hold it (agentcore_identity_variant.py).
CLIENT_SECRET = os.getenv("OAUTH_CLIENT_SECRET", "dev-only-client-secret")

CONSENT_SCOPES = ["offline_access", "reports:read", "reports:write"]  # what Alice grants once
JOB_SCOPES = ["reports:read"]                                            # what the 2 AM job may use


class ConsentRequired(Exception):
    """The vaulted grant is missing, revoked or rotated away: the user must consent again."""


def _post(url: str, data: dict, as_json: bool = False) -> dict:
    body = json.dumps(data).encode() if as_json else urllib.parse.urlencode(data).encode()
    req = urllib.request.Request(url, data=body, method="POST", headers={
        "Content-Type": "application/json" if as_json else "application/x-www-form-urlencoded"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        detail = json.loads(e.read() or b"{}").get("error", e.reason)
        raise PermissionError(f"{e.code}: {detail}") from None


def grant_offline_consent(user: str, password: str, vault, idp_url: str = IDP_URL) -> dict:
    """While the user is online: authorization code + PKCE with offline_access, then vault the refresh token.

    In a real deployment the first half is a browser redirect to the IdP's consent screen;
    the lab IdP accepts the same form POST directly.
    """
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    code = _post(f"{idp_url}/authorize", {"user": user, "password": password, "client_id": CLIENT_ID,
                                          "scope": " ".join(CONSENT_SCOPES), "code_challenge": challenge},
                 as_json=True)["code"]
    tokens = _post(f"{idp_url}/token", {"grant_type": "authorization_code", "code": code, "code_verifier": verifier,
                                        "client_id": CLIENT_ID, "client_secret": CLIENT_SECRET})
    if "refresh_token" not in tokens:
        raise RuntimeError("IdP returned no refresh token: was offline_access granted?")
    version = vault.write_initial(secret_name(user), tokens["refresh_token"])
    return {"user": user, "scopes": CONSENT_SCOPES, "vault_version": version[:8]}


def get_delegated_access_token(user_id: str, vault, scopes: list[str] = JOB_SCOPES, idp_url: str = IDP_URL) -> dict:
    """Headless: vaulted refresh token -> 15-minute, down-scoped access token; rotate the vault."""
    name = secret_name(user_id)
    with vault.lock(name):
        try:
            refresh_token, version_id = vault.read_current(name)  # layer 1: the agent opens the vault
        except VaultError as e:
            raise ConsentRequired(f"no offline consent stored for {user_id}") from e
        try:
            tokens = _post(f"{idp_url}/token", {                    # layer 2: the user's delegated grant
                "grant_type": "refresh_token", "refresh_token": refresh_token, "scope": " ".join(scopes),
                "client_id": CLIENT_ID, "client_secret": CLIENT_SECRET})
        except PermissionError as e:
            if "invalid_grant" in str(e):
                raise ConsentRequired(f"offline consent for {user_id} is no longer valid ({e})") from e
            raise
        if "refresh_token" in tokens:
            # Rotate: the new refresh token becomes AWSCURRENT, the used one is deprecated.
            vault.rotate(name, tokens["refresh_token"], version_id)
    return {"access_token": tokens["access_token"], "expires_in": tokens["expires_in"], "scope": tokens["scope"]}


def fetch_reports(access_token: str, idp_url: str = IDP_URL) -> dict:
    req = urllib.request.Request(f"{idp_url}/reports", headers={"Authorization": f"Bearer {access_token}"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        raise PermissionError(f"{e.code}: {json.loads(e.read() or b'{}').get('error', e.reason)}") from None
