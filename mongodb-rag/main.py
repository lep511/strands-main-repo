import logging
from pypdf import PdfReader
from langchain_text_splitters import RecursiveCharacterTextSplitter
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
    reader = PdfReader("files/AnyCompany_financial_10K.pdf")
    documents = [page.extract_text() for page in reader.pages]
    print(f"      Páginas extraídas: {len(documents)}")

    print("[2/4] Dividiendo texto en chunks...")
    from langchain_text_splitters import RecursiveCharacterTextSplitter
    separators = ["#", "##", "###"]
    text_splitter = RecursiveCharacterTextSplitter.from_tiktoken_encoder(
        model_name="gpt-4", separators=separators, chunk_size=350, chunk_overlap=0
    )

    chunked_docs = []

    chunk_id = 0
    for page in documents:
        chunks = text_splitter.split_text(page)
        for chunk in chunks:
            text = chunk.replace("#", "")
            chunked_docs.append(text)

    print(f"      Total de chunks generados: {len(chunked_docs)}")
    return chunked_docs

# def embeddings_voyage_context(documents):
#     print("[3/4] Generando embeddings contextualizados con voyage-context-4...")
#     voyage_api_key = os.getenv("VOYAGE_API_KEY")
#     vo = voyageai.Client()
#     document = " ".join(documents)
#     print(f"      Documento unificado: {len(document)} caracteres")

#     result = vo.contextualized_embed(
#         inputs=[document],
#         model=EMBEDDING_CONTEXT_MODEL,
#         input_type="document",
#         enable_auto_chunking=True,
#         chunk_size=512,
#         chunk_overlap=64,
#         output_dimension=2048,
#     )

#     chunk_embeddings = result.results[0].embeddings
#     chunk_texts = result.results[0].chunk_texts
#     print(f"      Total de chunk embeddings: {len(chunk_embeddings)}")
#     print("[3/4] Embeddings contextualizados generados correctamente.")

def save_to_mongodb(documents):
    print("[3/4] Conectando a MongoDB...")
    mongodb_conn = os.environ["MONGODB_CONNECTION"]
    client = MongoClient(mongodb_conn)
    collection = client["rag_db"]["test"]
    print("      Conexión establecida.")

    print(f"[3/4] Generando embeddings para {len(documents)} chunks...")
    docs_to_insert = []
    for i, doc in enumerate(documents):
        embedding = get_embedding(doc)
        docs_to_insert.append({"text": doc, "embedding": embedding})
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
