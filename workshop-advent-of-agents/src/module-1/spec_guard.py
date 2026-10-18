"""Turn DESIGN_SPEC.md into a runtime control.

`SpecGuard` is a Strands hook provider that:
  * prints an audit line `[tool_call: name(args)]` for every tool call, and
  * cancels any tool that is not listed under "Allowed tools:" in the spec.

That is the Scope -> Govern link of the ADLC: the spec is not just a document,
the agent cannot step outside it.
"""

import json
import re
from pathlib import Path

from strands.hooks import BeforeToolCallEvent, HookProvider, HookRegistry

SPEC_PATH = Path(__file__).with_name("DESIGN_SPEC.md")


def load_allowed_tools(spec_path: Path = SPEC_PATH) -> set[str]:
    """Read the comma-separated `Allowed tools:` line from the design spec."""
    match = re.search(r"^Allowed tools:\s*(.+)$", spec_path.read_text(), re.MULTILINE)
    if match is None:
        raise ValueError(f"{spec_path} has no 'Allowed tools:' line")
    return {name.strip() for name in match.group(1).split(",") if name.strip()}


class SpecGuard(HookProvider):
    def __init__(self, allowed_tools: set[str] | None = None, verbose: bool = True):
        self.allowed_tools = allowed_tools if allowed_tools is not None else load_allowed_tools()
        self.verbose = verbose
        self.audit_log: list[dict] = []

    def register_hooks(self, registry: HookRegistry) -> None:
        registry.add_callback(BeforeToolCallEvent, self.check_tool)

    def check_tool(self, event: BeforeToolCallEvent) -> None:
        name = event.tool_use["name"]
        args = event.tool_use.get("input", {})
        allowed = name in self.allowed_tools
        self.audit_log.append({"tool": name, "input": args, "allowed": allowed})

        if self.verbose:
            rendered = ", ".join(f"{k}={json.dumps(v, ensure_ascii=False)}" for k, v in args.items())
            status = "" if allowed else "  <-- BLOCKED by DESIGN_SPEC.md"
            print(f"\n[tool_call: {name}({rendered})]{status}", flush=True)

        if not allowed:
            event.cancel_tool = (
                f"Tool '{name}' is not allowed by DESIGN_SPEC.md. "
                f"Allowed tools: {', '.join(sorted(self.allowed_tools))}."
            )
