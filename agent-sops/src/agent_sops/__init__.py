import os
import subprocess
from typing import Any

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.text import Text
from rich.theme import Theme
from strands import Agent
from strands.tools import tool
from strands_agents_sops import code_task_generator

custom_theme = Theme({
    "info": "cyan",
    "warning": "yellow",
    "error": "bold red",
    "success": "bold green",
    "tool": "magenta",
    "thinking": "dim italic",
})

console = Console(theme=custom_theme)


class RichCallbackHandler:
    """Callback handler that buffers streamed text and renders as Rich markdown."""

    def __init__(self) -> None:
        self._buffer = ""
        self._tool_count = 0
        self._reasoning_buffer = ""

    def __call__(self, **kwargs: Any) -> None:
        reasoning_text = kwargs.get("reasoningText", "")
        data = kwargs.get("data", "")
        tool_use = (
            kwargs.get("event", {})
            .get("contentBlockStart", {})
            .get("start", {})
            .get("toolUse")
        )

        if reasoning_text:
            self._reasoning_buffer += reasoning_text

        if tool_use:
            self._flush_buffer()
            self._flush_reasoning()
            self._tool_count += 1
            tool_name = tool_use["name"]
            console.print(
                f"  [tool]⚙ Tool #{self._tool_count}:[/tool] {tool_name}",
            )

        if data:
            self._buffer += data

        if "message" in kwargs or "result" in kwargs:
            self._flush_buffer()

    def _flush_buffer(self) -> None:
        if self._buffer:
            self._flush_reasoning()
            console.print()
            md = Markdown(self._buffer)
            console.print(md)
            console.print()
            self._buffer = ""

    def _flush_reasoning(self) -> None:
        if self._reasoning_buffer:
            console.print(
                Panel(
                    Text(self._reasoning_buffer.strip(), style="thinking"),
                    title="[thinking]Thinking[/thinking]",
                    border_style="dim",
                    expand=False,
                )
            )
            self._reasoning_buffer = ""


@tool
def read_file(file_path: str) -> str:
    """Read the contents of a file.

    Parameters:
        file_path: The path to the file to read.
    """
    path = os.path.expanduser(file_path)
    if not os.path.isfile(path):
        return f"Error: File not found: {path}"
    with open(path) as f:
        return f.read()


@tool
def write_file(file_path: str, content: str) -> str:
    """Write content to a file, creating directories if needed.

    Parameters:
        file_path: The path to the file to write.
        content: The content to write to the file.
    """
    path = os.path.expanduser(file_path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(content)
    return f"Successfully wrote {len(content)} characters to {path}"


@tool
def list_directory(directory_path: str) -> str:
    """List files and directories at the given path.

    Parameters:
        directory_path: The directory path to list.
    """
    path = os.path.expanduser(directory_path)
    if not os.path.isdir(path):
        return f"Error: Directory not found: {path}"
    entries = sorted(os.listdir(path))
    result = []
    for entry in entries:
        full = os.path.join(path, entry)
        prefix = "[DIR] " if os.path.isdir(full) else "[FILE]"
        result.append(f"{prefix} {entry}")
    return "\n".join(result) if result else "(empty directory)"


@tool
def run_command(command: str) -> str:
    """Run a shell command and return the output.

    Parameters:
        command: The shell command to execute.
    """
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=30,
            cwd=os.getcwd(),
        )
        output = ""
        if result.stdout:
            output += result.stdout
        if result.stderr:
            output += f"\n[STDERR]\n{result.stderr}"
        if result.returncode != 0:
            output += f"\n[EXIT CODE: {result.returncode}]"
        return output.strip() or "(no output)"
    except subprocess.TimeoutExpired:
        return "Error: Command timed out after 30 seconds"
    except Exception as e:
        return f"Error: {e}"


def main() -> None:
    console.print(
        Panel(
            "[bold]Agent SOP CLI[/bold]\n"
            "Code Task Generator powered by Strands Agents",
            title="[success]● Online[/success]",
            border_style="green",
            expand=False,
        )
    )
    console.print(
        "[info]Type your request to generate code tasks.[/info]\n"
        "[info]Type[/info] [bold]quit[/bold] [info]or[/info] [bold]exit[/bold] [info]to leave.[/info]\n"
    )

    agent = Agent(
        system_prompt=code_task_generator,
        tools=[read_file, write_file, list_directory, run_command],
        callback_handler=RichCallbackHandler(),
    )

    while True:
        try:
            user_input = console.input("[bold green]You >[/bold green] ")
        except (KeyboardInterrupt, EOFError):
            console.print("\n[warning]Goodbye![/warning]")
            break

        if user_input.strip().lower() in ("quit", "exit", "q"):
            console.print("[warning]Goodbye![/warning]")
            break

        if not user_input.strip():
            continue

        console.print()
        try:
            agent(user_input)
        except Exception as e:
            console.print(f"[error]Error: {e}[/error]")
            console.print()
