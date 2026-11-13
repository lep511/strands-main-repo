# harness-strand-example

Ejemplos de agentes construidos con el [Strands SDK](https://github.com/strands-agents)
que demuestran distintas capacidades de **Amazon Bedrock Guardrails**: bloqueo de
temas, filtros de contenido, palabras prohibidas, contextual grounding y
**Automated Reasoning checks**.

Todos los ejemplos comparten dos ideas:

- **Crean sus guardrails automáticamente si no existen** (y reutilizan los
  existentes), así que no hay que provisionar nada a mano antes de ejecutarlos.
- Usan una interfaz de terminal con [Rich](https://github.com/Textualize/rich):
  streaming en vivo, spinner de espera, edición de línea con flechas/historial
  (`readline`) y paneles de color.

---

## Requisitos

- **Python ≥ 3.13** y [`uv`](https://docs.astral.sh/uv/).
- Credenciales de **AWS** con acceso a Amazon Bedrock en la región configurada
  (por defecto `us-east-1`), o un **emulador local** de AWS (ver más abajo).
- Permisos de IAM para las operaciones que use cada ejemplo:
  `bedrock:CreateGuardrail`, `bedrock:ListGuardrails`, `bedrock:GetGuardrail`,
  `bedrock-runtime:ApplyGuardrail`, `bedrock-runtime:Converse`, y para el
  ejemplo de Automated Reasoning también las operaciones
  `bedrock:*AutomatedReasoningPolicy*`. `main.py` además usa DynamoDB.

### Instalación

```bash
uv sync
```

---

## Ejemplos

| Archivo | Qué demuestra | Guardrail |
| --- | --- | --- |
| [`main.py`](main.py) | Agente de programa de recompensas con herramientas DynamoDB y memoria persistente; guardrail en modo **notificación** (detecta, no bloquea). | `rewards-agent-guardrail` |
| [`abcd_bank_example.py`](abcd_bank_example.py) | Chatbot bancario con guardrail **adjunto al modelo** (bloqueo real), pre-screening de entrada, contextual grounding y base de conocimiento. | `abcd-bank-chatbot-guardrail` |
| [`automated_reasoning_example.py`](automated_reasoning_example.py) | **Automated Reasoning checks**: valida respuestas con lógica formal y las reescribe si no son `VALID`. Soporta emulador y modo híbrido. | `parental-leave-ar-guardrail` |

---

### 1. `main.py` — Agente de recompensas (guardrail notify-only)

Un asistente de un programa de puntos que:

- Usa herramientas Strands sobre **DynamoDB**: `lookup_rewards_tier`,
  `list_all_rewards_tiers` (tabla `RewardsDatabase`), `register_user`,
  `get_user` (tabla `UserTable`).
- Guarda memoria entre sesiones con `MemoryManager` + `TestMemoryStore`
  (`~/.strands/memory/rewards-agent.json`).
- Aplica un guardrail mediante `NotifyOnlyGuardrailsHook`: evalúa entrada y
  salida con `ApplyGuardrail` y **avisa** cuando detecta una violación, pero
  **no bloquea** — la respuesta del modelo se entrega igualmente.

```bash
uv run main.py
```

> Requiere dos tablas DynamoDB existentes: `RewardsDatabase` (clave `tier`) y
> `UserTable` (claves `PK`/`SK`).

---

### 2. `abcd_bank_example.py` — Chatbot bancario (bloqueo real)

Asistente de atención al cliente de "ABCD Bank" que ejerce **enforcement real**
adjuntando el guardrail al `BedrockModel` (se aplica dentro del `Converse` sobre
entrada y salida). Demuestra:

- **Temas denegados** (`DENY`): Financial Advice, Political Advice, Medical Advice.
- **Palabras bloqueadas** (`suicide`, `self-harm`, `terrorist`, `illegal`).
- **Filtros de contenido** (sexual, violencia, odio, insultos, misconduct,
  prompt-attack).
- **Contextual grounding** (GROUNDING + RELEVANCE, umbral 0.7) contra una base
  de conocimiento embebida.
- **Pre-screening determinista** de la entrada antes de llamar al modelo, para
  bloquear de forma consistente y evitar falsos positivos de grounding sobre
  rechazos.
- Paneles que distinguen claramente **"🛡 Blocked by Guardrail"** vs
  **"🤖 model response"**, y una señal informativa de grounding.

```bash
uv run abcd_bank_example.py
```

Prueba, por ejemplo: *"Can you suggest some good stocks to invest in right now?"*
(bloqueado) frente a *"What are your branch hours?"* (respondido).

---

### 3. `automated_reasoning_example.py` — Automated Reasoning checks

Valida matemáticamente, con **lógica formal**, si las respuestas del LLM son
consistentes con una política (reglas de elegibilidad de permiso parental).
A diferencia de los filtros que bloquean, Automated Reasoning trabaja en
*detect mode* y devuelve findings estructurados.

Flujo (según la [documentación oficial](https://docs.aws.amazon.com/bedrock/latest/userguide/guardrails-automated-reasoning-checks.html)):

1. **Aprovisiona** la política AR a partir de un documento embebido
   (`create_automated_reasoning_policy` → `start_...build_workflow` con
   `INGEST_CONTENT` → poll → `create_...version`) y crea el guardrail con
   `automatedReasoningPolicyConfig`, si no existen.
2. Un agente Strands **responde** la pregunta.
3. Valida la respuesta con `ApplyGuardrail` y muestra los findings
   (`valid` / `invalid` / `satisfiable` / `impossible` /
   `translationAmbiguous` / `tooComplex` / `noTranslations`).
4. Si no es `VALID`, construye un prompt con el feedback y **reescribe** la
   respuesta (hasta `MAX_REWRITE_ITERATIONS`).

```bash
uv run automated_reasoning_example.py
```

> Construir la política AR es un proceso **asíncrono** que puede tardar varios
> minutos. En producción normalmente se crea y revisa una vez en la consola.

Para saltarte el aprovisionamiento y usar un guardrail que ya tengas con una
política AR adjunta:

```bash
AR_GUARDRAIL_ID=<id> AR_GUARDRAIL_VERSION=1 uv run automated_reasoning_example.py
```

---

## Emulador local de AWS (solo `automated_reasoning_example.py`)

Este ejemplo **detecta automáticamente** un emulador local de AWS leyendo su
configuración en `~/.aws/emulator/<puerto>/config` (endpoint, CA y
credenciales) y dirige allí las llamadas de guardrails y Automated Reasoning,
sin necesidad de exportar variables de entorno.

- El emulador ejerce el **control plane** (crear/listar guardrails y políticas
  AR) y el `ApplyGuardrail`, pero **no ejecuta un LLM real** ni el razonamiento
  AR en runtime: las respuestas del modelo son texto de relleno y los findings
  AR llegan vacíos (`automatedReasoningPolicyUnits=0`), aunque la política esté
  correctamente adjunta.

> **Para obtener findings AR reales hay que ejecutar contra AWS real.** El
> emulador no evalúa Automated Reasoning en runtime. Fuerza el uso de AWS real
> para guardrails + AR con `AR_USE_EMULATOR=off`:
>
> ```bash
> AR_USE_EMULATOR=off uv run automated_reasoning_example.py
> ```
>
> (Esto aprovisiona la política AR en tu cuenta real, lo que tarda varios
> minutos y tiene coste; requiere acceso a Automated Reasoning, GA en
> us-east-1, us-west-2, us-east-2, eu-central-1, eu-west-3, eu-west-1 y
> ap-southeast-2.)

Si tu identidad IAM **no tiene permisos** de Automated Reasoning (p. ej. un rol
de workshop sin `bedrock:CreateAutomatedReasoningPolicy`), el ejemplo lo detecta
y te lo indica. Para ver igualmente el flujo completo (paneles de findings y
bucle de reescritura) con datos de muestra, usa el **modo demo**:

```bash
AR_DEMO=1 uv run automated_reasoning_example.py
```

### Modo híbrido: LLM real + guardrails en el emulador

Puedes ejecutar el **modelo contra tu cuenta real** (vía un profile de AWS) y
mantener los guardrails/AR en el emulador:

```bash
AR_REAL_LLM_PROFILE=default uv run automated_reasoning_example.py
```

Variables de entorno soportadas:

| Variable | Descripción | Por defecto |
| --- | --- | --- |
| `AR_REAL_LLM_PROFILE` | Profile de AWS para ejecutar el LLM en tu cuenta real (modo híbrido). | — (todo-emulador) |
| `AR_REAL_LLM_REGION` | Región para el LLM real. | `us-east-1` |
| `AR_MODEL_ID` | Id del modelo de Bedrock. | `global.anthropic.claude-sonnet-4-6` |
| `AR_GUARDRAIL_ID` / `AR_GUARDRAIL_VERSION` | Usar un guardrail AR existente y saltar el aprovisionamiento. | — |
| `AR_USE_EMULATOR` | `off` ignora el emulador y usa AWS real para guardrails + AR (necesario para findings AR reales). | `auto` (detecta emulador) |
| `AR_DEMO` | `1` ejecuta el flujo completo (findings + rewriting loop) con findings de **muestra**, sin llamar a AR. Útil si tu cuenta no tiene permisos de Automated Reasoning. | — |

> Nota: el emulador rechaza el prefijo de inference profile (`global.`), por lo
> que en modo todo-emulador el id se recorta automáticamente a
> `anthropic.claude-sonnet-4-6`. En modo híbrido se mantiene el id real.

---

## Región

Todos los ejemplos usan `us-east-1` por defecto (constante `REGION` en cada
archivo). Edítala si tu acceso a Bedrock está en otra región.
