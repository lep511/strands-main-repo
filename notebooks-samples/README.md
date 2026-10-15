# notebooks-samples

Notebooks de agentes con [Strands Agents](https://strandsagents.com) y Amazon
Bedrock: uno con servidores MCP locales y tres sobre MongoDB Atlas **sin
embeddings**, cada uno con una forma distinta de recuperar datos y con Brave
Search para lo que la base no tiene. El proyecto se gestiona con
[uv](https://docs.astral.sh/uv/): las dependencias viven en `pyproject.toml` /
`uv.lock` y el entorno se crea en `.venv`.

| Notebook | Datos | Recuperación | Brave Search |
|---|---|---|---|
| [`search_brave.ipynb`](#search_braveipynb--dos-servidores-mcp-por-stdio) | web | — | servidor MCP vía `npx` |
| [`mongodb_text_search.ipynb`](#mongodb_text_searchipynb--rag-sin-embeddings) | PDF 10-K → `rag_db.text_search` | Atlas Search (`$search`, BM25) | API directa con `httpx` |
| [`mongodb_movies_brave.ipynb`](#mongodb_movies_braveipynb--catálogo-de-películas--brave) | `sample_mflix.movies` | `find` + índice de texto nativo (`$text`) | API directa con `httpx` |
| [`mongodb_analytics_brave.ipynb`](#mongodb_analytics_braveipynb--agregaciones-sobre-sample_analytics) | `sample_analytics` | pipelines de agregación (`$lookup`, `$group`) | API directa con `httpx` |

Los tres notebooks `mongodb_*` siguen la misma regla: **la base de datos decide
qué existe**. El agente solo busca en la web para ampliar algo que ya encontró
en MongoDB, y si no está, lo dice en vez de buscarlo.

## Requisitos

| | |
|---|---|
| Python | 3.13 (fijado en `.python-version`; `uv` lo descarga si falta) |
| uv | 0.13 o superior |
| AWS | credenciales con acceso a Amazon Bedrock en la región que uses |
| Brave Search | una API key de <https://api-dashboard.search.brave.com> (el plan gratuito basta: los notebooks espacian las llamadas a 1/s) |
| Node.js | solo para `search_brave.ipynb`, cuyo servidor MCP de Brave se ejecuta vía `npx` |
| MongoDB Atlas | solo para los notebooks `mongodb_*`: un cluster (el M0 gratuito sirve) con el **Sample Dataset** cargado (*Load Sample Dataset* en la consola de Atlas), que trae `sample_mflix` y `sample_analytics` |

## Instalación

```bash
uv sync
```

Esto crea `.venv` con todo lo declarado en `uv.lock`, incluido `ipykernel`.

### Variables de entorno

Copia [`.env.example`](.env.example) a `.env` en esta carpeta y completa tus
claves (los notebooks lo leen con `python-dotenv`; `.env` está en el
`.gitignore`):

```bash
BRAVE_API_KEY=...        # obligatorio para todos los notebooks
MONGODB_CONNECTION=...   # obligatorio para los notebooks mongodb_* (cluster Atlas)
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
| `--name mi-proyecto` | identificador interno del kernel. Es el que los notebooks guardan en sus metadatos, así que **conviene no cambiarlo**: los cuatro notebooks ya apuntan a `mi-proyecto` y se abren con el kernel correcto sin seleccionarlo a mano |
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

Los notebooks se guardan con sus salidas, así que puedes leer las respuestas de
los agentes sin ejecutarlos.

## `search_brave.ipynb` — dos servidores MCP por stdio

Un agente con búsqueda web (servidor MCP de Brave, TypeScript vía `npx`) y
cálculo ([`calculator_mcp.py`](calculator_mcp.py), Python), más los gestores de
conversación de Strands (`SlidingWindowConversationManager` y
`SummarizingConversationManager`) para mantener un chat largo dentro de la
ventana de contexto. Necesita `BRAVE_API_KEY` en `.env` y Node.js.

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
definición del índice. `rag_db.test` y su índice vectorial no se tocan. Es el
único notebook que escribe datos en el cluster y crea un índice de Atlas
Search; la última celda tiene el `drop()` para deshacerlo.

## `mongodb_movies_brave.ipynb` — catálogo de películas + Brave

Un agente sobre `sample_mflix.movies`, el dataset de ejemplo de Atlas (unas
21.000 películas hasta 2016). En vez de recuperar pasajes, consulta documentos
estructurados: filtra por director, reparto, género, año y nota con `find`, y
busca por argumento con el índice de texto nativo de MongoDB (`$text`), que el
dataset ya incluye. Sin embeddings y sin Atlas Search.

Brave Search aporta lo que una foto de 2016 no puede tener (dónde ver la
película hoy, secuelas, recaudación), pero con una regla: **el catálogo decide
qué películas existen**. Antes de buscar en la web el agente confirma que la
película está en la colección; si no está, lo dice y no la busca. Necesita
`MONGODB_CONNECTION` (con el dataset de ejemplo cargado) y `BRAVE_API_KEY`.

Los ejemplos cubren los cuatro caminos: ficha de una película y dónde verla hoy,
una consulta estructurada (Nolan con IMDb > 8) seguida de la web solo para la
mejor valorada, una búsqueda por argumento con `$text`, y una película
posterior a 2016 que el agente rechaza por no estar en el catálogo.

## `mongodb_analytics_brave.ipynb` — agregaciones sobre `sample_analytics`

Un agente "analista de cartera" sobre el dataset bancario de ejemplo de Atlas:
500 clientes, 1.746 cuentas y 88.000 operaciones bursátiles en 18 símbolos. Las
colecciones se relacionan por `account_id`, así que las herramientas son
pipelines de agregación: `$lookup` para unir clientes, cuentas y operaciones,
`$unwind` + `$group` para convertir las operaciones en posiciones netas por
acción, `$top` para la última operación de cada símbolo (un `$sort` previo
supera el límite de 32 MB). Sin embeddings ni índices de búsqueda.

Brave Search aporta lo único que el dataset no puede tener: el precio actual
de cada acción, con el que el agente valora la posición neta de un cliente.
Misma regla que el notebook de películas: solo busca en la web símbolos que
aparecen en las operaciones. Los datos son sintéticos (1962–2017, precios
inventados, ventas sin compra previa), y el agente lo advierte. Necesita
`MONGODB_CONNECTION` (con el dataset de ejemplo cargado) y `BRAVE_API_KEY`.

Dos detalles del dataset que el código tiene en cuenta: `price` y `total` están
guardados como strings (de ahí el `$toDouble`), y no hay índice en
`account_id`, así que el notebook lo crea en `accounts` y `transactions` para
que los `$lookup` no escaneen la colección.

## Modelo

`search_brave.ipynb` usa Amazon Bedrock con `us.anthropic.claude-sonnet-5`;
los notebooks `mongodb_*`, con `us.anthropic.claude-sonnet-5-5`. Todos usan
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

**`sample_mflix` / `sample_analytics` no existen** — el cluster no tiene cargado
el Sample Dataset de Atlas. Cárgalo desde la consola (*Load Sample Dataset*);
tarda unos minutos.

**Atlas Search: límite de índices** — el tier gratuito M0 admite tres índices de
Atlas Search por cluster. `mongodb_text_search.ipynb` crea uno (`text_index`);
`mongodb-rag` otro (`vector_index`). Si alcanzas el límite, borra los que no
uses con `collection.drop_search_index(nombre)` o desde la consola.

**`Sort exceeded memory limit of 33554432 bytes`** — un `$sort` dentro de una
agregación que supera 32 MB en memoria. O bien se evita (como hace
`mongodb_analytics_brave.ipynb` con el acumulador `$top` en vez de `$sort` +
`$last`), o se permite escribir a disco con `allowDiskUse=True` en
`collection.aggregate(...)`.

**Brave devuelve 429** — el plan gratuito permite una petición por segundo. Los
notebooks `mongodb_*` espacian las llamadas con un `Lock` porque Strands ejecuta
en paralelo las tools de un mismo turno; si lo eliminas, vuelven los 429.
