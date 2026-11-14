"""Interactive terminal client for an Amazon Bedrock AgentCore *harness*.

This is the AgentCore counterpart to ``../harness-strand-example/main.py``:
instead of running a Strands ``Agent`` locally, the agent is hosted in Bedrock
AgentCore and we talk to it through ``bedrock-agentcore:invoke_harness``. The
request/response streaming shape mirrors the Bedrock Converse stream, so we get
the same rich terminal experience — live Markdown streaming, a thinking
spinner, tool-use indicators, and arrow-key line editing via ``readline``.

**Client-side tool execution.** The harness has the ``get_weather`` tool
registered, so when the hosted agent decides to use it the stream stops with
``stopReason == "tool_use"`` and a tool-use request. This client runs the tool
locally (``weather.get_weather``), appends the result as a ``toolResult`` and
re-invokes the harness, looping until the agent produces its final answer.

Run it with::

    HARNESS_ARN=arn:aws:bedrock-agentcore:us-east-1:...:harness/... uv run main.py

If ``HARNESS_ARN`` is not set it falls back to the example ARN below. The
session id is generated automatically (AgentCore requires at least 33 chars)
and reused for the whole conversation so the hosted agent keeps context.
"""

import json
import os
import uuid
from typing import Self

import boto3

# Importing readline enables arrow-key navigation, line editing, and input
# history for the built-in input(). Without it, arrow keys emit raw escape
# sequences (e.g. ^[[D, ^[[A).
try:
    import readline
except ImportError:  # readline is unavailable on some platforms (e.g. Windows)
    readline = None

from botocore.exceptions import ClientError
from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.spinner import Spinner
from rich.table import Table
from rich.text import Text

# The tool the harness expects this client to execute locally.
from weather import get_weather

REGION = os.environ.get("AWS_REGION", "us-east-1")

# The AgentCore harness to invoke. Override with the HARNESS_ARN env var.
HARNESS_ARN = os.environ.get(
    "HARNESS_ARN",
    "arn:aws:bedrock-agentcore:us-east-1:919724646876:harness/harness_6poah-4cXwUpAdGr",
)

# Safety net so a misbehaving tool loop can't invoke the harness forever.
MAX_TOOL_ROUNDS = 8

# Client-side Bedrock Guardrail. The harness's own execution role can't call
# ApplyGuardrail in this workshop, so we enforce the guardrail here instead: the
# client's identity (which created the guardrail) screens the user INPUT before
# invoking the harness and the model OUTPUT after. Set GUARDRAIL_ID="" to disable.
GUARDRAIL_ID = os.environ.get("GUARDRAIL_ID", "62hxpxwipsyt")
GUARDRAIL_VERSION = os.environ.get("GUARDRAIL_VERSION", "DRAFT")

console = Console()


# ---------------------------------------------------------------------------
# Client-side guardrail enforcement (pre-screen input, post-screen output)
# ---------------------------------------------------------------------------

def screen_with_guardrail(text: str, source: str) -> tuple[bool, str | None]:
    """Run text through the guardrail. Returns (intervened, message_to_show).

    ``source`` is "INPUT" or "OUTPUT". When the guardrail intervenes, the second
    element is the block message to display instead of the original text. On any
    error (or when disabled) it fails open: (False, None).
    """
    if not GUARDRAIL_ID or not text.strip():
        return False, None
    try:
        client = boto3.client("bedrock-runtime", region_name=REGION)
        response = client.apply_guardrail(
            guardrailIdentifier=GUARDRAIL_ID,
            guardrailVersion=GUARDRAIL_VERSION,
            source=source,
            content=[{"text": {"text": text}}],
        )
    except ClientError as e:
        console.print(
            f"[dim yellow]⚠ guardrail {source} no aplicado: "
            f"{e.response['Error'].get('Code', 'Error')}[/dim yellow]"
        )
        return False, None

    if response.get("action") != "GUARDRAIL_INTERVENED":
        return False, None

    # The guardrail returns the configured block message in `outputs`.
    outputs = response.get("outputs") or []
    message = outputs[0].get("text") if outputs else None
    return True, message or "Contenido bloqueado por la política del guardrail."


# ---------------------------------------------------------------------------
# Client-side tools — name -> callable. The harness asks, we execute, we reply.
# ---------------------------------------------------------------------------


def _run_get_weather(tool_input: dict) -> tuple[list[dict], str]:
    """Execute get_weather and return (toolResult content, status).

    The harness only accepts ``text`` content blocks in a toolResult (it rejects
    ``json`` with ``runtimeClientError: content_type=<json_> unsupported type``),
    so the structured result is serialized to a JSON string.
    """
    result = get_weather(**tool_input)
    if isinstance(result, dict) and "error" in result:
        return [{"text": result["error"]}], "error"
    return [{"text": json.dumps(result, ensure_ascii=False)}], "success"


TOOLS = {"get_weather": _run_get_weather}


def read_user_input() -> str:
    """Read a line from the user with a colored prompt.

    When readline is available we call input() directly with the ANSI color
    codes wrapped in \\001/\\002 markers so readline excludes them from its
    cursor-width accounting. This keeps the "You>" prompt from being erased
    when the line wraps. If readline is missing, fall back to Rich's prompt.
    """
    if readline is not None:
        # \001 = RL_PROMPT_START_IGNORE, \002 = RL_PROMPT_END_IGNORE.
        prompt = "\001\033[1;34m\002You>\001\033[0m\002 "
        return input(prompt)
    return console.input("[bold blue]You>[/bold blue] ")


def new_session_id() -> str:
    """Generate a runtime session id.

    AgentCore requires ``runtimeSessionId`` to be at least 33 characters, so we
    prefix a uuid4 hex (32 chars) to comfortably clear the minimum.
    """
    return f"agentcore-{uuid.uuid4().hex}"


class RichStreamRenderer:
    """Renders AgentCore harness events into a Rich Live display as Markdown.

    Lives for a whole user turn (which may span several tool rounds). Each round
    is parsed by :meth:`start_round` / :meth:`handle` / :meth:`finish_round`,
    which also reconstructs the assistant message and any tool-use requests from
    the Converse-style streaming events.
    """

    def __init__(self):
        self.tool_count = 0
        self.stop_reason: str | None = None
        self.usage: dict | None = None
        self._buffer = ""
        # Per-round content blocks keyed by contentBlockIndex.
        self._blocks: dict[int, dict] = {}
        self._spinner = Spinner(
            "dots", text=Text(" Thinking…", style="cyan"), style="cyan"
        )
        # transient=True clears the live stream when stopped, so the final
        # answer is only shown once (in the "Agent Response" panel below).
        self._live = Live(
            console=console,
            refresh_per_second=12,
            vertical_overflow="visible",
            transient=True,
        )

    def __enter__(self) -> Self:
        self._buffer = ""
        self.tool_count = 0
        self.usage = None
        self._live.start()
        self._live.update(self._spinner)
        return self

    def __exit__(self, *exc) -> None:
        self._live.stop()

    @property
    def text(self) -> str:
        return self._buffer

    def _refresh(self) -> None:
        self._live.update(Markdown(self._buffer) if self._buffer else self._spinner)

    def note(self, markdown: str) -> None:
        """Append an out-of-band note (e.g. local tool execution) to the view."""
        self._buffer += markdown
        self._refresh()

    def start_round(self) -> None:
        self._blocks = {}
        self.stop_reason = None

    def handle(self, event: dict) -> None:
        """Process a single event from the ``response['stream']`` iterator."""
        # --- Streaming error exceptions ---------------------------------
        for exc_key in (
            "runtimeClientError",
            "internalServerException",
            "throttlingException",
            "validationException",
            "modelStreamErrorException",
            "serviceUnavailableException",
        ):
            if exc_key in event:
                msg = event[exc_key].get("message", "unknown error")
                self.note(f"\n\n> ⚠ **{exc_key}**: {msg}\n")
                return

        # --- Content block start (text or tool use) ---------------------
        if "contentBlockStart" in event:
            start = event["contentBlockStart"]
            idx = start.get("contentBlockIndex", 0)
            tool_use = start.get("start", {}).get("toolUse")
            if tool_use:
                self.tool_count += 1
                self._blocks[idx] = {
                    "type": "tool",
                    "toolUseId": tool_use.get("toolUseId"),
                    "name": tool_use.get("name"),
                    "input": "",
                }
                self.note(
                    f"\n\n`🔧 Tool #{self.tool_count}: {tool_use.get('name', '?')}`\n\n"
                )
            else:
                self._blocks.setdefault(idx, {"type": "text", "text": ""})
            return

        # --- Content deltas (text / reasoning / tool input) -------------
        if "contentBlockDelta" in event:
            cbd = event["contentBlockDelta"]
            idx = cbd.get("contentBlockIndex", 0)
            delta = cbd.get("delta", {})
            if "text" in delta:
                block = self._blocks.setdefault(idx, {"type": "text", "text": ""})
                block["text"] = block.get("text", "") + delta["text"]
                self._buffer += delta["text"]
                self._refresh()
            elif "reasoningContent" in delta and "text" in delta["reasoningContent"]:
                self._buffer += delta["reasoningContent"]["text"]
                self._refresh()
            elif "toolUse" in delta:
                block = self._blocks.setdefault(
                    idx, {"type": "tool", "toolUseId": None, "name": None, "input": ""}
                )
                block["input"] = block.get("input", "") + delta["toolUse"].get(
                    "input", ""
                )
            return

        # --- Message stop / metadata ------------------------------------
        if "messageStop" in event:
            self.stop_reason = event["messageStop"].get("stopReason")
            return
        if "metadata" in event:
            self.usage = event["metadata"].get("usage")
            return

    def finish_round(self) -> tuple[dict, list[dict]]:
        """Return (assistant_message, tool_use_requests) for the round."""
        content: list[dict] = []
        tool_uses: list[dict] = []
        for idx in sorted(self._blocks):
            block = self._blocks[idx]
            if block["type"] == "text":
                if block.get("text"):
                    content.append({"text": block["text"]})
            else:  # tool
                try:
                    args = json.loads(block["input"]) if block.get("input") else {}
                except json.JSONDecodeError:
                    args = {}
                tool_use = {
                    "toolUseId": block["toolUseId"],
                    "name": block["name"],
                    "input": args,
                }
                content.append({"toolUse": tool_use})
                tool_uses.append(tool_use)
        return {"role": "assistant", "content": content}, tool_uses


def _execute_tools(tool_uses: list[dict], renderer: RichStreamRenderer) -> dict:
    """Run each requested tool locally and build the user toolResult message."""
    results = []
    for tu in tool_uses:
        name, args, tuid = tu["name"], tu["input"], tu["toolUseId"]
        handler = TOOLS.get(name)
        pretty_args = ", ".join(f"{k}={v!r}" for k, v in args.items()) or "—"
        if handler is None:
            renderer.note(f"> ⚠ Tool `{name}` no está disponible en el cliente\n\n")
            results.append(
                {
                    "toolResult": {
                        "toolUseId": tuid,
                        "content": [
                            {"text": f"Tool '{name}' is not available on the client."}
                        ],
                        "status": "error",
                    }
                }
            )
            continue
        try:
            tool_content, status = handler(args)
        except Exception as e:  # noqa: BLE001 — surface tool errors back to the agent
            tool_content, status = [{"text": f"Tool error: {e}"}], "error"
        icon = "✅" if status == "success" else "⚠"
        renderer.note(f"> {icon} `{name}({pretty_args})` → `{status}`\n\n")
        results.append(
            {
                "toolResult": {
                    "toolUseId": tuid,
                    "content": tool_content,
                    "status": status,
                }
            }
        )
    return {"role": "user", "content": results}


def converse(session_id: str, prompt: str) -> RichStreamRenderer:
    """Drive the harness through any tool rounds until a final answer arrives."""
    client = boto3.client("bedrock-agentcore", region_name=REGION)
    messages: list[dict] = [{"role": "user", "content": [{"text": prompt}]}]

    renderer = RichStreamRenderer()
    with renderer:
        for _ in range(MAX_TOOL_ROUNDS):
            renderer.start_round()
            response = client.invoke_harness(
                harnessArn=HARNESS_ARN,
                runtimeSessionId=session_id,
                messages=messages,
            )
            for event in response["stream"]:
                renderer.handle(event)

            assistant_message, tool_uses = renderer.finish_round()
            messages.append(assistant_message)

            if renderer.stop_reason == "tool_use" and tool_uses:
                messages.append(_execute_tools(tool_uses, renderer))
                continue  # feed the tool results back to the harness
            break
        else:
            renderer.note(
                f"\n\n> ⚠ Alcanzado el máximo de {MAX_TOOL_ROUNDS} rondas de tools\n"
            )

    return renderer


def main() -> None:
    session_id = new_session_id()

    header = Table.grid(padding=(0, 1))
    header.add_column(justify="right", style="dim")
    header.add_column()
    header.add_row("Harness:", f"[cyan]{HARNESS_ARN}[/cyan]")
    header.add_row("Region:", f"[green]{REGION}[/green]")
    header.add_row("Session:", f"[magenta]{session_id}[/magenta]")
    header.add_row("Tools:", f"[yellow]{', '.join(TOOLS)}[/yellow]")
    header.add_row(
        "Guardrail:",
        f"[blue]{GUARDRAIL_ID} (v{GUARDRAIL_VERSION}) · client-side[/blue]"
        if GUARDRAIL_ID
        else "[dim]disabled[/dim]",
    )

    console.print(
        Panel(
            header,
            title="🤖 Bedrock AgentCore Harness",
            title_align="left",
            subtitle="[dim]Type a message and press Enter · 'exit' or 'quit' to leave[/dim]",
            border_style="cyan",
            padding=(1, 2),
        )
    )

    while True:
        try:
            console.print()
            prompt = read_user_input().strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]Goodbye![/dim]")
            break

        if not prompt:
            continue
        if prompt.lower() in ("exit", "quit"):
            console.print("[dim]Goodbye![/dim]")
            break

        # Pre-screen the user input; if the guardrail blocks it, never call the
        # harness — just show the block message.
        blocked, message = screen_with_guardrail(prompt, "INPUT")
        if blocked:
            console.print()
            console.print(
                Panel(
                    message,
                    title="🛡 Bloqueado por Guardrail (entrada)",
                    title_align="left",
                    border_style="bold red",
                    padding=(1, 2),
                )
            )
            continue

        try:
            renderer = converse(session_id, prompt)
        except ClientError as e:
            console.print(
                Panel(
                    f"{e.response['Error'].get('Code', 'Error')}: "
                    f"{e.response['Error'].get('Message', str(e))}",
                    title="⚠ Invocation Failed",
                    title_align="left",
                    border_style="bold red",
                    padding=(1, 2),
                )
            )
            continue
        except Exception as e:  # noqa: BLE001 — surface any client/stream error
            console.print(
                Panel(
                    str(e),
                    title="⚠ Unexpected Error",
                    title_align="left",
                    border_style="bold red",
                    padding=(1, 2),
                )
            )
            continue

        subtitle = None
        if renderer.usage:
            u = renderer.usage
            subtitle = (
                f"[dim]tokens in/out: {u.get('inputTokens', '?')}/"
                f"{u.get('outputTokens', '?')} · stop: "
                f"{renderer.stop_reason or '?'}[/dim]"
            )

        # Post-screen the model output; if the guardrail blocks it, show the
        # block message instead of the model's response.
        out_blocked, out_message = screen_with_guardrail(renderer.text, "OUTPUT")
        if out_blocked:
            console.print()
            console.print(
                Panel(
                    out_message,
                    title="🛡 Bloqueado por Guardrail (salida)",
                    title_align="left",
                    border_style="bold red",
                    padding=(1, 2),
                )
            )
            continue

        console.print()
        console.print(
            Panel(
                Markdown(renderer.text or "_(no content returned)_"),
                title="🤖 Agent Response",
                title_align="left",
                subtitle=subtitle,
                subtitle_align="right",
                border_style="green",
                padding=(1, 2),
            )
        )


if __name__ == "__main__":
    main()
