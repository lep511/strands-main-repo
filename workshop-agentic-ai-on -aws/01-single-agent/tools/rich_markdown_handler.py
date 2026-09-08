from rich.console import Console, Group
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel


class RichMarkdownHandler:
    """Callback handler that renders streaming text as Rich Markdown using Live display."""

    def __init__(self, console: Console | None = None, refresh_per_second: int = 8):
        self.console = console or Console()
        self.live = Live(console=self.console, refresh_per_second=refresh_per_second)
        self._reasoning_text = ""
        self._streamed_text = ""

    def _build_display(self):
        parts = []
        if self._reasoning_text:
            parts.append(Panel(Markdown(self._reasoning_text), title="Reasoning", border_style="dim"))
        if self._streamed_text:
            parts.append(Markdown(self._streamed_text))
        return Group(*parts) if parts else Markdown("")

    def __call__(self, **kwargs):
        reasoning = kwargs.get("reasoningText", "")
        data = kwargs.get("data", "")
        complete = kwargs.get("complete", False)
        tool_use = kwargs.get("event", {}).get("contentBlockStart", {}).get("start", {}).get("toolUse")

        if tool_use:
            self.console.print(f"\n[dim]🔧 Tool: {tool_use['name']}[/dim]")

        if reasoning:
            self._reasoning_text += reasoning
            self.live.update(self._build_display())

        if data:
            self._streamed_text += data
            self.live.update(self._build_display())

        if complete and data:
            self._reasoning_text = ""
            self._streamed_text = ""
