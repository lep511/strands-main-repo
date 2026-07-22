from strands import Agent, tool
from strands.vended_interventions.cedar import (
    CedarAuthorization,
)

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
        "environment": ctx["invocation_state"].get(
            "environment", "unknown"
        ),
    },
)

agent = Agent(
    tools=[deploy],
    interventions=[cedar],
)

def main():
    print("\nWorks in staging...")
    agent(
        "Deploy the service version 2.1",
        invocation_state={"environment": "staging"},
    )

    print("\n\nDenied in production...")
    agent(
        "Deploy the service version 2.4",
        invocation_state={"environment": "production"},
    )
    print("\n\n")

if __name__ == "__main__":
    main()
