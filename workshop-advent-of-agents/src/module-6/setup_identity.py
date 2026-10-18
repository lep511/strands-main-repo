"""STEPS 5-9: the auth provider (OAuth2 credential provider) and the agent's workload identity.

    uv run src/module-6/setup_identity.py workload          # STEP 5: agent identity + allowed return URL
    uv run src/module-6/setup_identity.py provider          # STEP 6-7: provider with placeholders -> callback URL
    #   STEP 8: register a GitHub OAuth app with that callback URL (see GUIDE.md)
    uv run src/module-6/setup_identity.py provider --client-id ID --client-secret SECRET   # STEP 9
    uv run src/module-6/setup_identity.py show              # print both resources

The client secret goes straight into AgentCore Identity (stored in Secrets Manager);
neither the agent nor the app ever reads it.
"""

import argparse
import json

import boto3

from config import (
    PLACEHOLDER_CLIENT_ID, PLACEHOLDER_CLIENT_SECRET, PROVIDER_NAME, REGION, RETURN_URL, WORKLOAD_NAME,
)

control = boto3.client("bedrock-agentcore-control", region_name=REGION)


def ensure_workload(name: str, return_urls: list[str]) -> dict:
    try:
        current = control.get_workload_identity(name=name)
        urls = sorted(set(current.get("allowedResourceOauth2ReturnUrls", [])) | set(return_urls))
        response = control.update_workload_identity(name=name, allowedResourceOauth2ReturnUrls=urls)
        print(f"updated workload identity {name}")
    except control.exceptions.ResourceNotFoundException:
        response = control.create_workload_identity(name=name, allowedResourceOauth2ReturnUrls=return_urls)
        print(f"created workload identity {name}")
    return response


def ensure_provider(client_id: str, client_secret: str) -> dict:
    config = {"githubOauth2ProviderConfig": {"clientId": client_id, "clientSecret": client_secret}}
    try:
        control.get_oauth2_credential_provider(name=PROVIDER_NAME)
        response = control.update_oauth2_credential_provider(
            name=PROVIDER_NAME, credentialProviderVendor="GithubOauth2", oauth2ProviderConfigInput=config
        )
        print(f"updated credential provider {PROVIDER_NAME}")
    except control.exceptions.ResourceNotFoundException:
        response = control.create_oauth2_credential_provider(
            name=PROVIDER_NAME, credentialProviderVendor="GithubOauth2", oauth2ProviderConfigInput=config
        )
        print(f"created credential provider {PROVIDER_NAME}")
    return response


def show() -> None:
    try:
        provider = control.get_oauth2_credential_provider(name=PROVIDER_NAME)
        client_id = provider["oauth2ProviderConfigOutput"]["githubOauth2ProviderConfig"].get("clientId")
        print(f"provider            {provider['credentialProviderArn']}")
        print(f"  client id         {client_id}{'  (placeholder: run STEP 9)' if client_id == PLACEHOLDER_CLIENT_ID else ''}")
        print(f"  client secret     {provider['clientSecretArn']['secretArn']}")
        print(f"  callback URL      {provider['callbackUrl']}   <- register this on GitHub")
    except control.exceptions.ResourceNotFoundException:
        print(f"provider {PROVIDER_NAME} not found")
    try:
        workload = control.get_workload_identity(name=WORKLOAD_NAME)
        print(f"workload identity   {workload['workloadIdentityArn']}")
        print(f"  return URLs       {workload.get('allowedResourceOauth2ReturnUrls')}")
    except control.exceptions.ResourceNotFoundException:
        print(f"workload identity {WORKLOAD_NAME} not found")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    w = sub.add_parser("workload", help="create/update the agent's workload identity")
    w.add_argument("--name", default=WORKLOAD_NAME, help="e.g. the workload identity of a deployed runtime")
    w.add_argument("--return-url", action="append", default=None)
    p = sub.add_parser("provider", help="create/update the GitHub credential provider")
    p.add_argument("--client-id", default=PLACEHOLDER_CLIENT_ID)
    p.add_argument("--client-secret", default=PLACEHOLDER_CLIENT_SECRET)
    sub.add_parser("show")
    args = parser.parse_args()

    if args.command == "workload":
        response = ensure_workload(args.name, args.return_url or [RETURN_URL])
        print(json.dumps({k: response[k] for k in ("workloadIdentityArn", "allowedResourceOauth2ReturnUrls")}, indent=2))
    elif args.command == "provider":
        response = ensure_provider(args.client_id, args.client_secret)
        print(f"\ncallback URL (register it as the GitHub 'Authorization callback URL'):\n  {response['callbackUrl']}")
    else:
        show()


if __name__ == "__main__":
    main()
