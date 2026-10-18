"""IAM documents for the agent's own identity, as pure functions (see test_policies.py)."""


def trust_policy(account: str, region: str, agent_name: str) -> dict:
    """Only AgentCore, and only for runtimes named after THIS agent, may assume the role."""
    return {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Sid": "AgentCoreRuntimeOnly",
                "Effect": "Allow",
                "Principal": {"Service": "bedrock-agentcore.amazonaws.com"},
                "Action": "sts:AssumeRole",
                "Condition": {
                    "StringEquals": {"aws:SourceAccount": account},
                    "ArnLike": {"aws:SourceArn": f"arn:aws:bedrock-agentcore:{region}:{account}:runtime/{agent_name}-*"},
                },
            }
        ],
    }


def baseline_policy(account: str, region: str, agent_name: str) -> dict:
    """What every runtime needs to start: logs, traces, metrics, its own workload token, the model.

    Deliberately NO data access. A fresh agent identity can reach nothing until granted.
    """
    log_group = f"arn:aws:logs:{region}:{account}:log-group:/aws/bedrock-agentcore/runtimes/{agent_name}-*"
    return {
        "Version": "2012-10-17",
        "Statement": [
            {"Effect": "Allow", "Action": ["logs:CreateLogGroup", "logs:DescribeLogStreams"], "Resource": log_group},
            {"Effect": "Allow", "Action": ["logs:CreateLogStream", "logs:PutLogEvents"], "Resource": f"{log_group}:log-stream:*"},
            {"Effect": "Allow", "Action": "logs:DescribeLogGroups", "Resource": f"arn:aws:logs:{region}:{account}:log-group:*"},
            {
                "Effect": "Allow",
                "Action": ["xray:PutTraceSegments", "xray:PutTelemetryRecords", "xray:GetSamplingRules", "xray:GetSamplingTargets"],
                "Resource": "*",
            },
            {
                "Effect": "Allow",
                "Action": "cloudwatch:PutMetricData",
                "Resource": "*",
                "Condition": {"StringEquals": {"cloudwatch:namespace": "bedrock-agentcore"}},
            },
            {
                "Sid": "OwnWorkloadIdentityOnly",
                "Effect": "Allow",
                "Action": ["bedrock-agentcore:GetWorkloadAccessToken", "bedrock-agentcore:GetWorkloadAccessTokenForJWT"],
                "Resource": [
                    f"arn:aws:bedrock-agentcore:{region}:{account}:workload-identity-directory/default",
                    f"arn:aws:bedrock-agentcore:{region}:{account}:workload-identity-directory/default/workload-identity/{agent_name}-*",
                ],
            },
            {
                "Sid": "BedrockModelInvocation",
                "Effect": "Allow",
                "Action": ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"],
                "Resource": ["arn:aws:bedrock:*::foundation-model/*", f"arn:aws:bedrock:{region}:{account}:inference-profile/*"],
            },
        ],
    }


def athena_read_policy(account: str, region: str, bucket: str, workgroup: str, database: str) -> dict:
    """STEP 11: the AWS equivalent of bigquery.jobUser + bigquery.dataViewer, scoped to one dataset."""
    return {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Sid": "RunQueriesInOneWorkgroup",  # ~ roles/bigquery.jobUser
                "Effect": "Allow",
                "Action": [
                    "athena:StartQueryExecution",
                    "athena:GetQueryExecution",
                    "athena:GetQueryResults",
                    "athena:StopQueryExecution",
                    "athena:ListTableMetadata",
                    "athena:GetTableMetadata",
                ],
                "Resource": [
                    f"arn:aws:athena:{region}:{account}:workgroup/{workgroup}",
                    f"arn:aws:athena:{region}:{account}:datacatalog/AwsDataCatalog",
                ],
            },
            {
                "Sid": "ReadOneDatabaseCatalog",  # ~ roles/bigquery.dataViewer (metadata)
                "Effect": "Allow",
                "Action": ["glue:GetDatabase", "glue:GetTable", "glue:GetTables", "glue:GetPartitions"],
                "Resource": [
                    f"arn:aws:glue:{region}:{account}:catalog",
                    f"arn:aws:glue:{region}:{account}:database/{database}",
                    f"arn:aws:glue:{region}:{account}:table/{database}/*",
                ],
            },
            {
                "Sid": "ReadOneDatasetPrefix",  # ~ roles/bigquery.dataViewer (rows)
                "Effect": "Allow",
                "Action": "s3:GetObject",
                "Resource": f"arn:aws:s3:::{bucket}/data/*",
            },
            {
                "Sid": "ListOnlyDataAndResults",
                "Effect": "Allow",
                "Action": "s3:ListBucket",
                "Resource": f"arn:aws:s3:::{bucket}",
                "Condition": {"StringLike": {"s3:prefix": ["data/*", "athena-results/*"]}},
            },
            {
                "Sid": "LocateBucket",  # s3:GetBucketLocation carries no s3:prefix key
                "Effect": "Allow",
                "Action": "s3:GetBucketLocation",
                "Resource": f"arn:aws:s3:::{bucket}",
            },
            {
                "Sid": "WriteQueryResults",
                "Effect": "Allow",
                "Action": ["s3:PutObject", "s3:GetObject", "s3:AbortMultipartUpload"],
                "Resource": f"arn:aws:s3:::{bucket}/athena-results/*",
            },
        ],
    }
