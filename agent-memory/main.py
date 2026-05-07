import os
import sys
import logging
from typing import Any, Dict, List
from strands import Agent
from strands.models.gemini import GeminiModel
from strands_tools import use_agent
from mem0 import MemoryClient
from dotenv import load_dotenv
import os

load_dotenv()

# ── Constante global ───────────────────────────────────────────────────────────
USER_ID = "mem0_user"
MEMO_API_KEY = os.getenv("MEM0_API_KEY")

# ── Logger ─────────────────────────────────────────────────────────────────────
def setup_logger(name: str = __name__) -> logging.Logger:
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    logger = logging.getLogger(name)
    logger.setLevel(log_level)

    if logger.handlers:
        return logger

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    log_file = os.getenv("LOG_FILE")
    if log_file:
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger

logger = setup_logger("memory_agent")

model = GeminiModel(
    client_args={"api_key": os.getenv("GEMINI_API_KEY")},
    model_id="gemini-3.1-flash-lite-preview",
    params={
        "temperature": 1
    }
)

# ── Prompts ────────────────────────────────────────────────────────────────────
MEMORY_SYSTEM_PROMPT = f"""You are a personal assistant that maintains context by remembering user details.
Always use user_id={USER_ID} when referencing memories.
Be conversational, concise, and only share relevant information."""

ANSWER_SYSTEM_PROMPT = """You are an assistant that creates helpful responses based on retrieved memories.
Use the provided memories to answer naturally and directly.
If no relevant memories exist, say so honestly."""


# ── MemoryAssistant ────────────────────────────────────────────────────────────
class MemoryAssistant:
    def __init__(self):
        self.mem0 = MemoryClient(api_key=MEMO_API_KEY)
        self.agent = Agent(
            model=model,
            system_prompt=MEMORY_SYSTEM_PROMPT,
            tools=[use_agent],
        )
        logger.info("MemoryAssistant inicializado para user_id='%s'", USER_ID)

    # ── Store ──────────────────────────────────────────────────────────────────
    def store_memory(self, content: str) -> Dict[str, Any]:
        logger.debug("Storing memory | user_id=%s | content='%s'", USER_ID, content[:80])
        messages = [{"role": "user", "content": content}]
        result = self.mem0.add(messages, user_id=USER_ID)
        logger.info("Memory queued | status=%s | event_id=%s",
                    result.get("status"), result.get("event_id"))
        return result

    # ── Retrieve ───────────────────────────────────────────────────────────────
    def retrieve_memories(self, query: str, min_score: float = 0.3, max_results: int = 5) -> List[Dict[str, Any]]:
        logger.debug("Retrieving memories | query='%s' | min_score=%s", query[:80], min_score)
        result = self.mem0.search(
            query,
            filters={"AND": [{"user_id": USER_ID}]},
            limit=max_results,
        )
        memories = result.get("results", []) if isinstance(result, dict) else result
        filtered = [m for m in memories if m.get("score", 1.0) >= min_score]
        logger.info("Memories retrieved | total=%d | after_filter=%d", len(memories), len(filtered))
        return filtered

    # ── List all ───────────────────────────────────────────────────────────────
    def list_all_memories(self) -> List[Dict[str, Any]]:
        logger.debug("Listing all memories | user_id=%s", USER_ID)
        result = self.mem0.get_all(filters={"AND": [{"user_id": USER_ID}]})
        memories = result.get("results", []) if isinstance(result, dict) else result
        logger.info("Memories listed | count=%d", len(memories))
        return memories

    # ── Generate answer ────────────────────────────────────────────────────────
    def generate_answer_from_memories(self, query: str, memories: List[Dict[str, Any]]) -> str:
        if not memories:
            logger.info("No relevant memories found for query='%s'", query[:80])
            return (
                "I don't have any relevant memories to answer that question. "
                "You can ask me to remember something first."
            )

        memories_str = "\n".join(f"- {m['memory']}" for m in memories)
        prompt = f"""
User ID: {USER_ID}
User question: "{query}"

Relevant memories:
{memories_str}

Answer directly and concisely using only the memories above.
"""
        logger.debug("Calling LLM | memories_used=%d", len(memories))
        response = self.agent.tool.use_agent(
            prompt=prompt,
            system_prompt=ANSWER_SYSTEM_PROMPT,
        )

        # Extraer solo el bloque "Response:" del contenido
        answer = ""
        for block in response.get("content", []):
            text = block.get("text", "")
            if text.startswith("Response:"):
                answer = text.removeprefix("Response:").strip()
                break

        if not answer:
            logger.warning("Could not extract answer from use_agent response")
            answer = "I was unable to generate a response."

        logger.debug("LLM response length=%d chars", len(answer))
        return answer

    # ── Main entry point ───────────────────────────────────────────────────────
    def process_input(self, user_input: str) -> str:
        logger.debug("Processing input | '%s'", user_input[:80])
        lower = user_input.lower()

        store_triggers = ("remember ", "note that ", "i want you to know ")
        if any(lower.startswith(t) for t in store_triggers):
            content = user_input.split(" ", 1)[1]
            self.store_memory(content)
            return "I've stored that information in my memory."

        list_keywords   = ("show", "list", "display", "what do you remember", "what do you know")
        memory_keywords = ("memory", "memories", "mem")
        if any(w in lower for w in list_keywords) and any(w in lower for w in memory_keywords):
            all_memories = self.list_all_memories()
            if not all_memories:
                return "You don't have any memories stored yet."
            lines = [f"{i + 1}. {m['memory']}" for i, m in enumerate(all_memories)]
            return "Here's everything I remember:\n\n" + "\n".join(lines)

        relevant = self.retrieve_memories(user_input)
        return self.generate_answer_from_memories(user_input, relevant)

    # ── Demo helper ────────────────────────────────────────────────────────────
    def initialize_demo_memories(self) -> None:
        logger.info("Initializing demo memories")
        demo = (
            "My name is Alex. I like to travel and stay in Airbnbs rather than hotels. "
            "I am planning a trip to Japan next spring. "
            "I enjoy hiking and outdoor photography as hobbies. "
            "I have a dog named Max. My favorite cuisine is Italian food."
        )
        self.store_memory(demo)

# ── CLI ────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    assistant = MemoryAssistant()

    print("\n🧠 Memory Agent 🧠\n")
    assistant.initialize_demo_memories()
    print("Demo memories initialized!\n")

    user_input = "What are my travel preferences?"
    result = assistant.process_input(user_input)
    print(f"\n{result}\n")