"""2:00 AM, the user is asleep: run the summarizer headlessly for one user.

No browser, no user session, no admin key: only the agent's identity (to open the vault)
and the user's vaulted offline grant. In AWS this script's role is played by
EventBridge Scheduler invoking the agent on AgentCore Runtime with the user id header.

Usage:
    uv run src/module-7/nightly_job.py alice@example.com
    uv run src/module-7/nightly_job.py alice@example.com --vault aws
"""

import argparse
import json

from overnight_agent import MODEL_ID, run_job
from vault import get_vault, secret_name


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the overnight summarizer for one user")
    parser.add_argument("user")
    parser.add_argument("--vault", choices=["local", "aws"], default="local")
    args = parser.parse_args()

    vault = get_vault(args.vault)
    name = secret_name(args.user)
    try:
        before = vault.versions(name)
    except Exception:
        before = "(no secret)"
    print(f"[02:00] overnight_batch_summarizer for {args.user} on {MODEL_ID} (vault: {type(vault).__name__})")
    print(f"[vault] before: {before}")

    summary, audit, result = run_job(args.user, vault)

    for event in audit:
        print(f"[audit] {json.dumps(event)}")
    try:
        print(f"[vault] after:  {vault.versions(name)}")
    except Exception:
        pass
    usage = result.metrics.accumulated_usage
    print(f"\n{summary}\n")
    print(f"--- stop_reason={result.stop_reason} tokens in/out={usage['inputTokens']}/{usage['outputTokens']}")


if __name__ == "__main__":
    main()
