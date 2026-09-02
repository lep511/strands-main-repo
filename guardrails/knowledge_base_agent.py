#!/usr/bin/env python3
"""
ITSM Knowledge Base Agent

Queries the Bedrock Knowledge Base (demokb123) containing IT policies,
employee data, and trade secrets. Uses boto3 directly for KB retrieval
and the Converse API for answer generation.

Run: python knowledge_base_agent.py
Requires: export STRANDS_KNOWLEDGE_BASE_ID=XJZIZPSFH0  (or set in .env)
"""

import os
import json
import readline  # noqa: F401 — enables arrow keys and history in input()
import boto3

REGION = os.environ.get("AWS_REGION", os.environ.get("AWS_DEFAULT_REGION", "us-west-2"))
KB_ID = os.environ.get("STRANDS_KNOWLEDGE_BASE_ID", "XJZIZPSFH0")
MODEL_ID = os.environ.get("BEDROCK_MODEL_ID", "us.anthropic.claude-sonnet-4-5-20250929-v1:0")
GUARDRAIL_NAME = "Enterprise-Guardrail"

bedrock_agent_runtime = boto3.client("bedrock-agent-runtime", region_name=REGION)
bedrock_runtime = boto3.client("bedrock-runtime", region_name=REGION)
bedrock_control = boto3.client("bedrock", region_name=REGION)

guardrail_id = None
guardrail_version = None

SYSTEM_PROMPT = """You are an ITSM (IT Service Management) assistant. You answer questions
about company IT policies, employee information, and internal documentation based on
information retrieved from the knowledge base.

Your responses should:
- Be direct and concise
- Not mention document IDs, relevance scores, or metadata
- Acknowledge when information is not found
- Never fabricate information not present in the retrieved context"""


def retrieve(query, max_results=5, min_score=0.4):
    """Retrieve relevant chunks from the Knowledge Base."""
    resp = bedrock_agent_runtime.retrieve(
        knowledgeBaseId=KB_ID,
        retrievalQuery={"text": query},
        retrievalConfiguration={"vectorSearchConfiguration": {"numberOfResults": max_results}},
    )
    results = []
    for r in resp.get("retrievalResults", []):
        score = r.get("score", 0)
        if score >= min_score:
            results.append(r["content"]["text"])
    return results


def generate_answer(query, context_chunks):
    """Generate an answer using the Converse API with retrieved context."""
    if not context_chunks:
        return "I don't have any information about that in the knowledge base."

    context = "\n\n---\n\n".join(context_chunks)
    prompt = f"Context from knowledge base:\n{context}\n\nUser question: {query}"

    resp = bedrock_runtime.converse(
        modelId=MODEL_ID,
        messages=[{"role": "user", "content": [{"text": prompt}]}],
        system=[{"text": SYSTEM_PROMPT}],
        inferenceConfig={"maxTokens": 1024},
    )
    return resp["output"]["message"]["content"][0]["text"]


def apply_guardrail(text, source):
    """Apply guardrail to text. Returns (allowed, output_text)."""
    if not guardrail_id:
        return True, text
    resp = bedrock_runtime.apply_guardrail(
        guardrailIdentifier=guardrail_id,
        guardrailVersion=guardrail_version,
        source=source,
        content=[{"text": {"text": text}}],
    )
    outputs = resp.get("outputs", [])
    output_text = outputs[0].get("text", text) if outputs else text
    if resp["action"] == "GUARDRAIL_INTERVENED":
        return False, output_text
    return True, output_text


def run_query(query):
    """Retrieve from KB and generate an answer, with optional guardrail screening."""
    allowed, screened = apply_guardrail(query, "INPUT")
    if not allowed:
        return f"[Guardrail - input blocked] {screened}"

    chunks = retrieve(query)
    answer = generate_answer(query, chunks)

    allowed, screened = apply_guardrail(answer, "OUTPUT")
    if not allowed:
        return f"[Guardrail - output blocked] {screened}"
    return screened


def find_guardrail():
    """Look up the Enterprise-Guardrail by name. Returns (id, version) or (None, None)."""
    try:
        for g in bedrock_control.list_guardrails().get("guardrails", []):
            if g["name"] == GUARDRAIL_NAME:
                return g["id"], g["version"]
    except Exception:
        pass
    return None, None


if __name__ == "__main__":
    print(f"\nITSM Knowledge Base Agent")
    print(f"KB: {KB_ID} | Model: {MODEL_ID} | Region: {REGION}\n")

    choice = input("Enable guardrails? (y/n): ").strip().lower()
    if choice in ("y", "yes"):
        gid, gver = find_guardrail()
        if gid:
            guardrail_id = gid
            guardrail_version = gver
            print(f"Guardrail enabled: {GUARDRAIL_NAME} (id={gid}, version={gver})")
        else:
            print(f"\nGuardrail '{GUARDRAIL_NAME}' not found.")
            print("To create it, run the guardrails notebook:")
            print("  cc_bedrock_guardrails_lab.ipynb (Steps 4-6)\n")
            print("Continuing without guardrails.\n")
    else:
        print("Guardrails disabled.")

    print("\nAsk questions about IT policies, employee info, or company docs.")
    print("Type 'exit' to quit.\n")

    while True:
        try:
            user_input = input("> ").strip()
            if user_input.lower() in ("exit", "quit"):
                break
            if not user_input:
                continue
            print()
            print(run_query(user_input))
            print()
        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"\nError: {e}\n")