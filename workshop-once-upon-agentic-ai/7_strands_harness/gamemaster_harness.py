import sys
import uvicorn
import os
import httpx
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from tinydb import TinyDB, Query
from typing import List
from strands.vended_tools import make_a2a_client
from strands_harness import create_harness

UPSTREAM_SERVERS = {
    "Rules Agent":     "http://127.0.0.1:8000",
    "Character Agent": "http://127.0.0.1:8001",
    "Dice MCP Server": "http://127.0.0.1:8002",
}


def check_upstream_servers() -> list[str]:
    """Return names of servers that are not reachable."""
    down = []
    for name, url in UPSTREAM_SERVERS.items():
        try:
            httpx.get(url, timeout=2)
        except (httpx.ConnectError, httpx.TimeoutException):
            down.append(name)
    return down


down = check_upstream_servers()
if down:
    print("\n*** The following upstream servers are not reachable: ***\n")
    for name in down:
        print(f"  - {name} ({UPSTREAM_SERVERS[name]})")
    print("\nStart them before running the harness:")
    print("  uv run python 5_a2a_integration/agents/rules_agent/rules_agent.py        # port 8000")
    print("  uv run python 5_a2a_integration/agents/character_agent/character_agent.py # port 8001")
    print("  uv run python 4_mcp_integration/dice_roll_mcp_server.py                  # port 8002")
    print()
    sys.exit(1)

app = FastAPI(title="Game Master API (Strands harness)")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class QuestionRequest(BaseModel):
    question: str

class DiceOutput(BaseModel):
    dice_type: str = Field(description="The dice type. Ex: d4, d6, d20, etc")
    result: int = Field(description="The dice result value alone")
    reason: str = Field(description="The reason the dice was rolled. Ex: attack roll. And the modificators if there was any")

class StoryOutput(BaseModel):
    """A single Game Master turn: the narration, what the player could do next, and any dice rolled."""
    response: str = Field(description="Your narative response as Game Master")
    actions_suggestions: list[str] = Field(description="['Action 1', 'Action 2', 'Action 3']")
    details: str = Field(description="Brief summary of tools/agents used")
    dice_rolls: List[DiceOutput] = Field(default=[], description="List of dice rolls with dice_type, result, and reason")

# Domain instructions only: Strands harness prepends its own behavioral contract.
INSTRUCTIONS = """You are a Game Master for a fantasy role-playing game. Never make up what a tool can tell you.
- roll_dice (dice MCP server) rolls the dice.
- a2a_client talks to the Rules Agent (http://127.0.0.1:8000) and the Character Agent (http://127.0.0.1:8001).
Only use those endpoints. Keep each turn short: a few sentences of narration, then the options."""

# Same A2A client tool as in Chapter 5: the Rules Agent and the Character Agent are still just tools.
a2a_client = make_a2a_client(allowed_endpoints=[
    "http://127.0.0.1:8000",  # Rules Agent
    "http://127.0.0.1:8001",  # Character Agent
])

agent = create_harness(
    model="bedrock/global.anthropic.claude-sonnet-4-6",
    instructions=INSTRUCTIONS,
    mcp_servers={"dice": {"url": "http://127.0.0.1:8002/mcp"}},
    tools=[a2a_client],
    builtin_tools=[],
    session={"id": "fantasy-campaign"},
    structured_output_model=StoryOutput,
)

@app.get("/health")
def health_check():
    return {"status": "healthy"}

@app.get("/messages")
def get_messages():
    return agent.messages

@app.get("/user/{user_name}")
def get_user(user_name):
    characters_db = TinyDB(os.path.join(os.path.dirname(os.path.abspath(__file__)), "../5_a2a_integration/agents", "character_agent", "characters.json"))
    Character_Query = Query()
    result = characters_db.search(Character_Query.name == user_name)
    if not result:
        return f":x: Character with name '{user_name}' not found"
    
    character = result[0]
    print(f"✅ Found character: {character['name']} (ID: {character['character_id']}, {character['character_class']} {character['race']})")
    return character


@app.post("/inquire")
async def ask_agent(request: QuestionRequest):
    print("Processing request...")
    try:
        response = await agent.invoke_async(request.question)
        print(response.structured_output)
        return JSONResponse(content={"response": response.structured_output.model_dump()})
    except Exception as e:
        print(f"Error occurred: {str(e)}")
        return JSONResponse(content={"error": "Internal server error"}, status_code=500)

if __name__ == "__main__":
    uvicorn.run(app, port=8009)
