# Prerequisites:
# 1. Create an OpenSearch Serverless vector search collection by running:
#      bash create_cluster.sh
#    This script creates the required encryption, network, and data access policies,
#    then provisions the collection and waits until it is ACTIVE.
#
# 2. Copy the "Host" value from the script output into OPENSEARCH_HOST in .env
#    (see .env.example).
#
# 3. Install dependencies:
#      pip install boto3 opensearch-py mem0ai python-dotenv

import json
import logging
import os
import sys
import time

import boto3
from botocore.exceptions import ClientError, NoCredentialsError
from dotenv import load_dotenv
from opensearchpy import AWSV4SignerAuth, RequestsHttpConnection

# override=True so .env wins over an ambient AWS_REGION that may point at a
# different region than the collection (SigV4 signing must match the host).
load_dotenv(override=True)

# Configuration
REGION = os.getenv("AWS_REGION", "us-east-1")
OPENSEARCH_HOST = os.getenv("OPENSEARCH_HOST")
OPENSEARCH_PORT = int(os.getenv("OPENSEARCH_PORT", "443"))
COLLECTION_NAME = os.getenv("OPENSEARCH_COLLECTION", "mem0")

# Keep boto3 (Bedrock) and the SigV4 signer on the same region
os.environ["AWS_DEFAULT_REGION"] = REGION

# AWS_BEARER_TOKEN_BEDROCK makes botocore authenticate every bedrock/bedrock-runtime
# client with a bearer API key instead of SigV4. It is commonly exported for other
# tools (e.g. CLAUDE_CODE_USE_BEDROCK=1), and because mem0 builds its own boto3
# clients it gets picked up here too, failing with:
#   AccessDeniedException ... Authentication failed: Please make sure your API Key is valid
# Drop it for this process so the IAM role / profile credentials are used instead.
if os.environ.pop("AWS_BEARER_TOKEN_BEDROCK", None):
    print("Note: ignoring AWS_BEARER_TOKEN_BEDROCK; using SigV4 credentials for Bedrock.")

if not OPENSEARCH_HOST:
    raise SystemExit(
        "OPENSEARCH_HOST is not set. Run 'bash create_cluster.sh' and copy the "
        "printed Host value into .env (see .env.example)."
    )

if OPENSEARCH_HOST.startswith("http"):
    raise SystemExit("OPENSEARCH_HOST must be a bare hostname, without the https:// prefix.")

EMBEDDING_MODEL = "us.cohere.embed-v4:0"
EMBEDDING_DIMS = 1536  # Cohere Embed v4 default output dimension
LLM_MODEL = "us.anthropic.claude-sonnet-5"
LLM_MAX_TOKENS = 2000

credentials = boto3.Session().get_credentials()
if credentials is None:
    raise SystemExit(
        "No AWS credentials found. Attach an instance role or run 'aws configure' / "
        "'aws sso login' before starting this script."
    )
auth = AWSV4SignerAuth(credentials, REGION, "aoss")

# mem0 probes bedrock:ListFoundationModels at startup and warns when the model id is
# not in the result. Inference profile ids ("us.anthropic....") never are, so the
# warning is a false positive here.
logging.getLogger("mem0.llms.aws_bedrock").setLevel(logging.ERROR)

# Claude models from the reasoning generation reject sampling parameters in the
# Converse inferenceConfig ("`temperature` is deprecated for this model"), while mem0
# always sends temperature. Prefixes of the model families that require them stripped:
NO_SAMPLING_PARAMS = (
    "claude-sonnet-5",
    "claude-opus-5",
    "claude-opus-4-7",
    "claude-opus-4-8",
    "claude-haiku-5",
    "claude-fable-5",
    "claude-mythos-5",
)


def patch_mem0_for_aoss_and_bedrock():
    """Patch mem0 for AOSS, Cohere Embed v4 and current-generation Claude compatibility.

    1. OpenSearch Serverless has no _refresh API (it answers 404), but mem0 calls it
       after every insert.
    2. Cohere Embed v4 returns {"embeddings": {"float": [[...]]}} instead of the
       {"embeddings": [[...]]} shape mem0 expects, and queries should be embedded
       with input_type="search_query" rather than "search_document".
    3. Claude Sonnet 5 and the other reasoning models reject temperature/topP/topK.
    """
    from mem0.embeddings.aws_bedrock import AWSBedrockEmbedding
    from mem0.llms.aws_bedrock import AWSBedrockLLM
    from mem0.vector_stores.opensearch import OpenSearchDB

    # Patched on the class, not on a single client: mem0 also builds a second store
    # lazily (<collection>_entities) for entity linking, and it needs the same no-op.
    _original_init = OpenSearchDB.__init__

    def _init_without_refresh(self, **kwargs):
        _original_init(self, **kwargs)
        self.client.indices.refresh = lambda *args, **kwargs: None

    OpenSearchDB.__init__ = _init_without_refresh

    def _embed(self, text, memory_action=None):
        model_id = self.config.model
        is_cohere = "cohere" in model_id

        if is_cohere:
            # Asymmetric embeddings: queries and stored documents use different types.
            input_type = "search_query" if memory_action == "search" else "search_document"
            input_body = {"input_type": input_type, "texts": [text]}
        else:
            input_body = {"inputText": text}

        response = self.client.invoke_model(
            body=json.dumps(input_body),
            modelId=model_id,
            accept="application/json",
            contentType="application/json",
        )
        response_body = json.loads(response["body"].read())

        if not is_cohere:
            return response_body["embedding"]

        embeddings = response_body["embeddings"]
        if isinstance(embeddings, dict):  # Embed v4
            embeddings = embeddings.get("float") or next(iter(embeddings.values()))
        return embeddings[0]

    AWSBedrockEmbedding.embed = _embed
    AWSBedrockEmbedding._get_embedding = lambda self, text: _embed(self, text)

    _original_inference_config = AWSBedrockLLM._build_inference_config

    def _inference_config_without_sampling(self):
        inference_config = _original_inference_config(self)
        if any(family in (self.config.model or "") for family in NO_SAMPLING_PARAMS):
            for key in ("temperature", "topP", "topK"):
                inference_config.pop(key, None)
        return inference_config

    AWSBedrockLLM._build_inference_config = _inference_config_without_sampling


patch_mem0_for_aoss_and_bedrock()

from mem0 import Memory  # noqa: E402  (imported after the patches above)

config = {
    "embedder": {
        "provider": "aws_bedrock",
        "config": {
            "model": EMBEDDING_MODEL,
            "aws_region": REGION,
            "embedding_dims": EMBEDDING_DIMS,
        },
    },
    "llm": {
        "provider": "aws_bedrock",
        "config": {
            "model": LLM_MODEL,
            "aws_region": REGION,
            "max_tokens": LLM_MAX_TOKENS,
        },
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
        },
    },
}


def build_memory():
    """Initialize mem0 with readable errors for the usual credential failures."""
    try:
        memory = Memory.from_config(config)
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "")
        if code in ("AccessDeniedException", "UnrecognizedClientException"):
            raise SystemExit(
                f"Bedrock rejected the credentials ({code}): {exc}\n"
                f"Check that the caller may invoke {LLM_MODEL} and {EMBEDDING_MODEL} "
                f"in {REGION}, and that no stale AWS_* token is exported."
            ) from exc
        raise
    except NoCredentialsError as exc:
        raise SystemExit(f"No usable AWS credentials: {exc}") from exc

    return memory


def list_memories(memory, user_id):
    """List a user's memories. Uses a match_all query: no embedding or kNN call."""
    return memory.get_all(filters={"user_id": user_id}, top_k=MAX_MEMORIES).get("results", [])


def wait_for_indexing(memory, user_id, expected_ids, max_wait=90, interval=5, quiet=False):
    """AOSS indexing is near-real-time; new documents need a few seconds to show up.

    Polls for the ids that add() reported instead of comparing totals, which would
    be unreliable while deletes from a previous run are still settling. Pass
    ``quiet=True`` to poll without writing progress to stdout (for callers that
    render their own progress, such as chat_memory.py).
    """
    deadline = time.monotonic() + max_wait
    pending = set(expected_ids)
    total = len(pending)

    while True:
        pending -= {mem["id"] for mem in list_memories(memory, user_id) if mem.get("id")}
        if not quiet:
            sys.stdout.write(f"\r  Indexed: {total - len(pending)}/{total}")
            sys.stdout.flush()

        remaining = deadline - time.monotonic()
        if not pending or remaining <= 0:
            break
        time.sleep(min(interval, remaining))

    if not quiet:
        if pending:
            sys.stdout.write(f" - timed out after {max_wait}s, results may be incomplete\n")
        else:
            sys.stdout.write(" - done!       \n")
    return not pending


# --- Example: Store memories from multiple conversations ---
# To clear all memories before running, delete the indices with:
#   bash delete_indices.sh

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

QUERIES = [
    "What kind of movies does Alice like?",
    "What are her food preferences?",
    "What books has she read recently?",
    "Le gustan a Alice las películas de ciencia ficción?",
]

SCORE_THRESHOLD = 0.35
MAX_MEMORIES = 500  # upper bound used when listing a user's memories


def main():
    m = build_memory()

    print("=== Storing memories ===\n")
    stored_any = False
    for i, conv in enumerate((conversation_1, conversation_2, conversation_3), 1):
        events = m.add(conv, user_id=USER_ID).get("results", [])
        for r in events:
            print(f"  [{r.get('event')}] {r.get('memory')}")
        if not events:
            print(f"  [conversation {i}] nothing new - already stored for this user")

        # Wait before the next add(): mem0 searches the existing memories to decide
        # ADD vs UPDATE vs NONE, and with the _refresh patch in place that search
        # cannot see what this run just wrote. Without the wait, overlapping facts
        # from later conversations come back as ADD and the store fills with
        # near-duplicates.
        new_ids = [r["id"] for r in events if r.get("event") == "ADD" and r.get("id")]
        if new_ids:
            stored_any = True
            print(f"  waiting for {len(new_ids)} new memories to be indexed...")
            wait_for_indexing(m, USER_ID, new_ids)
        print()

    if not stored_any:
        print("  (nothing new stored in this run)\n")

    # --- Retrieve memories with semantic search ---
    print("\n=== Searching memories ===\n")
    for query in QUERIES:
        print(f"Q: {query}")
        results = m.search(query, filters={"user_id": USER_ID}, top_k=2, threshold=SCORE_THRESHOLD)
        hits = sorted(
            results.get("results", []),
            key=lambda h: h.get("created_at") or "",
            reverse=True,
        )
        if hits:
            for hit in hits:
                created = (hit.get("created_at") or "")[:10]
                print(f"  -> {hit['memory']} (score: {hit['score']:.3f}, {created})")
        else:
            print("  (no relevant memories found)")
        print()

    # --- List all stored memories for the user ---
    print("=== All memories ===\n")
    memories = sorted(
        list_memories(m, USER_ID),
        key=lambda mem: mem.get("created_at") or "",
        reverse=True,
    )
    for mem in memories:
        print(f"  - {mem['memory']} ({(mem.get('created_at') or '')[:10]})")


if __name__ == "__main__":
    main()
