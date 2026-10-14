"""Interactive trading-desk chat governed by the Dogwood Local Engine.

A Strands agent with four trading tools chats with you in the terminal (Rich).
Every tool call goes through `DogwoodHarness`, an InterventionHandler that plays
the harness role from the Dogwood Local Engine announcement: it submits a
`request` event to the engine, runs the tool only if the verdict is ALLOW, and
then submits the outcome as a `response` event - or as an `error` event when the
call was denied or failed, the same bookkeeping AgentCore Policy does at the
Gateway.

The engine is `dogwood-server`, the reference daemon in dogwood-local-engine. It
keeps the event history durably (redb) and decides each request incrementally
against it, so the temporal limits survive a restart of this chat. It speaks
length-prefixed JSON over two Unix sockets, which is all this file needs:

  data plane     <dir>/run/dogwood.sock   submit events, receive verdicts
  control plane  <dir>/control.sock       install policies, status, reset

Start the server once (needs a Rust toolchain):

    git clone https://github.com/dogwood-policy/dogwood-local-engine
    cd dogwood-local-engine
    cargo build --release -p dogwood-server
    ./target/release/dogwood-server --dir ~/.dogwood-chat run

Then, from cedar-auth/:

    uv run python dogwood/local_engine_chat.py [--user alice] [--dir ~/.dogwood-chat] [--reinstall]
                                               [--policies dogwood/policies/local_engine_chat]

Commands: /policies, /history, /status, /user <name>, /reset, /new, /help, /exit

The policies are the .dw files in policies/local_engine_chat/, one per file, each
opening with the natural-language rule it encodes - the traceability the
AgentCore natural-language authoring post is built around. They build on
policies/*.dw but are their own set: that directory also holds rules that would
undo these (approve_before_sell.dw permits a sale on any earlier approval,
anti_spike.dw forbids the first transfer of every hour). The agent is not given
the rules: it would refuse an obvious violation itself, and the engine would
never decide it. A denial quotes the rule that stopped the call instead.

The chat installs the set over the control socket when the store runs no
policies or a different revision of them. That is a demo convenience:
dogwood-server is only tamper-resistant when it runs as a different, more
privileged uid than the agent and an operator installs policy with
`dogwood-server policy install`. If the control socket is out of reach the chat
still works; it just cannot install, reset, or name the policies behind a
verdict.

To enforce the policies on an AgentCore Gateway instead, add
`eventResource: resource` to every temporal predicate and rename the actions to
`<Target>___<tool>`; see agentcore_temporal_policies.py.

Reference:
  https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/policy-temporal.html
  https://github.com/dogwood-policy/dogwood
  https://github.com/dogwood-policy/dogwood-local-engine
  https://aws.amazon.com/es/blogs/machine-learning/authoring-dogwood-policies-from-natural-language-in-amazon-bedrock-agentcore/
  https://aws.amazon.com/es/blogs/opensource/introducing-the-dogwood-local-engine-temporal-governance-for-agent-actions/
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import socket
import struct
import sys
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    # Loading readline is what gives input() arrow keys, line editing and history;
    # without it the arrows print escape codes such as ^[[D.
    import readline
except ImportError:  # Windows: no readline, and its console edits lines itself
    readline = None

from rich.console import Console
from rich.markdown import Markdown
from rich.markup import escape
from rich.panel import Panel
from rich.prompt import Confirm
from rich.syntax import Syntax
from rich.table import Table

from strands import Agent, tool
from strands.hooks.events import AfterToolCallEvent, BeforeToolCallEvent
from strands.interventions.actions import Deny, Proceed
from strands.interventions.handler import InterventionHandler, OnError
from strands.tools.executors import SequentialToolExecutor

console = Console()

DEFAULT_DIR = Path.home() / ".dogwood-chat"
POLICY_DIR = Path(__file__).resolve().parent / "policies" / "local_engine_chat"
DEFAULT_USER = "alice"
# Principal names end up inside an entity uid literal, User::"<name>".
PRINCIPAL_RE = re.compile(r"[A-Za-z0-9_.-]+")
SOCKET_TIMEOUT_S = 10.0

NAMESPACE = "AgentCore"
RESOURCE = f'{NAMESPACE}::Gateway::"trading-desk"'


# ---------------------------------------------------------------------------
# Schema and policies
# ---------------------------------------------------------------------------

# One Cedar action per tool, named exactly like the tool. Only ApproveSale declares
# an output: it is the one output a policy reads. The default event schema derives
# `request` / `response` / `error` events from these actions and pins every
# temporal predicate to the caller's principal, so each user has its own history.
#
# `callId` is not a tool argument: the harness adds the Strands toolUseId to every
# event of a call, so a policy can match a request with its outcome. (The wire
# only carries grouped fields, so it cannot use the event schema's `requestId`.)
ACTION_SCHEMA = """
namespace AgentCore {
  entity User;
  entity Gateway;

  type GetStockInfoInput = { stock: String, callId: String };
  type ApproveSaleInput  = { stock: String, shares: Long, callId: String };
  type ApproveSaleOutput = { approved: Bool };
  type SellSharesInput   = { stock: String, shares: Long, callId: String };
  type TransferInput     = { user: String, amount: Long, callId: String };

  action "GetStockInfo" appliesTo {
    principal: [User], resource: [Gateway],
    context: { input: GetStockInfoInput }
  };
  action "ApproveSale" appliesTo {
    principal: [User], resource: [Gateway],
    context: { input: ApproveSaleInput, output?: ApproveSaleOutput }
  };
  action "SellShares" appliesTo {
    principal: [User], resource: [Gateway],
    context: { input: SellSharesInput }
  };
  action "Transfer" appliesTo {
    principal: [User], resource: [Gateway],
    context: { input: TransferInput }
  };
}
"""


@dataclass(frozen=True)
class Policy:
    id: str
    rule: str  # the natural-language requirement it encodes
    source: str  # the .dw file as written

    @property
    def effect(self) -> str:
        match = re.search(r"^\s*(permit|forbid)\b", self.source, re.MULTILINE)
        return match.group(1) if match else "?"

    @property
    def actions(self) -> list[str]:
        """The actions the scope names with `action == ...::Action::"X"`."""
        return re.findall(r'action\s*==\s*[\w:]*Action::"([^"]+)"', self.source)


@dataclass(frozen=True)
class PolicySet:
    directory: Path
    policies: list[Policy]
    revision: str  # stamped on every installed policy, see ensure_policies
    source: str  # what gets installed


def _rule(source: str) -> str:
    """The first paragraph of the file's leading `//` comment block."""
    lines: list[str] = []
    for line in source.splitlines():
        text = line.strip()
        if not text.startswith("//"):
            break
        text = text[2:].strip()
        if text:
            lines.append(text)
        elif lines:
            break
    return " ".join(lines)


def load_policy_set(directory: Path) -> PolicySet:
    """Read every .dw file in `directory`, one policy per file, in file-name order.

    A file opens with the rule it encodes in natural language, as a `//` comment.
    A blank `//` line ends the rule; what follows is notes for whoever edits the
    policy. Only the rule reaches /policies and, through denials, the agent.
    """
    if not directory.is_dir():
        raise ValueError(f"{directory} is not a directory")
    policies = []
    for path in sorted(directory.glob("*.dw")):
        source = path.read_text().strip()
        ids = re.findall(r'@id\("([^"]+)"\)', source)
        if len(ids) != 1:
            raise ValueError(f"{path}: expected one policy with an @id, found {len(ids)} @id")
        rule = _rule(source)
        if not rule:
            raise ValueError(f"{path}: start the file with a // comment stating its rule")
        policies.append(Policy(ids[0], rule, source))
    if not policies:
        raise ValueError(f"no .dw files in {directory}")

    # Any change to the files or the schema gives a new revision, and a new
    # revision is reinstalled on the next start (resetting the history).
    revision = hashlib.sha256(
        (ACTION_SCHEMA + "".join(p.source for p in policies)).encode()
    ).hexdigest()[:12]
    # Stamp next to @id, so the annotations stay together after the comments.
    source = "\n\n".join(
        p.source.replace("@id(", f'@revision("{revision}")\n@id(', 1) for p in policies
    )
    return PolicySet(directory, policies, revision, source)


# ---------------------------------------------------------------------------
# dogwood-server client
# ---------------------------------------------------------------------------


class DogwoodError(RuntimeError):
    """The server answered with an error, such as a rejected policy install."""


class DogwoodUnreachable(DogwoodError):
    """The socket could not be reached, or the connection broke mid-call."""


def _recv_exact(sock: socket.socket, size: int) -> bytes:
    buf = b""
    while len(buf) < size:
        chunk = sock.recv(size - len(buf))
        if not chunk:
            raise ConnectionError("connection closed mid-frame")
        buf += chunk
    return buf


class DogwoodServer:
    """Client for dogwood-server: one 4-byte big-endian length + JSON frame each way.

    The two sockets carry disjoint verbs on purpose. The data socket has nothing
    that can read or change policy, so an agent that only reaches it cannot
    rewrite the rules it is judged by.
    """

    def __init__(self, state_dir: Path) -> None:
        self.state_dir = state_dir
        self.data_socket = state_dir / "run" / "dogwood.sock"
        self.control_socket = state_dir / "control.sock"

    def ping(self) -> str:
        return self._call(self.data_socket, {"op": "ping"})["version"]

    def submit(self, event: dict) -> dict:
        """Request events get a `decision`; response and error events get `recorded`."""
        return self._call(self.data_socket, {"op": "submit", "event": event})

    def control(self, op: str, **fields: Any) -> dict:
        return self._call(self.control_socket, {"op": op, **fields})

    @staticmethod
    def _call(path: Path, request: dict) -> dict:
        body = json.dumps(request).encode()
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
                sock.settimeout(SOCKET_TIMEOUT_S)
                sock.connect(str(path))
                sock.sendall(struct.pack(">I", len(body)) + body)
                (length,) = struct.unpack(">I", _recv_exact(sock, 4))
                response = json.loads(_recv_exact(sock, length))
        except OSError as exc:
            raise DogwoodUnreachable(f"{path}: {exc}") from exc
        # An error is not a deny, and must never be read as an allow.
        if response.get("status") == "error":
            raise DogwoodError(response.get("message", "unknown error"))
        return response


def ensure_policies(server: DogwoodServer, policy_set: PolicySet, reinstall: bool) -> str:
    """Install `policy_set` unless the store already runs this revision of it.

    Installing replaces the whole set and every policy starts with an empty
    history, so a store on the current revision is left alone: that is what lets
    a rate limit survive a restart of the chat. Any other set is replaced, since
    its schema may not even accept the events this harness sends.
    """
    status = server.control("status")
    done = "installed"
    if status["rule_count"] and not reinstall:
        if f'@revision("{policy_set.revision}")' in server.control("get_policy")["source"]:
            return (
                f"kept policy revision {policy_set.revision} ({status['rule_count']} rules) "
                "and its history; --reinstall replaces it"
            )
        done = "replaced an outdated policy set with"
    applied = server.control("install", policy=policy_set.source, action_schema=ACTION_SCHEMA)
    return (
        f"{done} revision {policy_set.revision}: {applied['rule_count']} rules, "
        f"{applied['leaf_count']} temporal leaves, empty history"
    )


def load_policy_names(server: DogwoodServer) -> dict[str, str]:
    """Map the engine's opaque policy tokens back to their @id annotations."""
    names: dict[str, str] = {}
    for summary in server.control("list")["policies"]:
        source = server.control("get_policy_by_id", id=summary["id"])["source"]
        match = re.search(r'@id\("([^"]+)"\)', source)
        names[summary["id"]] = match.group(1) if match else summary["id"]
    return names


# ---------------------------------------------------------------------------
# Harness: every tool call becomes Dogwood events
# ---------------------------------------------------------------------------


@dataclass
class AuditEntry:
    recorded_at_nanos: int
    principal: str
    action: str
    kind: str
    fields: dict
    verdict: str  # ALLOW, DENY, recorded, failed
    detail: str = ""


def _clock(nanos: int) -> str:
    if not nanos:
        return "-"
    return datetime.fromtimestamp(nanos / 1e9).strftime("%H:%M:%S.%f")[:-3]


def _tool_output(result: dict) -> dict | None:
    """The tool's JSON result, logged as the `output` group of its response event."""
    for block in result.get("content", []):
        try:
            value = json.loads(block.get("text", ""))
        except (TypeError, ValueError):
            continue
        if isinstance(value, dict):
            return value
    return None


class DogwoodHarness(InterventionHandler):
    """Decides each tool call with the Dogwood Local Engine.

    The engine only judges what it is shown, so every call produces two events:
    the `request` (the decision point) and its outcome. The engine prunes its own
    log after snapshots, so the harness keeps the audit trail in `audit`.
    """

    name = "dogwood-local-engine"

    def __init__(self, server: DogwoodServer, principal: str, policy_set: PolicySet) -> None:
        self.server = server
        self.principal = principal
        self.policy_set = policy_set
        self.policy_names: dict[str, str] = {}  # engine token -> @id
        self.audit: list[AuditEntry] = []

    @property
    def on_error(self) -> OnError:
        return "deny"  # no verdict, no tool call

    def before_tool_call(self, event: BeforeToolCallEvent, **kwargs: Any) -> Proceed | Deny:
        action = event.tool_use["name"]
        tool_input = dict(event.tool_use.get("input") or {})
        try:
            decision = self.server.submit(
                self._event(action, "request", tool_input, event.tool_use["toolUseId"])
            )
        except DogwoodError as exc:
            self._log(AuditEntry(0, self.principal, action, "request", tool_input, "failed", str(exc)))
            return Deny(reason=f"the Dogwood engine is unavailable, so {action} was refused: {exc}")

        policies = ", ".join(self.policy_names.get(t, t) for t in decision.get("reason", []))
        errors = "; ".join(decision.get("errors", []))
        allowed = decision["allowed"]
        if allowed:
            detail = policies
        else:
            detail = f"forbidden by {policies}" if policies else "no permit applies (deny by default)"
        if errors:
            detail = f"{detail}; errors: {errors}" if detail else f"errors: {errors}"

        self._log(
            AuditEntry(
                decision["recorded_at_nanos"],
                self.principal,
                action,
                "request",
                tool_input,
                "ALLOW" if allowed else "DENY",
                detail,
            )
        )
        if allowed:
            return Proceed(reason=detail)
        reason = f"Dogwood policy denied {action}: {self._explain(action, decision.get('reason', []))}"
        if errors:
            reason += f" Evaluation errors: {errors}"
        return Deny(reason=reason)

    def _explain(self, action: str, tokens: list[str]) -> str:
        """A denial as the agent reads it: the rules involved, in natural language.

        The agent is not told the rules up front - it would refuse an obvious
        violation itself and the engine would never decide it - so this is where
        it learns the rule it has to explain.
        """
        rules = {p.id: p.rule for p in self.policy_set.policies}

        def quote(policy_id: str) -> str:
            return f'{policy_id} ("{rules[policy_id]}")' if policy_id in rules else policy_id

        if tokens:
            return "forbidden by " + "; ".join(quote(self.policy_names.get(t, t)) for t in tokens) + "."
        permits = [
            p.id for p in self.policy_set.policies if p.effect == "permit" and action in p.actions
        ]
        if not permits:
            return "no policy permits this action."
        return "no permit applies. It is only allowed under " + "; ".join(map(quote, permits)) + "."

    def after_tool_call(self, event: AfterToolCallEvent, **kwargs: Any) -> Proceed:
        action = event.tool_use["name"]
        tool_input = dict(event.tool_use.get("input") or {})
        # Denied and failed calls are history too. They go in as `error`, so a
        # condition on `response`, such as a granted approval, never sees them, and
        # the money limits stop counting their request.
        if event.cancel_message or event.exception or event.result.get("status") == "error":
            kind, output = "error", None
        else:
            kind, output = "response", _tool_output(event.result)

        try:
            ack = self.server.submit(
                self._event(action, kind, tool_input, event.tool_use["toolUseId"], output)
            )
        except DogwoodError as exc:
            # The tool already ran, and the history now has a gap. A lost ApproveSale
            # response fails closed, but a lost SellShares response would let the
            # same approval cover a second sale, and a lost Transfer error keeps a
            # refused amount in the budget: say so.
            self._log(AuditEntry(0, self.principal, action, kind, tool_input, "failed", str(exc)))
            return Proceed()

        fields = {"output": output} if output else {"input": tool_input}
        self._log(AuditEntry(ack["recorded_at_nanos"], self.principal, action, kind, fields, "recorded"))
        return Proceed()

    def _event(
        self, action: str, kind: str, tool_input: dict, call_id: str, output: dict | None = None
    ) -> dict:
        # The tool never sees callId; it only ties a request to its outcome.
        call_input = {**tool_input, "callId": call_id}
        logged: dict[str, Any] = {"input": call_input}
        if output is not None:
            logged["output"] = output
        event: dict[str, Any] = {
            "action": f"{NAMESPACE}::Action::{action}",
            "kind": kind,
            # The principal becomes the event's callerPrincipal, the pinned field.
            "principal": f'{NAMESPACE}::User::"{self.principal}"',
            "resource": RESOURCE,
            # What later events are matched against (`input.stock`, `output.approved`).
            "logged": logged,
        }
        # Only the decision point carries the request context (`context.input.*`).
        if kind == "request":
            event["context"] = {"input": call_input}
        return event

    def _log(self, entry: AuditEntry) -> None:
        self.audit.append(entry)
        show_event(entry)


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

PRICES = {"AMZN": 185, "AAPL": 230, "GOOGL": 170, "MSFT": 450, "NVDA": 140}

# The "thinking" spinner of the current turn. ApproveSale pauses it while it
# waits for the human: a live spinner redraws over the prompt.
spinner = console.status("[dim]thinking...[/]")


@contextmanager
def spinner_paused():
    spinner.stop()
    try:
        yield
    finally:
        spinner.start()


@tool
def GetStockInfo(stock: str) -> dict:
    """Get the current price of a stock, in whole US dollars (demo data)."""
    if stock not in PRICES:
        raise ValueError(f"unknown ticker {stock!r}; known tickers: {', '.join(PRICES)}")
    return {"stock": stock, "price": PRICES[stock]}


@tool
def ApproveSale(stock: str, shares: int) -> dict:
    """Ask the human operator to approve selling `shares` shares of `stock`.

    Returns {"approved": true|false}. SellShares needs an approval for exactly
    the same stock and number of shares, and each approval covers one sale.
    """
    with spinner_paused():
        approved = Confirm.ask(
            f"  [bold yellow]approval needed[/] sell [bold]{shares}[/] shares of "
            f"[bold]{escape(stock)}[/]?",
            default=False,
        )
    return {"stock": stock, "shares": shares, "approved": approved}


@tool
def SellShares(stock: str, shares: int) -> dict:
    """Sell shares of a stock. Requires a prior ApproveSale for the same stock and shares."""
    return {"stock": stock, "shares": shares, "proceeds": shares * PRICES.get(stock, 0)}


@tool
def Transfer(user: str, amount: int) -> dict:
    """Transfer `amount` whole US dollars to `user`."""
    return {"user": user, "amount": amount, "status": "sent"}


TOOLS = [GetStockInfo, ApproveSale, SellShares, Transfer]

# No rules here on purpose: an agent that knows them refuses obvious violations
# itself, so the engine never decides them. It learns a rule from the denial.
SYSTEM_PROMPT = (
    "You are the assistant of a stock trading desk. Answer in the language the user "
    "writes in, and keep answers short.\n\n"
    "Every tool call is decided by a Dogwood temporal policy engine that looks at what "
    "already happened in this session. You are not told its rules, so never decide "
    "yourself whether an action is allowed: when the user asks for one, make the call "
    "and let the engine decide. To sell, call ApproveSale with exactly the stock and "
    "number of shares you will sell, then SellShares with the same values, unless the "
    "user tells you to skip the approval. Use upper-case tickers (AMZN, not amzn) and "
    "whole numbers. Call tools one at a time. A denied call says which rule stopped it: "
    "explain that rule to the user and do not retry the same call."
)


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def show_event(entry: AuditEntry) -> None:
    fields = escape(json.dumps(entry.fields, ensure_ascii=False))
    detail = f"  [dim]· {escape(entry.detail)}[/]" if entry.detail else ""
    if entry.verdict in ("ALLOW", "DENY"):
        style = "green" if entry.verdict == "ALLOW" else "red"
        console.print(
            f"  [bold blue]dogwood[/] [bold {style}]{entry.verdict:<5}[/] "
            f"[bold]{entry.action}[/] [dim]{fields}[/]{detail}"
        )
    elif entry.verdict == "recorded":
        console.print(f"  [bold blue]dogwood[/] [dim]recorded {entry.action}::{entry.kind} {fields}[/]")
    else:
        console.print(f"  [bold blue]dogwood[/] [bold red]FAILED[/] {entry.action}::{entry.kind}{detail}")


def show_policies(server: DogwoodServer, policy_set: PolicySet) -> None:
    table = Table(title=f"Dogwood policies in {policy_set.directory}", show_lines=True)
    table.add_column("@id", style="bold", no_wrap=True)
    table.add_column("Effect", no_wrap=True)
    table.add_column("Rule (natural language)")
    for p in policy_set.policies:
        style = "green" if p.effect == "permit" else "red"
        table.add_row(p.id, f"[{style}]{p.effect}[/]", p.rule)
    console.print(table)
    source = "\n\n".join(p.source for p in policy_set.policies)
    console.print(Syntax(source, "cedar", theme="monokai", word_wrap=True))
    try:
        rules = server.control("status")["rule_count"]
        console.print(
            f"  [dim]revision {policy_set.revision}; {rules} rule(s) installed in {server.state_dir}[/]"
        )
    except DogwoodError:
        console.print("  [dim]control plane unreachable: cannot confirm what is installed[/]")


def show_history(harness: DogwoodHarness) -> None:
    if not harness.audit:
        console.print(Panel("No events submitted yet", border_style="yellow"))
        return
    table = Table(title="Events submitted to Dogwood (harness audit log)", show_lines=True)
    table.add_column("Time", no_wrap=True)
    table.add_column("User", style="cyan", no_wrap=True)
    table.add_column("Event", style="bold", no_wrap=True)
    table.add_column("Fields")
    table.add_column("Verdict", no_wrap=True)
    table.add_column("Determined by")
    styles = {"ALLOW": "green", "DENY": "red", "failed": "red", "recorded": "dim"}
    for e in harness.audit:
        table.add_row(
            _clock(e.recorded_at_nanos),
            e.principal,
            f"{e.action}::{e.kind}",
            escape(json.dumps(e.fields, ensure_ascii=False)),
            f"[{styles[e.verdict]}]{e.verdict}[/]",
            escape(e.detail),
        )
    console.print(table)


def show_status(server: DogwoodServer, harness: DogwoodHarness) -> None:
    lines = [f"[bold]state dir[/]   {server.state_dir}", f"[bold]principal[/]   {harness.principal}"]
    try:
        status = server.control("status")
        lines += [
            f"[bold]rules[/]       {status['rule_count']}",
            f"[bold]temporal[/]    {status['leaf_count']} leaves, "
            f"{status['incremental_leaves']} incremental",
            f"[bold]decisions[/]   on {', '.join(status['decision_kinds']) or '-'} events",
            f"[bold]partition[/]   {', '.join(status.get('partition_key', [])) or 'none (single instance)'}",
            f"[bold]events[/]      {status['log_offset']} appended to the log",
        ]
    except DogwoodError as exc:
        lines.append(f"[yellow]control plane unreachable: {escape(str(exc))}[/]")
    console.print(Panel("\n".join(lines), title="Dogwood Local Engine", border_style="blue"))


def show_help() -> None:
    console.print(
        Panel(
            "[bold]/policies[/]     the Dogwood policies and the rule each one encodes\n"
            "[bold]/history[/]      every event the harness submitted, with its verdict\n"
            "[bold]/status[/]       what the engine has installed and recorded\n"
            "[bold]/user <name>[/]  act as another principal (each has its own history)\n"
            "[bold]/reset[/]        clear every policy's history (asks first)\n"
            "[bold]/new[/]          start a new conversation; Dogwood history is kept\n"
            "[bold]/help[/]         this message\n"
            "[bold]/exit[/]         quit (Ctrl-D and Ctrl-C too)\n\n"
            "[dim]Try: sell 100 AMZN · transfer $2000 to bob, $2000 to carol, "
            "then $1500 to dave · send $10 to five different people[/]",
            title="Commands",
            border_style="cyan",
        )
    )


def reset_history(server: DogwoodServer) -> None:
    if not Confirm.ask("Clear the temporal history of [bold red]every[/] policy?", default=False):
        console.print("  [dim]kept[/]")
        return
    try:
        server.control("batch", verbs=[{"verb": "reset_all"}])
    except DogwoodError as exc:
        console.print(Panel(escape(str(exc)), title="Reset failed", border_style="red"))
        return
    console.print(Panel("Every policy starts again with an empty window", border_style="red"))


def setup_failed(server: DogwoodServer, exc: DogwoodError) -> None:
    console.print(
        Panel(
            f"Cannot reach dogwood-server at [bold]{server.data_socket}[/]\n"
            f"[dim]{escape(str(exc))}[/]\n\n"
            "Build and start it:\n\n"
            "  git clone https://github.com/dogwood-policy/dogwood-local-engine\n"
            "  cd dogwood-local-engine\n"
            "  cargo build --release -p dogwood-server\n"
            f"  ./target/release/dogwood-server --dir {server.state_dir} run",
            title="Setup failed",
            border_style="red",
        )
    )


# ---------------------------------------------------------------------------
# Chat loop
# ---------------------------------------------------------------------------


ANSI_ESCAPE = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")


def read_line(prompt: str) -> str:
    """input() with arrow keys and history, behind a Rich-styled prompt.

    console.input() prints its prompt and then calls input() with none, so
    readline does not know where the prompt ends and can redraw over it when it
    edits the line or recalls history. Here input() gets the prompt itself, with
    every escape sequence between \\001 and \\002 so readline (and editline)
    count it as zero columns wide.
    """
    if readline is None:
        return console.input(prompt)
    with console.capture() as capture:
        console.print(prompt, end="")
    line = input(ANSI_ESCAPE.sub(lambda m: f"\x01{m.group()}\x02", capture.get()))
    if line.strip():
        readline.add_history(line)
    return line


def chat_turn(agent: Agent, user_input: str) -> None:
    with spinner:
        response = agent(user_input)
    console.rule("[bold green]assistant[/]")
    console.print(Panel(Markdown(str(response)), border_style="green"))
    console.print()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dir", type=Path, default=DEFAULT_DIR, help="dogwood-server state directory")
    parser.add_argument(
        "--policies", type=Path, default=POLICY_DIR, help="directory of .dw files, one policy each"
    )
    parser.add_argument("--user", default=DEFAULT_USER, help="principal the agent acts for")
    parser.add_argument(
        "--reinstall", action="store_true", help="install the policies even if the store runs them"
    )
    args = parser.parse_args()
    if not PRINCIPAL_RE.fullmatch(args.user):
        parser.error("--user takes letters, digits, _ . - only")

    try:
        policy_set = load_policy_set(args.policies.expanduser())
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        console.print(Panel(escape(str(exc)), title="Cannot load the policies", border_style="red"))
        sys.exit(1)

    server = DogwoodServer(args.dir.expanduser())
    try:
        version = server.ping()
    except DogwoodError as exc:
        setup_failed(server, exc)
        sys.exit(1)

    harness = DogwoodHarness(server, args.user, policy_set)
    try:
        policy_note = ensure_policies(server, policy_set, args.reinstall)
        harness.policy_names = load_policy_names(server)
    except DogwoodUnreachable as exc:
        policy_note = f"[yellow]control plane unreachable ({escape(str(exc))}); using the installed set[/]"
    except DogwoodError as exc:
        # A rejected install leaves the previous set running - none at all on a new
        # store, where every call would then be denied without saying why.
        console.print(Panel(escape(str(exc)), title="Policy install rejected", border_style="red"))
        sys.exit(1)

    agent = Agent(
        tools=TOOLS,
        system_prompt=SYSTEM_PROMPT,
        interventions=[harness],
        # One tool at a time: a sale must not start before its approval is recorded.
        tool_executor=SequentialToolExecutor(),
        callback_handler=lambda **kwargs: None,  # Rich owns the output
    )

    console.print(
        Panel(
            "[bold]Strands + Dogwood Local Engine chat[/]\n"
            f"Trading desk for [bold cyan]{escape(args.user)}[/], every tool call decided by "
            f"dogwood-server {escape(version)}\n"
            f"[dim]{server.state_dir}: {policy_note}[/]\n"
            "[dim]/policies  /history  /status  /user  /reset  /new  /help  /exit[/]",
            title="Chat",
        )
    )
    console.print()

    if readline is not None:
        # read_line() adds chat lines itself, so the y/n answers to Confirm prompts
        # stay out of the up-arrow history.
        readline.set_auto_history(False)

    while True:
        try:
            user_input = read_line(f"[bold cyan]{escape(harness.principal)}[/] › ").strip()
        except (EOFError, KeyboardInterrupt):
            console.print()
            break

        command, _, argument = user_input.partition(" ")
        if not user_input:
            continue
        if command in ("/exit", "/quit"):
            break
        if command == "/help":
            show_help()
        elif command == "/policies":
            show_policies(server, policy_set)
        elif command == "/history":
            show_history(harness)
        elif command == "/status":
            show_status(server, harness)
        elif command == "/reset":
            reset_history(server)
        elif command == "/new":
            agent.messages.clear()
            console.print("  [dim]new conversation; the engine still remembers every event[/]")
        elif command == "/user":
            if not PRINCIPAL_RE.fullmatch(argument.strip()):
                console.print("  [yellow]usage: /user <name> (letters, digits, _ . -)[/]")
                continue
            harness.principal = argument.strip()
            agent.messages.clear()
            console.print(
                f"  [dim]now acting as {harness.principal}; the event schema pins every "
                "temporal condition to the principal, so this user has its own history[/]"
            )
        elif command.startswith("/"):
            console.print(f"  [yellow]unknown command {escape(command)!r} - try /help[/]")
        else:
            try:
                chat_turn(agent, user_input)
            except Exception as exc:  # keep the session alive on a single bad turn
                console.print(
                    Panel(f"{type(exc).__name__}: {escape(str(exc))}", title="Turn failed", border_style="red")
                )

    console.print("[dim]bye[/]")


if __name__ == "__main__":
    main()
