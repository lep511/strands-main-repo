"""Prototype tools for the Day 1 agent.

Both tools are deterministic stand-ins (no network calls), matching the
"May not: act on external systems" line of DESIGN_SPEC.md and keeping the
evals reproducible.
"""

from datetime import datetime
from zoneinfo import ZoneInfo

from strands import tool

# city (lowercase) -> (IANA timezone, canned weather report)
CITIES: dict[str, tuple[str, str]] = {
    "san francisco": ("America/Los_Angeles", "Foggy, 16°C (61°F), wind 20 km/h from the west."),
    "new york": ("America/New_York", "Partly cloudy, 18°C (64°F), light breeze."),
    "london": ("Europe/London", "Light rain, 12°C (54°F), humidity 85%."),
    "madrid": ("Europe/Madrid", "Sunny, 24°C (75°F), clear skies."),
    "tokyo": ("Asia/Tokyo", "Clear, 20°C (68°F), humidity 55%."),
    "buenos aires": ("America/Argentina/Buenos_Aires", "Windy, 15°C (59°F), scattered clouds."),
}


def _lookup(city: str) -> tuple[str, str] | None:
    return CITIES.get(city.strip().lower())


@tool
def get_weather(city: str) -> dict:
    """Get the current weather report for a city.

    Args:
        city: Name of the city, e.g. "San Francisco".
    """
    entry = _lookup(city)
    if entry is None:
        return {"status": "error", "content": [{"text": f"Weather for '{city}' is not available."}]}
    return {"status": "success", "content": [{"text": f"Weather in {city}: {entry[1]}"}]}


@tool
def get_current_time(city: str) -> dict:
    """Get the current local time in a city.

    Args:
        city: Name of the city, e.g. "Tokyo".
    """
    entry = _lookup(city)
    if entry is None:
        return {"status": "error", "content": [{"text": f"Timezone for '{city}' is not available."}]}
    now = datetime.now(ZoneInfo(entry[0]))
    return {
        "status": "success",
        "content": [{"text": f"The current time in {city} is {now.strftime('%Y-%m-%d %H:%M:%S %Z%z')}"}],
    }
