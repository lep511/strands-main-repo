from strands import Agent, tool
from strands_tools import calculator
from tools.rich_markdown_handler import RichMarkdownHandler
import requests

handler = RichMarkdownHandler()

@tool
def weather_forecast(city: str) -> str:
    """Gets the current weather for a city using wttr.in API.
        Args:
            city: Name of the city
    """
    url = f"https://wttr.in/{city}?format=j1"
    response = requests.get(url)
    data = response.json()

    current = data["current_condition"][0]
    temp_c = current["temp_C"]
    description = current["lang_es"][0]["value"] if "lang_es" in current else current["weatherDesc"][0]["value"]
    humidity = current["humidity"]

    return f"City: {city}, Weather: {description}, Temperature: {temp_c}°C, Humidity: {humidity}%"

agent = Agent(
    model="us.anthropic.claude-sonnet-4-6",
    tools=[weather_forecast, calculator],
    callback_handler=handler,
    )

if __name__ == "__main__":
    user_input = "How's the weather in Montevideo?"

    with handler.live:
        response = agent(user_input)
