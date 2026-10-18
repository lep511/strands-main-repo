"""AGENT IDENTITY: short-lived, signed, per-agent credentials instead of one shared key.

A minimal stand-in for SPIFFE SVIDs / AgentCore Identity: each agent mints a token
that names itself (`sub`), the agent it wants to reach (`aud`) and expires in seconds.
The callee verifies the signature, the audience, the expiry, and that the registry
lets `sub` call `aud`. A stolen token is useless after TTL and only for one callee.

In production use AgentCore Identity, IAM roles + SigV4, or workload identity (SPIFFE);
never a hand-rolled HMAC. The shape of the check is what matters here.
"""

import base64
import hashlib
import hmac
import json
import os
import time

import registry

_SECRET = os.getenv("AGENT_IDENTITY_SECRET", "dev-only-secret-change-me").encode()
DEFAULT_TTL_SECONDS = 60


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def issue_token(agent_id: str, audience: str, ttl: int = DEFAULT_TTL_SECONDS) -> str:
    entry = registry.lookup(agent_id)
    now = int(time.time())
    claims = {"sub": agent_id, "spiffe_id": entry.spiffe_id, "aud": audience, "iat": now, "exp": now + ttl}
    payload = _b64(json.dumps(claims, separators=(",", ":")).encode())
    signature = _b64(hmac.new(_SECRET, payload.encode(), hashlib.sha256).digest())
    return f"{payload}.{signature}"


def verify_token(token: str, audience: str) -> dict:
    """Return the token claims, or raise PermissionError."""
    try:
        payload, signature = token.split(".")
    except (AttributeError, ValueError):
        raise PermissionError("malformed identity token") from None

    expected = _b64(hmac.new(_SECRET, payload.encode(), hashlib.sha256).digest())
    if not hmac.compare_digest(signature, expected):
        raise PermissionError("bad token signature")

    claims = json.loads(_unb64(payload))
    if claims["aud"] != audience:
        raise PermissionError(f"token audience is '{claims['aud']}', not '{audience}'")
    if claims["exp"] < time.time():
        raise PermissionError("token expired")
    if not registry.can_call(claims["sub"], audience):
        raise PermissionError(f"registry does not allow '{claims['sub']}' to call '{audience}'")
    return claims
