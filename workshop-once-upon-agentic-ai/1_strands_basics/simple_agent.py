import logging

from strands import Agent

logging.basicConfig(level=logging.ERROR)

agent = Agent(system_prompt="You are a game master for a fantasy role-playing game")

agent("Hi, I am an adventurer ready for adventure!")
