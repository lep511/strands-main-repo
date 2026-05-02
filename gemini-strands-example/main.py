from dotenv import load_dotenv
from strands import Agent, tool
from strands.models.gemini import GeminiModel
from strands_tools import calculator, current_time
from strands.types.exceptions import StructuredOutputException
from pydantic import BaseModel, Field, field_validator
from pydantic import ValidationError
import os

load_dotenv()

class PersonInfo(BaseModel):
    """Model that contains information about a Person"""
    name: str | None = Field(default=None, description="Full name of the person")
    age: int | None = Field(default=None, description="Age of the person")
    occupation: str | None = Field(default=None, description="Occupation of the person in Title Style")

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        if value:
            if not value.startswith(("Mr.", "Ms.")):
                raise ValueError("You must append 'Mr.' or 'Ms.' to the start of the name")
            return value

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
    if not isinstance(word, str) or not isinstance(letter, str):
        return 0

    if len(letter) != 1:
        raise ValueError("The 'letter' parameter must be a single character")

    return word.lower().count(letter.lower())

def main(question):
    print("Starting agent...")
    model = GeminiModel(
        client_args={"api_key": os.getenv("GEMINI_API_KEY")},
        model_id="gemini-3.1-flash-lite-preview",
        params={
            "temperature": 1
        }
    )

    weather_agent = Agent(
        system_prompt="You are a helpful agent.",   
        tools=[calculator, current_time, letter_counter],
        model=model,
    )

    response = weather_agent(question)
    # print(response)
    print("\n\n====================")
    print("Total tokens:", response.metrics.get_summary()["accumulated_usage"]["totalTokens"])

    agent = Agent(
        system_prompt="Retrieves the person's data; if any data is missing, it returns 'None'",  
        model=model
    )

    prompt = "Valeria Martinez is a 44 year-old software engineer"
    try:
        result = agent(prompt, structured_output_model=PersonInfo)
        person_info: PersonInfo = result.structured_output

        # Revalidate the result
        person_info = PersonInfo.model_validate(person_info.model_dump())

        print(f"Name: {person_info.name}")
        print(f"Age: {person_info.age}")
        print(f"Job: {person_info.occupation}")
    except ValidationError as e:
        print(f"Validation failed: {e}")
    except StructuredOutputException as e:
        print(f"Structured output failed: {e}")


if __name__ == "__main__":
    question = """
        I have 4 requests:

        1. What is the time right now (readable format)
        2. Calculate 3111696 / 74088
        3. Tell me how many letter R's are in the word "Bababadalgharaghtakamminarronnkonnbronntonnerronntuonnthunntrovarrhounawnskawntoohoohoordenenthurnuk"
    """
    main(question)