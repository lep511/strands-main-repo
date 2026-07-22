"""Namespaced Cedar policies example.

Demonstrates how to use Cedar policies with namespace prefixes (e.g. Agent::Action::"search")
as produced by policy generators like cedar-agent-policy-builder.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime as dt
from datetime import timezone
from typing import Any

import cedarpy

from strands import Agent, tool
from strands.hooks.events import BeforeToolCallEvent
from strands.interventions.actions import Deny, Proceed
from strands.interventions.handler import InterventionHandler, OnError
from strands.vended_interventions.cedar import CedarAuthorization, ToolDefinition
from strands.vended_interventions.cedar._file_loaders import load_entities, load_policies
from strands.vended_interventions.cedar._schema_generator import (
    DEFAULT_STUB,
    generate_cedar_schema,
)

TypeAndId = dict[str, str]
PrincipalResolver = Callable[[dict[str, Any]], TypeAndId | None]
ContextEnricher = Callable[[dict[str, Any]], dict[str, Any]]

_STATE_KEY = "cedar-authorization"


def _generate_namespaced_schema(tools: list[ToolDefinition], namespace: str) -> str:
    """Generate a Cedar schema preserving the namespace wrapper."""
    try:
        from cedar_mcp_schema_generator import SchemaGeneratorError, generate_schema_or_raise
    except ImportError as e:
        raise ImportError(
            "cedar-policy-mcp-schema-generator is required for auto schema generation. "
            "Install it with: pip install cedar-policy-mcp-schema-generator"
        ) from e

    stub = f"""
namespace {namespace} {{
  @mcp_principal
  entity User;
  @mcp_resource
  entity Resource;
  @mcp_context("session")
  type SessionContext = {{
    hour_utc: Long,
    call_count: Long
  }};
}}
"""

    try:
        result = generate_schema_or_raise(stub, tools, config={"flattenNamespaces": True})
    except SchemaGeneratorError as e:
        raise RuntimeError(f"Schema generation failed: {e}") from e

    schema = result["schema"]
    if not schema:
        raise RuntimeError("Schema generation returned empty schema")

    return schema


class NamespacedCedarAuthorization(InterventionHandler):
    """Cedar authorization handler with namespace support.

    When namespace is set, all Cedar entity references are prefixed:
    - Action::"tool" becomes Namespace::Action::"tool"
    - Resource::"agent" becomes Namespace::Resource::"default"
    - User::"anonymous" becomes Namespace::User::"anonymous"

    This is required when using policy generators like cedar-agent-policy-builder
    that produce namespaced Cedar policies.
    """

    name = "cedar-authorization"

    @property
    def on_error(self) -> OnError:
        return self._on_error

    def __init__(
        self,
        *,
        namespace: str,
        policies: str,
        tools: list[ToolDefinition] | None = None,
        entities: list[dict[str, Any]] | str | None = None,
        schema: str | None = None,
        principal: TypeAndId | None = None,
        principal_resolver: PrincipalResolver | None = None,
        context_enricher: ContextEnricher | None = None,
        on_error: OnError = "throw",
    ) -> None:
        if principal and principal_resolver:
            raise ValueError("Provide either `principal` or `principal_resolver`, not both")

        self._namespace = namespace
        self._on_error = on_error
        self._policies = load_policies(policies)
        self._entities = load_entities(entities) if entities else [
            {"uid": {"type": f"{namespace}::Resource", "id": "default"}, "attrs": {}, "parents": []}
        ]

        if schema:
            from strands.vended_interventions.cedar._file_loaders import load_schema
            self._schema = load_schema(schema)
        elif tools:
            self._schema = _generate_namespaced_schema(tools, namespace)
        else:
            self._schema = None

        if principal_resolver:
            self._principal: TypeAndId | None = None
        else:
            self._principal = principal or {"type": f"{namespace}::User", "id": "anonymous"}

        self._principal_resolver = principal_resolver
        self._context_enricher = context_enricher
        self._call_counts: dict[str, int] = {}

        self._validate()

    def _validate(self) -> None:
        try:
            cedarpy.format_policies(self._policies)
        except ValueError as e:
            raise ValueError(f"Invalid Cedar policy: {e}") from e

        if self._schema:
            result = cedarpy.validate_policies(self._policies, self._schema)
            if not result.validation_passed and result.errors:
                errors = [
                    e
                    for e in result.errors
                    if "unrecognized action" in e.error or "unable to find an applicable action" in e.error
                ]
                if errors:
                    msg = ", ".join(f"{e.policy_id}: {e.error}" for e in errors)
                    raise ValueError(f"Cedar policy validation failed: {msg}")

    def before_tool_call(self, event: BeforeToolCallEvent, **kwargs: Any) -> Proceed | Deny:
        invocation_state = event.invocation_state

        if self._principal_resolver:
            principal = self._principal_resolver(invocation_state)
        else:
            principal = self._principal

        if not principal or not principal.get("type") or not principal.get("id"):
            return Deny(reason="No principal identity found in invocation state")

        tool_name = event.tool_use["name"]
        call_count = self._increment_call_count(event.agent, tool_name)
        tool_input = event.tool_use.get("input") or {}

        enricher_fields: dict[str, Any] = {}
        if self._context_enricher:
            enricher_fields = self._context_enricher(
                {"tool_name": tool_name, "tool_input": tool_input, "invocation_state": invocation_state}
            )

        ns = self._namespace
        context = {
            "input": tool_input,
            "session": {
                **enricher_fields,
                "hour_utc": dt.now(timezone.utc).hour,
                "call_count": call_count,
            },
        }

        request = {
            "principal": f'{principal["type"]}::"{principal["id"]}"',
            "action": f'{ns}::Action::"{tool_name}"',
            "resource": f'{ns}::Resource::"default"',
            "context": context,
        }

        try:
            result = cedarpy.is_authorized(request, self._policies, self._entities, self._schema)
        except Exception as e:
            self._decrement_call_count(event.agent, tool_name)
            return Deny(reason=f"Cedar evaluation failed: {e}")

        if result.decision == cedarpy.Decision.NoDecision:
            self._decrement_call_count(event.agent, tool_name)
            errors = (
                [e.error if hasattr(e, "error") else str(e) for e in result.diagnostics.errors]
                if result.diagnostics.errors
                else []
            )
            error_detail = ": " + ", ".join(errors) if errors else ""
            return Deny(reason=f"Cedar evaluation failed{error_detail}")

        if not result.allowed:
            self._decrement_call_count(event.agent, tool_name)
            return Deny(reason="Access denied by Cedar policy")

        return Proceed()

    def reload(self) -> None:
        policies = load_policies(self._policies)
        self._policies = policies
        self._validate()

    def _increment_call_count(self, agent: Agent, tool_name: str) -> int:
        if not self._call_counts:
            stored = agent.state.get(_STATE_KEY)
            if isinstance(stored, dict):
                self._call_counts.update(stored)
        current = self._call_counts.get(tool_name, 0)
        next_count = current + 1
        self._call_counts[tool_name] = next_count
        agent.state.set(_STATE_KEY, dict(self._call_counts))
        return next_count

    def _decrement_call_count(self, agent: Agent, tool_name: str) -> None:
        current = self._call_counts.get(tool_name, 0)
        if current > 0:
            self._call_counts[tool_name] = current - 1
        agent.state.set(_STATE_KEY, dict(self._call_counts))


# --- Example tools ---

@tool
def search(query: str) -> str:
    """Search for information."""
    return f"Results for: {query}"


@tool
def delete_record(record_id: str) -> str:
    """Delete a record by ID."""
    return f"Deleted {record_id}"


# --- Tool definitions for schema validation ---

search_def: ToolDefinition = {
    "name": "search",
    "inputSchema": {
        "type": "object",
        "properties": {"query": {"type": "string"}},
    },
}

delete_def: ToolDefinition = {
    "name": "delete_record",
    "inputSchema": {
        "type": "object",
        "properties": {"record_id": {"type": "string"}},
    },
}


# --- Namespaced Cedar authorization ---

cedar = NamespacedCedarAuthorization(
    namespace="Agent",
    policies="""
      permit(
        principal,
        action == Agent::Action::"search",
        resource
      );
    """,
    tools=[search_def, delete_def],
    entities=[
        {"uid": {"type": "Agent::Resource", "id": "default"}, "attrs": {}, "parents": []},
    ],
    principal_resolver=lambda state: (
        {"type": "Agent::User", "id": state["user_id"]}
        if state.get("user_id")
        else None
    ),
)

agent = Agent(
    tools=[search, delete_record],
    interventions=[cedar],
)


def main():
    print("\n--- Namespaced policies: search is permitted ---")
    agent(
        "Search for quarterly reports",
        invocation_state={"user_id": "alice"},
    )

    print("\n\n--- Namespaced policies: delete_record is denied ---")
    agent(
        "Delete record 42",
        invocation_state={"user_id": "alice"},
    )
    print("\n\n")


if __name__ == "__main__":
    main()
