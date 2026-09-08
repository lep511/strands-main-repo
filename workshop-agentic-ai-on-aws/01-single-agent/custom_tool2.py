from strands import Agent
from tools import python_repl_tool, bash_tool
from tools.rich_markdown_handler import RichMarkdownHandler

handler = RichMarkdownHandler()

agent = Agent(
    model="us.anthropic.claude-sonnet-4-6",
    tools=[bash_tool, python_repl_tool],
    callback_handler=handler,
    )

if __name__ == "__main__":
    # user_input = "Can you write and execute Python code that use Statistical Functions with Numpy?"

    ## Or, uncomment below to change the prompt and execute
    user_input = "Check what files are in the 01-single-agent/completed folder"

    with handler.live:
        response = agent(user_input)

