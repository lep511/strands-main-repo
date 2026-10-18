"""GATEWAY: the inline policy enforcement point for every hop.

* inbound  - user -> case manager: block prompt injection, mask PII.
* lateral  - agent -> agent (both directions): validate requests, redact injected
             instructions and PII from responses before they reach the next model.
* outbound - agent -> tool: business policies (`ToolPolicy` hook), e.g. discount caps.

The regexes are a teaching stand-in for Amazon Bedrock Guardrails (prompt-attack
filter + sensitive-information filters). Set GUARDRAIL_ID to also attach a real
Bedrock guardrail to the case manager's model (see case_manager.py).
"""

import re
from dataclasses import dataclass, field

from strands.hooks import BeforeToolCallEvent, HookProvider, HookRegistry

from audit import audit

INJECTION_PATTERNS = [
    r"ignore (all |any )?(the )?(previous|prior|above) (instructions|rules)",
    r"disregard (all |your )?(previous |prior )?(instructions|rules|guidelines)",
    r"you are now (an? )?(admin|administrator|developer|system)",
    r"(reveal|print|show|dump|list) (me )?(your |the )?(system prompt|instructions)",
    r"(list|dump|export|show) (me )?(all|every) (customer|user)s?",
    r"\bjailbreak\b|\bDAN mode\b",
]
PII_PATTERNS = {
    "EMAIL": r"[\w.+-]+@[\w-]+\.[\w.-]+",
    # International format only, so ISO dates like 2026-03-10 are not mistaken for phones.
    "PHONE": r"\+\d{1,3}[\s-]?\d{2,4}(?:[\s-]?\d{2,4}){2,3}",
    "CARD": r"\b(?:\d[ -]?){13,16}\b",
}
CLAIM_ID = re.compile(r"^CLM-\d{4}$")
MAX_DISCOUNT_PERCENT = 25


@dataclass
class Screened:
    text: str
    blocked: bool = False
    findings: list[str] = field(default_factory=list)


def _injections(text: str) -> list[str]:
    return [p for p in INJECTION_PATTERNS if re.search(p, text, re.IGNORECASE)]


def _mask_pii(text: str) -> tuple[str, list[str]]:
    found = []
    # Cards before phones: a card number also matches the phone pattern.
    for label in ("EMAIL", "CARD", "PHONE"):
        text, count = re.subn(PII_PATTERNS[label], f"<{label}>", text)
        if count:
            found.append(f"pii:{label.lower()}")
    return text, found


def screen_inbound(text: str) -> Screened:
    """User -> case manager. Injection blocks the request; PII is masked."""
    if hits := _injections(text):
        audit("gateway", "inbound:user", "blocked", reason="prompt_injection", patterns=hits)
        return Screened(text="", blocked=True, findings=["prompt_injection"])
    masked, pii = _mask_pii(text)
    audit("gateway", "inbound:user", "allowed", findings=pii)
    return Screened(text=masked, findings=pii)


def screen_lateral(source: str, dest: str, text: str) -> Screened:
    """Agent -> agent. Injected instructions are redacted (not executed), PII masked."""
    findings = []
    for pattern in _injections(text):
        text = re.sub(pattern, "[REDACTED: instruction-like text]", text, flags=re.IGNORECASE)
        findings.append("prompt_injection")
    text, pii = _mask_pii(text)
    findings += pii
    audit("gateway", f"lateral:{source}->{dest}", "redacted" if findings else "allowed", findings=sorted(set(findings)))
    return Screened(text=text, findings=sorted(set(findings)))


def valid_claim_id(claim_id: str) -> bool:
    return bool(CLAIM_ID.match(claim_id.strip()))


class ToolPolicy(HookProvider):
    """Outbound business rules evaluated before a tool runs."""

    def __init__(self, agent_id: str):
        self.agent_id = agent_id

    def register_hooks(self, registry: HookRegistry) -> None:
        registry.add_callback(BeforeToolCallEvent, self.check)

    def check(self, event: BeforeToolCallEvent) -> None:
        name = event.tool_use["name"]
        args = event.tool_use.get("input", {})
        reason = None
        if "claim_id" in args and not valid_claim_id(str(args["claim_id"])):
            reason = f"invalid claim id {args['claim_id']!r}"
        elif name == "issue_discount" and float(args.get("percent", 0)) > MAX_DISCOUNT_PERCENT:
            reason = f"discount {args['percent']}% exceeds the {MAX_DISCOUNT_PERCENT}% policy cap"
        if reason:
            audit("gateway", f"policy:{name}", "blocked", agent=self.agent_id, reason=reason)
            event.cancel_tool = f"Blocked by gateway policy: {reason}."
