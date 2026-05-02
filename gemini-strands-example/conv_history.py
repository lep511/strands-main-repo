from strands import Agent
from strands.models.gemini import GeminiModel
from pydantic import BaseModel
from typing import Optional
from dotenv import load_dotenv
import os

load_dotenv()

model = GeminiModel(
    client_args={"api_key": os.getenv("GEMINI_API_KEY")},
    model_id="gemini-3.1-flash-lite-preview",
    params={
        "temperature": 1
    }
)

agent = Agent(model=model)

# Build up conversation context
agent("What do you know about Paris, France?")
agent("Tell me about the weather there in spring.")

class CityInfo(BaseModel):
    city: str
    country: str
    population: Optional[int] = None
    climate: str

# Extract structured information from the conversation
result = agent(
    "Extract structured information about Paris from our conversation",
    structured_output_model=CityInfo
)

print(f"City: {result.structured_output.city}")
print(f"Country: {result.structured_output.country}")
print(f"Population: {result.structured_output.population}")
print(f"Climate: {result.structured_output.climate}")

