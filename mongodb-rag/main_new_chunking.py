"""Pipeline RAG: PDF -> Markdown -> chunks por sección -> embeddings Voyage -> MongoDB Atlas."""

import os
import re
import time
from functools import lru_cache

import pymupdf
import pymupdf4llm
import tiktoken
import voyageai
from dotenv import load_dotenv
from langchain_text_splitters import (
    MarkdownHeaderTextSplitter,
    RecursiveCharacterTextSplitter,
)
from pymongo import MongoClient
from pymongo.errors import OperationFailure
from pymongo.operations import SearchIndexModel

load_dotenv()

PDF_PATH = "files/AnyCompany_financial_10K.pdf"

# Specify the embedding model
EMBEDDING_MODEL = "voyage-4-large"
EMBEDDING_DIMENSION = 2048

# Límites por request de la API de Voyage. Nos quedamos holgados respecto al
# máximo para no depender del modelo concreto.
MAX_BATCH_TEXTS = 128
MAX_BATCH_TOKENS = 100_000

# MarkdownHeaderTextSplitter no acota el tamaño del chunk: una sección larga del
# 10-K se subdivide después con estos topes (tokens).
CHUNK_SIZE = 512
CHUNK_OVERLAP = 64

HEADERS_TO_SPLIT_ON = [
    ("#", "Header 1"),
    ("##", "Header 2"),
    ("###", "Header 3"),
]

DB_NAME = "rag_db"
COLLECTION_NAME = "test"
INDEX_NAME = "vector_index"
INDEX_WAIT_TIMEOUT = 300

# El texto del PDF ya traía marcas markdown, así que los encabezados salen como
# '## ### Table: Market Risks' o '# **EXHIBITS...**'.
HEADER_PREFIX = re.compile(r"^[#\s]+")
HEADER_EMPHASIS = re.compile(r"[*~]+")

# PyMuPDF lee un tachado falso en el PDF y parte palabras: 'Any ~~Com~~ pany'.
FALSE_STRIKETHROUGH = re.compile(r"\s?~~(.*?)~~\s?")
WHITESPACE = re.compile(r"\s+")


@lru_cache(maxsize=1)
def get_voyage_client():
    """Cliente único y reutilizado. max_retries activa backoff ante 429 / 5xx."""
    return voyageai.Client(max_retries=5)


@lru_cache(maxsize=1)
def get_token_encoder():
    return tiktoken.encoding_for_model("gpt-4")


def count_tokens(text):
    return len(get_token_encoder().encode(text, disallowed_special=()))


def iter_batches(texts):
    """Agrupa textos respetando los límites de textos y de tokens por request."""
    batch = []
    batch_tokens = 0

    for text in texts:
        tokens = count_tokens(text)
        if batch and (
            len(batch) >= MAX_BATCH_TEXTS or batch_tokens + tokens > MAX_BATCH_TOKENS
        ):
            yield batch
            batch, batch_tokens = [], 0
        batch.append(text)
        batch_tokens += tokens

    if batch:
        yield batch


def get_embeddings(texts, input_type="document"):
    """Genera embeddings en lotes: la API acepta varios textos por request."""
    vo = get_voyage_client()
    embeddings = []

    for batch in iter_batches(texts):
        embeddings.extend(
            vo.embed(
                batch,
                model=EMBEDDING_MODEL,
                input_type=input_type,
                output_dimension=EMBEDDING_DIMENSION,
            ).embeddings
        )
        print(f"      Progreso: {len(embeddings)}/{len(texts)} embeddings generados")

    return embeddings


def unique_page_numbers():
    """Páginas sin repetir: este PDF trae cada una dos veces.

    Se descartan antes de generar el markdown, no después: con las dos copias
    presentes, pymupdf4llm detecta los encabezados de forma distinta en cada una
    y el mismo contenido termina en secciones y chunks diferentes.
    """
    seen = set()
    numbers = []

    with pymupdf.open(PDF_PATH) as doc:
        for number, page in enumerate(doc):
            text = WHITESPACE.sub(" ", page.get_text()).strip()
            if text and text in seen:
                continue
            seen.add(text)
            numbers.append(number)

    return numbers


def load_pdf_file():
    print("[1/5] Cargando PDF...")
    pages = unique_page_numbers()
    print(f"      Páginas únicas: {len(pages)}")
    markdown = FALSE_STRIKETHROUGH.sub(
        r"\1", pymupdf4llm.to_markdown(PDF_PATH, pages=pages)
    )
    print(f"      Cantidad de caracteres: {len(markdown)}")
    return markdown


def clean_header(text):
    return HEADER_EMPHASIS.sub("", HEADER_PREFIX.sub("", text)).strip()


def section_breadcrumb(metadata):
    """'Header 1 > Header 2 > Header 3' con los encabezados presentes."""
    headers = [
        clean_header(metadata[key])
        for _, key in HEADERS_TO_SPLIT_ON
        if metadata.get(key)
    ]
    return " > ".join(header for header in headers if header)


def chunk_markdown(markdown):
    print("[2/5] Dividiendo texto en chunks...")

    header_splitter = MarkdownHeaderTextSplitter(
        headers_to_split_on=HEADERS_TO_SPLIT_ON
    )
    sections = header_splitter.split_text(markdown)
    print(f"      Secciones por encabezado: {len(sections)}")

    size_splitter = RecursiveCharacterTextSplitter.from_tiktoken_encoder(
        model_name="gpt-4",
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        disallowed_special=(),
    )

    chunks = []
    seen = set()
    for section in sections:
        breadcrumb = section_breadcrumb(section.metadata)
        for piece in size_splitter.split_text(section.page_content):
            if not piece.strip():
                continue
            # El breadcrumb va dentro del texto que se embebe: el splitter mueve
            # los encabezados al metadata y el chunk perdería su contexto.
            text = f"{breadcrumb}\n\n{piece}" if breadcrumb else piece
            # El PDF trae cada página dos veces (la segunda mitad repite la
            # primera), así que sin esto se embebe y se guarda todo duplicado.
            if text in seen:
                continue
            seen.add(text)
            chunks.append(
                {
                    "text": text,
                    "section": breadcrumb,
                    "headers": {
                        key: clean_header(value)
                        for key, value in section.metadata.items()
                    },
                }
            )

    print(f"      Total de chunks generados: {len(chunks)}")
    return chunks


def get_collection(client):
    return client[DB_NAME][COLLECTION_NAME]


def save_to_mongodb(client, chunks, embeddings):
    collection = get_collection(client)

    print("[4/5] Limpiando la colección antes de cargar los nuevos chunks...")
    deleted = collection.delete_many({}).deleted_count
    print(f"      Documentos eliminados: {deleted}")

    docs_to_insert = [
        {
            "text": chunk["text"],
            "embedding": embedding,
            "section": chunk["section"],
            "headers": chunk["headers"],
            "chunk_index": i,
            "source": os.path.basename(PDF_PATH),
        }
        for i, (chunk, embedding) in enumerate(zip(chunks, embeddings))
    ]

    print(f"      Insertando {len(docs_to_insert)} documentos en MongoDB...")
    result = collection.insert_many(docs_to_insert)
    print(f"      Insertados {len(result.inserted_ids)} documentos correctamente.")


def vector_field(definition):
    """Parte comparable de la definición: Atlas añade sus propios defaults."""
    for field in definition.get("fields", []):
        if field.get("type") == "vector":
            return {
                key: field.get(key)
                for key in ("path", "numDimensions", "similarity")
            }
    return None


def create_mongodb_index(client):
    print("[5/5] Creando el índice vectorial en MongoDB...")
    collection = get_collection(client)

    definition = {
        "fields": [
            {
                "type": "vector",
                "numDimensions": EMBEDDING_DIMENSION,
                "path": "embedding",
                "similarity": "cosine",
            }
        ]
    }

    existing = next(iter(collection.list_search_indexes(INDEX_NAME)), None)
    try:
        if existing is None:
            collection.create_search_index(
                model=SearchIndexModel(
                    definition=definition, name=INDEX_NAME, type="vectorSearch"
                )
            )
            print(f"      Índice '{INDEX_NAME}' creado. Esperando a que esté listo...")
        elif vector_field(existing.get("latestDefinition", {})) != vector_field(
            definition
        ):
            collection.update_search_index(name=INDEX_NAME, definition=definition)
            print(
                f"      Índice '{INDEX_NAME}' actualizado. Esperando a que esté listo..."
            )
        else:
            print(f"      Índice '{INDEX_NAME}' ya existe con la definición esperada.")
    except OperationFailure as error:
        print(f"      Error al crear el índice: {error}")
        print("      Verifica que el cluster soporte Atlas Vector Search.")
        return

    deadline = time.monotonic() + INDEX_WAIT_TIMEOUT
    while True:
        index = next(iter(collection.list_search_indexes(INDEX_NAME)), None)
        if index and index.get("queryable"):
            print(f"      Índice '{INDEX_NAME}' listo para consultas.")
            return
        if time.monotonic() > deadline:
            print(
                f"      El índice '{INDEX_NAME}' sigue construyéndose tras "
                f"{INDEX_WAIT_TIMEOUT}s. Revisa su estado en Atlas."
            )
            return
        time.sleep(5)


def main():
    print("=" * 50)
    print("MongoDB RAG Pipeline")
    print("=" * 50)

    markdown = load_pdf_file()
    chunks = chunk_markdown(markdown)

    # Los embeddings se generan antes de tocar la colección: si falla la API, la
    # colección actual queda intacta.
    print(f"[3/5] Generando embeddings para {len(chunks)} chunks...")
    embeddings = get_embeddings([chunk["text"] for chunk in chunks])

    print("      Conectando a MongoDB...")
    with MongoClient(os.environ["MONGODB_CONNECTION"]) as client:
        save_to_mongodb(client, chunks, embeddings)
        create_mongodb_index(client)
    print("      Conexión a MongoDB cerrada.")

    print("=" * 50)
    print("Pipeline completado.")
    print("=" * 50)


if __name__ == "__main__":
    main()
