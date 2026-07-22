from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel

from strands import Agent, tool
from strands.vended_interventions.cedar import CedarAuthorization


console = Console()


@tool
def query_database(sql: str) -> str:
    """Execute a read-only SQL query against the database."""
    return f"Query executed: {sql}\nResults: [row1, row2, row3]"


@tool
def insert_record(table: str, data: str) -> str:
    """Insert a new record into a database table."""
    return f"Inserted into {table}: {data}"


@tool
def delete_record(table: str, record_id: str) -> str:
    """Delete a record from a database table."""
    return f"Deleted record {record_id} from {table}"


cedar = CedarAuthorization(
    policies="./policies/database_access.cedar",
    principal_resolver=lambda state: (
        {"type": "User", "id": state["user_id"]}
        if state.get("user_id")
        else None
    ),
    context_enricher=lambda ctx: {
        "role": ctx["invocation_state"].get("role", "none"),
    },
)

ALL_TOOLS = [query_database, insert_record, delete_record]


def run_scenario(title: str, style: str, prompt: str, invocation_state: dict):
    console.rule(f"[bold {style}]{title}[/]")
    agent = Agent(
        tools=ALL_TOOLS,
        interventions=[cedar],
        callback_handler=lambda **kwargs: None,
    )
    result = agent(prompt, invocation_state=invocation_state)
    console.print(Panel(Markdown(str(result)), border_style=style))
    console.print()


if __name__ == "__main__":
    console.print(Panel("[bold]Cedar Database Access Control[/]\nPolicy loaded from: policies/database_access.cedar", title="Demo"))
    console.print()

    run_scenario(
        title="Admin: full database access (query + insert + delete)",
        style="green",
        prompt="Query all users from the users table, then insert a new user 'Carlos' into the users table",
        invocation_state={"user_id": "alice", "role": "admin"},
    )

    run_scenario(
        title="Analyst: read-only access (query permitted, insert denied)",
        style="yellow",
        prompt="Query the sales table for Q4 results, then insert a correction record",
        invocation_state={"user_id": "bob", "role": "analyst"},
    )

    run_scenario(
        title="No identity: all access denied",
        style="red",
        prompt="Query the users table",
        invocation_state={},
    )
