from strands import Agent
from strands_tools import calculator, current_time, python_repl # Reference: https://github.com/strands-agents/tools
from strands.models import BedrockModel
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
    tools=[calculator, current_time, python_repl],
    system_prompt="Answer as if you are explaining to an elementary school student",
    callback_handler=handler,
)

with handler.live:
    response = agent("What is the square root of 80 / 4 * 5?") # prompt
