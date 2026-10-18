"""STEPS 5-8: create the data the agent will query (Athena + Glue + S3 ~ BigQuery dataset).

Runs as YOU (the operator), not as the agent.

Usage:
    uv run src/module-5/setup_data.py
"""

import time

import boto3

from config import ATHENA_WORKGROUP, GLUE_DATABASE, REGION, TABLE, account_id, bucket

CSV = """city,state,temp_f,condition
San Francisco,CA,60,Foggy
New York,NY,75,Sunny
Seattle,WA,58,Rainy
"""

s3 = boto3.client("s3", region_name=REGION)
athena = boto3.client("athena", region_name=REGION)
glue = boto3.client("glue", region_name=REGION)


def run_query(sql: str) -> list[list[str]]:
    execution_id = athena.start_query_execution(QueryString=sql, WorkGroup=ATHENA_WORKGROUP)["QueryExecutionId"]
    while True:
        status = athena.get_query_execution(QueryExecutionId=execution_id)["QueryExecution"]["Status"]
        if status["State"] in {"SUCCEEDED", "FAILED", "CANCELLED"}:
            break
        time.sleep(0.5)
    if status["State"] != "SUCCEEDED":
        raise RuntimeError(f"{sql!r} -> {status['State']}: {status.get('StateChangeReason')}")
    rows = athena.get_query_results(QueryExecutionId=execution_id)["ResultSet"]["Rows"]
    return [[col.get("VarCharValue", "") for col in row["Data"]] for row in rows]


def create_bucket(name: str) -> None:
    try:
        kwargs = {} if REGION == "us-east-1" else {"CreateBucketConfiguration": {"LocationConstraint": REGION}}
        s3.create_bucket(Bucket=name, **kwargs)
        print(f"created bucket s3://{name}")
    except s3.exceptions.BucketAlreadyOwnedByYou:
        print(f"bucket s3://{name} already exists")
    s3.put_public_access_block(
        Bucket=name,
        PublicAccessBlockConfiguration={
            "BlockPublicAcls": True, "IgnorePublicAcls": True, "BlockPublicPolicy": True, "RestrictPublicBuckets": True,
        },
    )


def create_workgroup(name: str, results: str) -> None:
    try:
        athena.create_work_group(
            Name=name,
            Configuration={
                "ResultConfiguration": {"OutputLocation": results},
                "EnforceWorkGroupConfiguration": True,
                "PublishCloudWatchMetricsEnabled": False,
            },
            Description="Advent of Agents Day 5",
        )
        print(f"created Athena workgroup {name}")
    except athena.exceptions.InvalidRequestException as exc:
        if "already" not in str(exc).lower():
            raise
        print(f"Athena workgroup {name} already exists")


def main() -> None:
    name = bucket()
    print(f"account {account_id()} · region {REGION}")

    create_bucket(name)
    s3.put_object(Bucket=name, Key=f"data/{TABLE}/{TABLE}.csv", Body=CSV.encode(), ExpectedBucketOwner=account_id())
    print(f"uploaded s3://{name}/data/{TABLE}/{TABLE}.csv")

    create_workgroup(ATHENA_WORKGROUP, f"s3://{name}/athena-results/")

    try:
        glue.create_database(DatabaseInput={"Name": GLUE_DATABASE, "Description": "Advent of Agents Day 5"})
        print(f"created Glue database {GLUE_DATABASE}")
    except glue.exceptions.AlreadyExistsException:
        print(f"Glue database {GLUE_DATABASE} already exists")

    run_query(
        f"""CREATE EXTERNAL TABLE IF NOT EXISTS {GLUE_DATABASE}.{TABLE} (
              city string, state string, temp_f int, condition string)
            ROW FORMAT DELIMITED FIELDS TERMINATED BY ','
            LOCATION 's3://{name}/data/{TABLE}/'
            TBLPROPERTIES ('skip.header.line.count'='1')"""
    )
    print(f"table {GLUE_DATABASE}.{TABLE} ready\n")

    # STEP 8 - verify, like `bq head`
    header, *rows = run_query(f"SELECT * FROM {GLUE_DATABASE}.{TABLE} ORDER BY city")
    print(" | ".join(f"{h:<13}" for h in header))
    for row in rows:
        print(" | ".join(f"{v:<13}" for v in row))


if __name__ == "__main__":
    main()
