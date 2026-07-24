#!/bin/bash
# Delete all mem0 indices from OpenSearch Serverless to start fresh.
# This removes all stored memories and migration state.

set -e

REGION="us-east-1"
HOST="r8wdwqn28on4qyruksn1.us-east-1.aoss.amazonaws.com"
ENDPOINT="https://${HOST}"

echo "Deleting mem0 indices from ${HOST}..."

uv run python3 -c "
import boto3
from opensearchpy import RequestsHttpConnection, AWSV4SignerAuth, OpenSearch

credentials = boto3.Session().get_credentials()
auth = AWSV4SignerAuth(credentials, '${REGION}', 'aoss')

client = OpenSearch(
    hosts=[{'host': '${HOST}', 'port': 443}],
    http_auth=auth,
    connection_class=RequestsHttpConnection,
    use_ssl=True,
    verify_certs=True,
)

for index in ['mem0', 'mem0migrations', 'mem0_entities']:
    try:
        client.indices.delete(index=index)
        print(f'  {index}: deleted')
    except Exception as e:
        print(f'  {index}: {e}')
"

echo ""
echo "Done. Run 'uv run open_search_mem0.py' to re-create indices with fresh data."
echo ""
