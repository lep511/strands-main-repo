import os
import sys
from pypdf import PdfReader
from pymongo import MongoClient
from pymongo.server_api import ServerApi
from langchain_text_splitters import RecursiveCharacterTextSplitter
from dotenv import load_dotenv
import voyageai
from strands import Agent, tool
from typing import List, Dict
from utils import create_search_index, check_index_ready

load_dotenv()

# --- Config ---
PDF_PATH = os.path.join(os.path.dirname(__file__), "..", "files", "2024-Amazon-Shareholder-Letter.pdf")
DB_NAME = "mongodb_genai_devday_rag"
COLLECTION_NAME = "amazon_shareholder_letter"
INDEX_NAME = "vector_index"

# --- MongoDB ---
mongodb_client = MongoClient(os.environ["MONGODB_URI"], server_api=ServerApi("1"))
collection = mongodb_client[DB_NAME][COLLECTION_NAME]

# --- Voyage AI ---
voyageai.api_key = os.environ["VOYAGE_API_KEY"]
vo = voyageai.Client()

# --- Text splitter (same as notebook) ---
separators = ["\n\n", "\n", " ", "", "#", "##", "###"]
text_splitter = RecursiveCharacterTextSplitter.from_tiktoken_encoder(
    model_name="gpt-4", separators=separators, chunk_size=200, chunk_overlap=30
)


def extract_pdf_pages(file_path: str) -> List[Dict]:
    reader = PdfReader(file_path)
    pages = []
    for i, page in enumerate(reader.pages):
        text = page.extract_text() or ""
        if text.strip():
            pages.append({"page_number": i + 1, "content": text})
    return pages


def get_embeddings(content: List[str], input_type: str):
    embds_obj = vo.contextualized_embed(inputs=[content], model="voyage-context-4", input_type=input_type)
    if input_type == "document":
        return [emb for r in embds_obj.results for emb in r.embeddings]
    return embds_obj.results[0].embeddings[0]


def ingest_pdf():
    print(f"Reading PDF: {PDF_PATH}")
    pages = extract_pdf_pages(PDF_PATH)
    print(f"Extracted {len(pages)} pages")

    print("Chunking and embedding...")
    embedded_docs = []
    for page in pages:
        chunks = text_splitter.split_text(page["content"])
        if not chunks:
            continue
        chunk_embeddings = get_embeddings(chunks, "document")
        for chunk, embedding in zip(chunks, chunk_embeddings):
            embedded_docs.append({
                "page_number": page["page_number"],
                "body": chunk,
                "embedding": embedding,
                "source": "2024-Amazon-Shareholder-Letter.pdf",
            })

    print(f"Generated {len(embedded_docs)} chunks with embeddings")

    collection.delete_many({})
    collection.insert_many(embedded_docs)
    print(f"Ingested {collection.count_documents({})} documents into {COLLECTION_NAME}")

    model = {
        "name": INDEX_NAME,
        "type": "vectorSearch",
        "definition": {
            "fields": [
                {
                    "type": "vector",
                    "path": "embedding",
                    "numDimensions": 1024,
                    "similarity": "cosine",
                }
            ]
        },
    }
    create_search_index(collection, INDEX_NAME, model)
    check_index_ready(collection, INDEX_NAME)
    print("Ready for queries!\n")


def vector_search(user_query: str) -> List[Dict]:
    query_embedding = get_embeddings([user_query], "query")
    pipeline = [
        {
            "$vectorSearch": {
                "index": INDEX_NAME,
                "queryVector": query_embedding,
                "path": "embedding",
                "numCandidates": 150,
                "limit": 5,
            }
        },
        {
            "$project": {
                "_id": 0,
                "body": 1,
                "page_number": 1,
                "score": {"$meta": "vectorSearchScore"},
            }
        },
    ]
    return list(collection.aggregate(pipeline))


@tool
def search_amazon_letter(query: str) -> str:
    """Search the 2024 Amazon Shareholder Letter for information relevant to the query.
    Args:
        query: The search query to find relevant passages in the letter.
    """
    results = vector_search(query)
    if not results:
        return "No relevant passages found."
    passages = []
    for r in results:
        passages.append(f"[Page {r['page_number']}, score: {r['score']:.3f}]\n{r['body']}")
    return "\n\n---\n\n".join(passages)


SYSTEM_PROMPT = """You are a research assistant specialized in the 2024 Amazon Shareholder Letter.
Use the search_amazon_letter tool to find relevant passages before answering.
Always cite the page number when referencing information from the document.
If the information is not in the document, say so."""

agent = Agent(
    model="us.anthropic.claude-sonnet-4-6",
    tools=[search_amazon_letter],
    system_prompt=SYSTEM_PROMPT,
    callback_handler=None,
)


if __name__ == "__main__":
    ingest_pdf()

    print("=" * 60)
    print("Amazon Shareholder Letter RAG - type 'exit' to quit")
    print("=" * 60 + "\n")

    while True:
        query = input("Question: ").strip()
        if query.lower() in ("exit", "quit", "q", ""):
            break
        response = agent(query)
        print(f"\n{response}\n")
