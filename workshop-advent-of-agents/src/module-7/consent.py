"""6:00 PM, the user is online: grant offline consent once and vault the refresh token.

Usage:
    uv run src/module-7/consent.py alice@example.com
    uv run src/module-7/consent.py alice@example.com --vault aws      # AWS Secrets Manager
    uv run src/module-7/consent.py alice@example.com --revoke         # "remove app access" at the IdP
"""

import argparse
import getpass

from delegation import CONSENT_SCOPES, IDP_URL, _post, grant_offline_consent
from lab_server import USERS
from vault import get_vault, secret_name


def main() -> None:
    parser = argparse.ArgumentParser(description="Grant or revoke offline consent for the overnight summarizer")
    parser.add_argument("user")
    parser.add_argument("--vault", choices=["local", "aws"], default="local")
    parser.add_argument("--yes", action="store_true", help="approve without prompting")
    parser.add_argument("--revoke", action="store_true", help="revoke every grant of this user at the IdP")
    args = parser.parse_args()

    if args.revoke:
        print(_post(f"{IDP_URL}/admin/revoke", {"user": args.user}, as_json=True))
        return

    print("=" * 66)
    print(" overnight-summarizer wants to act for you while you are offline")
    print(f"   account : {args.user}")
    print(f"   scopes  : {', '.join(CONSENT_SCOPES)}")
    print("   offline_access lets it refresh access without you being signed in.")
    print("=" * 66)
    if not args.yes and input("Allow? (y/N): ").strip().lower() not in {"y", "yes"}:
        print("Consent denied; nothing stored.")
        return
    # The lab IdP knows the demo passwords; a real IdP would show its own login page here.
    password = USERS.get(args.user) or getpass.getpass("password: ")

    vault = get_vault(args.vault)
    result = grant_offline_consent(args.user, password, vault)
    print(f"Consent granted. Refresh token vaulted in {type(vault).__name__} as '{secret_name(args.user)}'.")
    print(f"Vault versions: {vault.versions(secret_name(args.user))}")
    print(f"(scopes granted: {result['scopes']}; the token itself is never printed)")


if __name__ == "__main__":
    main()
