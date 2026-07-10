"""Strands Agent with Strands Shell via MCP + mem0 memory.

Uses Claude Sonnet on Amazon Bedrock as the model provider and
Strands Shell as the sandboxed execution environment via its MCP server.
The agent gets four tools: shell, read_file, write_file, list_dir.

Memory is provided by mem0 — the agent can store and retrieve user
preferences via curl calls to api.mem0.ai from within the sandbox.
"""

import os

from dotenv import load_dotenv
from mcp import stdio_client, StdioServerParameters
from strands import Agent
from strands.handlers import null_callback_handler
from strands.models import BedrockModel
from strands.tools.mcp import MCPClient

load_dotenv()


def main():
    mem0_key = os.environ["MEM0_API_KEY"]
    mem0_auth = f"Token {mem0_key}"

    model = BedrockModel(
        model_id="us.anthropic.claude-sonnet-4-6",
        region_name="us-east-1",
    )

    shell_mcp = MCPClient(lambda: stdio_client(
        StdioServerParameters(
            command="uvx",
            args=["strands-shell", "--mcp"],
        )
    ))

    agent = Agent(
        model=model,
        tools=[shell_mcp],
        callback_handler=null_callback_handler,
        system_prompt=(
            "You are a sandboxed coding assistant with persistent memory. "
            "You have access to a virtual shell environment through the shell, "
            "read_file, write_file, and list_dir tools.\n\n"
            "## Memory (mem0)\n"
            "You can store and retrieve information about users using the mem0 API "
            "via curl in the shell.\n\n"
            "To ADD a memory:\n"
            "1. Write your JSON payload to /tmp/payload.json\n"
            "2. Run: curl -X POST https://api.mem0.ai/v3/memories/add/ "
            "-H 'Content-Type: application/json' "
            f"-H 'Authorization: {mem0_auth}' "
            "-d \"$(cat /tmp/payload.json)\"\n\n"
            "Payload format: {\"messages\": [{\"role\": \"user\", \"content\": \"...\"}, "
            "{\"role\": \"assistant\", \"content\": \"...\"}], \"user_id\": \"USER_ID\"}\n\n"
            "To SEARCH memories:\n"
            "1. Write your JSON payload to /tmp/payload.json\n"
            "2. Run: curl -X POST https://api.mem0.ai/v3/memories/search/ "
            "-H 'Content-Type: application/json' "
            f"-H 'Authorization: {mem0_auth}' "
            "-d \"$(cat /tmp/payload.json)\"\n\n"
            "Payload format: {\"query\": \"...\", \"filters\": {\"OR\": [{\"user_id\": \"USER_ID\"}]}}\n\n"
            "Always search memory at the start of a conversation to recall user context. "
            "Store important user preferences and facts after learning them. "
            "Use 'default_user' as the user_id unless told otherwise."
        ),
    )

    print("Agent ready (with mem0 memory). Type your requests (Ctrl+C to exit).\n")

    while True:
        try:
            user_input = input("You: ")
            if not user_input.strip():
                continue
            response = agent(user_input)
            print(f"\nAgent: {response}\n")
        except KeyboardInterrupt:
            print("\nBye!")
            break


if __name__ == "__main__":
    main()
