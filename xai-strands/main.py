from strands import Agent, ModelRetryStrategy
from strands_tools.tavily import tavily_search
from strands_xai import xAIModel
from dotenv import load_dotenv
from pydantic import BaseModel, Field
from datetime import date
from enum import Enum
import os

load_dotenv()
XAI_API_KEY = os.getenv("XAI_API_KEY")

class Currency(str, Enum):
    USD = "USD"
    EUR = "EUR"
    GBP = "GBP"

class LineItem(BaseModel):
    description: str = Field(description="Description of the item or service")
    quantity: int = Field(description="Number of units", ge=1)
    unit_price: float = Field(description="Price per unit", ge=0)

class Address(BaseModel):
    street: str = Field(description="Street address")
    city: str = Field(description="City")
    postal_code: str = Field(description="Postal/ZIP code")
    country: str = Field(description="Country")

class Invoice(BaseModel):
    vendor_name: str = Field(description="Name of the vendor")
    vendor_address: Address = Field(description="Vendor's address")
    invoice_number: str = Field(description="Unique invoice identifier")
    invoice_date: date = Field(description="Date the invoice was issued")
    line_items: list[LineItem] = Field(description="List of purchased items/services")
    total_amount: float = Field(description="Total amount due", ge=0)
    currency: Currency = Field(description="Currency of the invoice")

class ProofInfo(BaseModel):
    name: str = Field(description="Name of the proof or paper")
    authors: str = Field(description="Authors of the proof")
    year: str = Field(description="Year published")
    summary: str = Field(description="Brief summary of the approach")

AGENT_SYSTEM_PROMPT = """Given a raw invoice, carefully analyze the text and extract the invoice data into JSON format.
Return ONLY a valid JSON object with these exact fields:
    - vendor_name: string
    - vendor_address: object with fields: street, city, postal_code, country
    - invoice_number: string
    - invoice_date: string (YYYY-MM-DD)
    - line_items: list of objects with fields: description, quantity, unit_price
    - total_amount: float
    - currency: one of USD, EUR, GBP

Return ONLY the JSON, no explanation, no markdown."""

def invoice_example(message: str):
    model = xAIModel(
        client_args={"api_key": XAI_API_KEY},
        # model_id="grok-4.3",
        model_id="grok-4-1-fast-non-reasoning-latest",
    )

    agent = Agent(
        model=model,
        system_prompt=AGENT_SYSTEM_PROMPT,
        retry_strategy=ModelRetryStrategy(
            max_attempts=3,
            initial_delay=2,
            max_delay=30,
        )
    )
    
    result = agent(message, structured_output_model=Invoice)

    invoice: Invoice = result.structured_output
    # print(invoice.model_dump_json(indent=2))
    return invoice

def search_web_example(message: str):
    model = xAIModel(
        client_args={"api_key": XAI_API_KEY},
        # model_id="grok-4.3",
        model_id="grok-4-1-fast-non-reasoning-latest",
    )

    agent = Agent(
        model=model,
        tools=[tavily_search],
    )

    result = agent(message, structured_output_model=ProofInfo)

    proof_info: ProofInfo = result.structured_output
    return proof_info

if __name__ == "__main__":
    prompt = """Vendor: Acme Corp, 123 Main St, Springfield, IL 62704
        Invoice Number: INV-2025-001
        Date: 2025-02-10
        Items: - Widget A, 5 units, $10.00 each - Widget B, 2 units, $15.00 each
        Total: $80.00 USD"""

    # invoice = invoice_example(prompt)
    # print(invoice.vendor_name)
    # print(invoice.invoice_date)
    # print(invoice.currency)

    proof_data = search_web_example("Find the latest machine-checked proof of the four color theorem.")
    print(f"Proof: {proof_data.name}")
    print(f"Authors: {proof_data.authors}")