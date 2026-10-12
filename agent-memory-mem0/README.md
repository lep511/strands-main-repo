# agent-memory-mem0

Persistent memory for [Strands](https://github.com/strands-agents/sdk-python) agents using [Mem0](https://mem0.ai/).

The project contains four independent examples that cover both Mem0 deployment models:

| File | Memory backend | What it shows |
|------|----------------|---------------|
| `main.py` | Mem0 Platform (hosted API) | `MemoryAssistant` class: store / retrieve / list memories, answer generation through a Strands sub-agent |
| `companion_example.py` | Mem0 Platform (hosted API) | Minimal pattern: inject retrieved memories into the system prompt, then store the exchange |
| `open_search_mem0.py` | Self-hosted Mem0 on AWS (OpenSearch Serverless + Bedrock) | Full local `Memory` instance with no Mem0 cloud dependency |
| `chat_memory.py` | Self-hosted (reuses `open_search_mem0.py`) | Interactive REPL rendered with [Rich](https://rich.readthedocs.io/): recall → answer → remember, one turn at a time |

## Requirements

- Python >= 3.13 (`.python-version` pins 3.13)
- [uv](https://docs.astral.sh/uv/)
- A `MEM0_API_KEY` for the hosted examples ([app.mem0.ai](https://app.mem0.ai))
- For `open_search_mem0.py`: AWS credentials, Amazon Bedrock model access, and the AWS CLI

## Installation

```bash
uv sync
cp .env.example .env   # then fill in the real keys
```

### Environment variables

| Variable | Used by | Notes |
|----------|---------|-------|
| `MEM0_API_KEY` | `main.py`, `companion_example.py` | Mem0 Platform API key |
| `GEMINI_API_KEY` | `main.py`, `companion_example.py`, optional | Only needed if you uncomment the `GeminiModel` block |
| `LOG_LEVEL` | `main.py`, `companion_example.py`, optional | Default `INFO` |
| `LOG_FILE` | `main.py`, `companion_example.py`, optional | Adds a file handler next to the stderr handler |
| `AWS_REGION` | `open_search_mem0.py`, `create_cluster.sh`, `delete_indices.sh` | Default `us-east-1`; also picked up by boto3 |
| `OPENSEARCH_HOST` | `open_search_mem0.py`, `delete_indices.sh` | Collection endpoint without the `https://` prefix, printed by `create_cluster.sh`. Required — no default |
| `OPENSEARCH_PORT` | `open_search_mem0.py`, `delete_indices.sh` | Default `443` |
| `OPENSEARCH_COLLECTION` | `open_search_mem0.py`, `create_cluster.sh`, `delete_indices.sh` | Collection / index name, default `mem0` |

All three Python files read `.env` with [python-dotenv](https://github.com/theskumar/python-dotenv).
`open_search_mem0.py` calls `load_dotenv(override=True)` on purpose: `.env` must win over an ambient
`AWS_REGION` pointing somewhere other than the collection, because SigV4 signing has to match the
host's region. It also exports `AWS_DEFAULT_REGION` so the Bedrock clients created inside mem0 land
in the same region. Both shell scripts `source` the `.env` next to them, so Python and Bash always
agree on host, region, and collection.

AWS credentials themselves are not read from `.env` — `open_search_mem0.py` uses the ambient
credential chain via `boto3.Session().get_credentials()`. It fails fast with an explanatory message if
that chain is empty, if `OPENSEARCH_HOST` is unset, or if `OPENSEARCH_HOST` still carries an
`https://` prefix.

By default both Strands examples run with the SDK's default model (Amazon Bedrock). To switch to
Gemini, uncomment the `model = GeminiModel(...)` block and the `model=model` argument.

## Usage

### 1. Hosted Mem0 — memory assistant (`main.py`)

```bash
uv run python main.py
```

Seeds a set of demo memories for `USER_ID = "mem0_user"` and then answers
`"What do you remember about me?"`.

`MemoryAssistant.process_input()` routes on simple keyword rules rather than tool calling:

- starts with `remember `, `note that `, `i want you to know ` → `store_memory()`
- contains a list keyword (`show`, `list`, `display`, `what do you remember`, …) **and** a memory
  keyword (`memory`, `memories`, `mem`) → `list_all_memories()`
- anything else → `retrieve_memories()` (semantic search, `min_score=0.3`, top 5) followed by
  `generate_answer_from_memories()`, which delegates to the `use_agent` tool with a dedicated
  answer-only system prompt and extracts the `Response:` block from the tool result.

### 2. Hosted Mem0 — conversational companion (`companion_example.py`)

```bash
uv run python companion_example.py
```

`chat(user_input, user_id)` searches Mem0 for the top 5 relevant memories, embeds them in the system
prompt of a "Ray, a running coach" agent, runs the turn, then writes both the user and assistant
messages back to Mem0. The first demo call is commented out so that repeated runs exercise recall
(`"What did we discuss before?"`) against memories stored earlier.

### 3. Self-hosted Mem0 on AWS (`open_search_mem0.py`)

Provision the vector store first:

```bash
./create_cluster.sh
```

The script creates the encryption, network (public access), and data access policies for the caller's
IAM role, creates a `VECTORSEARCH` collection named `$OPENSEARCH_COLLECTION` (default `mem0`), waits
for it to become `ACTIVE`, and prints the collection `Host`. Copy that value into `OPENSEARCH_HOST`
in `.env`:

```bash
OPENSEARCH_HOST=xxxxxxxxxxxxxxxxxxxx.us-east-1.aoss.amazonaws.com
```

Then run the example:

```bash
uv run python open_search_mem0.py
```

Endpoint, port, region, and collection name come from `.env`; the model settings are constants at the
top of the file:

- **Embedder** — Bedrock `us.cohere.embed-v4:0`, 1536 dimensions
- **LLM** (memory extraction / consolidation) — Bedrock `us.anthropic.claude-sonnet-5`, max tokens
  `2000`; sampling parameters are deliberately not sent (see the patches below)
- **Vector store** — OpenSearch Serverless over `AWSV4SignerAuth` with service `aoss`

The script stores three conversations for `USER_ID = "alice"`, waiting for AOSS to index each one
before adding the next, runs four semantic queries (including one in Spanish, to show cross-lingual
retrieval) filtered at `SCORE_THRESHOLD = 0.35`, and finally lists every stored memory newest-first.

Waiting *between* conversations rather than once at the end is what keeps the store clean: mem0
decides ADD vs UPDATE vs NONE by searching the existing memories, and with the `_refresh` patch in
place that search cannot see what the same run just wrote. Without the per-conversation wait, the
three conversations produced 12 memories with four near-duplicate pairs; with it, 7 — each fact once.

#### The three compatibility patches

`patch_mem0_for_aoss_and_bedrock()` monkey-patches mem0 before `from mem0 import Memory`:

1. **`OpenSearchDB.__init__`** — AOSS has no `_refresh` API (it answers `404`), so `indices.refresh` is
   stubbed to a no-op on the client of every store the class builds. Patching the class instead of a
   single client matters: mem0 lazily creates a second store, `<collection>_entities`, for entity
   linking, and without the stub its writes fail with
   `Batch entity insert failed: NotFoundError(404)`. Because nothing forces a refresh, newly added
   memories are not immediately searchable; `wait_for_indexing()` polls `m.get_all(...)` for up to
   90 s until the ids returned by `add()` appear. It polls by id rather than by count so that deletes
   still settling from a previous run cannot satisfy the wait early.
2. **`AWSBedrockEmbedding.embed`** — Cohere Embed v4 returns `{"embeddings": {"float": [[...]]}}` while
   mem0 expects `{"embeddings": [[...]]}`. The replacement also sends the Cohere-shaped request body
   (`input_type` / `texts`) for `cohere` model ids, falls back to `inputText` for Titan-style models,
   and selects the input type per action — `search_query` for queries, `search_document` for stored
   memories — because Cohere embeddings are asymmetric.
3. **`AWSBedrockLLM._build_inference_config`** — mem0 always puts `temperature` in the Converse
   `inferenceConfig`, which the current Claude generation rejects with
   ``ValidationException: `temperature` is deprecated for this model``. For the model families listed
   in `NO_SAMPLING_PARAMS`, `temperature` / `topP` / `topK` are dropped.

### 4. Interactive chat on the self-hosted store (`chat_memory.py`)

```bash
uv run python chat_memory.py [user_id]      # user_id defaults to "alice"
```

Importing `open_search_mem0` reuses its patches, environment validation, and model
configuration, so this file only holds the chat loop and the rendering. Each turn runs
recall → answer → remember and prints the stages as separate sections: the recalled
memories with their scores (cyan), the answer as Markdown in a green panel, and the
ADD / UPDATE events mem0 derived from the exchange (magenta).

The agent is created once and its `system_prompt` is rewritten every turn with the freshly
recalled facts; because Strands keeps the message history on the agent, the in-session
thread survives the swap. Commands: `/memories` (a Rich table of everything stored),
`/forget` (deletes every memory for the user, asks first), `/help`, `/exit`.

**Writes never block the prompt.** `MemoryWriter` hands each turn to a single background
worker, so the next question can be typed while the previous exchange is still being stored
and indexed; the prompt shows `(n saving)` while writes are outstanding, finished writes are
rendered on the main thread just before the next prompt, and `/exit` (or Ctrl-D) flushes the
queue instead of dropping it. The worker is deliberately *one* thread: mem0 derives
ADD / UPDATE / NONE from a search over what is already stored, so parallel writes — or a
write starting before the previous one is visible — would reintroduce the duplicates the
per-turn wait prevents. The tradeoff is that a turn's recall may not yet see the previous
turn's facts, which is what the `(n saving)` counter makes visible.

**Only durable user facts are stored.** `MEMORY_RULES` is passed to `m.add()` as `prompt`,
which mem0 renders as a highest-priority `## Custom Instructions` section of its extraction
prompt (the system prompt defining the JSON it parses is left alone). Without it the
assistant's own output becomes memory: a turn recommending two novels stored
*"User was recommended 'The Martian'…"*, which then outranked every real preference on the
next book question. With it, that same turn stores nothing, while a reply like *"I already
read The Martian, and I'm allergic to shellfish"* stores two facts phrased about the user.
To apply the same rules to every example, set `custom_instructions` in the mem0 config
instead of per call.

Console conventions — module-level `Console()`, `console.rule()` per section,
`Panel(Markdown(...))` for results, green/red/cyan by outcome, and
`callback_handler=lambda **kwargs: None` so Strands' own streaming does not fight Rich —
follow the sibling `cedar-auth` project.

#### Resetting the store

```bash
./delete_indices.sh
```

Deletes the `mem0`, `mem0migrations`, and `mem0_entities` indices (prefixed with
`$OPENSEARCH_COLLECTION`) from the host in `.env`. The equivalent one-off with `awscurl`:

```bash
awscurl --service aoss --region us-east-1 -X DELETE "https://<OPENSEARCH_HOST>/mem0"
awscurl --service aoss --region us-east-1 -X DELETE "https://<OPENSEARCH_HOST>/mem0migrations"
awscurl --service aoss --region us-east-1 -X DELETE "https://<OPENSEARCH_HOST>/mem0_entities"
```

## Project layout

```
main.py                 MemoryAssistant (hosted Mem0 + Strands use_agent)
companion_example.py    Minimal memory-in-prompt chat loop
open_search_mem0.py     Self-hosted Mem0: AOSS vector store + Bedrock embedder/LLM
chat_memory.py          Interactive Rich REPL over the self-hosted store
create_cluster.sh       Provisions the AOSS VECTORSEARCH collection and its policies
delete_indices.sh       Drops the mem0 indices to start from a clean slate
.env.example            Template for API keys and the OpenSearch host / region / collection
pyproject.toml          Dependencies (strands-agents, mem0ai[nlp], opensearch-py, rich, …)
```

## Troubleshooting

- **Searches return nothing right after `add()` (self-hosted)** — AOSS indexing is asynchronous and
  the `_refresh` patch disables the usual forced refresh. Wait, or reuse `wait_for_indexing()` in
  `open_search_mem0.py`.
- **`AccessDeniedException` from AOSS** — `create_cluster.sh` grants access to the IAM role of
  whoever ran it. A different role needs to be added to the `mem0-access` data access policy.
- **`KeyError: 'embeddings'` or a dimension mismatch** — the embedding model and `EMBEDDING_DIMS`
  must agree, and changing either requires deleting the existing indices before re-indexing.
- **Bedrock `AccessDeniedException: Authentication failed: Please make sure your API Key is valid`** —
  an `AWS_BEARER_TOKEN_BEDROCK` in the environment takes precedence over SigV4 for every boto3
  `bedrock-runtime` client, including the ones mem0 builds, and those keys are region-scoped.
  `open_search_mem0.py` pops the variable at startup (printing a note) so the ambient role is used
  instead.
- **Bedrock `AccessDeniedException` on invoke, without that message** — request model access for the
  Cohere embedding and Claude models in the Bedrock console of `$AWS_REGION`.
- ``ValidationException: `temperature` is deprecated for this model`` — `LLM_MODEL` points at a
  Claude family that is not covered by `NO_SAMPLING_PARAMS`; add its prefix to that tuple.
