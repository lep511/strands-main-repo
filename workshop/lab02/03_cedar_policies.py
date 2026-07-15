"""
Lab 02 - Paso 3: Cedar Policies para AgentCore

Este script muestra ejemplos de políticas Cedar que se usan con
Amazon Bedrock AgentCore Gateway para controlar el acceso de agentes
a herramientas MCP.

Hay dos formas de crear políticas:
1. Escribir Cedar directamente (archivos .cedar)
2. Generar desde lenguaje natural con el CLI de AgentCore

Las políticas Cedar son DETERMINÍSTICAS (permit/forbid), mientras que
Guardrails son PROBABILÍSTICOS (detección ML). Juntos forman una
defensa en profundidad en la capa del Gateway.
"""


CEDAR_EXAMPLES = {
    "refund_limit": {
        "description": "Permitir reembolsos solo si el monto es menor a $1000",
        "policy": """
permit(
    principal,
    action == AgentCore::Action::"RefundTarget___process_refund",
    resource == AgentCore::Gateway::"arn:aws:bedrock-agentcore:us-east-1:123456789:gateway/my-gateway"
)
when {
    context.input.amount < 1000
};
""",
    },
    "gdpr_data_residency": {
        "description": "Bloquear acceso a datos individuales para usuarios EU (GDPR)",
        "policy": """
forbid(
    principal,
    action in [
        AgentCore::Action::"DataTarget___query_customer_records",
        AgentCore::Action::"DataTarget___get_customer_details"
    ],
    resource == AgentCore::Gateway::"arn:aws:bedrock-agentcore:us-east-1:123456789:gateway/my-gateway"
)
when {
    context.input has geography &&
    context.input.geography == "EU"
};
""",
    },
    "restricted_geography": {
        "description": "Denegar todo acceso a herramientas desde geografías restringidas",
        "policy": """
forbid(
    principal,
    action in [
        AgentCore::Action::"DataTarget___query_customer_records",
        AgentCore::Action::"DataTarget___get_customer_details",
        AgentCore::Action::"DataTarget___get_summary",
        AgentCore::Action::"DataTarget___query_audit_log"
    ],
    resource == AgentCore::Gateway::"arn:aws:bedrock-agentcore:us-east-1:123456789:gateway/my-gateway"
)
when {
    context.input has geography &&
    context.input.geography == "RESTRICTED"
};
""",
    },
    "coverage_limit": {
        "description": "Limitar creación de aplicaciones a coberturas <= $1M",
        "policy": """
permit(
    principal,
    action == AgentCore::Action::"ApplicationToolTarget___create_application",
    resource == AgentCore::Gateway::"arn:aws:bedrock-agentcore:us-east-1:123456789:gateway/my-gateway"
)
when {
    context.input.coverage_amount <= 1000000
};
""",
    },
}

CLI_EXAMPLES = """
# ============================================================
# Comandos AgentCore CLI para desplegar políticas Cedar
# ============================================================

# 1. Crear un Policy Engine y asociarlo a un Gateway
agentcore add policy-engine --name BankingPolicyEngine \\
    --gateway BankingGateway \\
    --enforcement ENFORCE

# 2. Agregar una política desde un archivo .cedar
agentcore add policy --name RefundLimit \\
    --engine BankingPolicyEngine \\
    --source policies/refund_limit.cedar

# 3. Generar una política desde lenguaje natural
#    (requiere que el Gateway esté desplegado primero)
agentcore add policy --name GDPRRestriction \\
    --engine BankingPolicyEngine \\
    --generate "Block access to individual customer records for EU users" \\
    --gateway BankingGateway

# 4. Ver el estado del despliegue
agentcore status

# 5. Desplegar todo
agentcore deploy

# ============================================================
# Nota sobre el despliegue en dos fases:
# Las políticas Cedar que referencian ARNs específicos de Gateway
# requieren:
#   1. Desplegar sin la política para crear el Gateway
#   2. Obtener el ARN del Gateway con `agentcore status`
#   3. Actualizar el archivo .cedar con el ARN
#   4. Agregar la política y redesplegar
#
# Alternativa: usar --generate que resuelve ARNs automáticamente
# ============================================================
"""


def print_cedar_examples():
    """Muestra todos los ejemplos de políticas Cedar."""
    print("=" * 70)
    print(" EJEMPLOS DE POLÍTICAS CEDAR PARA AGENTCORE GATEWAY")
    print("=" * 70)

    for name, example in CEDAR_EXAMPLES.items():
        print(f"\n{'─'*70}")
        print(f" Política: {name}")
        print(f" Descripción: {example['description']}")
        print(f"{'─'*70}")
        print(example["policy"])

    print("\n" + "=" * 70)
    print(" COMBINACIÓN: GUARDRAILS + CEDAR EN AGENTCORE")
    print("=" * 70)
    print("""
┌─────────────────────────────────────────────────────────────────┐
│                    AgentCore Gateway                             │
│                                                                 │
│  1. REQUEST llega al Gateway                                    │
│     │                                                           │
│  2. ▼ GUARDRAILS evalúa contenido (ML, probabilístico)         │
│     │  - Prompt injection? → señal                             │
│     │  - Contenido dañino? → señal                             │
│     │  - PII expuesto?     → señal                             │
│     │                                                           │
│  3. ▼ CEDAR POLICY decide (determinístico)                     │
│     │  - ¿permit o forbid?                                     │
│     │  - Evalúa principal + action + resource + conditions      │
│     │  - forbid SIEMPRE gana sobre permit                      │
│     │                                                           │
│  4. ▼ RESULTADO                                                │
│     ├── ALLOW → request pasa a la herramienta MCP              │
│     └── DENY  → request bloqueado, respuesta al agente         │
└─────────────────────────────────────────────────────────────────┘

Ventaja clave: Las verificaciones ocurren FUERA del código del agente.
El agente no puede ver ni razonar alrededor de estas protecciones.
""")


def print_cli_examples():
    """Muestra comandos CLI de AgentCore."""
    print("\n" + "=" * 70)
    print(" COMANDOS AGENTCORE CLI")
    print("=" * 70)
    print(CLI_EXAMPLES)


if __name__ == "__main__":
    print_cedar_examples()
    print_cli_examples()
