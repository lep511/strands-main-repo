import os
from lambda_agent import handler
from dotenv import load_dotenv
import os

load_dotenv()

# Simular el evento de Lambda
event = {
    "prompt": "What's the weather like in New York City? (lat: 40.7128, lon: -74.0060)"
}

result = handler(event, None)
print(result)