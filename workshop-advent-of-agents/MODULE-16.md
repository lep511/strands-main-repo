---
season: 3
season_name: "Season 3 — October 2026 (Autumn / Halloween Edition)"
day: 16
title: "Agent Payments: Secure Shopping with Gemini platform"
summary: "Let an agent shop across UCP merchants while AP2 mandates and Agent Gateway policies ensure money moves only after you approve the exact cart."
tags: ["Phase 3: Agent Payments", "AP2", "UCP", "Human-in-the-Loop"]
canonical_url: "https://adventofagents.com/2026/10/16"
markdown_url: "https://adventofagents.com/2026/10/16.md"
video_url: "https://www.youtube.com/embed/3Q1L4z5-6ug"
primary_video:
  title: "Day 16: Secure Agent Payments with Gemini platform"
  creator_name: "Sita Lakshmi Sangameswaran"
  duration: "9:25"
  video_url: "https://www.youtube.com/embed/3Q1L4z5-6ug"
---

# 💳 Day 16: Agent Payments: Secure Shopping with Gemini platform

> **Season 3 — October 2026 (Autumn / Halloween Edition)** · [Interactive Web View](https://adventofagents.com/2026/10/16?utm_source=adventofagents&utm_medium=markdown&utm_campaign=adventofagents_s3_2026&utm_content=day16) · [Raw Markdown](https://adventofagents.com/2026/10/16.md?utm_source=adventofagents&utm_medium=markdown&utm_campaign=adventofagents_s3_2026&utm_content=day16)

**Summary:** Let an agent shop across UCP merchants while AP2 mandates and Agent Gateway policies ensure money moves only after you approve the exact cart.

**Day 16 of Google's Advent of Agents — Season 3**

So far in Season 3, our agents have read enterprise data, called internal tools, and acted under scoped identities (Day 5) and user delegation (Day 6). Today we tackle **agentic commerce**: what happens when you ask an AI agent to buy something for you with real money across external merchants?

Letting an agent browse catalogs, compare options, and assemble a shopping cart is safe because browsing costs nothing. The risk begins at checkout. If the LLM can connect to any store on the web or trigger a payment tool directly, a hallucinated tool call or a prompt injection hidden inside a product listing can spend your money at an unapproved merchant or charge you for items you never asked for. System prompt instructions like "always ask the user before paying" and "never spend over $100" cannot prevent this, because prompts can be bypassed and a model must never hold the authority to authorize a payment on its own.

**Separating Shopping from Paying**

To make agent payments safe, you separate **shopping** (which the model can do within platform guardrails) from **paying** (which requires cryptographic proof of human approval). In today's kata, we build and red-team **`CineAgent`**, a movie-ticket booking agent on the Gemini platform that combines two open commerce protocols with Google Cloud's network and policy controls:

- **Universal Commerce Protocol (UCP)**: An open standard for agentic shopping. Merchants publish a `/.well-known/ucp` profile with their public signing key and expose catalog and checkout tools over MCP. When the agent builds a cart, the merchant signs the cart total so the price cannot be altered in transit.
- **Agent Payments Protocol (AP2)**: An open standard for cryptographic payment consent. Instead of trusting the LLM when it claims the user said yes, a non-agentic UI outside the model collects your approval, and deterministic platform code signs single-use **Checkout and Payment Mandates** bound to that exact merchant-signed cart.
- **Agent Gateway & Semantic Governance**: Platform guardrails from Days 8 and 12 that sit around **Agent Runtime**. They restrict which merchants the agent is allowed to contact and block oversized purchases before the approval card is even shown to you.

**End-to-End Architecture & Request Flow**

![Secure Agent Commerce Architecture: UCP, AP2, and Agent Gateway](/s03/s3-day16-agent-payments.png)

Follow the numbered arrows (**1** to **6**) in the architecture diagram above to trace what happens when you ask `CineAgent` to book tickets:

1. **User Request (1)**: From your browser or terminal, you ask `CineAgent` (running on **Agent Runtime** with a SPIFFE **Agent Identity**) to *"Book 2 tickets at Meridian"*.
2. **Gated Checkout Call (2)**: `CineAgent` calls the `create_checkout` MCP tool through the **Egress Agent Gateway + IAP**. Because outbound traffic is deny-by-default, the gateway allows calls to **Meridian Cinemas** (which has an IAM `roles/iap.egressor` grant) and blocks unapproved merchants like **StarLight Theaters** with `403 Forbidden`.
3. **Merchant-Signed Cart (3)**: **Meridian Cinemas** creates the $32.40 checkout, locks the line items and total with an `ap2.merchant_authorization` cryptographic signature, and returns the signed cart to `CineAgent`.
4. **Semantic Spend Cap & Non-Agentic Approval Card (4a & 4)**: When `CineAgent` proposes `complete_purchase($32.40)` (**4a**), the **Semantic Governance Policy** evaluates the tool call first and denies any purchase over $100 (such as a $118.80 five-ticket IMAX order) before prompting you. Because $32.40 is within the cap, ADK pauses execution (`require_confirmation=True`) and renders a deterministic **ADK Approval Card** in your UI (**4**) where you click **Approve** or **Decline**.
5. **Deterministic AP2 Mandate Signing (5)**: Clicking **Approve** (**5**) invokes deterministic code in `trusted_platform.py`. It verifies the merchant's cart signature, confirms that your approved $32.40 matches the merchant-signed total, and uses the signing key in **Secret Manager** (which the LLM never sees) to sign two single-use SD-JWTs: an AP2 **Checkout Mandate** and **Payment Mandate**.
6. **Merchant Verification & Signed Receipt (6)**: `Trusted Platform` sends `complete_checkout` and both mandates through the **Egress Agent Gateway** to **Meridian Cinemas** (**6**). Meridian fetches your platform's public key from the **Platform UCP Profile** on Cloud Storage (`/.well-known/ucp`), verifies that both mandates are unexpired, single-use, and bound to the SHA-256 hash of the $32.40 cart it signed in step 3, and returns your tickets with a signed AP2 receipt.

👉 To try this yourself, clone the [Day 16 Demo Repository](https://g.dev/cloud/adventofagents-season3-day16-demo) or check the **Code** tab above to run the UCP merchants, AP2 attack suite, and Agent Gateway deployment.

**Resources:**

- [AP2 Specification](https://g.dev/cloud/adventofagents-season3-docs-ap2-specification)
- [UCP AP2 Mandates Extension](https://g.dev/cloud/adventofagents-season3-docs-ucp-ap2-mandates)
- [ADK Tool Confirmation](https://g.dev/cloud/adventofagents-season3-docs-adk-tool-confirmation)
- [Day 16 Demo Repository](https://g.dev/cloud/adventofagents-season3-day16-demo)

## Code & Commands

### 1. Start Here: Run the Demo & Red-Team Suite (setup.sh)

```bash
export CLOUDSDK_METRICS_ENVIRONMENT="advent-of-agents-s3-day16"

# START HERE: run these commands to start two UCP theater merchants and the
# CineAgent booking agent locally. Snippets 2, 3, and 4 are reference excerpts
# that are already included in the repository.
#
# Prerequisites: uv, git, and gcloud with Application Default Credentials for a
# Google Cloud project with the Vertex AI API enabled.
gcloud auth application-default login

git clone https://github.com/Sita04/secure-agent-commerce-gemini-enterprise.git
cd secure-agent-commerce-gemini-enterprise

# 1. Start two UCP merchants (:8081, :8082) and ADK web UI (:8080):
./setup.sh local YOUR_PROJECT_ID

# 2. Open http://127.0.0.1:8080, select "cineagent", and ask:
#    "Book 2 standard tickets for Oppenheimer at 9:30 PM at Meridian"
#    ADK pauses complete_purchase(total_cents=3240) at a confirmation card.
#    Approve to mint AP2 mandates and get a signed receipt, or decline to pay $0.

# 3. In a second terminal, run the attack suite against the merchants:
./setup.sh test
# PASS  Honest purchase                  -> completed
# PASS  Replay used mandates             -> checkout_already_completed
# PASS  Pay $1 for a $47.52 cart         -> mandate_scope_mismatch
# PASS  Reuse approval on another cart   -> mandate_scope_mismatch
# PASS  Untrusted platform profile       -> agent_missing_key
# PASS  Forged key, trusted profile URL  -> mandate_invalid_signature
# PASS  Expired mandate                  -> mandate_expired
# PASS  No mandate (skipped approval)    -> mandate_required
# PASS  Approved amount != signed total  -> approved amount does not match

# 4. Optional (~25 min): deploy behind Agent Gateway and a semantic governance policy,
#    then chat with the deployed agent and approve payments in your terminal:
gcloud auth login
./setup.sh deploy YOUR_PROJECT_ID
./setup.sh chat YOUR_PROJECT_ID
```

### 2. Reference: Step 2 Human Approval & Signing (cineagent/agent.py)

```python
# REFERENCE ONLY: simplified excerpt of cineagent/agent.py from the Day 16 demo repo.
# You do not need to copy it; the repo cloned in Snippet 1 already contains it.

async def complete_purchase(checkout_id: str, merchant_url: str, total_cents: int) -> str:
    """Pay total_cents for a checkout with AP2 mandates. The user must approve first."""
    # Step 1 check: Fetch checkout and verify the merchant's ap2.merchant_authorization JWT
    checkout = await platform.call(merchant_url, "get_checkout", {"id": checkout_id})
    checkout_jwt = await platform.verified_checkout_jwt(merchant_url, checkout)
    if not checkout_jwt:
        return json.dumps({"error": "merchant_authorization_invalid"})

    # Step 2A: Sign only if the human-approved amount matches the merchant-signed total
    if platform.total(checkout) != total_cents:
        return json.dumps({"error": "approved amount does not match the merchant-signed total"})

    # Step 2B: Deterministic platform code signs both AP2 mandates; the LLM never sees the key
    checkout_mandate, payment_mandate = platform.sign_mandates(
        checkout, checkout_jwt, merchant_url
    )
    result = await platform.call(
        merchant_url,
        "complete_checkout",
        await platform.completion_request(
            checkout_id, merchant_url, checkout_mandate, payment_mandate
        ),
    )
    return json.dumps(result)

root_agent = Agent(
    name="cineagent",
    model=Gemini(model="gemini-3.8-flash"),
    instruction="Search UCP theaters, call create_checkout, then call complete_purchase with total_cents.",
    tools=[
        discover_theaters,
        search_movies,
        create_checkout,
        # ADK pauses execution at a trusted confirmation UI until the user approves.
        FunctionTool(complete_purchase, require_confirmation=True),
    ],
)
```

### 3. Reference: Step 3 Merchant Verification (merchant/main.py)

```python
# REFERENCE ONLY: simplified excerpt of merchant/main.py from the Day 16 demo repo.
# You do not need to copy it; the repo cloned in Snippet 1 already contains it.

@mcp.tool()
def complete_checkout(meta: dict, id: str, checkout: dict) -> dict[str, Any]:
    """Complete a checkout. Requires AP2 mandates signed by a trusted platform."""
    session = sessions[id]
    if session["status"] == "completed":
        return error("checkout_already_completed", "Mandates are single use")

    ap2_data = checkout.get("ap2", {})
    checkout_mandate = ap2_data.get("checkout_mandate")
    # UCP places the Payment Mandate in the payment instrument's credential token
    payment_mandate = checkout["payment"]["instruments"][0]["credential"]["token"]
    if not checkout_mandate or not payment_mandate:
        return error("mandate_required", "No proof that the user approved this checkout")

    # Step 3A: Load public keys from the allowlisted platform's UCP profile, never from the payload
    keys = platform_keys(meta)
    if not keys:
        return error("agent_missing_key", "Unknown platform")
    cm = MandateClient().verify(checkout_mandate, JWK(**keys[0]), payload_type=CheckoutMandate).mandate_payload
    pm = MandateClient().verify(payment_mandate, JWK(**keys[0]), payload_type=PaymentMandate).mandate_payload

    # Step 3B: Both mandates must match the SHA-256 hash and amount of the merchant-signed checkout
    checkout_hash = compute_sha256_b64url(signed_checkouts[id])
    if (cm.checkout_hash != checkout_hash or pm.transaction_id != checkout_hash
            or pm.payment_amount.amount != total(session)):
        return error("mandate_scope_mismatch", "Bound to a different checkout or amount")

    return complete_order_with_signed_receipt(session)
```

### 4. Reference: Step 4 Agent Gateway & Spend Policy (setup.sh deploy)

```bash
export CLOUDSDK_METRICS_ENVIRONMENT="advent-of-agents-s3-day16"

# REFERENCE ONLY: excerpt of ./setup.sh deploy. The agent runs on Agent Runtime with
# Agent Identity and sends all outbound traffic through an egress Agent Gateway.

# Egress is deny-by-default: grant the agent access to the approved merchant only.
gcloud beta iap web add-iam-policy-binding --resource-type=agent-registry \
  --mcp-server=$MERIDIAN_REGISTRY_ID --region=$REGION \
  --member="$AGENTS" --role=roles/iap.egressor
# StarLight gets no grant, so the gateway answers the agent with:
#   403 Forbidden: Egress request is not authorized.

# Semantic governance checks every tool call the model proposes, before it runs:
gcloud beta ai semantic-governance-policies create ticket-spend-cap \
  --location=$REGION --agent="$REGISTRY_AGENT" \
  --display-name="Ticket spend cap" \
  --natural-language-constraint='Deny any call to the complete_purchase tool where total_cents is greater than 10000.'

# "Buy 5 IMAX tickets" ($118.80) is stopped before the approval card appears:
gcloud logging read 'logName="projects/'"$PROJECT_ID"'/logs/semantic-governance-policy"' \
  --freshness=10m --format='value(jsonPayload.evaluations)'
# complete_purchase  DENY  "The total_cents for the purchase is 11880 ($118.80), which exceeds..."
```

## Resources & Links

- **[AP2 Specification](https://g.dev/cloud/adventofagents-season3-docs-ap2-specification)** — Protocol roles, Checkout and Payment Mandates, and why the Trusted Surface must never be an LLM.
- **[UCP AP2 Mandates Extension](https://g.dev/cloud/adventofagents-season3-docs-ucp-ap2-mandates)** — How UCP checkouts carry merchant signatures, AP2 mandates, and standard verification error codes.
- **[ADK Tool Confirmation](https://g.dev/cloud/adventofagents-season3-docs-adk-tool-confirmation)** — Pause high-impact tool calls until a human approves the exact arguments with require_confirmation.
- **[Day 16 Demo Repository](https://g.dev/cloud/adventofagents-season3-day16-demo)** — Run the UCP merchants, AP2 mandates, attack suite, and Agent Gateway deployment with one setup.sh script.
