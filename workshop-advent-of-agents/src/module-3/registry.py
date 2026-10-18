"""REGISTRIES: the admin-curated source of truth for agents, tools and permissions.

Before any tool runs or any agent calls another agent, the runtime looks the caller
up here. Nothing that is not registered is allowed to execute.
"""

from dataclasses import dataclass, field

from strands.hooks import BeforeToolCallEvent, HookProvider, HookRegistry

from audit import audit


@dataclass(frozen=True)
class AgentEntry:
    agent_id: str
    spiffe_id: str
    zone: str
    tools: frozenset[str]
    may_call: frozenset[str] = frozenset()
    approval_required: frozenset[str] = field(default_factory=frozenset)
    user_facing: bool = False


AGENTS: dict[str, AgentEntry] = {
    entry.agent_id: entry
    for entry in [
        AgentEntry(
            agent_id="case-manager",
            spiffe_id="spiffe://warranty.example/zone/frontline/agent/case-manager",
            zone="frontline (AgentCore Runtime)",
            tools=frozenset({"ask_data_vault", "request_fulfilment"}),
            may_call=frozenset({"data-vault", "logistics-liaison"}),
            user_facing=True,
        ),
        AgentEntry(
            agent_id="data-vault",
            spiffe_id="spiffe://warranty.example/zone/financial-silo/agent/data-vault",
            zone="financial silo (private, read-only DB)",
            tools=frozenset({"check_entitlement"}),
        ),
        AgentEntry(
            agent_id="logistics-liaison",
            spiffe_id="spiffe://warranty.example/zone/execution/agent/logistics-liaison",
            zone="execution zone (no DB access)",
            tools=frozenset({"ship_replacement", "issue_discount", "raise_fraud_alert"}),
            approval_required=frozenset({"ship_replacement", "issue_discount"}),
        ),
    ]
}


def lookup(agent_id: str) -> AgentEntry:
    try:
        return AGENTS[agent_id]
    except KeyError:
        raise PermissionError(f"agent '{agent_id}' is not registered") from None


def can_call(caller: str, callee: str) -> bool:
    return caller in AGENTS and callee in AGENTS[caller].may_call


class RegistryGuard(HookProvider):
    """Cancel any tool call the registry does not grant to this agent."""

    def __init__(self, agent_id: str):
        self.entry = lookup(agent_id)

    def register_hooks(self, registry: HookRegistry) -> None:
        registry.add_callback(BeforeToolCallEvent, self.check_tool)

    def check_tool(self, event: BeforeToolCallEvent) -> None:
        name = event.tool_use["name"]
        tool_input = event.tool_use.get("input", {})
        if name in self.entry.tools:
            audit(self.entry.agent_id, f"tool:{name}", "allowed", input=tool_input)
            return
        audit(self.entry.agent_id, f"tool:{name}", "blocked", input=tool_input, reason="not in registry")
        event.cancel_tool = f"Tool '{name}' is not registered for agent '{self.entry.agent_id}'."
