#!/usr/bin/env python3
"""Weather lookup como *tool* de Strands, servido en Amazon Bedrock AgentCore.

Adapta el script original de consulta de clima (wttr.in) a una herramienta que
un agente puede invocar. Tiene tres piezas:

1. ``_fetch_weather`` — lógica pura de red (sin dependencias de Strands).
2. ``get_weather`` — la misma lógica expuesta como ``@tool`` de Strands, con un
   docstring/tipos que el modelo usa para decidir cuándo y cómo llamarla.
3. Un ``Agent`` de Strands montado en un ``BedrockAgentCoreApp`` mediante
   ``@app.entrypoint`` — así se despliega en **AgentCore Runtime** y el cliente
   ``main.py`` lo invoca vía ``invoke_harness``.

**Guardrail.** El agente adjunta un Bedrock Guardrail a su ``BedrockModel``, así
que Amazon Bedrock lo aplica de forma nativa en cada ``Converse`` (entrada y
salida) y **bloquea** el contenido prohibido. El guardrail se busca por nombre y
se **crea automáticamente** si no existe (ver :func:`ensure_guardrail`). Para
reutilizar uno ya creado, define ``GUARDRAIL_ID`` (y opcionalmente
``GUARDRAIL_VERSION``) y se salta el aprovisionamiento.

Uso local:

    uv run weather.py                 # arranca el servidor AgentCore (app.run)
    uv run weather.py --cli Madrid    # prueba la tool directa, sin servidor
    uv run weather.py --cli           # clima de la ubicación detectada por IP

Variables de entorno:

    AWS_REGION          Región de Bedrock (por defecto us-east-1).
    GUARDRAIL_NAME      Nombre del guardrail a buscar/crear.
    GUARDRAIL_ID        Usar un guardrail existente por ID (salta la creación).
    GUARDRAIL_VERSION   Versión del guardrail existente (por defecto DRAFT).
    BEDROCK_MODEL_ID    Model id de Bedrock (si se omite, usa el default regional).
"""

import json
import os
import sys
from urllib.error import URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

import boto3
from bedrock_agentcore.runtime import BedrockAgentCoreApp
from botocore.exceptions import ClientError
from strands import Agent, tool
from strands.models.bedrock import BedrockModel

REGION = os.environ.get("AWS_REGION", "us-east-1")
GUARDRAIL_NAME = os.environ.get("GUARDRAIL_NAME", "weather-agent-guardrail")

BLOCKED_INPUT_MESSAGE = "Lo siento, solo puedo ayudarte con consultas sobre el clima."
BLOCKED_OUTPUT_MESSAGE = "Lo siento, no puedo proporcionar esa respuesta."


def _fetch_weather(ciudad: str = "") -> dict:
    """Consulta wttr.in y devuelve un resumen estructurado del clima.

    Lanza ``RuntimeError`` si el servicio no responde, para que el llamador
    (la tool o el CLI) decida cómo reportarlo.
    """
    # Codifica el nombre para que ciudades con espacios/acentos (p. ej.
    # "Buenos Aires", "São Paulo") formen una URL válida.
    url = f"https://wttr.in/{quote(ciudad)}?format=j1"
    req = Request(url, headers={"User-Agent": "curl/8.0"})
    try:
        with urlopen(req, timeout=15) as resp:
            datos = json.loads(resp.read().decode("utf-8"))
    except (URLError, TimeoutError) as e:
        raise RuntimeError(f"No se pudo conectar con el servicio del clima: {e}") from e

    actual = datos["current_condition"][0]
    zona = datos["nearest_area"][0]
    descripcion = (
        actual["lang_es"][0]["value"]
        if "lang_es" in actual
        else actual["weatherDesc"][0]["value"]
    )

    return {
        "ubicacion": f"{zona['areaName'][0]['value']}, "
        f"{zona['region'][0]['value']}, {zona['country'][0]['value']}",
        "condicion": descripcion,
        "temperatura_c": int(actual["temp_C"]),
        "sensacion_c": int(actual["FeelsLikeC"]),
        "humedad_pct": int(actual["humidity"]),
        "viento_kmph": int(actual["windspeedKmph"]),
        "visibilidad_km": int(actual["visibility"]),
        "presion_hpa": int(actual["pressure"]),
    }


@tool
def get_weather(ciudad: str = "") -> dict:
    """Obtiene el estado del tiempo actual de una ciudad usando wttr.in.

    Úsala cuando el usuario pregunte por el clima, la temperatura, la humedad,
    el viento o condiciones actuales de un lugar. No necesita clave de API.

    Args:
        ciudad: Nombre de la ciudad a consultar (p. ej. "Madrid", "Buenos Aires").
            Si se omite, se usa la ubicación detectada por la IP del servidor.

    Returns:
        Un dict con ``ubicacion``, ``condicion``, ``temperatura_c``,
        ``sensacion_c``, ``humedad_pct``, ``viento_kmph``, ``visibilidad_km`` y
        ``presion_hpa``; o un dict ``{"error": "..."}`` si la consulta falla.
    """
    try:
        return _fetch_weather(ciudad.strip())
    except RuntimeError as e:
        return {"error": str(e)}


# ---------------------------------------------------------------------------
# Bedrock Guardrail — buscar por nombre o crear si no existe
# ---------------------------------------------------------------------------


def _guardrail_config() -> dict:
    """Política del guardrail para un asistente del clima.

    Mantiene al agente en tema (deniega consejo financiero/médico/legal),
    aplica filtros de contenido y protege contra prompt injection.
    """
    return {
        "topicPolicyConfig": {
            "topicsConfig": [
                {
                    "name": "Consejo fuera de tema",
                    "definition": (
                        "Dar consejo financiero, de inversión, médico, legal o "
                        "cualquier recomendación personal ajena al clima. El "
                        "asistente solo informa sobre el estado del tiempo."
                    ),
                    "examples": [
                        "¿En qué acciones debería invertir?",
                        "¿Qué medicamento tomo para el dolor de cabeza?",
                        "¿Puedo demandar a mi vecino?",
                    ],
                    "type": "DENY",
                },
            ],
        },
        "contentPolicyConfig": {
            "filtersConfig": [
                {"type": "SEXUAL", "inputStrength": "HIGH", "outputStrength": "HIGH"},
                {"type": "VIOLENCE", "inputStrength": "HIGH", "outputStrength": "HIGH"},
                {"type": "HATE", "inputStrength": "HIGH", "outputStrength": "HIGH"},
                {
                    "type": "INSULTS",
                    "inputStrength": "MEDIUM",
                    "outputStrength": "MEDIUM",
                },
                {
                    "type": "MISCONDUCT",
                    "inputStrength": "MEDIUM",
                    "outputStrength": "MEDIUM",
                },
                # PROMPT_ATTACK solo admite filtrado de entrada; output debe ser NONE.
                {
                    "type": "PROMPT_ATTACK",
                    "inputStrength": "HIGH",
                    "outputStrength": "NONE",
                },
            ],
        },
        "blockedInputMessaging": BLOCKED_INPUT_MESSAGE,
        "blockedOutputsMessaging": BLOCKED_OUTPUT_MESSAGE,
    }


def ensure_guardrail(name: str = GUARDRAIL_NAME) -> tuple[str, str] | None:
    """Devuelve ``(id, version)`` del guardrail ``name``, creándolo si falta.

    Prioridad: si existe la variable ``GUARDRAIL_ID`` se usa tal cual. Si no, se
    busca por nombre; si no existe, se crea con :func:`_guardrail_config`.
    Devuelve ``None`` si no se pudo encontrar ni crear (p. ej. faltan permisos
    IAM), de modo que el agente pueda arrancar sin guardrail.
    """
    env_id = os.environ.get("GUARDRAIL_ID")
    if env_id:
        version = os.environ.get("GUARDRAIL_VERSION", "DRAFT")
        print(f"[guardrail] usando existente por env: {env_id} (v{version})")
        return env_id, version

    client = boto3.client("bedrock", region_name=REGION)

    # 1. Buscar un guardrail existente con ese nombre.
    try:
        paginator = client.get_paginator("list_guardrails")
        for page in paginator.paginate():
            for g in page.get("guardrails", []):
                if g.get("name") == name:
                    print(f"[guardrail] encontrado '{name}' ({g['id']})")
                    # DRAFT siempre refleja la última versión de trabajo.
                    return g["id"], "DRAFT"
    except ClientError as e:
        print(
            f"[guardrail] no se pudo listar guardrails: {e.response['Error']['Message']}"
        )
        return None

    # 2. No existe — crearlo.
    print(f"[guardrail] no existe '{name}' — creándolo…")
    try:
        response = client.create_guardrail(
            name=name,
            description="Guardrail autocreado para el asistente del clima (AgentCore).",
            **_guardrail_config(),
        )
        gid = response["guardrailId"]
        version = response.get("version", "DRAFT")
        print(f"[guardrail] creado '{name}' ({gid}) v{version}")
        return gid, version
    except ClientError as e:
        print(
            f"[guardrail] no se pudo crear: {e.response['Error']['Message']} "
            "— el agente seguirá SIN guardrail."
        )
        return None


def _build_model() -> BedrockModel:
    """Construye el BedrockModel, adjuntando el guardrail si está disponible."""
    kwargs: dict = {"region_name": REGION}
    model_id = os.environ.get("BEDROCK_MODEL_ID")
    if model_id:
        kwargs["model_id"] = model_id

    guardrail = ensure_guardrail()
    if guardrail is not None:
        gid, gver = guardrail
        # Al adjuntarlo al modelo, Bedrock lo aplica nativamente en el Converse,
        # sobre entrada y salida, y bloquea el contenido prohibido.
        kwargs.update(
            guardrail_id=gid,
            guardrail_version=gver,
            guardrail_trace="enabled",
            guardrail_redact_input=True,
            guardrail_redact_input_message=BLOCKED_INPUT_MESSAGE,
            guardrail_redact_output=True,
            guardrail_redact_output_message=BLOCKED_OUTPUT_MESSAGE,
        )

    return BedrockModel(**kwargs)


# ---------------------------------------------------------------------------
# Agente de Strands servido en AgentCore Runtime
# ---------------------------------------------------------------------------

app = BedrockAgentCoreApp()

# El agente se construye de forma perezosa (en la primera invocación) para que
# importar solo la tool `get_weather` desde el cliente NO provisione el
# guardrail ni llame a AWS. En el runtime se crea una vez por cold start.
_agent: Agent | None = None


def get_agent() -> Agent:
    """Devuelve el Agent (lo construye y cachea en la primera llamada)."""
    global _agent
    if _agent is None:
        _agent = Agent(
            model=_build_model(),
            system_prompt=(
                "Eres un asistente del clima. Cuando el usuario pregunte por el "
                "tiempo de un lugar, llama a get_weather con el nombre de la "
                "ciudad y resume el resultado en lenguaje natural, claro y breve. "
                "Si la tool devuelve un error, explícalo con amabilidad."
            ),
            tools=[get_weather],
        )
    return _agent


@app.entrypoint
def invoke(payload: dict) -> dict:
    """Punto de entrada que AgentCore Runtime llama en cada invocación."""
    user_message = payload.get("prompt", "¿Qué tiempo hace?")
    result = get_agent()(user_message)
    return {"result": result.message}


# ---------------------------------------------------------------------------
# Prueba local
# ---------------------------------------------------------------------------


def _cli() -> None:
    """Invoca la tool directamente e imprime un resumen legible (sin servidor)."""
    args = [a for a in sys.argv[2:]]  # tras el flag --cli
    ciudad = args[0] if args else ""
    datos = get_weather(ciudad)

    if "error" in datos:
        print(datos["error"])
        sys.exit(1)

    print("=" * 40)
    print("        ESTADO DEL TIEMPO")
    print("=" * 40)
    print(f"Ubicacion    : {datos['ubicacion']}")
    print(f"Condicion    : {datos['condicion']}")
    print(
        f"Temperatura  : {datos['temperatura_c']} C (sensacion {datos['sensacion_c']} C)"
    )
    print(f"Humedad      : {datos['humedad_pct']} %")
    print(f"Viento       : {datos['viento_kmph']} km/h")
    print(f"Visibilidad  : {datos['visibilidad_km']} km")
    print(f"Presion      : {datos['presion_hpa']} hPa")
    print("=" * 40)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--cli":
        _cli()
    else:
        # app.run() levanta el servidor HTTP que AgentCore Runtime espera
        # (POST /invocations, GET /ping) en el puerto 8080 y se queda escuchando.
        # No es una CLI: no imprime nada por sí solo ni termina. Para probar la
        # tool sin servidor usa `--cli`. Para probar el agente completo:
        #   curl -s localhost:8080/invocations \
        #        -H 'Content-Type: application/json' \
        #        -d '{"prompt": "¿Qué tiempo hace en Madrid?"}'
        banner = (
            "🌤  Servidor AgentCore escuchando en http://localhost:8080\n"
            "    Salud:   curl localhost:8080/ping\n"
            "    Invocar: curl -s localhost:8080/invocations "
            "-H 'Content-Type: application/json' "
            '-d \'{"prompt": "¿Qué tiempo hace en Madrid?"}\'\n'
            "    (Ctrl-C para detener · la 1ª invocación crea el guardrail)"
        )
        print(banner, flush=True)
        app.run()
