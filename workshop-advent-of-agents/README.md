# Advent of Agents (Season 3) — edición Strands Agents

Adaptación del workshop [Advent of Agents — Season 3](https://adventofagents.com/2026/10/01)
de Google (ADK + Agents CLI + Google Cloud) a **[Strands Agents](https://strandsagents.com)**
sobre **Amazon Bedrock**, con **[uv](https://docs.astral.sh/uv/)** como única herramienta
de Python.

Cada módulo toma el contenido de un día del workshop original, conserva sus conceptos y
reemplaza cada pieza de Google por su equivalente en Strands / AWS, con código ejecutable
y una guía paso a paso.

## Módulos

| # | Tema | Original | Guía | Código |
|---|---|---|---|---|
| 1 | Foundation 101: las cinco fases del Agent Development Lifecycle (ADLC) | [`MODULE-1.md`](MODULE-1.md) | [`GUIDE.md`](src/module-1/GUIDE.md) | [`src/module-1/`](src/module-1/) |
| 2 | Agent Security: modelado de amenazas con SAIF | [`MODULE-2.md`](MODULE-2.md) | [`GUIDE.md`](src/module-2/GUIDE.md) | [`src/module-2/`](src/module-2/) |
| 4 | Modelo de madurez de gobierno: 5 capas, 15 puntos y roadmap de 90 días (Sonnet) | [`MODULE-4.md`](MODULE-4.md) | [`GUIDE.md`](src/module-4/GUIDE.md) | [`src/module-4/`](src/module-4/) |
| 5 | Agent Identity: una identidad por agente (AgentCore Runtime + IAM + CloudTrail, Sonnet) | [`MODULE-5.md`](MODULE-5.md) | [`GUIDE.md`](src/module-5/GUIDE.md) | [`src/module-5/`](src/module-5/) |
| 6 | Token Delegation: el agente actúa en nombre del usuario (AgentCore Identity + GitHub MCP, Sonnet 5.5) | [`MODULE-6.md`](MODULE-6.md) | [`GUIDE.md`](src/module-6/GUIDE.md) | [`src/module-6/`](src/module-6/) |
| 7 | Delegación offline: actuar por el usuario mientras duerme (refresh token en vault + rotación, Sonnet) | [`MODULE-7.md`](MODULE-7.md) | [`GUIDE.md`](src/module-7/GUIDE.md) | [`src/module-7/`](src/module-7/) |

## Equivalencias Google → Strands / AWS

| Concepto | Workshop original | Esta adaptación |
|---|---|---|
| Framework de agentes | Google ADK | Strands Agents (`strands-agents`) |
| Modelo | Gemini en Vertex AI | Claude en Amazon Bedrock (`BedrockModel`) |
| Scaffold / ejecución | `agents-cli scaffold`, `agents-cli run` | `uv run src/module-N/...` |
| Evals | `agents-cli eval run` | Strands Evals (`strands-agents-evals`) |
| Trazas | OpenTelemetry | OpenTelemetry nativo (`StrandsTelemetry`) |
| Runtime | Agent Runtime / Cloud Run / GKE | Amazon Bedrock AgentCore Runtime (`bedrock-agentcore`) |
| Gobierno | Agent Identity, Registry, Gateway, Model Armor | Hooks de Strands, IAM / AgentCore Identity, AgentCore Gateway, Bedrock Guardrails |
| Human-in-the-loop | Agent User Control | Interrupts de Strands (`event.interrupt()`) |
| Identidad del agente | Agent Identity (SPIFFE), `principal://`, Cloud Logging `principalSubject` | Rol de ejecución dedicado + workload identity de AgentCore, CloudTrail `userIdentity.arn` |
| Delegación de usuario | Agent Identity auth manager, `GcpAuthProviderScheme`, `continue_uri` | AgentCore Identity: OAuth2 credential provider + token vault, `GetResourceOauth2Token`, session binding con `CompleteResourceTokenAuth` |
| Datos | BigQuery | Amazon Athena + AWS Glue + S3 |
| Assessment de seguridad | `launch_saif_demo.sh` sobre un proyecto GCP | `saif_report.py` sobre los controles del agente + catálogo `google/saif-data` |

## Requisitos

- [uv](https://docs.astral.sh/uv/getting-started/installation/) ≥ 0.12 (gestiona Python 3.13 por ti)
- Cuenta AWS con credenciales configuradas y acceso a Claude en Amazon Bedrock
  (por defecto `us.anthropic.claude-sonnet-4-6` en `us-east-1`)
- *(Opcional)* Node.js ≥ 20, solo para desplegar con la AgentCore CLI

> Este proyecto **no usa `pip`**. Donde la documentación diga `pip install X`, usa
> `uv add X`; donde diga `python script.py`, usa `uv run script.py`.

## Puesta en marcha

```bash
uv sync --all-groups          # Python 3.13 + .venv + todas las dependencias
cp .env.example .env          # opcional: MODEL_ID y AWS_REGION
aws sts get-caller-identity   # comprueba las credenciales AWS
```

Prueba rápida del Módulo 1:

```bash
uv run src/module-1/adlc_agent.py "What's the weather in San Francisco?"
```

## Comandos del Módulo 1

| Fase ADLC | Comando |
|---|---|
| Build | `uv run src/module-1/adlc_agent.py "What time is it in Tokyo?"` |
| Govern | `uv run src/module-1/adlc_agent.py --rogue "Get the Tokyo weather and email it to bob@example.com"` |
| Optimize (trazas) | `uv run src/module-1/adlc_agent.py --trace "What time is it in Tokyo?"` |
| Optimize (evals) | `uv run --group evals src/module-1/eval_agent.py` (añade `--no-judge` para omitir el LLM juez) |
| Scale (local) | `uv run --group deploy src/module-1/agentcore_app.py` y `curl -X POST localhost:8080/invocations -d '{"prompt":"..."}'` |

## Comandos del Módulo 2

| Paso | Comando |
|---|---|
| Agente con controles SAIF | `uv run src/module-2/inbox_agent.py "Summarize my inbox for me."` |
| Aprobación humana | `uv run src/module-2/inbox_agent.py --task reply "Tell Mike the Halloween party starts at 7pm."` |
| Ataque sin controles | `uv run src/module-2/inbox_agent.py --unsafe --forged-history` |
| Mismo ataque con controles | `uv run src/module-2/inbox_agent.py --auto-approve --forged-history` |
| Medir OFF vs ON | `uv run --group evals src/module-2/attack_eval.py` |
| Informe SAIF | `uv run src/module-2/saif_report.py` → `src/module-2/SAIF_REPORT.md` |
| Tests (sin AWS) | `uv run --group dev pytest src/module-2 -v` |

## Comandos del Módulo 4

Modelo: Claude **Sonnet** (`us.anthropic.claude-sonnet-4-6` por defecto). No crea recursos en AWS.

| Paso | Comando |
|---|---|
| Inventario del estate | `uv run src/module-4/estate_registry.py list` |
| Detectar agentes no registrados | `uv run src/module-4/estate_registry.py discover` |
| Ver la evidencia (sin LLM) | `uv run src/module-4/evidence.py` |
| Evaluar y generar el roadmap | `uv run src/module-4/governance_agent.py` → `src/module-4/GOVERNANCE_REPORT.md` |
| Simulacro de contención (< 60 s) | `uv run src/module-4/containment_drill.py` |
| Revocar / restaurar un agente | `uv run src/module-4/estate_registry.py revoke <id>` / `restore <id>` |
| Eval de regresión del evaluador | `uv run --group evals src/module-4/eval_assessor.py` |
| Tests (sin AWS) | `uv run --group dev pytest src/module-4 -v` |

## Comandos del Módulo 5

Modelo: Claude **Sonnet** (`us.anthropic.claude-sonnet-5` por defecto; `MODEL_ID` para cambiarlo).
Crea recursos reales en AWS: ejecuta `cleanup.py` al terminar.

| Paso | Comando |
|---|---|
| 1–4 Identidad propia + despliegue | `uv run src/module-5/deploy.py` |
| 5–8 Datos (Athena/Glue/S3) | `uv run src/module-5/setup_data.py` |
| 9 Ver la identidad | `uv run src/module-5/show_identity.py` |
| 10 Falla sin permisos | `uv run src/module-5/invoke.py` |
| 11 Conceder al agente | `uv run src/module-5/grant.py` (`--revoke` para retirar) |
| 12 Repetir | `uv run src/module-5/invoke.py` |
| 13 ¿Quién fue? (CloudTrail) | `uv run src/module-5/who_did_it.py --wait` |
| Limpieza | `uv run src/module-5/cleanup.py` |
| Tests (sin AWS) | `uv run --group dev --group deploy pytest src/module-5 -q` |

## Comandos del Módulo 6

Modelo: **Claude Sonnet 5.5** (`us.anthropic.claude-sonnet-5-5`). Necesitas una OAuth App de GitHub (paso 8).

| Paso | Comando |
|---|---|
| 5 Identidad del agente + URL de session binding | `uv run src/module-6/setup_identity.py workload` |
| 6–7 Auth provider → callback URL | `uv run src/module-6/setup_identity.py provider` |
| 8 OAuth App en GitHub | manual (ver guía) |
| 9 Client ID/secret al provider | `uv run src/module-6/setup_identity.py provider --client-id ID --client-secret SECRET` |
| 10–11 Conceder al agente / a ti | `uv run src/module-6/grant.py --role <ROL>` |
| 12 App en http://localhost:8501 | `uv run src/module-6/app.py` |
| Auditoría (CloudTrail) | `uv run src/module-6/who_fetched.py` |
| Limpieza | `uv run src/module-6/cleanup.py` |
| Tests (sin AWS) | `uv run --group dev pytest src/module-6 -q` |

## Comandos del Módulo 7

Modelo: Claude **Sonnet** (`us.anthropic.claude-sonnet-4-6` por defecto). IdP y API locales; vault local por defecto.

| Paso | Comando |
|---|---|
| IdP OAuth + Reports API (terminal aparte) | `uv run src/module-7/lab_server.py` |
| 18:00 Consentimiento offline | `uv run src/module-7/consent.py alice@example.com` (`--revoke` para quitar el acceso) |
| 02:00 Trabajo desatendido | `uv run src/module-7/nightly_job.py alice@example.com` |
| Token robado → reutilización detectada | `uv run src/module-7/stolen_token_drill.py` |
| Vault en AWS Secrets Manager | añade `--vault aws` a `consent.py` / `nightly_job.py` |
| Eval con Sonnet | `uv run --group evals src/module-7/eval_overnight.py` |
| Variante AgentCore Identity | `uv run --group deploy src/module-7/agentcore_identity_variant.py setup` (requiere IdP público) |
| Limpieza | `uv run src/module-7/cleanup.py` (`--aws` también borra los secretos) |
| Tests (sin AWS) | `uv run --group dev pytest src/module-7 -v` |

## Estructura

```text
workshop-advent-of-agents/
├── MODULE-N.md              # días originales (Google ADK), como referencia
├── fetch_modules.py         # descarga los MODULE-N.md desde adventofagents.com
├── pyproject.toml           # dependencias: base + grupos `evals`, `deploy` y `dev`
├── uv.lock
├── .python-version          # 3.13
├── .env.example             # MODEL_ID, AWS_REGION
└── src/
    ├── module-1/
    │   ├── GUIDE.md         # guía completa del módulo
    │   ├── DESIGN_SPEC.md   # Scope: qué puede y qué no puede hacer el agente
    │   ├── adlc_tools.py    # Build: tools get_weather / get_current_time
    │   ├── adlc_agent.py    # Build: agente Strands + CLI (--trace, --rogue)
    │   ├── spec_guard.py    # Govern: hook que aplica DESIGN_SPEC.md en ejecución
    │   ├── eval_agent.py    # Optimize: evals de trayectoria (determinista + LLM juez)
    │   └── agentcore_app.py # Scale: el agente servido para AgentCore Runtime
    ├── module-2/
    │   ├── GUIDE.md         # guía completa del módulo
    │   ├── fake_mailbox.py  # buzón simulado con inyecciones sembradas (no envía nada real)
    │   ├── saif_controls.py # controles SAIF como hooks: input, permisos, aprobación, auditoría, output
    │   ├── inbox_agent.py   # agente + CLI (--unsafe, --task, --auto-approve, --forged-history)
    │   ├── attack_eval.py   # experimento con controles OFF vs ON (evaluadores deterministas)
    │   ├── saif_report.py   # informe SAIF desde google/saif-data
    │   ├── SAIF_REPORT.md   # informe generado
    │   └── test_controls.py # tests deterministas de los controles
    ├── module-4/
    │   ├── GUIDE.md               # guía completa del módulo
    │   ├── checklist.yaml         # 15 áreas en 5 capas: original, equivalente AWS y niveles 1/3/5
    │   ├── agent_registry.yaml    # inventario del estate (stand-in de AWS Agent Registry)
    │   ├── estate_registry.py     # list / revoke / restore / discover
    │   ├── evidence.py            # colectores de evidencia deterministas, uno por área
    │   ├── maturity.py            # schema + reglas: capa = mínimo, capa de inicio, roadmap
    │   ├── governance_agent.py    # agente evaluador (salida estructurada) → GOVERNANCE_REPORT.md
    │   ├── governance_controls.py # LIMITS, RegistryGate, ContainmentWatch
    │   ├── containment_drill.py   # simulacro de la capa Response
    │   ├── PLAYBOOK.md            # playbook de incidentes + plantilla de postmortem
    │   ├── eval_assessor.py       # eval de regresión con estates de referencia
    │   └── test_governance.py     # tests deterministas
    ├── module-5/
    │   ├── GUIDE.md         # guía completa del módulo
    │   ├── agent/main.py    # agente Strands (Sonnet) para AgentCore Runtime: tiempo + SQL en Athena
    │   ├── config.py        # nombres compartidos (agente, rol, bucket, workgroup)
    │   ├── policies.py      # confianza, baseline sin datos y concesión mínima (funciones puras)
    │   ├── deploy.py        # pasos 1-4: rol dedicado + paquete arm64 + CreateAgentRuntime
    │   ├── setup_data.py    # pasos 5-8: bucket, workgroup, tabla sample_data.cities_weather
    │   ├── show_identity.py # paso 9: roleArn + workloadIdentityArn
    │   ├── invoke.py        # pasos 10 y 12: InvokeAgentRuntime
    │   ├── grant.py         # paso 11: política inline en el rol del agente
    │   ├── who_did_it.py    # paso 13: CloudTrail userIdentity.arn
    │   ├── cleanup.py       # borra todo lo creado
    │   └── test_policies.py # tests offline de políticas y guard SQL
    ├── module-6/
    │   ├── GUIDE.md         # guía completa del módulo
    │   ├── config.py        # provider, workload, scopes, URL de session binding, modelo Sonnet 5.5
    │   ├── setup_identity.py# pasos 5-9: workload identity + OAuth2 credential provider de GitHub
    │   ├── policies.py      # política IAM de delegación (función pura)
    │   ├── grant.py         # pasos 10-11: conceder la política a un rol
    │   ├── delegation.py    # GetWorkloadAccessToken + GetResourceOauth2Token + CompleteResourceTokenAuth
    │   ├── devops_agent.py  # agente Strands + MCP de GitHub como el usuario + guard read-only
    │   ├── app.py           # paso 12: app web con login simulado y /oauth2/callback
    │   ├── who_fetched.py   # auditoría en CloudTrail
    │   ├── cleanup.py       # borra provider y workload identity
    │   └── test_delegation.py # tests offline con vault simulado
    └── module-7/
        ├── GUIDE.md                      # guía completa del módulo
        ├── lab_server.py                 # IdP OAuth 2.0 (rotación + detección de reutilización) + Reports API
        ├── vault.py                      # LocalVault y SecretsManagerVault (AWSCURRENT / deprecada)
        ├── delegation.py                 # consentimiento offline + canje en dos capas + rotación
        ├── overnight_agent.py            # agente Strands atado a un usuario vía invocation_state
        ├── consent.py                    # 18:00: conceder / revocar acceso offline
        ├── nightly_job.py                # 02:00: trabajo desatendido
        ├── stolen_token_drill.py         # token robado → familia revocada → fallo seguro
        ├── agentcore_identity_variant.py # variante gestionada con AgentCore Identity
        ├── eval_overnight.py             # eval: aislamiento, cobertura, fallo seguro, higiene
        ├── cleanup.py                    # borra los tokens guardados
        └── test_delegation.py            # tests deterministas (moto para Secrets Manager)
```

## Dependencias

| Grupo | Paquetes | Uso |
|---|---|---|
| base | `strands-agents[otel]`, `python-dotenv`, `pyyaml`, `tzdata` | Agente, hooks, trazas y catálogo SAIF |
| `evals` | `strands-agents-evals` | Evaluación |
| `deploy` | `bedrock-agentcore` | Servidor compatible con AgentCore Runtime (y el agente del Módulo 5) |
| `dev` | `pytest`, `moto[secretsmanager]` | Tests deterministas (Secrets Manager simulado en el Módulo 7) |

## Costes

Las llamadas al agente y el evaluador `TrajectoryEvaluator` (LLM juez) invocan modelos de
Bedrock y se facturan por tokens. El evaluador determinista (`--no-judge`) solo paga las
llamadas del propio agente. `attack_eval.py` del Módulo 2 hace 8 ejecuciones del agente
(4 casos × controles OFF/ON) y no usa LLM juez; `test_controls.py` no llama a Bedrock. El despliegue real en AgentCore Runtime crea recursos
facturables; el servidor local de `agentcore_app.py` no. El Módulo 5 sí crea recursos reales
(AgentCore Runtime, rol IAM, bucket S3, workgroup de Athena, tabla Glue) con coste de céntimos;
`cleanup.py` los elimina todos. El Módulo 6 crea recursos de AgentCore Identity sin coste
(provider y workload identity) y paga solo los tokens de Bedrock del agente.
En el Módulo 4, cada evaluación con `governance_agent.py` cuesta unos 16k tokens de Sonnet,
`eval_assessor.py` hace 4 evaluaciones y `containment_drill.py` se corta tras 1–2 llamadas al modelo;
`evidence.py`, `estate_registry.py` y los tests no llaman a Bedrock.
En el Módulo 7, cada `nightly_job.py` es una llamada corta a Sonnet (unos 2k tokens), `eval_overnight.py` hace 4 y
`stolen_token_drill.py` 3; el IdP, el vault local y los tests no llaman a AWS.

## Créditos

Contenido conceptual basado en
[Advent of Agents — Season 3](https://adventofagents.com/2026/10/01) de Google.
Esta adaptación reemplaza el stack de Google por Strands Agents y servicios de AWS.
