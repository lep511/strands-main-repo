import os

from strands import Agent, tool
from strands.vended_tools import file_editor


@tool
def letter_counter(word: str, letter: str) -> int:
    """
    Count occurrences of a specific letter in a word.

    Args:
        word (str): The input word to search in
        letter (str): The specific letter to count

    Returns:
        int: The number of occurrences of the letter in the word
    """
    if len(letter) != 1:
        raise ValueError("The 'letter' parameter must be a single character")
    return word.lower().count(letter.lower())


# file_editor only accepts absolute paths, so tell the agent where "answer.txt" is.
agent = Agent(
    tools=[letter_counter, file_editor],
    system_prompt=f"The working directory is {os.getcwd()}. Resolve relative filenames against it.",
)
agent('How many letter R\'s are in the word "strawberry"? Write the answer to answer.txt.')
