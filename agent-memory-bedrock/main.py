"""Strands Agents - Memory with Amazon Bedrock Knowledge Bases.

Demonstrates long-term memory that persists across sessions using
BedrockKnowledgeBaseStore backed by a CUSTOM data source.
"""

import asyncio

from strands import Agent
from strands.memory import MemoryManager
from strands.memory.types import (
    MemoryAddToolConfig,
    MemoryInjectionConfig,
    MemoryToolConfig,
)
from strands.models import BedrockModel
from strands.vended_memory_stores import BedrockKnowledgeBaseStore


def memory_callback_handler(**kwargs):
    tool_use = kwargs.get("event", {}).get("contentBlockStart", {}).get("start", {}).get("toolUse")
    if tool_use and tool_use.get("name") == "add_memory":
        print("[save_memory]", flush=True)

KNOWLEDGE_BASE_ID = "PHXTT2FZSH"
DATA_SOURCE_ID = "RBVU63OEDY"


def create_agent() -> Agent:
    store = BedrockKnowledgeBaseStore(
        name="user-memory",
        description="User preferences, facts, and important information across sessions.",
        writable=True,
        scope="agent-memory",
        config={
            "knowledge_base_id": KNOWLEDGE_BASE_ID,
            "data_source_type": "CUSTOM",
            "data_source_id": DATA_SOURCE_ID,
        },
    )

    memory_manager = MemoryManager(
        stores=[store],
        search_tool_config=MemoryToolConfig(
            name="recall",
            description="Search what you know about the user's preferences and history.",
        ),
        add_tool_config=MemoryAddToolConfig(wait_for_writes=False),
        injection=MemoryInjectionConfig(
            trigger="userTurn",
            max_entries=5,
        ),
    )

    return Agent(
        model=BedrockModel(model_id="us.anthropic.claude-sonnet-4-20250514-v1:0"),
        system_prompt=(
            "You are a helpful assistant with long-term memory. "
            "You remember user preferences and past interactions across sessions. "
            "Use the recall tool to search your memory when relevant. "
            "ALWAYS use the add_memory tool to save important user preferences, "
            "names, dates, appointments, and facts for future reference. "
            "Do not rely on automatic extraction — explicitly save with add_memory."
        ),
        memory_manager=memory_manager,
        callback_handler=memory_callback_handler,
    )


def main():
    print("=" * 60)
    print("Strands Agent - Memory Demo (Bedrock Knowledge Base)")
    print("=" * 60)
    print("The agent remembers your preferences across sessions.")
    print("Try telling it your preferences, then restart and ask.")
    print("Type 'quit' to exit.\n")

    agent = create_agent()

    while True:
        try:
            user_input = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            break

        if not user_input:
            continue
        if user_input.lower() == "quit":
            print("Goodbye!")
            break

        response = agent(user_input)
        print(f"Agent: {str(response).strip()}\n")


if __name__ == "__main__":
    main()
