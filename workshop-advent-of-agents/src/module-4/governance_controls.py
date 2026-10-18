"""Prevention and Response controls for any Strands agent in the estate.

  * LIMITS          - circuit breaker: turn and token ceilings per invocation (Strands `limits`)
  * RegistryGate    - only registered, active agents may run or call tools
  * ContainmentWatch - watches the registry and cancels a running invocation on revoke

Revocation path (Response layer):

    estate_registry.py revoke <id>
        -> .registry_state.json status=revoked
        -> ContainmentWatch sees it within POLL_SECONDS and calls agent.cancel()
        -> RegistryGate also refuses the next tool call and every new invocation
"""

import threading
import time

from strands import Agent
from strands.hooks import BeforeInvocationEvent, BeforeToolCallEvent, HookProvider, HookRegistry

import estate_registry

# Circuit breaker for one invocation; see "Production lifecycle controls" in the Strands docs.
LIMITS = {"turns": 25, "total_tokens": 200_000}
POLL_SECONDS = 0.5


class RegistryGate(HookProvider):
    """Fail closed: an agent that is not registered and active does nothing."""

    def __init__(self, agent_id: str, **registry_paths):
        self.agent_id = agent_id
        self.registry_paths = registry_paths

    def _blocked(self) -> str | None:
        current = estate_registry.status(self.agent_id, **self.registry_paths)
        return None if current == "active" else f"agent '{self.agent_id}' is {current} in the registry"

    def register_hooks(self, registry: HookRegistry) -> None:
        registry.add_callback(BeforeInvocationEvent, self.check_invocation)
        registry.add_callback(BeforeToolCallEvent, self.check_tool)

    def check_invocation(self, event: BeforeInvocationEvent) -> None:
        if reason := self._blocked():
            event.cancel = f"Invocation refused: {reason}."

    def check_tool(self, event: BeforeToolCallEvent) -> None:
        if reason := self._blocked():
            event.cancel_tool = f"Tool call refused: {reason}."


class ContainmentWatch:
    """Background watcher that cancels the agent as soon as the registry revokes it.

    with ContainmentWatch(agent, "inbox-assistant") as watch:
        result = agent(prompt, limits=LIMITS)
    watch.contained_at  # monotonic time of the cancel, or None
    """

    def __init__(self, agent: Agent, agent_id: str, poll_seconds: float = POLL_SECONDS, **registry_paths):
        self.agent = agent
        self.agent_id = agent_id
        self.poll_seconds = poll_seconds
        self.registry_paths = registry_paths
        self.contained_at: float | None = None
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._watch, daemon=True)

    def _watch(self) -> None:
        while not self._stop.wait(self.poll_seconds):
            if estate_registry.status(self.agent_id, **self.registry_paths) != "active":
                self.contained_at = time.monotonic()
                self.agent.cancel()  # thread-safe; the loop stops at its next checkpoint
                return

    def __enter__(self) -> "ContainmentWatch":
        self._thread.start()
        return self

    def __exit__(self, *exc) -> None:
        self._stop.set()
        self._thread.join()
