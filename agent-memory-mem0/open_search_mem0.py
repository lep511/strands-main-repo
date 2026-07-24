# Prerequisites:
# 1. Create an OpenSearch Serverless vector search collection by running:
#      bash create_cluster.sh
#    This script creates the required encryption, network, and data access policies,
#    then provisions the collection and waits until it is ACTIVE.
#
# 2. Copy the "Host" value from the script output and replace the placeholder below.
#
# 3. Install dependencies:
#      pip install boto3 opensearch-py mem0ai

import boto3
from opensearchpy import RequestsHttpConnection, AWSV4SignerAuth
from mem0 import Memory

# Configuration
REGION = "us-east-1"
OPENSEARCH_HOST = "r8wdwqn28on4qyruksn1.us-east-1.aoss.amazonaws.com"
OPENSEARCH_PORT = 443
COLLECTION_NAME = "mem0"
EMBEDDING_MODEL = "us.cohere.embed-v4:0"
EMBEDDING_DIMS = 1536
LLM_MODEL = "us.anthropic.claude-sonnet-4-6"
LLM_TEMPERATURE = 0.1
LLM_MAX_TOKENS = 2000

credentials = boto3.Session().get_credentials()
auth = AWSV4SignerAuth(credentials, REGION, "aoss")


def patch_for_aoss_and_cohere_v4():
    """Patch mem0 for AOSS and Cohere Embed v4 compatibility.

    1. AOSS does not support the _refresh API — patched to no-op.
    2. Cohere Embed v4 returns {"embeddings": {"float": [[...]]}} instead of
       {"embeddings": [[...]]} which mem0 expects.
    """
    from mem0.vector_stores.opensearch import OpenSearchDB
    from mem0.embeddings.aws_bedrock import AWSBedrockEmbedding

    # Fix AOSS _refresh
    _original_insert = OpenSearchDB.insert

    def _insert_no_refresh(self, vectors, payloads, ids):
        original_refresh = self.client.indices.refresh
        self.client.indices.refresh = lambda *a, **kw: None
        try:
            return _original_insert(self, vectors, payloads, ids)
        finally:
            self.client.indices.refresh = original_refresh

    OpenSearchDB.insert = _insert_no_refresh

    # Fix Cohere Embed v4 response format
    import json

    def _get_embedding_v4(self, text):
        model_id = self.config.model
        is_cohere = "cohere" in model_id
        if is_cohere:
            input_body = {"input_type": "search_document", "texts": [text]}
        else:
            input_body = {"inputText": text}

        response = self.client.invoke_model(
            body=json.dumps(input_body),
            modelId=self.config.model,
            accept="application/json",
            contentType="application/json",
        )
        response_body = json.loads(response["body"].read())

        if is_cohere:
            embeddings = response_body["embeddings"]
            if isinstance(embeddings, dict):
                return embeddings["float"][0]
            return embeddings[0]
        return response_body["embedding"]

    AWSBedrockEmbedding._get_embedding = _get_embedding_v4


patch_for_aoss_and_cohere_v4()

config = {
    "embedder": {
        "provider": "aws_bedrock",
        "config": {
            "model": EMBEDDING_MODEL
        }
    },
    "llm": {
        "provider": "aws_bedrock",
        "config": {
            "model": LLM_MODEL,
            "temperature": LLM_TEMPERATURE,
            "max_tokens": LLM_MAX_TOKENS
        }
    },
    "vector_store": {
        "provider": "opensearch",
        "config": {
            "collection_name": COLLECTION_NAME,
            "host": OPENSEARCH_HOST,
            "port": OPENSEARCH_PORT,
            "http_auth": auth,
            "connection_class": RequestsHttpConnection,
            "pool_maxsize": 20,
            "use_ssl": True,
            "verify_certs": True,
            "embedding_model_dims": EMBEDDING_DIMS,
        }
    },
}

# Initialize the memory system
m = Memory.from_config(config)

# --- Example: Store memories from multiple conversations ---
# To clear all memories before running, delete the indices via AWS CLI:
#   awscurl --service aoss --region us-east-1 \
#     -X DELETE "https://<OPENSEARCH_HOST>/mem0"
#   awscurl --service aoss --region us-east-1 \
#     -X DELETE "https://<OPENSEARCH_HOST>/mem0migrations"

USER_ID = "alice"

conversation_1 = [
    {"role": "user", "content": "I'm planning to watch a movie tonight. Any recommendations?"},
    {"role": "assistant", "content": "How about thriller movies? They can be quite engaging."},
    {"role": "user", "content": "I'm not a big fan of thriller movies but I love sci-fi movies."},
    {"role": "assistant", "content": "Got it! I'll suggest sci-fi movies in the future."},
]

conversation_2 = [
    {"role": "user", "content": "I just finished reading Dune by Frank Herbert. Absolutely loved it."},
    {"role": "assistant", "content": "Great choice! Would you like similar book recommendations?"},
    {"role": "user", "content": "Yes! I also enjoyed The Expanse series. I prefer hard sci-fi with realistic physics."},
]

conversation_3 = [
    {"role": "user", "content": "Can you recommend a good restaurant for dinner? I'm vegetarian."},
    {"role": "assistant", "content": "Sure! Any cuisine preference?"},
    {"role": "user", "content": "I love Indian and Thai food. Nothing too spicy though."},
]

import time, sys

print("=== Storing memories ===\n")
stored_count = 0
for i, conv in enumerate([conversation_1, conversation_2, conversation_3], 1):
    result = m.add(conv, user_id=USER_ID)
    for r in result.get("results", []):
        if r["event"] == "ADD":
            stored_count += 1
        print(f"  [{r['event']}] {r['memory']}")

# Wait for AOSS to index documents (serverless has no manual _refresh)
if stored_count > 0:
    elapsed = 0
    max_wait = 90
    print(f"\nWaiting for AOSS to index {stored_count} memories...")
    while elapsed < max_wait:
        results = m.search("test", filters={"user_id": USER_ID}, top_k=stored_count)
        indexed = len(results.get("results", []))
        sys.stdout.write(f"\r  Indexed: {indexed}/{stored_count} ({elapsed}s)")
        sys.stdout.flush()
        if indexed >= stored_count:
            break
        time.sleep(5)
        elapsed += 5
    sys.stdout.write(f"\r  Indexed: {indexed}/{stored_count} - done!       \n")

# --- Retrieve memories with semantic search ---
print("\n=== Searching memories ===\n")

queries = [
    "What kind of movies does Alice like?",
    "What are her food preferences?",
    "What books has she read recently?",
    "Le gustan a Alice las películas de ciencia ficción?",
]

SCORE_THRESHOLD = 0.35

for query in queries:
    print(f"Q: {query}")
    results = m.search(query, filters={"user_id": USER_ID}, top_k=2)
    hits = [h for h in results.get("results", []) if h["score"] >= SCORE_THRESHOLD]
    hits.sort(key=lambda h: h["created_at"], reverse=True)
    if hits:
        for hit in hits:
            print(f"  -> {hit['memory']} (score: {hit['score']:.3f}, {hit['created_at'][:10]})")
    else:
        print("  (no relevant memories found)")
    print()

# --- List all stored memories for the user ---
print("=== All memories ===\n")
all_memories = m.get_all(filters={"user_id": USER_ID})
memories = all_memories.get("results", [])
memories.sort(key=lambda m: m["created_at"], reverse=True)
for mem in memories:
    print(f"  - {mem['memory']} ({mem['created_at'][:10]})")