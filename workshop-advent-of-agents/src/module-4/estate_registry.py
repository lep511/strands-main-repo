"""The agent estate: registry records, runtime status, and discovery of unregistered agents.

agent_registry.yaml is the reviewed catalog (versioned, like AWS Agent Registry records).
.registry_state.json holds runtime status changes, so revoking an agent during an
incident never requires editing the reviewed file.

Usage:
    uv run src/module-4/estate_registry.py list
    uv run src/module-4/estate_registry.py revoke inbox-assistant --reason "suspected exfiltration"
    uv run src/module-4/estate_registry.py restore inbox-assistant
    uv run src/module-4/estate_registry.py discover
"""

import argparse
import json
import re
import time
from pathlib import Path

import yaml

HERE = Path(__file__).parent
REPO_ROOT = HERE.parent.parent
REGISTRY_PATH = HERE / "agent_registry.yaml"
STATE_PATH = HERE / ".registry_state.json"

# `Agent(` constructions that define an agent (not test files, not evals).
AGENT_DEF_RE = re.compile(r"(?:=|return)\s*(?:A2A)?Agent\(")
# Build outputs and vendored dependencies are not agents you own.
VENDOR_DIRS = {".venv", "site-packages", "node_modules", "build", "dist", "package", "__pycache__"}


def load_registry(path: Path = REGISTRY_PATH) -> dict:
    return yaml.safe_load(path.read_text())


def _load_state(state_path: Path) -> dict:
    return json.loads(state_path.read_text()) if state_path.exists() else {}


def agents(path: Path = REGISTRY_PATH, state_path: Path = STATE_PATH) -> list[dict]:
    """Registry records with any runtime status override applied."""
    state = _load_state(state_path)
    return [{**a, **state.get(a["id"], {})} for a in load_registry(path)["agents"]]


def get_agent(agent_id: str, path: Path = REGISTRY_PATH, state_path: Path = STATE_PATH) -> dict | None:
    return next((a for a in agents(path, state_path) if a["id"] == agent_id), None)


def status(agent_id: str, path: Path = REGISTRY_PATH, state_path: Path = STATE_PATH) -> str:
    """'active', 'revoked', or 'unregistered'."""
    record = get_agent(agent_id, path, state_path)
    return record["status"] if record else "unregistered"


def set_status(agent_id: str, new_status: str, reason: str = "", state_path: Path = STATE_PATH,
               path: Path = REGISTRY_PATH) -> dict:
    if get_agent(agent_id, path, state_path) is None:
        raise KeyError(f"'{agent_id}' is not in {path.name}")
    state = _load_state(state_path)
    state[agent_id] = {"status": new_status, "status_reason": reason, "status_changed_at": time.time()}
    tmp = state_path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2))
    tmp.replace(state_path)  # atomic: watchers never read a half-written file
    return state[agent_id]


def discover_agent_sources(root: Path = REPO_ROOT / "src") -> list[str]:
    """Files under src/ that construct an agent, relative to the repo root."""
    found = []
    for py in sorted(root.rglob("*.py")):
        if VENDOR_DIRS.intersection(py.relative_to(root).parts):
            continue
        if py.name.startswith("test_") or "eval" in py.name:
            continue
        if AGENT_DEF_RE.search(py.read_text(errors="ignore")):
            found.append(str(py.relative_to(root.parent)))  # e.g. "src/module-1/adlc_agent.py"
    return found


def unregistered_sources(root: Path = REPO_ROOT / "src", path: Path = REGISTRY_PATH) -> list[str]:
    """Agent-defining files that no registry record covers (shadow agents)."""
    sources = [a["source"].rstrip("/") + "/" for a in load_registry(path)["agents"]]
    return [f for f in discover_agent_sources(root) if not any(f.startswith(s) for s in sources)]


def main() -> None:
    parser = argparse.ArgumentParser(description="Inspect and change the agent estate")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    sub.add_parser("discover")
    for cmd in ("revoke", "restore"):
        p = sub.add_parser(cmd)
        p.add_argument("agent_id")
        p.add_argument("--reason", default="")
    args = parser.parse_args()

    if args.cmd == "list":
        for a in agents():
            print(f"{a['id']:<22} {a['status']:<8} owner={a['owner']:<18} tier={a['risk_tier']:<5} identity={a['identity']}")
    elif args.cmd == "discover":
        shadow = unregistered_sources()
        print(f"agent-defining files: {len(discover_agent_sources())}, unregistered: {len(shadow)}")
        for f in shadow:
            print(f"  UNREGISTERED  {f}")
    else:
        new = "revoked" if args.cmd == "revoke" else "active"
        print(json.dumps({args.agent_id: set_status(args.agent_id, new, args.reason)}, indent=2))


if __name__ == "__main__":
    main()
