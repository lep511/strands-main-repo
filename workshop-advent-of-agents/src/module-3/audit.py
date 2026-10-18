"""OBSERVABILITY: one structured log line per user or agent action.

Every allowed and blocked step (gateway decisions, tool calls, approvals, lateral
calls) goes through `audit()`. Lines are appended to audit.jsonl so an administrator
can replay trajectories, and kept in memory so the evals can assert on them.
"""

import json
import os
import threading
from datetime import UTC, datetime
from pathlib import Path

AUDIT_PATH = Path(os.getenv("AUDIT_LOG", Path(__file__).with_name("audit.jsonl")))
VERBOSE = os.getenv("AUDIT_VERBOSE", "1") == "1"

EVENTS: list[dict] = []
_lock = threading.Lock()


def audit(actor: str, action: str, decision: str, **details) -> dict:
    """Record an event. `decision` is one of allowed, blocked, redacted, approved, denied, info."""
    event = {
        "ts": datetime.now(UTC).isoformat(timespec="milliseconds"),
        "actor": actor,
        "action": action,
        "decision": decision,
        **details,
    }
    line = json.dumps(event, ensure_ascii=False, default=str)
    with _lock:
        EVENTS.append(event)
        with AUDIT_PATH.open("a") as fh:
            fh.write(line + "\n")
    if VERBOSE:
        print(f"  [audit] {actor:<18} {action:<40} {decision}", flush=True)
    return event


def reset() -> None:
    with _lock:
        EVENTS.clear()
