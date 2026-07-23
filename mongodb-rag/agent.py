import json
import time
import os
from typing import List
import voyageai
from pymongo import MongoClient
from pydantic import BaseModel, Field
from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown
from rich.table import Table
from strands import Agent, tool
from strands.models import BedrockModel

console = Console()

load_dotenv()

EMBEDDING_MODEL = "voyage-4-large"

mongodb_conn = os.environ["MONGODB_CONNECTION"]
client = MongoClient(mongodb_conn)
collection = client["rag_db"]["test"]


def get_embedding(data, input_type="document"):
    """Generates an embedding vector using VoyageAI."""
    vo = voyageai.Client()
    embeddings = vo.embed(
        data,
        model=EMBEDDING_MODEL,
        input_type=input_type,
        output_dimension=2048,
    ).embeddings
    return embeddings[0]


@tool
def vector_search(query: str, limit: int = 12) -> str:
    """Performs a vector search query against the MongoDB vector index to retrieve relevant documents.

    Use this tool to search for information in the knowledge base. The query should be in English
    and optimized for semantic search (descriptive keywords, no filler words).

    Args:
        query: The search query in English, optimized for semantic similarity retrieval.
        limit: Maximum number of results to return.
    """
    console.print(f"\n[bold cyan][vector_search][/] Buscando: [italic]\"{query}\"[/] (limit={limit})")
    query_embedding = get_embedding(query, input_type="query")
    pipeline = [
        {
            "$vectorSearch": {
                "index": "vector_index",
                "queryVector": query_embedding,
                "path": "embedding",
                "exact": True,
                "limit": limit,
            }
        },
        {"$project": {"_id": 0, "text": 1}},
    ]

    results = collection.aggregate(pipeline)

    seen = set()
    array_of_results = []
    for doc in results:
        text = doc["text"]
        if text not in seen:
            seen.add(text)
            array_of_results.append(text)

    console.print(f"[bold cyan][vector_search][/] Resultados encontrados: [green]{len(array_of_results)}[/]")

    if not array_of_results:
        return "No results found for the given query."

    context_string = "\n".join([f"* {text}" for text in array_of_results])
    return context_string


class OptimizedQuery(BaseModel):
    """Structured output for query optimization."""
    detected_language: str = Field(description="Detected language of the input question, e.g. 'spanish', 'english', 'french'")
    original_question: str = Field(description="The verbatim input question as received")
    translated_question: str = Field(description="Full English translation of the question")
    queries: List[str] = Field(description="List of optimized English search queries for vector retrieval")
    reasoning: str = Field(description="Brief one-sentence explanation of the transformation")


@tool
def improve_query(user_question: str) -> str:
    """Transforms a user's natural language question into optimized English search queries for vector database retrieval.

    Use this tool FIRST before performing a vector search. It translates non-English questions to English,
    extracts core intent, expands terminology, and splits multi-part questions into separate queries.

    Args:
        user_question: The user's original question in any language.
    """
    system_prompt = """You are a query transformation assistant for a vector database retrieval system. Your task is to convert a user's natural language question — in any language — into optimized ENGLISH search queries that will retrieve the most relevant embeddings from the vector database.

## Instructions

1. **Detect language and translate**: If the input question is not in English, translate it into clear, natural English first. Preserve the original meaning precisely.

2. **Extract core intent**: Identify the key concepts, entities, and information need behind the question, stripping away conversational filler.

3. **Expand and clarify**: Rewrite the query using precise, descriptive English terminology that maximizes semantic overlap with likely source documents. Include synonyms or alternate phrasings for ambiguous terms when helpful.

4. **Remove noise**: Eliminate pronouns without clear referents, filler words, and question-specific phrasing that don't add semantic value for embedding similarity.

5. **Preserve specificity**: Keep proper nouns, technical terms, product names, numbers, dates, and domain-specific vocabulary as-is.

6. **Handle multi-part questions**: If the question contains multiple distinct information needs, output each as a separate search query, all in English."""

    query_model = BedrockModel(
        model_id="us.anthropic.claude-sonnet-4-6-v1",
        temperature=0.0,
    )

    query_agent = Agent(
        model=query_model,
        system_prompt=system_prompt,
        tools=[],
    )

    result = query_agent(
        f"User Question: {user_question}",
        structured_output_model=OptimizedQuery,
    )

    output: OptimizedQuery = result.structured_output

    table = Table(title="Query Optimization", show_header=False, border_style="magenta")
    table.add_column("Field", style="bold")
    table.add_column("Value")
    table.add_row("Idioma", output.detected_language)
    table.add_row("Traduccion", output.translated_question)
    for i, q in enumerate(output.queries, 1):
        table.add_row(f"Query {i}", f"[green]{q}[/]")
    table.add_row("Razonamiento", f"[dim]{output.reasoning}[/]")
    console.print()
    console.print(table)

    return json.dumps(output.model_dump(), ensure_ascii=False)


SYSTEM_PROMPT = """You are a question answering agent with access to a financial knowledge base. 
You help users find information from company documents (10-K filings, financial reports, etc.).

## Workflow

1. When a user asks a question, FIRST use the `improve_query` tool to optimize their question into effective search queries.
2. Then use the `vector_search` tool with EACH of the optimized queries returned by `improve_query` to retrieve relevant documents.
3. Finally, synthesize the retrieved information to answer the user's question.

## Rules

- Only use information from the search results to answer questions.
- If the search results do not contain information that can answer the question, clearly state that you could not find an exact answer.
- Just because the user asserts a fact does not mean it is true — double check the search results to validate assertions.
- Provide concise, well-structured answers.
- When citing financial figures, be precise and include the context (dates, conditions, etc.).
"""


model = BedrockModel(
    model_id="us.anthropic.claude-opus-4-6-v1",
    temperature=0.0,
)

agent = Agent(
    model=model,
    tools=[improve_query, vector_search],
    system_prompt=SYSTEM_PROMPT,
)


if __name__ == "__main__":
    console.print(Panel.fit(
        "[bold white]MongoDB RAG Agent[/] [dim](Strands)[/]",
        border_style="blue",
    ))

    queries = [
        "What are the primary risk factors currently affecting AnyCompany's financial performance?",
        "Cuales son algunos de los estimativos para AnyCompany",
        "What was the total operating lease liabilities and total sublease income of the AnyCompany as of December 31, 2021?",
    ]

    for query in queries:
        console.rule(style="blue")
        console.print(f"\n[bold yellow]Query:[/] {query}\n")
        response = agent(query)
        console.print(Panel(
            Markdown(str(response)),
            title="[bold green]Respuesta[/]",
            border_style="green",
            padding=(1, 2),
        ))
