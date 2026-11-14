# agent-core-example

Cliente de terminal interactivo para un **harness de Amazon Bedrock AgentCore**.

Es la contraparte de [`../harness-strand-example/main.py`](../harness-strand-example/main.py):
en lugar de ejecutar un `Agent` de Strands en local, el agente vive en Bedrock
AgentCore y hablamos con él vía `bedrock-agentcore:invoke_harness`. La respuesta
llega en **streaming** (mismo formato que Bedrock Converse), así que reutilizamos
la misma experiencia de terminal con [Rich](https://github.com/Textualize/rich):

- Streaming en vivo renderizado como **Markdown**.
- **Spinner** de espera hasta el primer token.
- Indicadores de **uso de herramientas** (`🔧 Tool #n`).
- Edición de línea con flechas e historial (`readline`).
- Panel final con `stopReason` y conteo de tokens.

## Requisitos

- **Python ≥ 3.13** y [`uv`](https://docs.astral.sh/uv/).
- Credenciales de **AWS** con acceso a Bedrock AgentCore en la región configurada
  (por defecto `us-east-1`) y permiso `bedrock-agentcore:InvokeHarness`.
- Un harness de AgentCore ya desplegado (su ARN).

## Uso

```bash
uv sync
HARNESS_ARN=arn:aws:bedrock-agentcore:us-east-1:<cuenta>:harness/<id> uv run main.py
```

Si no defines `HARNESS_ARN` se usa el ARN de ejemplo incluido en `main.py`.
El `runtimeSessionId` se genera automáticamente (AgentCore exige ≥ 33 caracteres)
y se reutiliza durante toda la conversación para que el agente mantenga contexto.

### Variables de entorno

| Variable | Descripción | Por defecto |
| --- | --- | --- |
| `HARNESS_ARN` | ARN del harness de AgentCore a invocar. | ARN de ejemplo en `main.py` |
| `AWS_REGION` | Región de AWS. | `us-east-1` |

Escribe `exit` o `quit` (o `Ctrl-D` / `Ctrl-C`) para salir.
