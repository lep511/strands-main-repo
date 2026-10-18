---
season: 3
season_name: "Season 3 — October 2026 (Autumn / Halloween Edition)"
day: 2
title: "Agent Security: Threat Modeling with SAIF"
summary: "Map your AI agent's architecture against Google's Secure AI Framework (SAIF) to identify prompt injection vectors, prevent rogue tool actions, and block sensitive data disclosure."
tags: ["Phase 1: SAIF", "Threat Modeling"]
canonical_url: "https://adventofagents.com/2026/10/02"
markdown_url: "https://adventofagents.com/2026/10/02.md"
video_url: "https://www.youtube.com/embed/TA7lhezND7M"
primary_video:
  title: "Day 2: Why is Securing Agents Different? — 5-Minute Google Cloud Kata"
  creator_name: "Google Cloud Engineering"
  duration: "13:11"
  video_url: "https://www.youtube.com/embed/TA7lhezND7M"
---

# 🛡️ Day 2: Agent Security: Threat Modeling with SAIF

> **Season 3 — October 2026 (Autumn / Halloween Edition)** · [Interactive Web View](https://adventofagents.com/2026/10/02?utm_source=adventofagents&utm_medium=markdown&utm_campaign=adventofagents_s3_2026&utm_content=day02) · [Raw Markdown](https://adventofagents.com/2026/10/02.md?utm_source=adventofagents&utm_medium=markdown&utm_campaign=adventofagents_s3_2026&utm_content=day02)

**Summary:** Map your AI agent's architecture against Google's Secure AI Framework (SAIF) to identify prompt injection vectors, prevent rogue tool actions, and block sensitive data disclosure.

**Day 2 of Google's Advent of Agents — Season 3**

Unlike a standalone language model that only generates text, an AI agent takes autonomous actions in the real world and ingests both **explicit user instructions** (synchronous commands or asynchronous event triggers) and **implicit environmental context** (emails, opened documents, application state, or retrieved data). Because the model's reasoning loop cannot reliably separate trusted user commands from untrusted external content, naive system-prompt rules fail as a security boundary. An attacker can hide instructions inside an email, support ticket, or calendar invite to hijack the agent's reasoning loop via **indirect prompt injection**, manipulate inter-agent communication, or plant dormant **"named triggers"** that stay inactive until a future user query activates them.

**How It Works**

Google's **Secure AI Framework (SAIF)** provides an end-to-end threat model and machine-readable control catalog ([google/saif-data](https://github.com/google/saif-data?utm_source=adventofagents&utm_medium=markdown&utm_campaign=adventofagents_s3_2026&utm_content=day02)) for securing agentic systems. In [SAIF: Focus on Agents](https://saif.google/focus-on-agents), the framework maps an agent across the **Application** and **Model** layers (`Input Handling` → `MODEL` → `Output Handling`) and decomposes the agent runtime into **four operational components**, pinpointing where **two primary agent risks** emerge and how to mitigate them with **three core agent controls** alongside foundational input/output validation and privacy protections:

![Google Secure AI Framework (SAIF) Focus on Agents Architecture, Risks, and Controls](/s03/s3-day02-saif-guardrails.png)

- **Perception & Reasoning Core**: **Perception (`Input Transformation`)** combines explicit user queries, implicit context, and control-token-isolated **System Instructions** into a structured prompt. The **Reasoning Core** then plans actions in an iterative loop, where untrusted external inputs can trigger indirect prompt injection or goal misalignment.
- **Orchestration & Response Rendering**: **Orchestration** coordinates **Tools (Autonomous Actions)**, **Content / RAG**, **Agent Memory**, and **Auxiliary Models** (like safety classifiers), which must be guarded against excessive tool permissions, data poisoning, and cross-session memory leaks. **Response Rendering (`Output Transformation`)** formats dynamic client output (like Markdown), where unsanitized links or images can cause XSS or silent data exfiltration.
- **Two Primary Agent Risks**: **Sensitive Data Disclosure** happens when an agent leaks private data via responses, rendered URLs, tool actions (like sharing a file or sending an email), or context hijacking (sharing data inappropriate for the active task). **Rogue Actions** happen when an agent executes unintended actions, either *accidentally* (from reasoning errors or ambiguity, like emailing the wrong "Mike") or *maliciously* (via prompt injection or dormant triggers).
- **Three Core SAIF Agent Controls**: Alongside input/output sanitization, SAIF enforces **Agent Permissions** (least privilege as an upper bound, adapted dynamically to the active task context via reference monitors), **Agent User Control** (explicit human-in-the-loop approval before altering user data or critical systems), and **Agent Observability** (audit logs across actions, tool calls, and reasoning).

👉 **Action Item**: Complete the interactive [SAIF Agent Risk Self-Assessment](https://saif.google/agent-risk-self-assessment) for a tailored security checklist, then run the snippets below to query the [google/saif-data](https://github.com/google/saif-data?utm_source=adventofagents&utm_medium=markdown&utm_campaign=adventofagents_s3_2026&utm_content=day02) YAML catalog and generate a live SAIF report for your project.

**Resources:**

- [Google Secure AI Framework (SAIF)](https://saif.google/)
- [SAIF Agent Risk Self Assessment](https://saif.google/agent-risk-self-assessment)
- [SAIF Risk Map & Data Repository](https://github.com/google/saif-data?utm_source=adventofagents&utm_medium=markdown&utm_campaign=adventofagents_s3_2026&utm_content=day02)
- [OWASP Top 10 for LLMs](https://owasp.org/projects/top-10-for-large-language-model-applications)

## Code & Commands

### 1. Run the Live SAIF Project Assessment

```bash
export CLOUDSDK_METRICS_ENVIRONMENT="advent-of-agents-s3-day02"

# 1. Download the SAIF Live Demo & Assessment Runner
curl -sO https://adventofagents.com/s03/launch_saif_demo.sh
chmod +x launch_saif_demo.sh

# 2. Inspect the script to review the automated checks & SAIF mapping
cat launch_saif_demo.sh

# 3. Authenticate with Google Cloud Application Default Credentials (ADC)
gcloud auth application-default login

# 4. Launch the interactive SAIF live assessment & HTML dashboard
# Automatically clones https://github.com/google/saif-data.git into ./saif-data
./launch_saif_demo.sh --project YOUR_PROJECT_ID --serve
```

### 2. Explore the Raw SAIF Risk Catalog

```bash
# Alternatively, clone and explore the raw SAIF risk catalog & schemas directly:
git clone https://github.com/google/saif-data.git
cd saif-data

# Inspect the 15 core AI security risks and threat taxonomy
cat yaml/risks.yaml

# Explore mitigation controls mapped to model creators and consumers
cat yaml/controls.yaml

# Review the SAIF security self-assessment questionnaire
cat yaml/self-assessment.yaml
```

## Resources & Links

- **[SAIF: Focus on Agents](https://saif.google/focus-on-agents)** — How Google's Secure AI Framework maps agent components, rogue actions, and sensitive data disclosure.
- **[SAIF Agent Risk Self-Assessment](https://saif.google/agent-risk-self-assessment)** — Interactive self-assessment questionnaire to evaluate your agent's security controls.
- **[SAIF Risk Map & Data Repository](https://github.com/google/saif-data?utm_source=adventofagents&utm_medium=markdown&utm_campaign=adventofagents_s3_2026&utm_content=day02)** — Official GitHub repository containing the SAIF YAML risk catalog, controls, and JSON schemas.
- **[OWASP Top 10 for LLM Applications](https://owasp.org/projects/top-10-for-large-language-model-applications)** — Industry-standard taxonomy of the top 10 security risks for LLM applications.
