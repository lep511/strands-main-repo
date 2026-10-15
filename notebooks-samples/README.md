# notebooks-samples

Notebooks de [Strands Agents](https://strandsagents.com) con servidores MCP
locales. El proyecto se gestiona con [uv](https://docs.astral.sh/uv/): las
dependencias viven en `pyproject.toml` / `uv.lock` y el entorno se crea en
`.venv`.

## Requisitos

| | |
|---|---|
| Python | 3.13 (fijado en `.python-version`; `uv` lo descarga si falta) |
| uv | 0.13 o superior |
| Node.js | para el servidor MCP de Brave, que se ejecuta vía `npx` |
| AWS | credenciales con acceso a Amazon Bedrock en la región que uses |

## Instalación

```bash
uv sync
```

Esto crea `.venv` con todo lo declarado en `uv.lock`, incluido `ipykernel`.

### Variables de entorno

Copia tus claves a un `.env` en esta carpeta (los notebooks lo leen con
`python-dotenv`):

```bash
BRAVE_API_KEY=...        # obligatorio para los dos notebooks
MONGODB_CONNECTION=...   # obligatorio para mongodb_text_search.ipynb (cluster Atlas)
AWS_REGION=us-west-2     # opcional, es el valor por defecto
```

## Instalar el kernel en Jupyter Notebook con uv

El `.venv` que crea `uv` **no aparece como kernel** en Jupyter ni en VS Code
hasta que lo registras. Para hacerlo, ejecuta `ipykernel` *dentro* del entorno
del proyecto (eso es lo que hace `uv run`) y pídele que se instale como
kernelspec:

```bash
uv run python -m ipykernel install --user \
  --name mi-proyecto \
  --display-name "Python (mi-proyecto)"
```

Qué hace cada parte:

| Parte | Para qué sirve |
|---|---|
| `uv run` | ejecuta el comando con el `python` de `.venv`, así que el kernel que se registra es el del proyecto (no hace falta `source .venv/bin/activate`) |
| `python -m ipykernel install` | el instalador de kernelspecs que trae `ipykernel`, ya incluido como dependencia |
| `--user` | lo instala en tu usuario (`~/.local/share/jupyter/kernels/`), sin `sudo` y sin tocar el sistema |
| `--name mi-proyecto` | identificador interno del kernel. Es el que los notebooks guardan en sus metadatos, así que **conviene no cambiarlo**: `search_brave.ipynb` ya apunta a `mi-proyecto` y se abre con el kernel correcto sin seleccionarlo a mano |
| `--display-name "Python (mi-proyecto)"` | el nombre visible en el selector de kernels de Jupyter o VS Code |

Comprueba que quedó registrado:

```bash
uv run jupyter kernelspec list
```

```
Available kernels:
  python3        .../notebooks-samples/.venv/share/jupyter/kernels/python3
  mi-proyecto    /home/<usuario>/.local/share/jupyter/kernels/mi-proyecto
```

El `kernel.json` de `mi-proyecto` apunta al intérprete del proyecto
(`.../notebooks-samples/.venv/bin/python`), que es justamente lo que permite
abrir los notebooks desde un Jupyter instalado aparte y aun así tener
disponibles `strands-agents`, `mcp` y el resto de las dependencias.

Como la ruta queda escrita en el kernelspec, hay que **volver a ejecutar el
comando** si mueves o recreas el `.venv` (por ejemplo tras un `rm -rf .venv &&
uv sync`). Para darlo de baja:

```bash
uv run jupyter kernelspec uninstall mi-proyecto
```

## Abrir los notebooks

**VS Code** — abre el `.ipynb` y elige *Python (mi-proyecto)* en el selector de
kernel, arriba a la derecha. No necesitas instalar nada más.

**JupyterLab** — no es una dependencia del proyecto, así que instálalo primero
en el entorno:

```bash
uv add --dev jupyterlab
uv run jupyter lab
```

O, sin añadirlo al proyecto, lánzalo en un entorno aislado y selecciona el
kernel `Python (mi-proyecto)` dentro del notebook:

```bash
uvx --from jupyterlab jupyter lab
```

## `search_brave.ipynb` — dos servidores MCP por stdio

Un agente con búsqueda web (servidor MCP de Brave, TypeScript vía `npx`) y
cálculo ([`calculator_mcp.py`](calculator_mcp.py), Python), más los gestores de
conversación de Strands (`SlidingWindowConversationManager` y
`SummarizingConversationManager`) para mantener un chat largo dentro de la
ventana de contexto. Necesita `BRAVE_API_KEY` en `.env`.

La última sección usa un `context_window_limit` pequeño a propósito, para que la
compresión se dispare en un chat de cuatro turnos en vez de después de cientos.

## `mongodb_text_search.ipynb` — RAG sin embeddings

El agente de [`mongodb-rag`](../mongodb-rag) sobre el mismo 10-K de AnyCompany,
pero sin modelo de embeddings: los chunks se guardan como texto plano en
`rag_db.text_search` y se recuperan con Atlas Search (`$search`, BM25 con el
analizador `lucene.english`). Una segunda tool consulta la API de Brave Search
directamente con `httpx`, sin servidor MCP ni Node.js. Necesita
`MONGODB_CONNECTION` y `BRAVE_API_KEY` en `.env`.

La primera ejecución convierte el PDF (`../mongodb-rag/files/`) y crea el índice
`text_index`, lo que toma cerca de un minuto. Las siguientes reutilizan lo que
ya está en el cluster. Pon `REBUILD = True` si cambias el chunking o la
definición del índice. `rag_db.test` y su índice vectorial no se tocan.

## Modelo

`search_brave.ipynb` usa Amazon Bedrock con `us.anthropic.claude-sonnet-5`, y
`mongodb_text_search.ipynb` con `us.anthropic.claude-sonnet-5-5`. Los dos usan
`AWS_REGION` (por defecto `us-west-2`).

## Problemas frecuentes

**El notebook no encuentra `strands` / `mcp`** — está corriendo con otro kernel.
Selecciona *Python (mi-proyecto)*, o reinstala el kernelspec si recreaste el
`.venv`.

**`jupyter: command not found` tras `uv sync`** — `jupyterlab` no es una
dependencia del proyecto; instálalo como se indica más arriba. El CLI `jupyter`
que sí trae el entorno solo cubre subcomandos como `kernelspec`.

**Errores de Bedrock fuera de `us-west-2`** — si tienes `AWS_BEARER_TOKEN_BEDROCK`
exportado, boto3 lo usa en lugar de tus credenciales normales y solo funciona en
`us-west-2`. Haz `unset AWS_BEARER_TOKEN_BEDROCK` para volver a SigV4.
