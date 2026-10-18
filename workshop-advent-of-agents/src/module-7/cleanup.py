"""Delete every vaulted refresh token created by the lab (local and, optionally, AWS).

Usage:
    uv run src/module-7/cleanup.py            # local vault only
    uv run src/module-7/cleanup.py --aws      # also the Secrets Manager secrets (no recovery window)
"""

import argparse
import shutil

from lab_server import USERS
from vault import LocalVault, SecretsManagerVault, secret_name


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--aws", action="store_true")
    args = parser.parse_args()

    shutil.rmtree(LocalVault().root, ignore_errors=True)
    print(f"removed {LocalVault().root}")
    if args.aws:
        sm = SecretsManagerVault()
        for user in USERS:
            try:
                sm.delete(secret_name(user))
                print(f"deleted secret {sm.prefix}{secret_name(user)}")
            except sm.sm.exceptions.ClientError as e:
                print(f"could not delete {sm.prefix}{secret_name(user)}: {e.response['Error']['Code']}")


if __name__ == "__main__":
    main()
