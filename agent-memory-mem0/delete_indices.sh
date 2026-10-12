#!/bin/bash
# Delete all mem0 indices from OpenSearch Serverless to start fresh.
# This removes all stored memories and migration state.

set -e

# Load configuration from .env (see .env.example)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -f "${SCRIPT_DIR}/.env" ]; then
  set -a
  # shellcheck disable=SC1091
  source "${SCRIPT_DIR}/.env"
  set +a
fi

REGION="${AWS_REGION:-us-east-1}"
HOST="${OPENSEARCH_HOST}"
COLLECTION_NAME="${OPENSEARCH_COLLECTION:-mem0}"

if [ -z "$HOST" ]; then
  echo "ERROR: OPENSEARCH_HOST is not set. Add it to .env (see .env.example)." >&2
  exit 1
fi

echo "Deleting ${COLLECTION_NAME} indices from ${HOST}..."

uv run python3 -c "
import boto3
from opensearchpy import RequestsHttpConnection, AWSV4SignerAuth, OpenSearch

credentials = boto3.Session().get_credentials()
auth = AWSV4SignerAuth(credentials, '${REGION}', 'aoss')

client = OpenSearch(
    hosts=[{'host': '${HOST}', 'port': ${OPENSEARCH_PORT:-443}}],
    http_auth=auth,
    connection_class=RequestsHttpConnection,
    use_ssl=True,
    verify_certs=True,
)

collection = '${COLLECTION_NAME}'

for index in [collection, collection + 'migrations', collection + '_entities']:
    try:
        client.indices.delete(index=index)
        print(f'  {index}: deleted')
    except Exception as e:
        print(f'  {index}: {e}')
"

echo ""
echo "Done. Run 'uv run open_search_mem0.py' to re-create indices with fresh data."
echo ""
