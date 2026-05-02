from strands import Agent
from strands.models.gemini import GeminiModel
from pydantic import BaseModel, Field
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

class Person(BaseModel):
    """A person's basic information"""
    name: str = Field(description="Full name")
    age: int = Field(description="Age in years", ge=0, le=150)
    email: str = Field(description="Email address")
    phone: Optional[str] = Field(description="Phone number", default=None)

class Task(BaseModel):
    """A task or todo item"""
    title: str = Field(description="Task title")
    description: str = Field(description="Detailed description")
    priority: str = Field(description="Priority level: low, medium, high")
    completed: bool = Field(description="Whether task is completed", default=False)


agent = Agent(model=model)
person_res = agent("Extract person: John Doe, 35, john@test.com", structured_output_model=Person)

print("Person name:", person_res.structured_output.name)
print("Person age:", person_res.structured_output.age)
print("Person email:", person_res.structured_output.email)
print("Person phone:", person_res.structured_output.phone)

task_res = agent("Create task: Review code, high priority, completed", structured_output_model=Task)

print("Task title:", task_res.structured_output.title)
print("Task description:", task_res.structured_output.description)
print("Task priority:", task_res.structured_output.priority)
print("Task completed:", task_res.structured_output.completed)