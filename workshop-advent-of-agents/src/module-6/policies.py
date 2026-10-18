"""IAM for delegation (~ roles/agentidentity.user on the auth provider), as a pure function."""


def delegation_policy(account: str, region: str, workload_name: str, provider_name: str) -> dict:
    """What a principal needs to fetch a user's token for ONE workload from ONE provider.

    Grant it to the agent's execution role (STEP 10) and to yourself for local runs (STEP 11).
    """
    arn = f"arn:aws:bedrock-agentcore:{region}:{account}"
    workload = f"{arn}:workload-identity-directory/default/workload-identity/{workload_name}"
    return {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Sid": "ActAsThisWorkloadForAUser",
                "Effect": "Allow",
                # ForJWT in production (user proven by an IdP token). ForUserId only for local demos.
                "Action": ["bedrock-agentcore:GetWorkloadAccessTokenForJWT", "bedrock-agentcore:GetWorkloadAccessTokenForUserId"],
                "Resource": [f"{arn}:workload-identity-directory/default", workload],
            },
            {
                "Sid": "ReadUserTokensFromOneProvider",
                "Effect": "Allow",
                "Action": ["bedrock-agentcore:GetResourceOauth2Token", "bedrock-agentcore:CompleteResourceTokenAuth"],
                "Resource": [
                    f"{arn}:token-vault/default",
                    f"{arn}:token-vault/default/oauth2credentialprovider/{provider_name}",
                    f"{arn}:workload-identity-directory/default",
                    workload,
                ],
            },
            {
                "Sid": "ProviderClientSecretViaAgentCoreOnly",
                "Effect": "Allow",
                "Action": "secretsmanager:GetSecretValue",
                "Resource": f"arn:aws:secretsmanager:{region}:{account}:secret:bedrock-agentcore-identity!default/oauth2/{provider_name}*",
                "Condition": {"StringEquals": {"aws:ResourceTag/aws:secretsmanager:owningService": "bedrock-agentcore-identity"}},
            },
        ],
    }
