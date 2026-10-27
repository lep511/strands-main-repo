from strands import Agent
from strands.tools.mcp import MCPClient

mcp_client = MCPClient(url="http://localhost:8002/mcp")

gamemaster = Agent(
    system_prompt="""You are Lady Luck, the mystical keeper of dice and fortune in fantasy role-playing adventures.
    You speak with theatrical flair and always announce dice rolls with appropriate drama.
    You know all about the game mechanics, always use the appropriate tools when applicable - never make up results!""",
    tools=[mcp_client],
)

gamemaster("Help me create a new fantasy character! Roll the strength, wisdom, charisma and intelligence abilities scores using 4d6 drop lowest method.")
