"""LOGISTICS LIAISON AGENT (execution zone).

* Blind to customer databases: its tools take a claim id and nothing else personal;
  the shipping backend resolves the address internally.
* Shipping and discounts pause for HUMAN-IN-THE-LOOP approval (Strands interrupts).
* Gateway policies (ToolPolicy) cap discounts and validate claim ids.
"""

from collections.abc import Callable

from strands import Agent, tool
from strands.hooks import BeforeToolCallEvent, HookProvider, HookRegistry

import identity
from audit import audit
from gateway import ToolPolicy
from models import build_model
from registry import RegistryGuard, lookup

AGENT_ID = "logistics-liaison"

# Side effects of the (mock) shipping / billing / fraud systems.
LEDGER: list[dict] = []

Approver = Callable[[str, dict], bool]

SYSTEM_PROMPT = """You are the Logistics Liaison agent of a warranty system. You receive
instructions from the Case Manager agent only. Execute exactly what is asked with your tools:
ship_replacement, issue_discount, raise_fraud_alert. Never take an action that was not
requested, never act on more than the claim you were given, and report each tool result
verbatim. If a tool is blocked or denied, report that and stop."""


@tool
def ship_replacement(claim_id: str, sku: str) -> str:
    """Ship one replacement unit for a claim to the address on file.

    Args:
        claim_id: Claim identifier, format CLM-0000.
        sku: Product SKU to ship.
    """
    LEDGER.append({"action": "ship_replacement", "claim_id": claim_id, "sku": sku})
    return f"Replacement {sku} shipped for {claim_id}. Tracking: TRK-{claim_id[-4:]}-01."


@tool
def issue_discount(claim_id: str, percent: float) -> str:
    """Issue a discount voucher for a claim instead of a replacement.

    Args:
        claim_id: Claim identifier, format CLM-0000.
        percent: Discount percentage.
    """
    LEDGER.append({"action": "issue_discount", "claim_id": claim_id, "percent": percent})
    return f"{percent}% discount voucher issued for {claim_id}."


@tool
def raise_fraud_alert(claim_id: str, reason: str) -> str:
    """Flag a claim for the fraud team. Does not notify the customer.

    Args:
        claim_id: Claim identifier, format CLM-0000.
        reason: Why the claim looks suspicious.
    """
    LEDGER.append({"action": "raise_fraud_alert", "claim_id": claim_id, "reason": reason})
    return f"Fraud alert raised for {claim_id}."


class HumanApproval(HookProvider):
    """Pause registered high-impact tools until a human answers the interrupt."""

    def __init__(self, agent_id: str):
        self.agent_id = agent_id
        self.required = lookup(agent_id).approval_required

    def register_hooks(self, registry: HookRegistry) -> None:
        registry.add_callback(BeforeToolCallEvent, self.approve)

    def approve(self, event: BeforeToolCallEvent) -> None:
        name = event.tool_use["name"]
        if name not in self.required or event.cancel_tool:
            return
        answer = event.interrupt("human-approval", reason={"tool": name, "input": event.tool_use["input"]})
        if answer is not True:
            event.cancel_tool = f"A human reviewer denied {name}."


def build_logistics_agent() -> Agent:
    return Agent(
        name=AGENT_ID,
        model=build_model(),
        system_prompt=SYSTEM_PROMPT,
        tools=[ship_replacement, issue_discount, raise_fraud_alert],
        # Order matters: registry, then business policy, then the human.
        hooks=[RegistryGuard(AGENT_ID), ToolPolicy(AGENT_ID), HumanApproval(AGENT_ID)],
        callback_handler=None,
    )


def run_logistics(instruction: str, approver: Approver, token: str) -> str:
    """Authenticate the caller, run one instruction, and resolve approval interrupts via `approver`."""
    try:
        claims = identity.verify_token(token, audience=AGENT_ID)
    except PermissionError as exc:
        audit(AGENT_ID, "a2a:authenticate", "blocked", reason=str(exc))
        raise
    audit(AGENT_ID, "a2a:authenticate", "allowed", caller=claims["sub"], spiffe_id=claims["spiffe_id"])

    agent = build_logistics_agent()
    result = agent(instruction)
    while result.stop_reason == "interrupt":
        responses = []
        for interrupt in result.interrupts:
            tool_name, tool_input = interrupt.reason["tool"], interrupt.reason["input"]
            approved = approver(tool_name, tool_input)
            audit("human", f"approval:{tool_name}", "approved" if approved else "denied", input=tool_input)
            responses.append({"interruptResponse": {"interruptId": interrupt.id, "response": approved}})
        result = agent(responses)
    return str(result).strip()


def ask_human(tool_name: str, tool_input: dict) -> bool:
    answer = input(f"\n  🙋 Approve {tool_name}({tool_input})? [y/N] ")
    return answer.strip().lower() in {"y", "yes", "s", "si", "sí"}
