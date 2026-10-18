"""On-behalf-of token delegation with AgentCore Identity (~ Agent Identity auth manager).

Two identities take part in every token fetch:
  * the AGENT, as its workload identity (and the IAM principal calling AgentCore), and
  * the USER, bound into the workload access token (user id here; an IdP JWT in production).

The token vault keys each GitHub token by (workload, user, provider), so Alice's agent
session can never receive Bob's token.
"""

from dataclasses import dataclass

import boto3

from config import PROVIDER_NAME, REGION, RETURN_URL, SCOPES, WORKLOAD_NAME


@dataclass
class TokenResult:
    token: str | None = None
    consent_url: str | None = None
    session_uri: str | None = None


class Delegation:
    def __init__(self, client=None, workload: str = WORKLOAD_NAME, provider: str = PROVIDER_NAME):
        self.client = client or boto3.client("bedrock-agentcore", region_name=REGION)
        self.workload = workload
        self.provider = provider

    def workload_token(self, user_id: str) -> str:
        """The agent's identity, scoped to one user. On AgentCore Runtime this comes pre-made
        from the invocation (BedrockAgentCoreContext.get_workload_access_token())."""
        response = self.client.get_workload_access_token_for_user_id(workloadName=self.workload, userId=user_id)
        return response["workloadAccessToken"]

    def token_for(self, user_id: str, workload_token: str | None = None, force: bool = False) -> TokenResult:
        """Return the user's GitHub token from the vault, or a consent URL if there is none yet.

        `force` starts a fresh consent even if a (revoked) token is stored.
        """
        response = self.client.get_resource_oauth2_token(
            forceAuthentication=force,
            workloadIdentityToken=workload_token or self.workload_token(user_id),
            resourceCredentialProviderName=self.provider,
            scopes=SCOPES,
            oauth2Flow="USER_FEDERATION",
            resourceOauth2ReturnUrl=RETURN_URL,
        )
        if token := response.get("accessToken"):
            return TokenResult(token=token)
        return TokenResult(consent_url=response["authorizationUrl"], session_uri=response.get("sessionUri"))

    def complete(self, session_uri: str, user_id: str) -> None:
        """Session binding: the signed-in user who comes back must be the one who started the flow."""
        self.client.complete_resource_token_auth(sessionUri=session_uri, userIdentifier={"userId": user_id})
