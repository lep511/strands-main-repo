import os
import sys
import boto3
from strands import Agent, ModelRetryStrategy

KNOWLEDGE_BASE_ID = os.environ.get("STRANDS_KNOWLEDGE_BASE_ID")
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
if not KNOWLEDGE_BASE_ID:
    print("STRANDS_KNOWLEDGE_BASE_ID environment variable is not set!")
    print("Please set the STRANDS_KNOWLEDGE_BASE_ID environment variable.\n")
    sys.exit(0)

SYSTEM_PROMPT = """You are a knowledge base assistant. You ONLY answer based on the provided knowledge base results. You NEVER invent, assume, or add information that is not explicitly present in the results.

Rules:
1. ONLY use information from the knowledge base results below. Do not use your own knowledge.
2. If the results do not contain enough information to answer the question, say: "No tengo información suficiente en la base de conocimientos para responder esa pregunta."
3. Do not mention document IDs, scores, or metadata.
4. Be direct and concise.
5. Answer in the same language as the user's question.
6. If the results are only partially relevant, answer only the part you can support with the documents and explicitly state what you cannot confirm."""


def retrieve_from_kb(query: str, max_results: int = 5, min_score: float = 0.3):
    """Retrieve documents from the managed knowledge base."""
    client = boto3.client("bedrock-agent-runtime", region_name=AWS_REGION)

    response = client.retrieve(
        retrievalQuery={"text": query},
        knowledgeBaseId=KNOWLEDGE_BASE_ID,
        retrievalConfiguration={
            "managedSearchConfiguration": {
                "numberOfResults": max_results
            }
        },
    )
    results = response.get("retrievalResults", [])
    filtered = [r for r in results if r.get("score", 0) >= min_score]

    if not filtered:
        return None

    output_parts = []
    for i, r in enumerate(filtered, 1):
        score = r.get("score", 0)
        text = r.get("content", {}).get("text", "")
        output_parts.append(f"Result {i} (score: {score:.4f}):\n{text}")

    return "\n\n---\n\n".join(output_parts)


def run_kb_agent(query):
    """Process a user query against the knowledge base."""
    kb_results = retrieve_from_kb(query, max_results=5, min_score=0.3)

    if kb_results is None:
        print("\nNo relevant information found in the knowledge base.")
        return

    print("\n--- Context retrieved from knowledge base ---")
    print(kb_results)
    print("--- End of context ---\n")
    
    retry_strategy=ModelRetryStrategy(
        max_attempts=3,      # Total attempts (including first try)
        initial_delay=2,     # Seconds before first retry
        max_delay=60         # Cap on backoff delay
    )

    agent = Agent(
        system_prompt=SYSTEM_PROMPT, 
        retry_strategy=retry_strategy,
        tools=[]
    )
    
    agent(
        f"User question: \"{query}\"\n\n"
        f"Knowledge base results:\n{kb_results}"
    )


def main():
    print("\n🧠 Knowledge Base Agent 🧠\n")
    print("This agent helps you retrieve information from your knowledge base.")
    print("Type your request below or 'exit' to quit:")

    while True:
        try:
            user_input = input("\n> ")
            if user_input.lower() in ["exit", "quit"]:
                print("\nGoodbye! 👋")
                break

            if not user_input.strip():
                continue

            print("Processing...")
            run_kb_agent(user_input)

        except KeyboardInterrupt:
            print("\n\nExecution interrupted. Exiting...")
            break
        except Exception as e:
            print(f"\nAn error occurred: {str(e)}")


if __name__ == "__main__":
    main()
