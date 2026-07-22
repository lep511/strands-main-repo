from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel

from strands import Agent, tool
from strands.vended_interventions.cedar import CedarAuthorization


console = Console()


@tool
def send_email(to: str, body: str) -> str:
    """Send an email."""
    return f"Sent to {to}"


@tool
def search(query: str) -> str:
    """Search for information."""
    return f"Results for: {query}"


cedar = CedarAuthorization(
    policies="""
      permit(
        principal,
        action == Action::"send_email",
        resource
      )
      when { context.session.call_count < 5 };

      permit(
        principal,
        action == Action::"search",
        resource
      );
    """,
)


def run_scenario(title: str, style: str, prompt: str, agent: Agent):
    console.rule(f"[bold {style}]{title}[/]")
    result = agent(prompt)
    console.print(Panel(Markdown(str(result)), border_style=style))
    console.print()



if __name__ == "__main__":
    console.print(Panel("[bold]Cedar Rate Limiting[/]\nLimit tool calls using call_count in Cedar policies", title="Demo"))
    console.print()

    agent = Agent(
        tools=[send_email, search],
        interventions=[cedar],
        callback_handler=lambda **kwargs: None,
    )

    run_scenario(
        title="send_email permitted (calls 1-4)",
        style="green",
        prompt="Send 4 emails to test@example.com with body 'Hello'",
        agent=agent,
    )

    run_scenario(
        title="send_email denied on 5th call (rate limit)",
        style="red",
        prompt="Send another email to test@example.com with body 'This should be denied'",
        agent=agent,
    )

    run_scenario(
        title="search is always unlimited",
        style="cyan",
        prompt="Search for quarterly reports",
        agent=agent,
    )
