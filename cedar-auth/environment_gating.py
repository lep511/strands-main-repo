from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel

from strands import Agent, tool
from strands.vended_interventions.cedar import CedarAuthorization


console = Console()


@tool
def deploy(version: str) -> str:
    """Deploy the service."""
    return f"Deployed {version} successfully."


cedar = CedarAuthorization(
    policies="""
      permit(
        principal,
        action == Action::"deploy",
        resource
      )
      when {
        context.session has environment &&
        context.session.environment != "production"
      };
    """,
    context_enricher=lambda ctx: {
        "environment": ctx["invocation_state"].get("environment", "unknown"),
    },
)


def run_scenario(title: str, style: str, prompt: str, invocation_state: dict):
    console.rule(f"[bold {style}]{title}[/]")
    agent = Agent(
        tools=[deploy],
        interventions=[cedar],
        callback_handler=lambda **kwargs: None,
    )
    result = agent(prompt, invocation_state=invocation_state)
    console.print(Panel(Markdown(str(result)), border_style=style))
    console.print()


if __name__ == "__main__":
    console.print(Panel("[bold]Cedar Environment Gating[/]\nBlock tools based on deployment context", title="Demo"))
    console.print()

    run_scenario(
        title="Staging: deploy permitted",
        style="green",
        prompt="Deploy the service version 2.1",
        invocation_state={"environment": "staging"},
    )

    run_scenario(
        title="Production: deploy denied",
        style="red",
        prompt="Deploy the service version 2.4",
        invocation_state={"environment": "production"},
    )
