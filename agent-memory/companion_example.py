from strands import Agent
from strands.models.gemini import GeminiModel
from mem0 import MemoryClient
from dotenv import load_dotenv
import logging
import sys
import os

load_dotenv()

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

# ── Constante global ───────────────────────────────────────────────────────────
USER_ID = "mem0_user"
MEMO_API_KEY = os.getenv("MEM0_API_KEY")

mem0_client = MemoryClient(api_key=MEMO_API_KEY)

def chat(user_input, user_id):
    # Retrieve relevant memories
    memories = mem0_client.search(user_input, filters={"user_id": user_id}, top_k=5)
    context = "\\n".join(m["memory"] for m in memories["results"])

    system_prompt = f"You're Ray, a running coach. Memories:\\n{context}"
    agent = Agent(model=model, system_prompt=system_prompt)

    response = agent(user_input)

    # Store the exchange
    mem0_client.add([
        {"role": "user", "content": user_input},
        {"role": "assistant", "content": str(response)}
    ], user_id=user_id)

    return response

if __name__ == "__main__":
    # chat("Hello, I'm Alex. I want to get in shape.", USER_ID)
    print("\n================================\n\n" )
    chat("What did we discuss before?", USER_ID)
