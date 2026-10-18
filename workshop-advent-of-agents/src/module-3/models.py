"""Bedrock model factory shared by the three agents."""

import os

from dotenv import load_dotenv
from strands.models import BedrockModel

load_dotenv()

MODEL_ID = os.getenv("MODEL_ID", "us.anthropic.claude-sonnet-4-6")
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")


def build_model(guardrail: bool = False) -> BedrockModel:
    """Optionally attach a real Amazon Bedrock guardrail (GUARDRAIL_ID / GUARDRAIL_VERSION)."""
    config = {"model_id": MODEL_ID, "region_name": AWS_REGION}
    if guardrail and (guardrail_id := os.getenv("GUARDRAIL_ID")):
        config |= {
            "guardrail_id": guardrail_id,
            "guardrail_version": os.getenv("GUARDRAIL_VERSION", "DRAFT"),
            "guardrail_redact_input": True,
            "guardrail_redact_output": True,
        }
    return BedrockModel(**config)
