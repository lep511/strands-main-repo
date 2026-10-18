"""The Day 5 agent: weather/time tools plus read-only SQL over Athena.

This file is the AgentCore Runtime entry point (packaged by deploy.py). It never
receives credentials: boto3 picks up whatever identity it runs as. Locally that is
you; on AgentCore Runtime it is the agent's own execution role, nobody else's.

Run locally:
    uv run --group deploy src/module-5/agent/main.py
    curl -s -X POST localhost:8080/invocations -H 'Content-Type: application/json' \
        -d '{"prompt": "Who are you running as?"}'
"""

import datetime
import json
import os
import re
import time
from zoneinfo import ZoneInfo

import boto3
from bedrock_agentcore.runtime import BedrockAgentCoreApp
from strands import Agent, tool
from strands.models import BedrockModel

# Sonnet on Bedrock. Adaptive-thinking Sonnet models reject temperature/top_p, so none are set.
MODEL_ID = os.getenv("MODEL_ID", "us.anthropic.claude-sonnet-5")
REGION = os.getenv("AWS_REGION", "us-east-1")
ATHENA_WORKGROUP = os.getenv("ATHENA_WORKGROUP", "aoa-day05")
GLUE_DATABASE = os.getenv("GLUE_DATABASE", "sample_data")

READ_ONLY_SQL = re.compile(r"^\s*(select|with|show|describe)\b", re.IGNORECASE)

athena = boto3.client("athena", region_name=REGION)
sts = boto3.client("sts", region_name=REGION)


@tool
def get_weather(query: str) -> str:
    """Simulates a web search. Use it to get information on weather.

    Args:
        query: A string containing the location to get weather information for.
    """
    if "sf" in query.lower() or "san francisco" in query.lower():
        return "It's 60 degrees and foggy."
    return "It's 90 degrees and sunny."


@tool
def get_current_time(query: str) -> str:
    """Get the current time for a city.

    Args:
        query: The name of the city to get the current time for.
    """
    if "sf" in query.lower() or "san francisco" in query.lower():
        now = datetime.datetime.now(ZoneInfo("America/Los_Angeles"))
        return f"The current time for query {query} is {now.strftime('%Y-%m-%d %H:%M:%S %Z%z')}"
    return f"Sorry, I don't have timezone information for query: {query}."


@tool
def whoami() -> str:
    """Return the AWS principal (identity) this agent is running as."""
    identity = sts.get_caller_identity()
    return json.dumps({"arn": identity["Arn"], "account": identity["Account"]})


@tool
def list_tables() -> str:
    """List the tables in the analytics database."""
    try:
        tables = athena.list_table_metadata(CatalogName="AwsDataCatalog", DatabaseName=GLUE_DATABASE)
    except Exception as exc:  # AccessDenied is the expected first result on Day 5
        return f"ERROR: {exc}"
    return json.dumps([t["Name"] for t in tables["TableMetadataList"]])


@tool
def run_sql(query: str) -> str:
    """Run a read-only SQL query (Athena / Trino dialect) on the analytics database.

    Args:
        query: A SELECT, WITH, SHOW or DESCRIBE statement, e.g. "SELECT * FROM cities_weather".
    """
    if not READ_ONLY_SQL.match(query):
        return "ERROR: only read-only statements (SELECT, WITH, SHOW, DESCRIBE) are allowed."
    try:
        execution_id = athena.start_query_execution(
            QueryString=query,
            WorkGroup=ATHENA_WORKGROUP,
            QueryExecutionContext={"Database": GLUE_DATABASE},
        )["QueryExecutionId"]
        while True:
            status = athena.get_query_execution(QueryExecutionId=execution_id)["QueryExecution"]["Status"]
            if status["State"] in {"SUCCEEDED", "FAILED", "CANCELLED"}:
                break
            time.sleep(0.5)
        if status["State"] != "SUCCEEDED":
            return f"ERROR: query {status['State']}: {status.get('StateChangeReason', '')}"
        rows = athena.get_query_results(QueryExecutionId=execution_id, MaxResults=100)["ResultSet"]["Rows"]
    except Exception as exc:
        return f"ERROR: {exc}"

    header, *data = [[col.get("VarCharValue") for col in row["Data"]] for row in rows]
    return json.dumps([dict(zip(header, values)) for values in data])


SYSTEM_PROMPT = f"""You are a helpful AI assistant designed to provide accurate and useful information.
You can query the Athena database "{GLUE_DATABASE}" with list_tables and run_sql.
If a tool returns an ERROR (for example AccessDenied), report the exact error to the user;
do not invent data. Use whoami when asked which identity you run as."""

app = BedrockAgentCoreApp()


@app.entrypoint
def invoke(payload: dict) -> dict:
    agent = Agent(
        model=BedrockModel(model_id=MODEL_ID, region_name=REGION),
        system_prompt=SYSTEM_PROMPT,
        tools=[get_weather, get_current_time, whoami, list_tables, run_sql],
        callback_handler=None,
    )
    result = agent(payload.get("prompt", "Who are you running as?"))
    return {"result": str(result), "tools_used": sorted(result.metrics.tool_metrics)}


if __name__ == "__main__":
    app.run()
