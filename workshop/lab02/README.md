# Lab 02: Bedrock Guardrails con Cedar y AgentCore

Este laboratorio demuestra cómo proteger aplicaciones de IA generativa combinando
**Amazon Bedrock Guardrails** (detección probabilística de contenido dañino) con
**Cedar policies en AgentCore** (autorización determinística de acceso a herramientas).

## Arquitectura

```
┌──────────────┐     ┌─────────────────────────────────┐     ┌───────────────┐
│              │     │     AgentCore Gateway            │     │               │
│   Agente     │────▶│  ┌───────────┐  ┌────────────┐  │────▶│  Herramientas │
│   (LLM)      │     │  │ Guardrails│  │Cedar Policy│  │     │  (MCP Tools)  │
│              │◀────│  │(detección)│─▶│(decisión)  │  │◀────│               │
└──────────────┘     │  └───────────┘  └────────────┘  │     └───────────────┘
                     └─────────────────────────────────┘
```

**Flujo:**
1. El agente envía una solicitud al Gateway
2. Bedrock Guardrails evalúa el contenido (prompt injection, PII, contenido dañino)
3. Si Guardrails detecta una amenaza, señala al motor de políticas Cedar
4. Cedar toma la decisión final determinística (permit/forbid)
5. Las verificaciones ocurren en la capa del Gateway — el agente no puede eludirlas

## Contenido del Lab

| Archivo | Descripción |
|---------|-------------|
| `01_create_guardrail.py` | Crear un Guardrail con filtros de contenido, temas y PII |
| `02_test_guardrail.py` | Probar el Guardrail con la Converse API |
| `03_cedar_policies.py` | Ejemplos de políticas Cedar para AgentCore |
| `policies/` | Archivos `.cedar` de ejemplo |

## Conceptos Clave

### Bedrock Guardrails (Detección Probabilística)

Guardrails evalúa inputs y outputs del modelo usando ML para detectar:
- **Content filters**: Hate, Insults, Sexual, Violence, Misconduct, Prompt Attack
- **Denied topics**: Temas específicos que el agente no debe discutir
- **Word filters**: Palabras exactas bloqueadas (profanidad, competidores)
- **Sensitive information**: PII que se puede bloquear o enmascarar
- **Contextual grounding**: Detecta alucinaciones

### Cedar Policies (Autorización Determinística)

Cedar controla QUÉ herramientas puede invocar un agente y bajo qué condiciones:
- **permit/forbid**: Reglas explícitas de autorización
- **Principal**: Quién hace la solicitud
- **Action**: Qué herramienta/operación quiere ejecutar
- **Resource**: El Gateway donde aplica la política
- **Conditions**: Restricciones adicionales (montos, geografía, hora)

### Combinación en AgentCore

| Componente | Tipo | Función |
|-----------|------|---------|
| Guardrails | Probabilístico | Detecta amenazas de seguridad y contenido |
| Cedar Policy | Determinístico | Decisión final allow/deny |
| Gateway | Enforcement | Punto de aplicación fuera del agente |

## Pre-requisitos

- AWS CLI configurado con credenciales válidas
- Acceso a Amazon Bedrock en la región configurada
- Python 3.9+
- (Opcional) AgentCore CLI para desplegar políticas Cedar

## Ejecución

```bash
cd workshop/lab02

# Paso 1: Crear el Guardrail
python 01_create_guardrail.py

# Paso 2: Probar el Guardrail con Converse API
python 02_test_guardrail.py

# Paso 3: Ver ejemplos de políticas Cedar
python 03_cedar_policies.py
```

## Referencias

- [Bedrock Guardrails - Cómo funciona](https://docs.aws.amazon.com/bedrock/latest/userguide/guardrails-how.html)
- [Crear un Guardrail](https://docs.aws.amazon.com/bedrock/latest/userguide/guardrails-components.html)
- [AgentCore Policy - Getting Started](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/policy-getting-started.html)
- [Cedar en AgentCore (AWS Security Blog)](https://aws.amazon.com/blogs/security/why-policy-in-amazon-bedrock-agentcore-chose-cedar-for-securing-agentic-workflows/)
- [AgentCore FAQ - Guardrails + Policy](https://aws.amazon.com/bedrock/agentcore/faqs/)
