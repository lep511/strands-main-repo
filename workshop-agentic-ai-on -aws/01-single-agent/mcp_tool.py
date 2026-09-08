from mcp import stdio_client, StdioServerParameters
from strands import Agent
from strands.tools.mcp import MCPClient
from tools.rich_markdown_handler import RichMarkdownHandler

handler = RichMarkdownHandler()

aws_docs_mcptool = MCPClient(lambda: stdio_client(
    StdioServerParameters(command="uvx",
                          args=["awslabs.aws-documentation-mcp-server@latest"]
                          )
))
# Add below the existing AWS Documentation MCP
playwright_mcp_client = MCPClient(lambda: stdio_client(
    StdioServerParameters(command="npx",
                          args=["@playwright/mcp@latest"]
                          )
))


if __name__ == "__main__":
    user_input = "Visit https://aws.amazon.com and take a screenshot"

    agent = Agent(model="us.anthropic.claude-sonnet-4-6", tools=[aws_docs_mcptool, playwright_mcp_client], callback_handler=handler)
    with handler.live:
        response = agent(user_input)
