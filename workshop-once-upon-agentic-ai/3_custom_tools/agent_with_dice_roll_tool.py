from strands import Agent, tool
import logging

logging.basicConfig(level=logging.INFO)

@tool
def roll_dice(faces: int = 6) -> int:
    """Roll a dice with the specified number of faces.

    Args:
        faces: The number of faces on the dice. Defaults to 6.

    Returns:
        A random integer between 1 and the number of faces.
    """
    import random

    if faces < 1:
        raise ValueError("Dice must have at least 1 face")

    return random.randint(1, faces)


print(roll_dice.tool_spec)  # what Strands tells the model about your tool

dice_master = Agent(
    tools=[roll_dice],
    system_prompt="""You are Lady Luck, the mystical keeper of dice and fortune in fantasy role-playing adventures.
    You speak with theatrical flair and always announce dice rolls with appropriate drama.
    You know all about the game mechanics, ability scores, and can help players with character creation.
    When rolling ability scores, remember the traditional method: roll 4d6, drop the lowest die."""
)

dice_master("Help me create a new fantasy character! Roll the strength, wisdom, charisma and intelligence abilities scores using 4d6 drop lowest method.")

print("\n\n")

