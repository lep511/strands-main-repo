"""Interactive chat with long-term memory on self-hosted Mem0.

Importing `open_search_mem0` reuses that module's setup: the mem0 compatibility
patches, the environment validation, and the AOSS + Bedrock configuration. Only the
chat loop and the console rendering live here; console conventions follow the
sibling `cedar-auth` project (Console / Panel / Markdown / Table, green for the
answer, cyan for recall, red for failures).

Writes never block the prompt: every turn is handed to a single background worker
that stores it and waits for AOSS to index it. Results are rendered on the main
thread, just before the next prompt.

    uv run python chat_memory.py [user_id]

Commands: /memories, /forget, /help, /exit
"""

import queue
import sys
import threading

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Confirm
from rich.table import Table

from strands import Agent

from open_search_mem0 import (
    SCORE_THRESHOLD,
    build_memory,
    list_memories,
    wait_for_indexing,
)


console = Console()

DEFAULT_USER_ID = "alice"
TOP_K = 5

BASE_SYSTEM_PROMPT = (
    "You are a helpful assistant with long-term memory of this user. "
    "Answer in the language the user writes in, and keep answers short and concrete. "
    "Use the remembered facts when they are relevant, but never invent facts that are "
    "neither remembered nor in this conversation."
)

# Handed to m.add() as `prompt`, which mem0 renders as a "## Custom Instructions"
# section of its extraction prompt - documented there as the highest-priority rules -
# leaving untouched the system prompt that defines the JSON output format it parses.
#
# Without this, the assistant's own output becomes memory: a turn that recommended two
# novels stored "User was recommended 'The Martian'...", which then competes for the
# top-K on every later book question and crowds out the user's real preferences.
MEMORY_RULES = """
Store only durable facts about the user: their preferences, interests, constraints,
relationships, goals, and personal details they state about themselves.

Never store:
- recommendations, suggestions, explanations or opinions produced by the assistant
- the fact that the assistant answered, offered, or was asked something
- one-off requests, pleasantries, or anything meaningful only inside this exchange

When the user confirms or rejects something the assistant suggested, that IS a user
fact: store it as a statement about the user ("User has already read The Martian"),
never as a statement about the conversation.
"""


class MemoryWriter:
    """Serialized background writer for the chat's memories.

    Exactly one worker thread, deliberately: mem0 decides ADD vs UPDATE vs NONE by
    searching what is already stored, so two concurrent writes - or a write starting
    before the previous one is visible - would reintroduce the near-duplicates that
    the per-turn wait exists to prevent. Jobs therefore run strictly in order, each
    waiting for AOSS to index before the next one starts.
    """

    def __init__(self, memory, user_id: str) -> None:
        self._memory = memory
        self._user_id = user_id
        self._jobs: queue.Queue = queue.Queue()
        self._results: queue.Queue = queue.Queue()
        self._pending = 0
        self._lock = threading.Lock()
        self._worker = threading.Thread(target=self._run, daemon=True)
        self._worker.start()

    @property
    def pending(self) -> int:
        with self._lock:
            return self._pending

    def submit(self, user_input: str, answer: str) -> None:
        with self._lock:
            self._pending += 1
        self._jobs.put((user_input, answer))

    def drain(self) -> list[tuple[str, object]]:
        """Everything finished since the last call, for the main thread to render."""
        finished: list[tuple[str, object]] = []
        while True:
            try:
                finished.append(self._results.get_nowait())
            except queue.Empty:
                return finished

    def close(self, timeout: float = 180.0) -> bool:
        """Stop accepting work and let the queue finish. False if it timed out."""
        self._jobs.put(None)
        self._worker.join(timeout)
        return not self._worker.is_alive()

    def _run(self) -> None:
        while True:
            job = self._jobs.get()
            if job is None:  # sentinel from close(), never counted as pending
                return
            user_input, answer = job
            try:
                events = self._memory.add(
                    [
                        {"role": "user", "content": user_input},
                        {"role": "assistant", "content": answer},
                    ],
                    user_id=self._user_id,
                    prompt=MEMORY_RULES,
                ).get("results", [])
                new_ids = [e["id"] for e in events if e.get("event") == "ADD" and e.get("id")]
                indexed = (
                    wait_for_indexing(self._memory, self._user_id, new_ids, quiet=True)
                    if new_ids
                    else True
                )
                self._results.put(("ok", (events, indexed)))
            except Exception as exc:  # noqa: BLE001 - surfaced on the main thread
                self._results.put(("error", exc))
            finally:
                with self._lock:
                    self._pending -= 1


def build_system_prompt(memories: list[dict]) -> str:
    """Fold the recalled memories into the system prompt for this turn."""
    if not memories:
        return f"{BASE_SYSTEM_PROMPT}\n\nNothing is remembered about this user yet."
    facts = "\n".join(f"- {m['memory']}" for m in memories)
    return f"{BASE_SYSTEM_PROMPT}\n\nWhat you remember about this user:\n{facts}"


def show_recalled(memories: list[dict]) -> None:
    console.rule("[bold cyan]recalled[/]")
    if not memories:
        console.print("  [dim]no memory above the score threshold[/]")
        return
    for m in memories:
        console.print(f"  [cyan]{m['score']:.3f}[/]  {m['memory']}")


def render_writes(results: list[tuple[str, object]]) -> None:
    """Render background write results. Main thread only, between prompts."""
    for kind, payload in results:
        if kind == "error":
            console.print(
                Panel(
                    f"{type(payload).__name__}: {payload}",
                    title="Memory write failed",
                    border_style="red",
                )
            )
            continue

        events, indexed = payload  # type: ignore[misc]
        console.rule("[bold magenta]remembered[/]")
        if not events:
            console.print("  [dim]nothing durable to store from that turn[/]")
        for e in events:
            console.print(f"  [magenta]{e.get('event')}[/]  {e.get('memory')}")
        if not indexed:
            console.print("  [yellow]indexing timed out; recall may lag a turn[/]")
        console.print()


def show_memories(memory, user_id: str, pending: int) -> None:
    rows = sorted(
        list_memories(memory, user_id),
        key=lambda m: m.get("created_at") or "",
        reverse=True,
    )
    if not rows:
        console.print(
            Panel(f"Nothing stored yet for [bold]{user_id}[/]", border_style="yellow")
        )
    else:
        table = Table(title=f"Memories for {user_id}", show_lines=True)
        table.add_column("#", style="bold", no_wrap=True)
        table.add_column("Memory", style="cyan")
        table.add_column("Stored", style="magenta", no_wrap=True)
        for i, row in enumerate(rows, 1):
            table.add_row(str(i), row["memory"], (row.get("created_at") or "")[:19])
        console.print(table)

    if pending:
        console.print(f"  [dim]{pending} turn(s) still being written in the background[/]")


def forget_all(memory, user_id: str) -> None:
    count = len(list_memories(memory, user_id))
    if not count:
        console.print(Panel(f"Nothing to forget for [bold]{user_id}[/]", border_style="yellow"))
        return
    if not Confirm.ask(f"Delete all [bold red]{count}[/] memories for {user_id}?", default=False):
        console.print("  [dim]kept[/]")
        return
    memory.delete_all(user_id=user_id)
    console.print(Panel(f"Deleted {count} memories for [bold]{user_id}[/]", border_style="red"))


def show_help() -> None:
    console.print(
        Panel(
            "[bold]/memories[/]  list everything stored for this user\n"
            "[bold]/forget[/]    delete every memory for this user (asks first)\n"
            "[bold]/help[/]      this message\n"
            "[bold]/exit[/]      quit, flushing pending writes (Ctrl-D and Ctrl-C too)",
            title="Commands",
            border_style="cyan",
        )
    )


def chat_turn(memory, agent: Agent, writer: MemoryWriter, user_id: str, user_input: str) -> None:
    """One turn: recall, answer, hand the write to the background worker."""
    recalled = memory.search(
        user_input, filters={"user_id": user_id}, top_k=TOP_K, threshold=SCORE_THRESHOLD
    ).get("results", [])
    show_recalled(recalled)

    # The agent keeps its own message history, so swapping the system prompt each turn
    # refreshes the recalled facts without losing the in-session thread.
    agent.system_prompt = build_system_prompt(recalled)
    with console.status("[dim]thinking...[/]"):
        response = agent(user_input)

    console.rule("[bold green]assistant[/]")
    console.print(Panel(Markdown(str(response)), border_style="green"))
    console.print()

    writer.submit(user_input, str(response))


def flush(writer: MemoryWriter) -> None:
    """Drain the queue on the way out so the last turns are not lost."""
    outstanding = writer.pending
    if outstanding:
        with console.status(f"[dim]saving {outstanding} turn(s) before exit...[/]"):
            finished = writer.close()
    else:
        finished = writer.close(timeout=10)
    render_writes(writer.drain())
    if not finished:
        console.print("  [yellow]gave up waiting; the last turns may not be stored[/]")


def main() -> None:
    user_id = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_USER_ID

    try:
        memory = build_memory()
    except SystemExit as exc:
        console.print(Panel(str(exc), title="Setup failed", border_style="red"))
        raise

    agent = Agent(
        system_prompt=BASE_SYSTEM_PROMPT,
        callback_handler=lambda **kwargs: None,  # Rich owns the output
    )
    writer = MemoryWriter(memory, user_id)

    console.print(
        Panel(
            "[bold]Mem0 + Strands chat[/]\n"
            f"Long-term memory in OpenSearch Serverless for [bold cyan]{user_id}[/]\n"
            "[dim]/memories  /forget  /help  /exit[/]",
            title="Chat",
        )
    )
    console.print()

    try:
        while True:
            render_writes(writer.drain())

            pending = writer.pending
            label = (
                f"[bold cyan]you[/] [dim]({pending} saving)[/] › "
                if pending
                else "[bold cyan]you[/] › "
            )
            try:
                user_input = console.input(label).strip()
            except (EOFError, KeyboardInterrupt):
                console.print()
                return

            if not user_input:
                continue
            if user_input in ("/exit", "/quit"):
                return
            if user_input == "/help":
                show_help()
                continue
            if user_input == "/memories":
                show_memories(memory, user_id, writer.pending)
                continue
            if user_input == "/forget":
                forget_all(memory, user_id)
                continue
            if user_input.startswith("/"):
                console.print(f"  [yellow]unknown command {user_input!r} - try /help[/]")
                continue

            try:
                chat_turn(memory, agent, writer, user_id, user_input)
            except Exception as exc:  # keep the session alive on a single bad turn
                console.print(
                    Panel(f"{type(exc).__name__}: {exc}", title="Turn failed", border_style="red")
                )
    finally:
        flush(writer)
        console.print("[dim]bye[/]")


if __name__ == "__main__":
    main()
