"""Why rotation matters: an attacker copies the vaulted refresh token, then replays it.

  1. Attacker exfiltrates the current refresh token (e.g. from a leaked backup of the vault).
  2. The legitimate 2:00 AM job runs: it uses the token and the vault rotates it.
  3. Attacker replays the stolen (now rotated-away) token at the IdP.
     -> reuse detected: the IdP revokes the whole token family. The attacker gets nothing.
  4. The next night, the job fails SAFE: no token, no data, and the summary asks the
     user to re-authorize instead of inventing incidents.
  5. The user re-consents while online; the job works again.

Runs against the local lab server (start it first) with the local vault.

Usage:
    uv run src/module-7/stolen_token_drill.py
"""

import json

from delegation import CLIENT_ID, CLIENT_SECRET, IDP_URL, _post, grant_offline_consent
from lab_server import USERS
from overnight_agent import run_job
from vault import LocalVault, secret_name

USER = "alice@example.com"


def main() -> None:
    vault = LocalVault()
    grant_offline_consent(USER, USERS[USER], vault)
    stolen, _ = vault.read_current(secret_name(USER))
    print(f"[1] attacker copies the vaulted refresh token ({stolen[:6]}…)")

    summary, audit, _ = run_job(USER, vault)
    print(f"[2] legit 02:00 job: {[e['event'] for e in audit]}; vault now {vault.versions(secret_name(USER))}")

    try:
        _post(f"{IDP_URL}/token", {"grant_type": "refresh_token", "refresh_token": stolen,
                                   "client_id": CLIENT_ID, "client_secret": CLIENT_SECRET})
        print("[3] attacker replay: ACCEPTED (this should never happen)")
    except PermissionError as e:
        print(f"[3] attacker replay: REJECTED -> {e}")

    summary, audit, _ = run_job(USER, vault)
    print(f"[4] next night's job: {json.dumps(audit)}")
    print(f"    summary: {summary.strip()}")

    grant_offline_consent(USER, USERS[USER], vault)
    summary, audit, _ = run_job(USER, vault)
    print(f"[5] after re-consent: {[e['event'] for e in audit]}")


if __name__ == "__main__":
    main()
