"""File-based Cedar policy example.

Demonstrates file access control where:
- Analysts can only read .json files
- Admins can read any file and write .json files
- Nobody can access files under /etc/ or /secrets/ (hard deny)
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from typing import Any

import cedarpy
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel

from strands import Agent, tool
from strands.hooks.events import BeforeToolCallEvent
from strands.interventions.actions import Deny, Proceed
from strands.interventions.handler import InterventionHandler, OnError
from strands.vended_interventions.cedar._file_loaders import load_policies

console = Console()

TypeAndId = dict[str, str]
PrincipalResolver = Callable[[dict[str, Any]], TypeAndId | None]

_POLICIES = load_policies("./policies/file_based_policie.cedar")

_ENTITIES = [
    {
        "uid": {"type": "AgentTools::User", "id": "alice"},
        "attrs": {},
        "parents": [],
    },
    {
        "uid": {"type": "AgentTools::User", "id": "bob"},
        "attrs": {},
        "parents": [],
    },
    {
        "uid": {"type": "AgentTools::Resource", "id": "filesystem"},
        "attrs": {"path": "/", "tag": "system"},
        "parents": [],
    },
]


class FileBasedCedarAuthorization(InterventionHandler):
    """Cedar authorization handler for file-based access control."""

    name = "cedar-file-authorization"

    @property
    def on_error(self) -> OnError:
        return self._on_error

    def __init__(
        self,
        *,
        policies: str,
        entities: list[dict[str, Any]],
        principal_resolver: PrincipalResolver,
        on_error: OnError = "throw",
    ) -> None:
        self._on_error = on_error
        self._policies = policies
        self._entities = entities
        self._principal_resolver = principal_resolver

    def before_tool_call(self, event: BeforeToolCallEvent, **kwargs: Any) -> Proceed | Deny:
        invocation_state = event.invocation_state
        principal = self._principal_resolver(invocation_state)

        if not principal or not principal.get("type") or not principal.get("id"):
            return Deny(reason="No principal identity found in invocation state")

        tool_name = event.tool_use["name"]
        tool_input = event.tool_use.get("input") or {}

        request = {
            "principal": f'AgentTools::User::"{principal["id"]}"',
            "action": f'AgentTools::Action::"{tool_name}"',
            "resource": 'AgentTools::Resource::"filesystem"',
            "context": {
                "session": {"role": invocation_state.get("role", "")},
                "input": tool_input,
            },
        }

        try:
            result = cedarpy.is_authorized(request, self._policies, self._entities)
        except Exception as e:
            return Deny(reason=f"Cedar evaluation failed: {e}")

        if not result.allowed:
            reasons = result.diagnostics.reason if hasattr(result.diagnostics, "reason") else []
            return Deny(
                reason=f"Access denied by Cedar policy for action '{tool_name}' on path '{tool_input.get('path', 'unknown')}'"
            )

        return Proceed()


@tool
def read_file(path: str) -> str:
    """Read the contents of a file at the given path."""
    if not os.path.exists(path):
        return f"Error: file not found: {path}"
    with open(path, "r") as f:
        return f.read()


@tool
def write_file(path: str, content: str) -> str:
    """Write content to a file at the given path."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w") as f:
        f.write(content)
    return f"Successfully wrote {len(content)} bytes to {path}"


cedar = FileBasedCedarAuthorization(
    policies=_POLICIES,
    entities=_ENTITIES,
    principal_resolver=lambda state: (
        {"type": "User", "id": state["user_id"]}
        if state.get("user_id")
        else None
    ),
)

ALL_TOOLS = [read_file, write_file]


def run_scenario(title: str, style: str, prompt: str, invocation_state: dict):
    console.rule(f"[bold {style}]{title}[/]")
    agent = Agent(
        tools=ALL_TOOLS,
        interventions=[cedar],
        callback_handler=lambda **kwargs: None,
    )
    result = agent(prompt, invocation_state=invocation_state)
    console.print(Panel(Markdown(str(result)), border_style=style))
    console.print()


if __name__ == "__main__":
    console.print(Panel(
        "[bold]Cedar File-Based Access Policy[/]\n"
        "Policy: policies/file_based_policie.cedar\n\n"
        "Rules:\n"
        "  - Analysts: read .json files only\n"
        "  - Admins: read any file, write .json files\n"
        "  - Everyone: denied access to /etc/* and /secrets/*",
        title="Demo",
    ))
    console.print()

    # Scenario 1: Analyst reads a .json file - PERMITTED
    run_scenario(
        title="Bob (analyst): read sample_data/config.json - PERMITTED",
        style="green",
        prompt="Read the file at sample_data/config.json",
        invocation_state={"user_id": "bob", "role": "analyst"},
    )

    # Scenario 2: Analyst reads a .json file - PERMITTED
    run_scenario(
        title="Bob (analyst): read sample_data/users.json - PERMITTED",
        style="green",
        prompt="Read the file at sample_data/users.json",
        invocation_state={"user_id": "bob", "role": "analyst"},
    )

    # Scenario 3: Analyst tries to read a non-json file - DENIED
    run_scenario(
        title="Bob (analyst): read README.md - DENIED (not .json)",
        style="red",
        prompt="Read the file at README.md",
        invocation_state={"user_id": "bob", "role": "analyst"},
    )

    # Scenario 4: Admin reads any file - PERMITTED
    run_scenario(
        title="Alice (admin): read README.md - PERMITTED",
        style="green",
        prompt="Read the file at README.md",
        invocation_state={"user_id": "alice", "role": "admin"},
    )

    # Scenario 5: Admin writes a .json file - PERMITTED
    run_scenario(
        title="Alice (admin): write sample_data/output.json - PERMITTED",
        style="green",
        prompt='Write {"status": "ok"} to sample_data/output.json',
        invocation_state={"user_id": "alice", "role": "admin"},
    )

    # Scenario 6: Admin tries to read /etc/passwd - DENIED (forbid)
    run_scenario(
        title="Alice (admin): read /etc/passwd - DENIED (sensitive path)",
        style="red",
        prompt="Read the file at /etc/passwd",
        invocation_state={"user_id": "alice", "role": "admin"},
    )

    # Scenario 7: Admin tries to write to /secrets/ - DENIED (forbid)
    run_scenario(
        title="Alice (admin): write /secrets/key.json - DENIED (sensitive path)",
        style="red",
        prompt='Write {"key": "secret123"} to /secrets/key.json',
        invocation_state={"user_id": "alice", "role": "admin"},
    )
