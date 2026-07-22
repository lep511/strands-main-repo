"""User Group Cedar policy example.

Demonstrates group-based access control where only members of
UserGroup::"friendsAndFamily" can view or comment on albums,
unless the resource is tagged as private.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime as dt
from datetime import timezone
from typing import Any

import cedarpy
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel

from strands import Agent, tool
from strands.hooks.events import BeforeToolCallEvent
from strands.interventions.actions import Deny, Proceed
from strands.interventions.handler import InterventionHandler, OnError
from strands.vended_interventions.cedar._file_loaders import load_entities, load_policies

console = Console()

TypeAndId = dict[str, str]
PrincipalResolver = Callable[[dict[str, Any]], TypeAndId | None]

_POLICIES = load_policies("./policies/user_group.cedar")

_ENTITIES = [
    {
        "uid": {"type": "UserGroup", "id": "friendsAndFamily"},
        "attrs": {},
        "parents": [],
    },
    {
        "uid": {"type": "User", "id": "alice"},
        "attrs": {},
        "parents": [{"type": "UserGroup", "id": "friendsAndFamily"}],
    },
    {
        "uid": {"type": "User", "id": "bob"},
        "attrs": {},
        "parents": [{"type": "UserGroup", "id": "friendsAndFamily"}],
    },
    {
        "uid": {"type": "User", "id": "stranger"},
        "attrs": {},
        "parents": [],
    },
    {
        "uid": {"type": "Album", "id": "vacationTrip"},
        "attrs": {"tag": "public"},
        "parents": [],
    },
    {
        "uid": {"type": "Album", "id": "privateAlbum"},
        "attrs": {"tag": "private"},
        "parents": [{"type": "Album", "id": "vacationTrip"}],
    },
]


class UserGroupCedarAuthorization(InterventionHandler):
    """Cedar authorization handler using group membership and resource hierarchy."""

    name = "cedar-authorization"

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
        resource_id = tool_input.get("album", "vacationTrip")

        request = {
            "principal": f'{principal["type"]}::"{principal["id"]}"',
            "action": f'Action::"{tool_name}"',
            "resource": f'Album::"{resource_id}"',
            "context": {},
        }

        try:
            result = cedarpy.is_authorized(request, self._policies, self._entities)
        except Exception as e:
            return Deny(reason=f"Cedar evaluation failed: {e}")

        if not result.allowed:
            return Deny(reason="Access denied by Cedar policy: user is not in the allowed group or resource is private")

        return Proceed()


@tool
def view(album: str) -> str:
    """View photos in an album."""
    return f"Displaying photos from album: {album}"


@tool
def comment(album: str, text: str) -> str:
    """Leave a comment on an album."""
    return f"Comment added to {album}: '{text}'"


@tool
def delete(album: str) -> str:
    """Delete an album."""
    return f"Deleted album: {album}"


cedar = UserGroupCedarAuthorization(
    policies=_POLICIES,
    entities=_ENTITIES,
    principal_resolver=lambda state: (
        {"type": "User", "id": state["user_id"]}
        if state.get("user_id")
        else None
    ),
)

ALL_TOOLS = [view, comment, delete]


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
        "[bold]Cedar User Group Policy[/]\n"
        "Policy: policies/user_group.cedar\n\n"
        "Only members of UserGroup::\"friendsAndFamily\" can view/comment\n"
        "on Album::\"vacationTrip\", unless the resource tag is \"private\".",
        title="Demo",
    ))
    console.print()

    run_scenario(
        title="Alice (friendsAndFamily): view vacationTrip - PERMITTED",
        style="green",
        prompt="View the vacationTrip album",
        invocation_state={"user_id": "alice"},
    )

    run_scenario(
        title="Bob (friendsAndFamily): comment on vacationTrip - PERMITTED",
        style="green",
        prompt="Leave a comment 'Great photos!' on the vacationTrip album",
        invocation_state={"user_id": "bob"},
    )

    run_scenario(
        title="Alice (friendsAndFamily): view privateAlbum - DENIED (tag=private)",
        style="red",
        prompt="View the privateAlbum album",
        invocation_state={"user_id": "alice"},
    )

    run_scenario(
        title="Stranger (not in group): view vacationTrip - DENIED",
        style="red",
        prompt="View the vacationTrip album",
        invocation_state={"user_id": "stranger"},
    )

    run_scenario(
        title="Alice (friendsAndFamily): delete vacationTrip - DENIED (action not permitted)",
        style="red",
        prompt="Delete the vacationTrip album",
        invocation_state={"user_id": "alice"},
    )
