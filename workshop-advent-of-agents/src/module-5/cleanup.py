"""Delete everything the Day 5 scripts created: runtime, role, Athena, Glue and the bucket.

Usage:
    uv run src/module-5/cleanup.py
"""

import time

import boto3

from config import ATHENA_WORKGROUP, GLUE_DATABASE, REGION, ROLE_NAME, STATE_PATH, TABLE, bucket, load_state

control = boto3.client("bedrock-agentcore-control", region_name=REGION)
iam = boto3.client("iam")
athena = boto3.client("athena", region_name=REGION)
glue = boto3.client("glue", region_name=REGION)
s3 = boto3.resource("s3", region_name=REGION)


def step(label: str, fn, *args, **kwargs) -> None:
    try:
        fn(*args, **kwargs)
        print(f"deleted {label}")
    except Exception as exc:
        print(f"skip    {label}: {type(exc).__name__}")


def delete_runtime(runtime_id: str) -> None:
    control.delete_agent_runtime(agentRuntimeId=runtime_id)
    while True:
        try:
            control.get_agent_runtime(agentRuntimeId=runtime_id)
        except control.exceptions.ResourceNotFoundException:
            return
        time.sleep(5)


def delete_role() -> None:
    for name in iam.list_role_policies(RoleName=ROLE_NAME)["PolicyNames"]:
        iam.delete_role_policy(RoleName=ROLE_NAME, PolicyName=name)
    iam.delete_role(RoleName=ROLE_NAME)


def delete_bucket() -> None:
    b = s3.Bucket(bucket())
    b.object_versions.delete()
    b.objects.all().delete()
    b.delete()


def main() -> None:
    if runtime_id := load_state().get("runtime_id"):
        step(f"runtime {runtime_id}", delete_runtime, runtime_id)
    step(f"role {ROLE_NAME}", delete_role)
    step(f"Athena workgroup {ATHENA_WORKGROUP}", athena.delete_work_group, WorkGroup=ATHENA_WORKGROUP, RecursiveDeleteOption=True)
    step(f"Glue table {GLUE_DATABASE}.{TABLE}", glue.delete_table, DatabaseName=GLUE_DATABASE, Name=TABLE)
    step(f"Glue database {GLUE_DATABASE}", glue.delete_database, Name=GLUE_DATABASE)
    step(f"bucket s3://{bucket()}", delete_bucket)
    STATE_PATH.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
