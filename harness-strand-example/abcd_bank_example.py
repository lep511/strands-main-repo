"""ABCD Bank — AI customer-service chatbot on Amazon Bedrock with Guardrails.

ABCD Bank wants a safe, compliant, on-topic chatbot. Under the bank's internal
policies the following topics are OFF-LIMITS in customer conversations:

  * Financial advice  — e.g. "Can you suggest some good stocks to invest in?"
  * Political advice  — e.g. "What's your stance on current government policies?"
  * Medical advice    — e.g. "What should I do to manage my stress levels?"

This example provisions an Amazon Bedrock Guardrail that DENIES those three
topics (creating it automatically if it doesn't already exist), then attaches
it to a Strands Agent so the guardrail is enforced natively on every Converse
call — both on the customer's input and on the model's output.

Run:  uv run abcd_bank_example.py
"""

import boto3

# readline gives the prompt arrow-key navigation, line editing, and history.
try:
    import readline  # noqa: F401
except ImportError:  # not available on some platforms (e.g. Windows)
    readline = None

from botocore.exceptions import ClientError
from strands import Agent
from strands.models.bedrock import BedrockModel

from rich.console import Console, Group
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.live import Live
from rich.spinner import Spinner

REGION = "us-east-1"
GUARDRAIL_NAME = "abcd-bank-chatbot-guardrail"
MODEL_ID = "global.anthropic.claude-sonnet-4-6"

BLOCKED_INPUT_MESSAGE = (
    "I'm sorry, but I'm not able to help with that topic. I can assist you with "
    "ABCD Bank products, accounts, cards, payments, and general banking questions."
)
BLOCKED_OUTPUT_MESSAGE = (
    "I'm sorry, but I can't provide a response to that. Is there something about "
    "your ABCD Bank account or our services I can help you with instead?"
)

# Default contextual grounding thresholds (0.0–1.0). Responses scoring below
# these are considered ungrounded / irrelevant to the customer's question.
GROUNDING_THRESHOLD = 0.7
RELEVANCE_THRESHOLD = 0.7

# The bank's reference "source of truth". In a real deployment this would come
# from a knowledge base (e.g. Bedrock Knowledge Bases / RAG retrieval). The
# contextual grounding check verifies the assistant's answers against it.
KNOWLEDGE_BASE = (
    "ABCD Bank — official reference information:\n"
    "- Checking account: no monthly fee when you keep a $1,500 minimum daily balance; "
    "otherwise the fee is $12/month.\n"
    "- Savings account: 4.00% APY, no minimum balance, interest compounded daily.\n"
    "- Rewards credit card: 2% cashback on all purchases, no annual fee, 0% intro APR "
    "for the first 12 months.\n"
    "- Wire transfers: $25 for domestic, $45 for international.\n"
    "- Customer support: available 24/7 by phone at 1-800-555-ABCD.\n"
    "- Lost or stolen card: call 1-800-555-0199 immediately to freeze your card.\n"
    "- Branch hours: Monday–Friday 9:00 AM to 5:00 PM; Saturday 9:00 AM to 1:00 PM.\n"
    "- Mobile check deposits post within 1 business day; daily deposit limit is $5,000.\n"
)

console = Console()


def read_user_input() -> str:
    """Read a line from the customer with a colored, editable prompt."""
    if readline is not None:
        # \001 = RL_PROMPT_START_IGNORE, \002 = RL_PROMPT_END_IGNORE.
        # The reset is placed before the final visible space so readline does
        # not drop it, which would otherwise color the user's typed text.
        return input("\001\033[1;34m\002You>\001\033[0m\002 ")
    return console.input("[bold blue]You>[/bold blue] ")


# ---------------------------------------------------------------------------
# Guardrail provisioning — deny Financial / Political / Medical advice
# ---------------------------------------------------------------------------

def _guardrail_config() -> dict:
    """Policy configuration for the ABCD Bank chatbot guardrail.

    Denies the three off-limits topics on both input and output, applies
    content filters, and defends against prompt injection.
    """
    return {
        "topicPolicyConfig": {
            "topicsConfig": [
                {
                    "name": "Financial Advice",
                    "definition": (
                        "Personalized recommendations to buy, sell, or hold specific "
                        "investments such as stocks, funds, or crypto, or tax and "
                        "financial-planning advice beyond ABCD Bank's own products."
                    ),
                    "examples": [
                        "Can you suggest some good stocks to invest in right now?",
                        "What's the best way to save for retirement?",
                        "Should I put my money in a high-risk investment?",
                        "How can I maximize my returns on investments?",
                        "Is it a good time to buy real estate?",
                    ],
                    "type": "DENY",
                },
                {
                    "name": "Political Advice",
                    "definition": (
                        "Conversations that express views, opinions, or endorsements "
                        "related to political parties, political ideologies, elections, "
                        "or political figures."
                    ),
                    "examples": [
                        "What's your stance on the current government policies?",
                        "Do you support party X or Y in the upcoming election?",
                        "Can you tell me which political party is better?",
                        "What do you think about the new policy introduced by the president?",
                        "Should I vote for this candidate?",
                    ],
                    "type": "DENY",
                },
                {
                    "name": "Medical Advice",
                    "definition": (
                        "Discussions that provide guidance, recommendations, or "
                        "suggestions related to health, medical treatments, symptoms, "
                        "or overall wellness."
                    ),
                    "examples": [
                        "What are the best ways to manage chronic pain?",
                        "Can you recommend a good diet for heart health?",
                        "What should I do if I have persistent headaches?",
                        "Is it safe to combine these medications?",
                        "How can I improve my mental well-being?",
                    ],
                    "type": "DENY",
                },
            ],
        },
        "wordPolicyConfig": {
            "wordsConfig": [
                {"text": "suicide"},
                {"text": "self-harm"},
                {"text": "terrorist"},
                {"text": "illegal"},
            ],
        },
        "contentPolicyConfig": {
            "filtersConfig": [
                {"type": "SEXUAL", "inputStrength": "HIGH", "outputStrength": "HIGH"},
                {"type": "VIOLENCE", "inputStrength": "HIGH", "outputStrength": "HIGH"},
                {"type": "HATE", "inputStrength": "HIGH", "outputStrength": "HIGH"},
                {"type": "INSULTS", "inputStrength": "MEDIUM", "outputStrength": "MEDIUM"},
                {"type": "MISCONDUCT", "inputStrength": "MEDIUM", "outputStrength": "MEDIUM"},
                # PROMPT_ATTACK only supports input filtering; outputStrength must be NONE.
                {"type": "PROMPT_ATTACK", "inputStrength": "HIGH", "outputStrength": "NONE"},
            ],
        },
        "contextualGroundingPolicyConfig": {
            "filtersConfig": [
                {"type": "GROUNDING", "threshold": GROUNDING_THRESHOLD},
                {"type": "RELEVANCE", "threshold": RELEVANCE_THRESHOLD},
            ],
        },
        "blockedInputMessaging": BLOCKED_INPUT_MESSAGE,
        "blockedOutputsMessaging": BLOCKED_OUTPUT_MESSAGE,
    }


def ensure_guardrail(name: str = GUARDRAIL_NAME) -> tuple[str, str] | None:
    """Return the ``(id, version)`` of the guardrail named ``name``.

    Looks the guardrail up by name; if none exists, it is created with the
    policy configuration from :func:`_guardrail_config`. Returns ``None`` if the
    guardrail could not be found or created (e.g. missing IAM permissions).
    """
    client = boto3.client("bedrock", REGION)

    # 1. Try to find an existing guardrail with this name.
    try:
        paginator = client.get_paginator("list_guardrails")
        for page in paginator.paginate():
            for g in page.get("guardrails", []):
                if g.get("name") == name:
                    console.print(Panel(
                        f"Using existing guardrail [bold]{name}[/bold] "
                        f"([cyan]{g['id']}[/cyan])",
                        title="Guardrail Found",
                        title_align="left",
                        border_style="green",
                    ))
                    # DRAFT always reflects the latest working version.
                    return g["id"], "DRAFT"
    except ClientError as e:
        console.print(Panel(
            f"Could not list guardrails: {e.response['Error']['Message']}",
            title="Guardrails Unavailable",
            border_style="yellow",
        ))
        return None

    # 2. Not found — create it.
    console.print(Panel(
        f"No guardrail named [bold]{name}[/bold] found — creating it...",
        title="Creating Guardrail",
        title_align="left",
        border_style="cyan",
    ))
    try:
        response = client.create_guardrail(
            name=name,
            description="Auto-created guardrail for the ABCD Bank customer-service chatbot.",
            **_guardrail_config(),
        )
        gid = response["guardrailId"]
        version = response.get("version", "DRAFT")
        console.print(Panel(
            f"Created guardrail [bold]{name}[/bold] ([cyan]{gid}[/cyan]), "
            f"version [bold]{version}[/bold].\n"
            "[dim]Denied topics: Financial advice, Political advice, Medical advice.[/dim]",
            title="Guardrail Created",
            title_align="left",
            border_style="green",
        ))
        return gid, version
    except ClientError as e:
        console.print(Panel(
            f"Could not create guardrail: {e.response['Error']['Message']}\n\n"
            "[dim]The chatbot cannot run safely without its guardrail.[/dim]",
            title="Guardrail Creation Failed",
            title_align="left",
            border_style="red",
        ))
        return None


def show_guardrail_policies(guardrail_id: str, version: str) -> None:
    """Print the denied topics and active content filters for the guardrail."""
    client = boto3.client("bedrock", REGION)
    try:
        detail = client.get_guardrail(guardrailIdentifier=guardrail_id, guardrailVersion=version)
    except ClientError:
        return

    table = Table(
        title="Active Guardrail Policies",
        title_style="bold cyan",
        border_style="cyan",
        show_lines=True,
        padding=(0, 1),
    )
    table.add_column("Policy", style="bold", no_wrap=True)
    table.add_column("Detail")

    topics = detail.get("topicPolicy", {}).get("topics", [])
    if topics:
        names = "\n".join(f"• {t['name']} → [red]{t['type']}[/red]" for t in topics)
        table.add_row("Denied Topics", names)

    words = detail.get("wordPolicy", {}).get("words", [])
    if words:
        names = ", ".join(w["text"] for w in words)
        table.add_row("Blocked Words", names)

    filters = [
        f for f in detail.get("contentPolicy", {}).get("filters", [])
        if f.get("inputStrength", "NONE") != "NONE" or f.get("outputStrength", "NONE") != "NONE"
    ]
    if filters:
        names = "\n".join(
            f"• {f['type']} (in={f.get('inputStrength')}, out={f.get('outputStrength')})"
            for f in filters
        )
        table.add_row("Content Filters", names)

    grounding = detail.get("contextualGroundingPolicy", {}).get("filters", [])
    if grounding:
        names = "\n".join(
            f"• {f['type']} (threshold={f.get('threshold')})" for f in grounding
        )
        table.add_row("Contextual Grounding", names)

    console.print(table)
    console.print()


# ---------------------------------------------------------------------------
# Contextual grounding verification
# ---------------------------------------------------------------------------

def check_contextual_grounding(guardrail_id: str, version: str, query: str, answer: str) -> None:
    """Verify an answer against the knowledge base with the grounding filters.

    Calls ``apply_guardrail`` supplying the bank's knowledge base as the
    ``grounding_source`` and the customer's question as the ``query`` so Amazon
    Bedrock scores how grounded and relevant the assistant's answer is. Strands
    does not attach these qualifiers on the normal Converse path, so this
    explicit call is what makes the GROUNDING / RELEVANCE filters take effect.
    """
    client = boto3.client("bedrock-runtime", REGION)
    try:
        response = client.apply_guardrail(
            guardrailIdentifier=guardrail_id,
            guardrailVersion=version,
            source="OUTPUT",
            content=[
                {"text": {"text": KNOWLEDGE_BASE, "qualifiers": ["grounding_source"]}},
                {"text": {"text": query, "qualifiers": ["query"]}},
                {"text": {"text": answer}},
            ],
        )
    except ClientError as e:
        console.print(Panel(
            f"Contextual grounding check failed: {e.response['Error']['Message']}",
            title="Grounding Check Error",
            title_align="left",
            border_style="yellow",
        ))
        return

    filters = []
    for assessment in response.get("assessments", []):
        filters.extend(assessment.get("contextualGroundingPolicy", {}).get("filters", []))
    if not filters:
        return

    scores = {f["type"]: (f.get("score", 0.0), f.get("threshold", 0.0)) for f in filters}
    grounding_ok = scores.get("GROUNDING", (1.0, 0.0))[0] >= scores.get("GROUNDING", (1.0, 0.0))[1]
    relevance_ok = scores.get("RELEVANCE", (1.0, 0.0))[0] >= scores.get("RELEVANCE", (1.0, 0.0))[1]

    details = Text()
    for f in filters:
        score = f.get("score", 0.0)
        threshold = f.get("threshold", 0.0)
        passed = score >= threshold
        mark = "✓" if passed else "•"
        style = "green" if passed else "yellow"
        details.append(f"  {mark} {f['type']}: ", style=f"bold {style}")
        details.append(f"score={score:.2f} (threshold {threshold:.2f})\n", style=style)

    # These scores are an informational quality signal, NOT a pass/fail verdict.
    # Contextual grounding is designed for factual RAG answers; a conversational
    # assistant that declines, redirects, or adds empathy will legitimately score
    # low — that is expected behaviour, not an error. So we never alarm in red;
    # we explain what a low score on each filter means and let a human judge.
    notes = []
    if not relevance_ok:
        notes.append(
            "Low RELEVANCE usually means the assistant declined or redirected a "
            "question outside ABCD Bank's scope — expected for off-topic or "
            "off-limits requests."
        )
    if not grounding_ok:
        notes.append(
            "Low GROUNDING means part of the reply isn't drawn from the ABCD Bank "
            "knowledge base (e.g. a decline or general wording). Verify any "
            "factual claims before relying on them."
        )

    if notes:
        title = "ℹ Contextual Grounding (quality signal)"
        border = "yellow"
        for note in notes:
            details.append(f"\n{note}\n", style="dim italic")
    else:
        title = "✓ Contextual Grounding (grounded & relevant)"
        border = "green"

    console.print(Panel(
        details,
        title=title,
        title_align="left",
        border_style=border,
        padding=(0, 2),
    ))


def _assessment_reasons(response: dict) -> Text | None:
    """Build a human-readable summary of the policies triggered in a response."""
    reasons = Text()
    for assessment in response.get("assessments", []):
        for t in assessment.get("topicPolicy", {}).get("topics", []):
            reasons.append("• Topic: ", style="bold yellow")
            reasons.append(f"{t['name']} → {t['action']}\n", style="yellow")
        for w in assessment.get("wordPolicy", {}).get("customWords", []):
            reasons.append("• Blocked word: ", style="bold yellow")
            reasons.append(f"{w.get('match', '')} → {w['action']}\n", style="yellow")
        for f in assessment.get("contentPolicy", {}).get("filters", []):
            reasons.append("• Content filter: ", style="bold yellow")
            reasons.append(
                f"{f['type']} ({f.get('confidence', '')}) → {f['action']}\n",
                style="yellow",
            )
    return reasons if len(reasons) else None


def guardrail_reasons(guardrail_id: str, version: str, text: str, source: str) -> Text | None:
    """Return the policies ``text`` triggers for ``source`` (INPUT/OUTPUT), if any."""
    client = boto3.client("bedrock-runtime", REGION)
    try:
        response = client.apply_guardrail(
            guardrailIdentifier=guardrail_id,
            guardrailVersion=version,
            source=source,
            content=[{"text": {"text": text}}],
        )
    except ClientError:
        return None
    return _assessment_reasons(response)


def screen_input(guardrail_id: str, version: str, text: str) -> Text | None:
    """Pre-screen the user's message against the guardrail before calling the model.

    Returns the triggered-policy summary if the input violates an off-limits
    topic, word, or content policy (so the caller can block the turn
    deterministically), or ``None`` if the input is allowed.
    """
    client = boto3.client("bedrock-runtime", REGION)
    try:
        response = client.apply_guardrail(
            guardrailIdentifier=guardrail_id,
            guardrailVersion=version,
            source="INPUT",
            content=[{"text": {"text": text}}],
        )
    except ClientError:
        # Fail open on screening errors; the model-attached guardrail still applies.
        return None

    if response.get("action") != "GUARDRAIL_INTERVENED":
        return None
    return _assessment_reasons(response)


def show_blocked_panel(message: str, reason: Text | None, where: str) -> None:
    """Render the standard red 'blocked by guardrail' panel."""
    body: list = [Markdown(message)]
    if reason is not None:
        body.append(Text("\nTriggered policies:", style="bold"))
        body.append(reason)
    console.print(Panel(
        Group(*body),
        title=f"🛡 Blocked by Guardrail ({where})",
        title_align="left",
        border_style="red",
        padding=(1, 2),
    ))


# ---------------------------------------------------------------------------
# Streaming UI
# ---------------------------------------------------------------------------

class RichCallbackHandler:
    """Streams agent output into a Rich Live display, rendered as Markdown."""

    def __init__(self):
        self._buffer = ""
        self._spinner = Spinner("dots", text=Text(" Thinking…", style="cyan"), style="cyan")
        # transient=True clears the live stream when stopped, so the final
        # answer is only shown once (in the "ABCD Assistant" panel below).
        self._live = Live(
            console=console,
            refresh_per_second=12,
            vertical_overflow="visible",
            transient=True,
        )

    def start(self):
        self._buffer = ""
        self._live.start()
        self._live.update(self._spinner)

    def stop(self):
        self._live.stop()

    def __call__(self, **kwargs):
        reasoning = kwargs.get("reasoningText", "")
        data = kwargs.get("data", "")
        complete = kwargs.get("complete", False)

        if reasoning:
            self._buffer += reasoning
        if data:
            self._buffer += data

        if self._buffer:
            self._live.update(Markdown(self._buffer))
        if complete and self._buffer:
            self._live.update(Markdown(self._buffer))


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = (
    "You are the virtual customer-service assistant for ABCD Bank, a large, "
    "regulated financial institution. Be professional, concise, and friendly.\n\n"
    "Answer customer questions using ONLY the ABCD Bank reference information "
    "below. If the answer is not contained in it, say you don't have that "
    "information and offer to connect the customer with a representative. Do not "
    "invent account terms, fees, rates, or policies.\n\n"
    "You must NOT provide financial/investment advice, political opinions, or "
    "medical advice. If a customer asks for any of these, politely decline and "
    "steer the conversation back to how you can help with their banking needs. "
    "Never ask for full card numbers, PINs, or passwords.\n\n"
    "=== ABCD Bank reference information ===\n"
    f"{KNOWLEDGE_BASE}"
)


def build_agent(callback: RichCallbackHandler) -> tuple[Agent, str, str] | None:
    """Provision the guardrail and build the guardrail-enforced ABCD Bank agent.

    Returns ``(agent, guardrail_id, guardrail_version)`` or ``None`` if the
    guardrail could not be provisioned.
    """
    guardrail = ensure_guardrail()
    if guardrail is None:
        return None

    gid, gver = guardrail
    show_guardrail_policies(gid, gver)

    # The guardrail is attached to the Bedrock model, so Amazon Bedrock enforces
    # it natively during the Converse call for both input and output.
    model = BedrockModel(
        region_name=REGION,
        model_id=MODEL_ID,
        guardrail_id=gid,
        guardrail_version=gver,
        guardrail_trace="enabled",
        guardrail_redact_input=True,
        guardrail_redact_input_message=BLOCKED_INPUT_MESSAGE,
        guardrail_redact_output=True,
        guardrail_redact_output_message=BLOCKED_OUTPUT_MESSAGE,
    )

    agent = Agent(
        agent_id="abcd-bank-assistant",
        model=model,
        system_prompt=SYSTEM_PROMPT,
        callback_handler=callback,
    )
    return agent, gid, gver


def main():
    console.print(Panel(
        "[bold]ABCD Bank[/bold] — AI Customer Service Assistant\n"
        "[dim]Powered by Amazon Bedrock with Guardrails. Off-limits topics "
        "(financial, political, and medical advice) are blocked automatically.\n"
        "Type your message and press Enter. Type [bold]exit[/bold] or "
        "[bold]quit[/bold] to leave.[/dim]",
        border_style="cyan",
        padding=(0, 2),
    ))

    callback = RichCallbackHandler()
    built = build_agent(callback)
    if built is None:
        console.print("[bold red]Cannot start the chatbot without its guardrail. Exiting.[/bold red]")
        return
    agent, gid, gver = built

    while True:
        try:
            console.print()
            prompt = read_user_input().strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]Thank you for banking with ABCD Bank. Goodbye![/dim]")
            break

        if not prompt:
            continue
        if prompt.lower() in ("exit", "quit"):
            console.print("[dim]Thank you for banking with ABCD Bank. Goodbye![/dim]")
            break

        # 1. Deterministically pre-screen the input. If it violates an off-limits
        #    policy, block the turn here — don't call the model or run grounding
        #    (grounding a refusal to an off-limits request is meaningless).
        console.print()
        input_reason = screen_input(gid, gver, prompt)
        if input_reason is not None:
            show_blocked_panel(BLOCKED_INPUT_MESSAGE, input_reason, where="input")
            continue

        # 2. Input allowed — let the model answer (its attached guardrail still
        #    enforces the policies on the generated output as a second layer).
        callback.start()
        try:
            result = agent(prompt)
        finally:
            callback.stop()

        answer = str(result)
        console.print()

        if result.stop_reason == "guardrail_intervened":
            # The output (now redacted) was blocked; surface the input's triggers.
            show_blocked_panel(answer, guardrail_reasons(gid, gver, prompt, "INPUT"), where="output")
        else:
            console.print(Panel(
                Markdown(answer),
                title="🤖 ABCD Assistant (model response)",
                title_align="left",
                border_style="green",
                padding=(1, 2),
            ))
            # Verify the model's answer is grounded in and relevant to the KB.
            if answer.strip():
                check_contextual_grounding(gid, gver, prompt, answer)


if __name__ == "__main__":
    main()
