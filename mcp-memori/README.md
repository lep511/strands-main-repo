# mcp-memori

CLI interactivo que conecta un agente [Strands](https://github.com/strands-agents/sdk-python) con [Memori](https://memorilabs.ai/) via MCP, dando al agente memoria persistente para almacenar y recuperar informacion del usuario entre sesiones.

## Requisitos

- Python >= 3.13
- Variable de entorno `MEMORI_API_KEY` (definida en `.env`)

## Instalacion

```bash
uv sync
```

## Uso

```bash
uv run python main.py
```

El menu interactivo ofrece queries de demo (almacenar preferencias, recordar datos, actualizar memoria) y entrada libre. El agente usa las herramientas MCP de Memori (`memori_store`, `memori_recall`) de forma automatica segun el contexto de la conversacion.
