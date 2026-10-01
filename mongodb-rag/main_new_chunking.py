import logging
import pymupdf4llm
from langchain_text_splitters import MarkdownHeaderTextSplitter, RecursiveCharacterTextSplitter
import voyageai
import time
from pymongo import MongoClient
from pymongo.operations import SearchIndexModel
from dotenv import load_dotenv
import os

logging.getLogger("pypdf").setLevel(logging.ERROR)
load_dotenv()

# Specify the embedding model
EMBEDDING_MODEL = "voyage-4-large"
EMBEDDING_CONTEXT_MODEL = "voyage-context-4"

# Define a function to generate embeddings
def get_embedding(data, input_type="document"):
    voyage_api_key = os.getenv("VOYAGE_API_KEY")
    delay=0.0 # For too many request problems
    vo = voyageai.Client()
    embeddings = vo.embed(
        data,
        model=EMBEDDING_MODEL,
        input_type=input_type,
        output_dimension=2048,

    ).embeddings
    time.sleep(delay)
    return embeddings[0]

def load_pdf_file():
    print("[1/4] Cargando PDF...")
    documents = pymupdf4llm.to_markdown("files/AnyCompany_financial_10K.pdf")
    print(f"      Cantidad de caracteres: {len(documents)}")

    print("[2/4] Dividiendo texto en chunks...")
    headers_to_split_on = [
        ("#", "Header 1"),
        ("##", "Header 2"),
        ("###", "Header 3"),
    ]

    markdown_splitter = MarkdownHeaderTextSplitter(headers_to_split_on=headers_to_split_on)
    md_header_splits = markdown_splitter.split_text(documents)

    print(f"      Total de chunks generados: {len(md_header_splits)}")
    return md_header_splits


def save_to_mongodb(documents):
    print("[3/4] Conectando a MongoDB...")
    mongodb_conn = os.environ["MONGODB_CONNECTION"]
    client = MongoClient(mongodb_conn)
    collection = client["rag_db"]["test"]
    print("      Conexión establecida.")

    print(f"[3/4] Generando embeddings para {len(documents)} chunks...")
    docs_to_insert = []
    for i, doc in enumerate(documents):
        embedding = get_embedding(doc.page_content)
        docs_to_insert.append({"text": doc.page_content, "embedding": embedding})
        if (i + 1) % 10 == 0 or (i + 1) == len(documents):
            print(f"      Progreso: {i + 1}/{len(documents)} embeddings generados")

    print("[4/4] Insertando documentos en MongoDB...")
    try:
        result = collection.insert_many(docs_to_insert)
        print(f"      Insertados {len(result.inserted_ids)} documentos correctamente.")
    except Exception as e:
        print(f"      Error al insertar documentos: {e}")
    finally:
        client.close()
        print("      Conexión a MongoDB cerrada.")


def create_mongodb_index():
    print("[+] Creando índice vectorial en MongoDB...")
    mongodb_conn = os.environ["MONGODB_CONNECTION"]
    client = MongoClient(mongodb_conn)
    collection = client["rag_db"]["test"]

    index_name = "vector_index"
    search_index_model = SearchIndexModel(
        definition={
            "fields": [
                {
                    "type": "vector",
                    "numDimensions": 2048,
                    "path": "embedding",
                    "similarity": "cosine",
                }
            ]
        },
        name=index_name,
        type="vectorSearch",
    )
    collection.create_search_index(model=search_index_model)
    print(f"    Índice '{index_name}' creado. Esperando a que esté listo...")

    predicate = lambda index: index.get("queryable") is True

    while True:
        indices = list(collection.list_search_indexes(index_name))
        if len(indices) and predicate(indices[0]):
            break
        time.sleep(5)
    print(f"    Índice '{index_name}' listo para consultas.")
    client.close()
    print("    Conexión a MongoDB cerrada.")


def main():
    print("=" * 50)
    print("MongoDB RAG Pipeline")
    print("=" * 50)

    documents = load_pdf_file()

    # voyage_context(documents)

    save_to_mongodb(documents)

    print("=" * 50)
    print("Create Vector Index")
    print("=" * 50)
    create_mongodb_index()

    print("=" * 50)
    print("Pipeline completado.")
    print("=" * 50)


if __name__ == "__main__":
    main()
