"""
Lab 02 - Paso 1: Crear un Amazon Bedrock Guardrail

Crea un guardrail con:
- Content filters (hate, insults, sexual, violence, misconduct, prompt attack)
- Denied topics (investment advice)
- Word filters (competitor names, profanity)
- Sensitive information filters (PII: email, phone, credit card)
"""

import boto3
import json


def create_guardrail():
    client = boto3.client("bedrock", region_name="us-east-1")

    response = client.create_guardrail(
        name="lab02-guardrail",
        description="Guardrail para un asistente bancario que bloquea contenido dañino, "
        "temas no permitidos y protege información sensible.",
        blockedInputMessaging="Lo siento, no puedo procesar esa solicitud. "
        "Por favor reformule su pregunta.",
        blockedOutputsMessaging="Lo siento, no puedo proporcionar esa información. "
        "¿Puedo ayudarle con algo más?",
        # --- Content Filters ---
        contentPolicyConfig={
            "filtersConfig": [
                {
                    "type": "HATE",
                    "inputStrength": "HIGH",
                    "outputStrength": "HIGH",
                },
                {
                    "type": "INSULTS",
                    "inputStrength": "HIGH",
                    "outputStrength": "HIGH",
                },
                {
                    "type": "SEXUAL",
                    "inputStrength": "HIGH",
                    "outputStrength": "HIGH",
                },
                {
                    "type": "VIOLENCE",
                    "inputStrength": "MEDIUM",
                    "outputStrength": "HIGH",
                },
                {
                    "type": "MISCONDUCT",
                    "inputStrength": "HIGH",
                    "outputStrength": "HIGH",
                },
                {
                    "type": "PROMPT_ATTACK",
                    "inputStrength": "HIGH",
                    "outputStrength": "NONE",
                },
            ]
        },
        # --- Denied Topics ---
        topicPolicyConfig={
            "topicsConfig": [
                {
                    "name": "InvestmentAdvice",
                    "definition": "Consejos sobre inversiones financieras específicas, "
                    "recomendaciones de compra o venta de acciones, "
                    "criptomonedas o instrumentos financieros.",
                    "examples": [
                        "¿Debería comprar acciones de Tesla?",
                        "¿Es buen momento para invertir en Bitcoin?",
                        "Recomiéndame un fondo de inversión",
                    ],
                    "type": "DENY",
                },
                {
                    "name": "CompetitorDiscussion",
                    "definition": "Discusiones que comparan nuestros servicios con competidores "
                    "o recomiendan servicios de otras instituciones financieras.",
                    "examples": [
                        "¿Es mejor el banco X que ustedes?",
                        "¿Por qué no me cambio al banco Y?",
                    ],
                    "type": "DENY",
                },
            ]
        },
        # --- Word Filters ---
        wordPolicyConfig={
            "wordsConfig": [
                {"text": "hackear"},
                {"text": "estafar"},
                {"text": "lavar dinero"},
            ],
            "managedWordListsConfig": [
                {"type": "PROFANITY"},
            ],
        },
        # --- Sensitive Information Filters ---
        sensitiveInformationPolicyConfig={
            "piiEntitiesConfig": [
                {"type": "EMAIL", "action": "ANONYMIZE"},
                {"type": "PHONE", "action": "ANONYMIZE"},
                {"type": "NAME", "action": "ANONYMIZE"},
                {"type": "CREDIT_DEBIT_CARD_NUMBER", "action": "BLOCK"},
                {"type": "US_SOCIAL_SECURITY_NUMBER", "action": "BLOCK"},
            ],
        },
    )

    guardrail_id = response["guardrailId"]
    guardrail_version = response["version"]

    print(f"Guardrail creado exitosamente!")
    print(f"  ID:      {guardrail_id}")
    print(f"  Version: {guardrail_version}")
    print(f"  ARN:     {response['guardrailArn']}")

    return guardrail_id, guardrail_version


def list_guardrails():
    client = boto3.client("bedrock", region_name="us-east-1")
    response = client.list_guardrails()

    print("\n--- Guardrails existentes ---")
    for guardrail in response["guardrails"]:
        print(f"  {guardrail['name']} (ID: {guardrail['id']}, Status: {guardrail['status']})")


if __name__ == "__main__":
    guardrail_id, version = create_guardrail()
    list_guardrails()

    print(f"\n>>> Guarda estos valores para el siguiente paso:")
    print(f"    GUARDRAIL_ID={guardrail_id}")
    print(f"    GUARDRAIL_VERSION={version}")
