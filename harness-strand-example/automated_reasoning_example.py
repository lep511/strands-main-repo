"""Amazon Bedrock Guardrails — Automated Reasoning checks example.

Automated Reasoning checks use formal logic (not pattern matching) to
mathematically validate whether an LLM response is consistent with a policy you
define. Unlike content/topic filters that block or allow, Automated Reasoning
runs in *detect mode*: it returns structured findings (VALID, INVALID,
SATISFIABLE, ...) plus the premises, claims, and policy rules behind each
verdict. Your application decides what to do with that feedback — serve the
answer, rewrite it, or ask for clarification.

Docs: https://docs.aws.amazon.com/bedrock/latest/userguide/guardrails-automated-reasoning-checks.html
      https://docs.aws.amazon.com/bedrock/latest/userguide/integrate-automated-reasoning-checks.html

This example:
  1. Provisions a guardrail with an Automated Reasoning policy if one doesn't
     already exist (builds the policy from an embedded plain-text document).
  2. Has a Strands agent answer policy questions.
  3. Validates each answer with ApplyGuardrail and prints the findings.
  4. Runs an automatic rewriting loop when the answer isn't VALID.

Run:  uv run automated_reasoning_example.py

Note: building an Automated Reasoning policy is an asynchronous workflow that
can take several minutes. In production you normally create and review the
policy (and its fidelity report) once in the console, then pass its guardrail
to this kind of runtime integration.
"""

import os
import time
from pathlib import Path

import boto3

try:
    import readline  # noqa: F401  # arrow keys / history for input()
except ImportError:
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
GUARDRAIL_NAME = "parental-leave-ar-guardrail"
AR_POLICY_NAME = "parental-leave-policy"
MODEL_ID = os.environ.get("AR_MODEL_ID", "global.anthropic.claude-sonnet-4-6")
MAX_REWRITE_ITERATIONS = 3

# Hybrid mode: run the LLM (Converse) on a real AWS account via this named
# profile, while guardrails + Automated Reasoning use the local emulator.
# Set AR_REAL_LLM_PROFILE=default to use your account's real model inference.
REAL_LLM_PROFILE = os.environ.get("AR_REAL_LLM_PROFILE")
REAL_LLM_REGION = os.environ.get("AR_REAL_LLM_REGION", REGION)

# Demo mode: run the full findings + rewriting-loop UX against sample findings
# WITHOUT calling Bedrock. Useful where the account lacks Automated Reasoning
# permissions or the emulator can't run AR. Enable with AR_DEMO=1.
DEMO_MODE = os.environ.get("AR_DEMO", "").lower() in ("1", "true", "yes", "on")

# Populated by setup_targets(); the discovered emulator settings or None.
_EMULATOR: dict | None = None

# Optional override: if you already created a guardrail with an AR policy in the
# console, set these env vars and provisioning is skipped entirely.
ENV_GUARDRAIL_ID = os.environ.get("AR_GUARDRAIL_ID")
ENV_GUARDRAIL_VERSION = os.environ.get("AR_GUARDRAIL_VERSION")

# The source document the Automated Reasoning policy is extracted from. Clear,
# unambiguous rules extract into formal logic most reliably.
POLICY_DOCUMENT = """\
ABCD Company — Parental Leave Eligibility Policy

1. An employee is eligible for parental leave only if they are employed full-time.
2. An employee is eligible for parental leave only if they have been employed for at least 12 months.
3. Part-time employees are not eligible for parental leave.
4. An employee who has been employed for fewer than 12 months is not eligible for parental leave.
5. An eligible employee may take up to 12 weeks of parental leave.
6. An employee is not eligible for more than 12 weeks of parental leave.
"""

SYSTEM_PROMPT = (
    "You are an HR assistant for ABCD Company. Answer employee questions about "
    "the parental leave policy clearly and concisely. Base every answer strictly "
    "on the policy below; do not invent rules.\n\n"
    f"{POLICY_DOCUMENT}"
)

# Severity order from worst to best (from the AWS integration guide). Lower is worse.
SEVERITY_ORDER = {
    "tooComplex": 0,
    "translationAmbiguous": 0,
    "impossible": 1,
    "invalid": 2,
    "satisfiable": 3,
    "valid": 4,
    "noTranslations": 5,
}
FINDING_TYPES = [
    "valid", "invalid", "satisfiable", "impossible",
    "translationAmbiguous", "tooComplex", "noTranslations",
]

console = Console()


def read_user_input() -> str:
    if readline is not None:
        return input("\001\033[1;34m\002You>\001\033[0m\002 ")
    return console.input("[bold blue]You>[/bold blue] ")


# ---------------------------------------------------------------------------
# Local AWS emulator support
# ---------------------------------------------------------------------------

def _parse_kv_file(path: Path) -> dict:
    """Minimal 'key = value' parser for the emulator's config/credentials files."""
    values = {}
    try:
        for line in path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith(("[", "#")) or "=" not in line:
                continue
            key, _, val = line.partition("=")
            values[key.strip()] = val.strip()
    except OSError:
        pass
    return values


def _discover_emulator() -> dict | None:
    """Find a local AWS emulator from ~/.aws/emulator/<port>/{config,emulator_credentials}.

    Returns a dict with endpoint_url, ca_bundle, access/secret keys, and region,
    or None if no emulator config is present.
    """
    base = Path.home() / ".aws" / "emulator"
    if not base.is_dir():
        return None
    for cfg_path in sorted(base.glob("*/config")):
        cfg = _parse_kv_file(cfg_path)
        endpoint = cfg.get("endpoint_url")
        if not endpoint:
            continue
        creds = _parse_kv_file(cfg_path.parent / "emulator_credentials")
        return {
            "endpoint_url": endpoint,
            "ca_bundle": cfg.get("ca_bundle", ""),
            "region": cfg.get("region", REGION),
            "access_key": creds.get("aws_access_key_id", ""),
            "secret_key": creds.get("aws_secret_access_key", ""),
        }
    return None


def setup_targets() -> None:
    """Discover the local emulator (if any) for the guardrail / AR clients.

    Unlike setting global AWS_* env vars, this keeps the emulator config scoped
    to the explicit clients below, so the LLM can run on a real account in
    parallel (hybrid mode) without being redirected to the emulator.
    """
    global _EMULATOR
    # The local emulator implements the Bedrock control plane but does NOT run
    # Automated Reasoning at runtime (apply_guardrail returns no AR findings).
    # Set AR_USE_EMULATOR=off to route guardrails + AR to real AWS so findings
    # actually come back.
    if os.environ.get("AR_USE_EMULATOR", "auto").lower() in ("off", "0", "false", "no"):
        _EMULATOR = None
        return
    _EMULATOR = _discover_emulator()


def _strip_inference_prefix(model_id: str) -> str:
    """Drop a cross-Region inference-profile prefix the emulator rejects."""
    for prefix in ("global.", "us.", "eu.", "apac."):
        if model_id.startswith(prefix):
            return model_id[len(prefix):]
    return model_id


def _emulator_client(service: str):
    """Build a boto3 client bound to the emulator (endpoint + CA + creds)."""
    em = _EMULATOR
    session = boto3.Session(
        aws_access_key_id=em["access_key"] or None,
        aws_secret_access_key=em["secret_key"] or None,
        region_name=em["region"],
    )
    kwargs = {"endpoint_url": em["endpoint_url"]}
    if em["ca_bundle"]:
        kwargs["verify"] = em["ca_bundle"]
    return session.client(service, **kwargs)


def bedrock_client():
    """Control-plane client (guardrails + AR): emulator if present, else real."""
    if _EMULATOR is not None:
        return _emulator_client("bedrock")
    return boto3.client("bedrock", region_name=REGION)


def bedrock_runtime_client():
    """Runtime client used for apply_guardrail: emulator if present, else real."""
    if _EMULATOR is not None:
        return _emulator_client("bedrock-runtime")
    return boto3.client("bedrock-runtime", region_name=REGION)


# ---------------------------------------------------------------------------
# Provisioning — create the AR policy + guardrail if they don't exist
# ---------------------------------------------------------------------------

def _find_guardrail(name: str) -> str | None:
    client = bedrock_client()
    paginator = client.get_paginator("list_guardrails")
    for page in paginator.paginate():
        for g in page.get("guardrails", []):
            if g.get("name") == name:
                return g["id"]
    return None


def _build_ar_policy() -> str | None:
    """Create an Automated Reasoning policy from POLICY_DOCUMENT and return a
    versioned policy ARN, or None on failure."""
    client = bedrock_client()

    # Reuse an existing policy of the same name (e.g. left by a previous run)
    # instead of failing on a duplicate name or building a second time.
    policy_arn = None
    try:
        for p in client.list_automated_reasoning_policies().get("automatedReasoningPolicies", []):
            if p.get("name") == AR_POLICY_NAME:
                policy_arn = p["policyArn"]
                break
    except ClientError:
        pass

    if policy_arn is not None:
        console.print(Panel(
            f"Reusing existing Automated Reasoning policy [bold]{AR_POLICY_NAME}[/bold].",
            title="Automated Reasoning", title_align="left", border_style="green",
        ))
    else:
        console.print(Panel(
            f"Creating Automated Reasoning policy [bold]{AR_POLICY_NAME}[/bold]…",
            title="Automated Reasoning", title_align="left", border_style="cyan",
        ))
        try:
            description = "Parental leave eligibility rules for the AR checks example."
            try:
                policy = client.create_automated_reasoning_policy(
                    name=AR_POLICY_NAME, description=description,
                )
            except ClientError as e:
                msg = e.response["Error"].get("Message", "")
                code = e.response["Error"].get("Code", "")
                if code == "ConflictException" or "already exists" in msg:
                    # A policy with this name exists but isn't enumerable here
                    # (seen with the local emulator). Use a unique name so
                    # provisioning can still proceed.
                    unique_name = f"{AR_POLICY_NAME}-{int(time.time())}"
                    console.print(
                        f"[yellow]Policy name '{AR_POLICY_NAME}' is taken and not "
                        f"listable; creating '{unique_name}' instead.[/yellow]"
                    )
                    policy = client.create_automated_reasoning_policy(
                        name=unique_name, description=description,
                    )
                else:
                    raise
            policy_arn = policy["policyArn"]

            # Ingest the source document — extracts formal logic rules/variables.
            workflow = client.start_automated_reasoning_policy_build_workflow(
                policyArn=policy_arn,
                buildWorkflowType="INGEST_CONTENT",
                sourceContent={
                    "workflowContent": {
                        "documents": [{
                            "document": POLICY_DOCUMENT.encode("utf-8"),
                            "documentContentType": "txt",
                            "documentName": "parental-leave-policy",
                            "documentDescription": "ABCD Company parental leave eligibility rules.",
                        }],
                    },
                },
            )
            workflow_id = workflow["buildWorkflowId"]
        except ClientError as e:
            code = e.response["Error"].get("Code", "")
            if code in ("AccessDeniedException", "AccessDenied"):
                console.print(Panel(
                    "Your IAM identity is not allowed to create Automated Reasoning "
                    "policies (needs bedrock:CreateAutomatedReasoningPolicy, "
                    "StartAutomatedReasoningPolicyBuildWorkflow, "
                    "CreateAutomatedReasoningPolicyVersion).\n\n"
                    "Options:\n"
                    "• Point AR_GUARDRAIL_ID/AR_GUARDRAIL_VERSION at a guardrail that "
                    "already has an AR policy attached.\n"
                    "• Run the illustrative flow without AWS: [bold]AR_DEMO=1 uv run "
                    "automated_reasoning_example.py[/bold].",
                    title="⚠ Missing Automated Reasoning permissions",
                    title_align="left", border_style="red", padding=(1, 2),
                ))
                return None
            console.print(f"[yellow]Could not start policy build: {e.response['Error']['Message']}[/yellow]")
            return None

        # Poll the asynchronous build workflow until it finishes.
        spinner = Spinner("dots", text=Text(" Building policy (this can take a few minutes)…", style="cyan"))
        deadline = time.time() + 600
        with Live(spinner, console=console, refresh_per_second=8, transient=True):
            while True:
                try:
                    wf = client.get_automated_reasoning_policy_build_workflow(
                        policyArn=policy_arn, buildWorkflowId=workflow_id,
                    )
                except ClientError as e:
                    console.print(f"[yellow]Build status check failed: {e.response['Error']['Message']}[/yellow]")
                    return None
                status = wf.get("status")
                spinner.text = Text(f" Building policy… status={status}", style="cyan")
                if status == "COMPLETED":
                    break
                if status in ("FAILED", "CANCELLED"):
                    console.print(f"[red]Policy build ended with status {status}.[/red]")
                    return None
                if time.time() > deadline:
                    console.print("[red]Timed out waiting for the policy build.[/red]")
                    return None
                time.sleep(10)

    # Save an immutable version to attach to the guardrail. The version call
    # requires the hash of the current (post-ingest) policy definition as an
    # optimistic-concurrency guard, so fetch it first.
    try:
        current = client.get_automated_reasoning_policy(policyArn=policy_arn)
        version = client.create_automated_reasoning_policy_version(
            policyArn=policy_arn,
            lastUpdatedDefinitionHash=current["definitionHash"],
        )
        versioned_arn = f"{policy_arn}:{version['version']}"
    except ClientError as e:
        console.print(f"[yellow]Could not create policy version: {e.response['Error']['Message']}[/yellow]")
        return None

    console.print(Panel(
        f"Automated Reasoning policy ready: [cyan]{versioned_arn}[/cyan]",
        title="Automated Reasoning", title_align="left", border_style="green",
    ))
    return versioned_arn


def ensure_ar_guardrail() -> tuple[str, str] | None:
    """Return ``(guardrail_id, version)`` for a guardrail with an AR policy.

    Uses the env-var override if set, otherwise finds the named guardrail, and
    otherwise provisions the AR policy + guardrail from scratch.
    """
    if ENV_GUARDRAIL_ID:
        return ENV_GUARDRAIL_ID, (ENV_GUARDRAIL_VERSION or "DRAFT")

    existing = _find_guardrail(GUARDRAIL_NAME)
    if existing is not None:
        console.print(Panel(
            f"Using existing guardrail [bold]{GUARDRAIL_NAME}[/bold] ([cyan]{existing}[/cyan])",
            title="Guardrail Found", title_align="left", border_style="green",
        ))
        return existing, "DRAFT"

    console.print(Panel(
        f"No guardrail named [bold]{GUARDRAIL_NAME}[/bold] found — provisioning it "
        "(policy build can take several minutes)…",
        title="Provisioning", title_align="left", border_style="cyan",
    ))

    policy_arn = _build_ar_policy()
    if policy_arn is None:
        return None

    client = bedrock_client()
    try:
        guardrail = client.create_guardrail(
            name=GUARDRAIL_NAME,
            description="Guardrail with Automated Reasoning checks for parental leave answers.",
            # Attach the Automated Reasoning policy. AR runs in detect mode.
            automatedReasoningPolicyConfig={"policies": [policy_arn]},
            # Content filters complement AR (which does NOT block prompt injection).
            contentPolicyConfig={
                "filtersConfig": [
                    {"type": "PROMPT_ATTACK", "inputStrength": "HIGH", "outputStrength": "NONE"},
                ],
            },
            blockedInputMessaging="Sorry, I can't help with that request.",
            blockedOutputsMessaging="Sorry, I can't provide that response.",
        )
    except ClientError as e:
        console.print(Panel(
            f"Could not create guardrail: {e.response['Error']['Message']}",
            title="Guardrail Creation Failed", title_align="left", border_style="red",
        ))
        return None

    console.print(Panel(
        f"Created guardrail [bold]{GUARDRAIL_NAME}[/bold] ([cyan]{guardrail['guardrailId']}[/cyan]).",
        title="Guardrail Created", title_align="left", border_style="green",
    ))
    # DRAFT is fine for this demo; the docs recommend a numbered version for production.
    return guardrail["guardrailId"], "DRAFT"


# ---------------------------------------------------------------------------
# Runtime validation with ApplyGuardrail
# ---------------------------------------------------------------------------

def validate_response(guardrail_id: str, version: str, question: str, answer: str) -> tuple[list, int]:
    """Validate an answer with Automated Reasoning. Returns (findings, ar_units).

    ApplyGuardrail evaluates all content passed; we send the Q&A as a single
    agent-side (claim) block so AR has something to check.
    """
    client = bedrock_runtime_client()
    response = client.apply_guardrail(
        guardrailIdentifier=guardrail_id,
        guardrailVersion=version,
        source="OUTPUT",
        content=[{"text": {"text": f"User: {question}\nAssistant: {answer}"}}],
    )
    findings = []
    for assessment in response.get("assessments", []):
        findings.extend(assessment.get("automatedReasoningPolicy", {}).get("findings", []))
    # Coerce None/absent to 0 (the emulator omits or nulls this field).
    ar_units = response.get("usage", {}).get("automatedReasoningPolicyUnits") or 0
    return findings, ar_units


def get_finding_type(finding: dict) -> tuple[str | None, dict | None]:
    """Each finding is a union — return the single present key and its data."""
    for ft in FINDING_TYPES:
        if ft in finding:
            return ft, finding[ft]
    return None, None


def get_aggregate_result(findings: list) -> str | None:
    """Return the worst (lowest-severity) finding type across all findings."""
    worst, worst_sev = None, float("inf")
    for finding in findings:
        ft, _ = get_finding_type(finding)
        sev = SEVERITY_ORDER.get(ft, 0)
        if sev < worst_sev:
            worst_sev, worst = sev, ft
    return worst


_RESULT_STYLE = {
    "valid": ("✓", "green", "Proven consistent with the policy."),
    "invalid": ("✗", "red", "Contradicts the policy rules."),
    "satisfiable": ("~", "yellow", "Correct under some conditions but incomplete."),
    "impossible": ("!", "red", "Premises are contradictory."),
    "translationAmbiguous": ("?", "yellow", "Input has multiple interpretations."),
    "tooComplex": ("…", "yellow", "Exceeds logical-analysis limits."),
    "noTranslations": ("–", "dim", "Not relevant to this policy's domain."),
}


def render_findings(findings: list, ar_units: int) -> None:
    if ar_units == 0:
        msg = (
            "Automated Reasoning did not run (automatedReasoningPolicyUnits=0). "
            "Check that the guardrail has an AR policy attached and that content is tagged."
        )
        if _EMULATOR is not None:
            msg = (
                "Automated Reasoning did not run (automatedReasoningPolicyUnits=0).\n\n"
                "The local emulator implements the Bedrock control plane but does not "
                "execute Automated Reasoning at runtime, so no findings are returned.\n"
                "Run against real AWS to get findings, e.g.:\n"
                "  AR_USE_EMULATOR=off uv run automated_reasoning_example.py"
            )
        console.print(Panel(
            msg, title="⚠ AR Not Applied", title_align="left", border_style="yellow",
        ))
        return
    if not findings:
        console.print("[dim]No Automated Reasoning findings returned.[/dim]")
        return

    for finding in findings:
        ft, data = get_finding_type(finding)
        mark, color, blurb = _RESULT_STYLE.get(ft, ("•", "white", ""))
        body: list = [Text(f"{mark} {ft.upper()} — {blurb}", style=f"bold {color}")]

        translation = (data or {}).get("translation", {})
        premises = translation.get("premises", [])
        claims = translation.get("claims", [])
        if premises:
            body.append(Text("\nPremises (the 'if' facts understood):", style="bold"))
            for p in premises:
                body.append(Text(f"  • {p.get('naturalLanguage') or p.get('logic', '')}", style="cyan"))
        if claims:
            body.append(Text("\nClaims (the 'then' assertions checked):", style="bold"))
            for c in claims:
                body.append(Text(f"  • {c.get('naturalLanguage') or c.get('logic', '')}", style="cyan"))

        supporting = (data or {}).get("supportingRules", [])
        contradicting = (data or {}).get("contradictingRules", [])
        if supporting:
            ids = ", ".join(r.get("identifier", "") for r in supporting)
            body.append(Text(f"\nSupporting rules: {ids}", style="green"))
        if contradicting:
            ids = ", ".join(r.get("identifier", "") for r in contradicting)
            body.append(Text(f"\nContradicting rules: {ids}", style="red"))

        untranslated = translation.get("untranslatedClaims", []) + translation.get("untranslatedPremises", [])
        if untranslated:
            body.append(Text("\nNote: some content was outside the policy scope and was not verified.",
                             style="dim italic"))

        console.print(Panel(
            Group(*body),
            title=f"Automated Reasoning Finding: {ft}",
            title_align="left", border_style=color if color != "dim" else "white",
            padding=(1, 2),
        ))


# ---------------------------------------------------------------------------
# Generation + rewriting loop
# ---------------------------------------------------------------------------

def generate(agent: Agent, prompt: str) -> str:
    spinner = Spinner("dots", text=Text(" Thinking…", style="cyan"))
    with Live(spinner, console=console, refresh_per_second=10, transient=True):
        result = agent(prompt)
    return str(result)


def build_rewrite_prompt(question: str, answer: str, findings: list) -> str:
    """Construct the rewriting prompt from the AR feedback (per AWS guide)."""
    worst = get_aggregate_result(findings)
    data = {}
    for f in findings:
        ft, d = get_finding_type(f)
        if ft == worst:
            data = d or {}
            break
    translation = data.get("translation", {})
    premises = "; ".join(p.get("naturalLanguage") or p.get("logic", "") for p in translation.get("premises", []))
    claims = "; ".join(c.get("naturalLanguage") or c.get("logic", "") for c in translation.get("claims", []))
    rules = data.get("contradictingRules", []) or data.get("claimsFalseScenario", {})
    rule_ids = ", ".join(r.get("identifier", "") for r in data.get("contradictingRules", []))

    return (
        f"The following response was checked against our policy and found to be {worst}.\n\n"
        f"Original question: {question}\n"
        f"Original response: {answer}\n\n"
        "The validation found:\n"
        f"- Premises (understood from the input): {premises or '(none)'}\n"
        f"- Claims (what was asserted): {claims or '(none)'}\n"
        f"- Contradicting rules: {rule_ids or rules or '(none)'}\n\n"
        "Please rewrite the response so it is consistent with the parental leave "
        "policy. Keep a helpful tone and answer accurately. If you cannot answer "
        "accurately without more information, say what information is needed."
    )


def _demo_findings(iteration: int) -> tuple[list, int]:
    """Sample, realistically-shaped findings for AR_DEMO mode (no Bedrock call).

    First attempt returns INVALID (to exercise the rewriting loop); the rewrite
    then returns VALID.
    """
    if iteration == 1:
        return ([{
            "invalid": {
                "translation": {
                    "premises": [{"naturalLanguage": "The employee is employed part-time."}],
                    "claims": [{"naturalLanguage": "The employee is eligible for parental leave."}],
                    "untranslatedPremises": [], "untranslatedClaims": [],
                },
                "contradictingRules": [{"identifier": "R3"}],
            },
        }], 1)
    return ([{
        "valid": {
            "translation": {
                "premises": [
                    {"naturalLanguage": "The employee is employed full-time."},
                    {"naturalLanguage": "The employee's tenure is 24 months."},
                ],
                "claims": [{"naturalLanguage": "The employee is eligible for parental leave."}],
                "untranslatedPremises": [], "untranslatedClaims": [],
            },
            "supportingRules": [{"identifier": "R1"}, {"identifier": "R2"}],
        },
    }], 1)


def answer_with_validation(agent: Agent, guardrail_id: str, version: str, question: str) -> None:
    answer = generate(agent, question)

    for iteration in range(1, MAX_REWRITE_ITERATIONS + 1):
        console.print()
        console.print(Panel(
            Markdown(answer),
            title=f"🤖 HR Assistant (attempt {iteration})",
            title_align="left", border_style="green", padding=(1, 2),
        ))

        if DEMO_MODE:
            findings, ar_units = _demo_findings(iteration)
        else:
            try:
                findings, ar_units = validate_response(guardrail_id, version, question, answer)
            except ClientError as e:
                console.print(f"[yellow]Validation failed: {e.response['Error']['Message']}[/yellow]")
                return

        render_findings(findings, ar_units)
        result = get_aggregate_result(findings)

        # Serve on VALID (or when AR can't speak to it); stop looping otherwise.
        if result in ("valid", "noTranslations", None) or ar_units == 0:
            return
        if iteration == MAX_REWRITE_ITERATIONS:
            console.print(Panel(
                "Reached the maximum number of rewrite attempts without a VALID result. "
                "Returning the best answer with this caveat.",
                title="⚠ Not Fully Verified", title_align="left", border_style="yellow",
            ))
            return

        console.print(Panel(
            f"Answer was [bold]{result}[/bold] — rewriting using the Automated Reasoning feedback…",
            title="↻ Rewriting", title_align="left", border_style="cyan",
        ))
        answer = generate(agent, build_rewrite_prompt(question, answer, findings))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def build_agent() -> Agent:
    # AR validation is done standalone via ApplyGuardrail (the recommended path),
    # so the guardrail is NOT attached to the generation model here.
    if REAL_LLM_PROFILE:
        # Hybrid: run the real model on your AWS account via the named profile.
        # No emulator endpoint, so the real cross-Region model id works as-is.
        session = boto3.Session(profile_name=REAL_LLM_PROFILE, region_name=REAL_LLM_REGION)
        model = BedrockModel(boto_session=session, model_id=MODEL_ID)
    elif _EMULATOR is not None:
        # All-emulator: the model call also goes to the emulator. BedrockModel's
        # internal client has no 'verify' arg, so TLS to the emulator CA is set
        # via AWS_CA_BUNDLE; the id is stripped of its inference-profile prefix.
        if _EMULATOR["ca_bundle"]:
            os.environ.setdefault("AWS_CA_BUNDLE", _EMULATOR["ca_bundle"])
        session = boto3.Session(
            aws_access_key_id=_EMULATOR["access_key"] or None,
            aws_secret_access_key=_EMULATOR["secret_key"] or None,
            region_name=_EMULATOR["region"],
        )
        model = BedrockModel(
            boto_session=session,
            endpoint_url=_EMULATOR["endpoint_url"],
            model_id=_strip_inference_prefix(MODEL_ID),
        )
    else:
        model = BedrockModel(region_name=REGION, model_id=MODEL_ID)

    # callback_handler=None suppresses Strands' default stdout streaming so the
    # answer is shown only inside the Rich panel (no duplicated output).
    return Agent(agent_id="hr-assistant", model=model, system_prompt=SYSTEM_PROMPT,
                 callback_handler=None)


def main():
    console.print(Panel(
        "[bold]Automated Reasoning checks[/bold] — ABCD Company parental leave policy\n"
        "[dim]Ask an eligibility question. The assistant answers, then Amazon Bedrock "
        "Automated Reasoning validates the answer against the formal policy and, if it "
        "isn't VALID, the answer is rewritten using the feedback.\n"
        "Example: [italic]Am I eligible for parental leave if I've worked full-time for 2 years?[/italic]\n"
        "Type [bold]exit[/bold] or [bold]quit[/bold] to leave.[/dim]",
        border_style="cyan", padding=(0, 2),
    ))

    setup_targets()

    if DEMO_MODE:
        console.print(Panel(
            "[bold]Demo mode[/bold] (AR_DEMO=1): the findings below are illustrative "
            "samples, NOT a real Automated Reasoning validation. No AR calls are made.\n"
            "Use this when your account lacks Automated Reasoning permissions.",
            title="🧪 Demo Mode", title_align="left", border_style="magenta", padding=(0, 2),
        ))
        gid, gver = "demo", "DRAFT"
    else:
        if _EMULATOR is not None and REAL_LLM_PROFILE:
            console.print(Panel(
                f"[bold]Hybrid mode[/bold]\n"
                f"• LLM (Converse): real AWS account via profile [bold]{REAL_LLM_PROFILE}[/bold] "
                f"(region {REAL_LLM_REGION}), model [bold]{MODEL_ID}[/bold]\n"
                f"• Guardrails + Automated Reasoning: emulator at [cyan]{_EMULATOR['endpoint_url']}[/cyan]",
                title="🧪 Emulator + Real LLM", title_align="left", border_style="yellow", padding=(0, 2),
            ))
        elif _EMULATOR is not None:
            console.print(Panel(
                f"Local AWS emulator detected — guardrails, Automated Reasoning AND the LLM "
                f"run on [cyan]{_EMULATOR['endpoint_url']}[/cyan] (model "
                f"[bold]{_strip_inference_prefix(MODEL_ID)}[/bold]).\n"
                "[yellow]Note:[/yellow] the emulator does not run a real LLM, so the assistant's "
                "text will be placeholder output. Set [bold]AR_REAL_LLM_PROFILE=default[/bold] to "
                "use your account's real model while keeping guardrails on the emulator.",
                title="🧪 Emulator Mode", title_align="left", border_style="yellow", padding=(0, 2),
            ))

        guardrail = ensure_ar_guardrail()
        if guardrail is None:
            console.print("[bold red]Could not provision a guardrail with an Automated Reasoning policy. Exiting.[/bold red]")
            return
        gid, gver = guardrail

    table = Table(title="Automated Reasoning Finding Types", title_style="bold cyan", border_style="cyan")
    table.add_column("Result", style="bold")
    table.add_column("Meaning")
    for ft, (_, _, blurb) in _RESULT_STYLE.items():
        table.add_row(ft, blurb)
    console.print(table)

    while True:
        try:
            console.print()
            question = read_user_input().strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]Goodbye![/dim]")
            break
        if not question:
            continue
        if question.lower() in ("exit", "quit"):
            console.print("[dim]Goodbye![/dim]")
            break

        agent = build_agent()  # fresh context per question
        answer_with_validation(agent, gid, gver, question)


if __name__ == "__main__":
    main()
