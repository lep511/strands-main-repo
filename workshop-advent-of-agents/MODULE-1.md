---
season: 3
season_name: "Season 3 — October 2026 (Autumn / Halloween Edition)"
day: 1
title: "Foundation 101: Five Phases of Agent Development Lifecycle"
summary: "Map the five phases every production agent moves through, from Scope to Optimize, and walk a prototype agent around the loop in five minutes."
tags: ["Phase 1: Foundations", "ADLC", "Governance"]
canonical_url: "https://adventofagents.com/2026/10/01"
markdown_url: "https://adventofagents.com/2026/10/01.md"
video_url: "https://www.youtube.com/embed/ngNxiZhxJjI"
primary_video:
  title: "Day 1: What is ADLC (Agent Development Lifecycle)? — 5-Minute Google Cloud Kata"
  creator_name: "Afrina M"
  duration: "7:23"
  video_url: "https://www.youtube.com/embed/ngNxiZhxJjI"
---

# 🔄 Day 1: Foundation 101: Five Phases of Agent Development Lifecycle

> **Season 3 — October 2026 (Autumn / Halloween Edition)** · [Interactive Web View](https://adventofagents.com/2026/10/01?utm_source=adventofagents&utm_medium=markdown&utm_campaign=adventofagents_s3_2026&utm_content=day01) · [Raw Markdown](https://adventofagents.com/2026/10/01.md?utm_source=adventofagents&utm_medium=markdown&utm_campaign=adventofagents_s3_2026&utm_content=day01)

**Summary:** Map the five phases every production agent moves through, from Scope to Optimize, and walk a prototype agent around the loop in five minutes.

**Day 1 of Google's Advent of Agents — Season 3**

Before you lock an agent down, you need a map of where it lives. Agents choose their own actions at runtime: they call tools, touch data, and keep changing after you ship them. The **Agent Development Lifecycle (ADLC)** is that map, and every control in this season plugs into one of its five phases.

**How It Works**

The **Agent Development Lifecycle (ADLC)** organizes agent engineering into a continuous five-phase loop that applies across any agent framework or runtime (including ADK). Every security and governance control in Season 3 plugs directly into one of these five checkpoints:

![Five Phases of the Agent Development Lifecycle](/s03/s3-day01-adlc-loop.png)

- **Scope**: Write down what the agent may do, what it must never do, which data it touches, and who owns it. A `DESIGN_SPEC.md` is your first governance artifact.

- **Build**: Scaffold with Agents CLI and ADK, then iterate locally with `agents-cli run` until every tool call in the trace matches the spec.

- **Scale**: Deploy to Agent Runtime, Cloud Run, or GKE, with infrastructure defined as code instead of console clicks.

- **Govern**: Give the agent its own identity, register it in Agent Registry, route its traffic through Agent Gateway, and screen prompts with Model Armor.

- **Optimize**: Re-run evals on every change, trace tool calls with OpenTelemetry, and feed what you learn back into Scope.

**Why Not Just SDLC or MLOps?**

SDLC assumes deterministic code, so tests prove correctness. MLOps adds data and model drift, but a model only returns predictions. An agent decides which tools to call, so ADLC adds two things on top: evaluating behavior (the tool trajectory, not just the answer) and governing what the agent is allowed to reach.

**Resources:**

- [Automate your agent development lifecycle](https://cloud.google.com/blog/topics/developers-practitioners/automate-agent-development-lifecycles-with-gemini-enterprise?utm_source=adventofagents&utm_medium=markdown&utm_campaign=adventofagents_s3_2026&utm_content=day01)
- [Agents CLI in Agent Platform](https://developers.googleblog.com/agents-cli-in-agent-platform-create-to-production-in-one-cli/?utm_source=adventofagents&utm_medium=markdown&utm_campaign=adventofagents_s3_2026&utm_content=day01)

## Code & Commands

### Walk One Agent Around the ADLC Loop

```bash
export CLOUDSDK_METRICS_ENVIRONMENT="advent-of-agents-s3-day01"

# Day 1: walk one agent around the ADLC loop in about five minutes.
# Prereqs: Python 3.11+, uv, Node.js, gcloud, and a Google Cloud project with billing.
gcloud auth application-default login
gcloud services enable aiplatform.googleapis.com
export GOOGLE_CLOUD_PROJECT=YOUR_PROJECT_ID
export GOOGLE_CLOUD_LOCATION=us-central1

# 1. SCOPE: decide what the agent may and may not do before any code exists.
cat > DESIGN_SPEC.md <<'EOF'
# adlc-day1
Owner: you@example.com
May: answer weather and time questions with get_weather and get_current_time
May not: call any other tool, store user data, or act on external systems
Success: picks the right tool for each question (see tests/eval)
EOF

# 2. BUILD: install Agents CLI, scaffold a prototype agent, move the spec in, run it.
uvx google-agents-cli setup
agents-cli scaffold create adlc-day1 --prototype --yes
mv DESIGN_SPEC.md adlc-day1/ && cd adlc-day1
agents-cli install
agents-cli run "What's the weather in San Francisco?"
# Find the [tool_call: get_weather(...)] line. That trace is your first audit trail.

# 3. OPTIMIZE: score the agent's behavior against the scaffolded eval set (LLM judge, billable).
agents-cli eval run

# 4. SCALE + GOVERN: preview of Day 5 (deploy takes about 5-10 minutes).
# agents-cli scaffold enhance . --deployment-target agent_runtime --prototype --yes
# agents-cli deploy --agent-identity --project $GOOGLE_CLOUD_PROJECT --region us-central1
```

## Resources & Links

- **[Automate your agent development lifecycle](https://cloud.google.com/blog/topics/developers-practitioners/automate-agent-development-lifecycles-with-gemini-enterprise?utm_source=adventofagents&utm_medium=markdown&utm_campaign=adventofagents_s3_2026&utm_content=day01)** — Set up, build, deploy, govern, evaluate, and publish an agent with Agents CLI skills.
- **[Agents CLI in Agent Platform](https://developers.googleblog.com/agents-cli-in-agent-platform-create-to-production-in-one-cli/?utm_source=adventofagents&utm_medium=markdown&utm_campaign=adventofagents_s3_2026&utm_content=day01)** — Why Agents CLI is the programmatic backbone for the ADLC on Google Cloud.
- **[Gemini Enterprise Agent Platform docs](https://g.dev/cloud/adventofagents-season3-gemini-enterprise-govern)** — Build, scale, govern, and optimize: the platform behind each ADLC phase.
- **[Introduction to Agents whitepaper](https://www.kaggle.com/whitepaper-introduction-to-agents)** — Google's foundational whitepaper on how agents work.