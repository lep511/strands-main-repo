from strands import Agent
from strands.models import BedrockModel
from strands_tools import calculator
from tools.rich_markdown_handler import RichMarkdownHandler

handler = RichMarkdownHandler()

bedrock_model = BedrockModel(
    model_id="us.anthropic.claude-sonnet-4-6",
    additional_request_fields={
        "anthropic_beta": [ "interleaved-thinking-2025-05-14" ],
        "thinking": { "type": "enabled", "budget_tokens": 8000 },
    }
)

agent = Agent(
    model=bedrock_model,
    tools=[calculator],
    callback_handler=handler,
    )

if __name__ == "__main__":
    user_input = "What is Amazon Bedrock?"

    with handler.live:
        response = agent(user_input)
