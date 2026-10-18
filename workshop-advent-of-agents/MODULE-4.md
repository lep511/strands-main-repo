---
season: 3
season_name: "Season 3 — October 2026 (Autumn / Halloween Edition)"
day: 4
title: "Governance Maturity Model: Progressive Trust for Agents"
summary: "Score your agent estate across five governance layers, from Foundation to Continuous Alignment, and turn the result into a staged 90-day roadmap."
tags: ["Phase 1: Governance Framework", "Maturity Model", "Roadmap"]
canonical_url: "https://adventofagents.com/2026/10/04"
markdown_url: "https://adventofagents.com/2026/10/04.md"
video_url: "https://www.youtube.com/embed/nNjqaKVR3tc"
primary_video:
  title: "Day 4: The 5-Layer Agent Governance Maturity Framework — 5-Minute Google Cloud Kata"
  creator_name: "Afrina M"
  duration: "7:16"
  video_url: "https://www.youtube.com/embed/nNjqaKVR3tc"
---

# 🪜 Day 4: Governance Maturity Model: Progressive Trust for Agents

> **Season 3 — October 2026 (Autumn / Halloween Edition)** · [Interactive Web View](https://adventofagents.com/2026/10/04?utm_source=adventofagents&utm_medium=markdown&utm_campaign=adventofagents_s3_2026&utm_content=day04) · [Raw Markdown](https://adventofagents.com/2026/10/04.md?utm_source=adventofagents&utm_medium=markdown&utm_campaign=adventofagents_s3_2026&utm_content=day04)

**Summary:** Score your agent estate across five governance layers, from Foundation to Continuous Alignment, and turn the result into a staged 90-day roadmap.

**Day 4 of Google's Advent of Agents — Season 3**

Most enterprises can't say how many agents they run, who owns each one, what those agents can reach, or what happens when one misbehaves. Before adding another control, score where you are: a **maturity model** turns "are we governed?" into five questions you can answer, and the answers into a staged roadmap.

**How It Works**

Five layers make the governance loop (reason, enforce, prove, respond, learn) measurable. Each layer answers one question and builds on the one below it:

- **Foundation**: Is every agent cataloged, owned, and identifiable? Every production agent is in Agent Registry with a named owner and its own SPIFFE identity, deployed from IaC templates.
- **Prevention**: Can you block policy violations inline? Every tool call goes through Agent Gateway, Model Armor fails closed, and sandboxes deny egress by default.
- **Detection**: Can you spot anomalies, permission changes, and new agents, with an immutable audit trail? OpenTelemetry traces and audit logs land in a sink you can query.
- **Response**: Can you prove containment worked? Tested playbooks revoke one agent's credentials in under a minute.
- **Continuous Alignment**: Do escapes become better policy? Postmortems become policy updates, tested by regression evals before release.

![Five-Layer Agent Governance Maturity Model](/s03/s3-day04-governance-maturity.png)

**From Score to Roadmap**

The `README.md` checklist covers 15 assessment points, three per layer, to build your plan:

1. **Score**: Rate each area Level 1 (Basic), 3 (Advanced), or 5 (Optimized) for the estate as it runs today. A layer scores its weakest area.
2. **Start low**: Begin at the lowest layer below Level 3. The order is structural: the gateway enforces against identities that must already exist, and detection needs governed traffic to watch.
3. **Phase it**: Foundation in days 1–30, Prevention and Detection in days 31–60, Response and Continuous Alignment in days 61–90.

**Resources:**

- [Govern your agents](https://g.dev/cloud/adventofagents-season3-gemini-enterprise-govern)
- [SAIF: Google's Guide to Secure AI](https://g.dev/cloud/adventofagents-season3-google-saif)

## Code & Commands

### 15-Point Readiness Checklist & 90-Day Roadmap

```markdown
# Agent Governance Readiness Checklist & 90-Day Roadmap

Score your agent estate as it runs today (1 = manual/ad hoc, 3 = standardized in production, 5 = automated everywhere).
**Scoring rule:** Each layer scores its **weakest** area. Start at the lowest layer scoring below Level 3.

## 1. Foundation (Days 1-30 | Season 3 Days: 5, 17, 18)
- [ ] **Identity** (Level 3): Each agent has its own cryptographic identity (SPIFFE).
- [ ] **Inventory** (Level 3): Core agents and tools are cataloged in a central registry.
- [ ] **Infrastructure** (Level 3): Agents deploy from Terraform or other IaC templates.
- **Done when:** Every agent is registered, owned, and given its own identity.

## 2. Prevention (Days 31-60 | Season 3 Days: 6, 8-13, 16, 20)
- [ ] **Prompt shielding** (Level 3): Model Armor screens prompts inline at the gateway.
- [ ] **Data leaks** (Level 3): Managed PII masking and domain allowlists run on output.
- [ ] **Circuit breakers** (Level 3): Iteration ceilings and rate limits are enforced at the gateway.
- **Done when:** Every tool call routes via a gateway and Model Armor fails closed.

## 3. Detection (Days 31-60 | Season 3 Days: 22, 23, 24)
- [ ] **Tracing** (Level 3): OpenTelemetry spans land in Cloud Trace for model and tool calls.
- [ ] **Anomalies** (Level 3): Alerts fire on token-volume and trajectory anomalies.
- [ ] **Audit** (Level 3): Immutable audit logs export to BigQuery.
- **Done when:** OpenTelemetry traces land in a queryable sink and Security Command Center drift alerts are active.

## 4. Response (Days 61-90 | Season 3 Day: 26)
- [ ] **Containment** (Level 3): A single agent's credentials can be revoked in the console.
- [ ] **Threat alerts** (Level 3): Security Command Center alerts on anomalous API calls.
- [ ] **Playbooks** (Level 3): Standard incident and postmortem templates are tested.
- **Done when:** Tested playbooks can revoke an agent in under a minute.

## 5. Continuous Alignment (Days 61-90 | Season 3 Days: 30, 31)
- [ ] **Drift** (Level 3): Automated evaluations run daily in QA.
- [ ] **Red teaming** (Level 3): Scheduled automated prompt-injection scans run continuously.
- [ ] **Policy updates** (Level 3): Engineering leads hold scheduled policy reviews.
- **Done when:** Postmortems update policy, gated by regression evals before release.
```

## Resources & Links

- **[Agent Registry overview](https://g.dev/cloud/adventofagents-season3-agent-registry)** — Layer 1: catalog every agent, tool, and MCP server in one place.
- **[Agent Gateway overview](https://g.dev/cloud/adventofagents-season3-agent-gateway)** — Layer 2: the enforcement point for agent traffic, with Model Armor attached.
- **[Agent Platform Observability](https://g.dev/cloud/adventofagents-season3-gemini-enterprise-observability)** — Layer 3: OpenTelemetry traces and dashboards for your agents.
- **[Agent Evaluation](https://g.dev/cloud/adventofagents-season3-gemini-enterprise-agent-evaluation)** — Layer 5: measure agent quality and catch regressions before release.
