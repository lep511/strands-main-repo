# Agent Governance Readiness — assessment & 90-day roadmap

Assessed by the `governance-assessor` agent (us.anthropic.claude-sonnet-4-6) from deterministic evidence; layer scores and roadmap are computed by `maturity.py`.

> The estate of three registered agents (adlc-day1, inbox-assistant, governance-assessor) is at an early, largely ad-hoc governance posture: 13 of 15 areas score Level 1, with only Playbooks reaching Level 3 on the strength of a single successful containment drill and the existence of PLAYBOOK.md. The most critical gaps are the complete absence of per-agent workload identities (all agents run on shared developer credentials), four unregistered agent files that are entirely outside governance, no IaC-based deployments, no centrally enforced Bedrock Guardrails, and no immutable audit trail — all of which expose the high-risk inbox-assistant agent to uncontrolled data-leak and prompt-injection risk. Closing the Identity and Infrastructure areas first will unblock several downstream controls (containment, threat alerts, circuit breakers) and provide the strongest near-term risk reduction.

## Layer scores (each layer = its weakest area)

| Layer | Score | Question |
|---|---|---|
| Foundation | **1** ← **start here** | Is every agent cataloged, owned, and identifiable? |
| Prevention | **1** | Can you block policy violations inline? |
| Detection | **1** | Can you spot anomalies, permission changes, and new agents, with an immutable audit trail? |
| Response | **1** | Can you prove containment worked? |
| Continuous Alignment | **1** | Do escapes become better policy? |

## Area scores

| Layer | Area | Level | Evidence | Gap |
|---|---|---|---|---|
| Foundation | Identity | 1 | Registry shows identity=None for all three registered agents (adlc-day1, inbox-assistant, governance-assessor). Evidence confirms all agents authenticate to Bedrock via the default boto3 credential chain (shared developer credentials). Workload identity code exists only in src/module-4/eval_assessor.py:30 but is not wired into any running agent. | No agent has its own IAM role or AgentCore Identity workload identity. All agents share developer credentials. No automatic issuance or rotation exists. |
| Foundation | Inventory | 1 | agent_registry.yaml lists 3 agents, all with owners. However, 4 unregistered agent-defining files exist: src/module-3/case_manager.py, src/module-3/data_vault.py, src/module-3/logistics.py, src/module-5/agent/main.py. RegistryGate enforcement is wired only into governance-assessor (src/module-4/governance_agent.py:6, governance_controls.py:4), not into adlc-day1 or inbox-assistant. Unregistered-agent discovery runs on demand only (estate_registry.py discover), not on a schedule. | 4 unregistered agent files exist. RegistryGate is not enforced at deploy time for adlc-day1 or inbox-assistant. Discovery is not automated. |
| Foundation | Infrastructure | 1 | No IaC templates (CDK, CloudFormation, Terraform) and no CI pipelines were found for any agent. Only adlc-day1 has a local AgentCore-compatible server file (src/module-1/agentcore_app.py:3); inbox-assistant and governance-assessor have none. No drift detection is in place. | No agent deploys from IaC; no CI pipeline exists for any agent. Deployments are manual/console-based. |
| Prevention | Prompt shielding | 1 | Bedrock Guardrails (prompt-attack filter) is absent for all three agents (adlc-day1: NONE, inbox-assistant: NONE, governance-assessor: NONE). Untrusted-content isolation exists only for inbox-assistant (src/module-2/inbox_agent.py:27, saif_controls.py:8, saif_report.py:41) but not for adlc-day1 or governance-assessor. Level 3 requires every agent to be covered. | Bedrock Guardrails prompt-attack filter is not applied to any agent. Untrusted-content isolation covers only 1 of 3 agents. |
| Prevention | Data leaks | 1 | Output sanitizer/domain allowlist exists only for inbox-assistant (src/module-2/inbox_agent.py:28, saif_controls.py:12, attack_eval.py:21). PII masking is absent for all three agents. Tool-argument allowlists exist for adlc-day1 (src/module-1/spec_guard.py:5) and inbox-assistant (src/module-2/attack_eval.py:19, fake_mailbox.py:20, saif_controls.py:24) but not governance-assessor. No centrally managed configuration or regression tests are in place. | PII masking is absent for all agents. Output controls are missing for adlc-day1 and governance-assessor. Coverage is not central or managed. |
| Prevention | Circuit breakers | 1 | Invocation limits (turns/tokens) are configured only for governance-assessor (src/module-4/governance_agent.py:6, governance_controls.py:3, containment_drill.py:24, eval_assessor.py:42). adlc-day1 and inbox-assistant have no turn or token ceilings. Tool-call budgets are absent for all agents. No AgentCore Gateway is deployed for rate limiting. | adlc-day1 and inbox-assistant have no iteration or token ceilings. No gateway-level rate limiting exists for any agent. |
| Detection | Tracing | 1 | Strands telemetry is set up only in adlc-day1 (src/module-1/adlc_agent.py:72); inbox-assistant and governance-assessor have no telemetry setup. OTLP export to a backend is absent for all agents. ADOT/CloudWatch reference exists only in governance-assessor's eval file (src/module-4/eval_assessor.py:40) but is not wired into the running agent. | No agent exports OTel spans to a queryable backend (CloudWatch/X-Ray). Telemetry setup is partial (1 of 3 agents) and not connected to an OTLP sink. |
| Detection | Anomalies | 1 | No CloudWatch alarms or anomaly-detection rules exist for any agent (adlc-day1: NONE, inbox-assistant: NONE, governance-assessor: NONE). Token usage is captured per call in adlc-day1 (src/module-1/adlc_agent.py:79) and governance-assessor (src/module-4/governance_agent.py:137, containment_drill.py:65) but no alarms are wired to those metrics. | No alerts exist for token-volume or trajectory anomalies on any agent. Token data is captured locally but never sent to an alerting system. |
| Detection | Audit | 1 | Audit logging exists for adlc-day1 (src/module-1/agentcore_app.py:27, spec_guard.py:32) and inbox-assistant (src/module-2/inbox_agent.py:24, saif_controls.py:11, saif_report.py:46), but not for governance-assessor. All audit sinks are local mutable files (audit.jsonl) on each machine. An immutable store reference appears in src/module-4/eval_assessor.py:45 but is not wired into any agent. | Audit logs are written to mutable local files, not an immutable store. governance-assessor has no audit logging. No Athena/CloudTrail Lake queryable backend is in use. |
| Response | Containment | 1 | Single-agent revocation via RegistryGate/ContainmentWatch is implemented only for governance-assessor (src/module-4/containment_drill.py:24, governance_agent.py:6, governance_controls.py:4). A drill was run and passed (time_to_contain=3.98s, new invocations refused). However, adlc-day1 and inbox-assistant have no revocation capability, and no per-agent IAM roles exist to revoke for any agent, meaning true credential revocation is not possible. | Revocation is only functional for governance-assessor. adlc-day1 and inbox-assistant cannot be individually revoked. No per-agent IAM roles exist to revoke credentials. |
| Response | Threat alerts | 1 | GuardDuty and Security Hub are absent for all three agents (adlc-day1: NONE, inbox-assistant: NONE, governance-assessor: NONE). No alerting on anomalous API calls by agent identities is configured. | No GuardDuty findings or Security Hub alerts are set up for any agent identity. This is also blocked by the lack of per-agent IAM roles (Identity area). |
| Response | Playbooks | 3 | A playbook document exists at src/module-4/PLAYBOOK.md. A containment drill for governance-assessor ran successfully (time_to_contain=3.98s, passed=True, new invocations refused, 0.0 days ago). These satisfy 'a standard playbook exists and has been tested in a drill.' However, scheduled drills are listed as NONE, so Level 5 is not reached. | Drills are not scheduled; only a single ad-hoc drill for governance-assessor has been run. Level 5 requires scheduled drills with tracked results. |
| Continuous Alignment | Drift | 1 | Eval suites exist for adlc-day1 (src/module-1/eval_agent.py:14), inbox-assistant (src/module-2/attack_eval.py:15), and governance-assessor (src/module-4/eval_assessor.py:18). However, no CI scheduled runs are configured (scheduled CI runs: NONE). Evals are run manually only. | No scheduled or CI-triggered eval runs exist for any agent. Evals must run daily or on every change to reach Level 3. |
| Continuous Alignment | Red teaming | 1 | Adversarial/injection suites exist for inbox-assistant (src/module-2/attack_eval.py:1, fake_mailbox.py:1, inbox_agent.py:53, saif_controls.py:35, saif_report.py:35). adlc-day1 and governance-assessor have no adversarial suites. No scheduled CI runs are configured for any agent (scheduled CI runs: NONE). | Red-team coverage exists for only 1 of 3 agents and no scheduled runs exist. All three agents must be covered and scans must run on a schedule for Level 3. |
| Continuous Alignment | Policy updates | 1 | Versioned policy artifacts exist (src/module-1/DESIGN_SPEC.md, src/module-2/saif_controls.py, src/module-4/agent_registry.yaml, src/module-4/checklist.yaml) but all show 0 commits — they have never been updated. No postmortems exist. No scheduled policy reviews are documented. | Policy files exist but have never been committed or revised. No postmortems have been written and no review cadence is scheduled. |

## 90-day roadmap

Start with **Foundation**: the gateway enforces against identities that must already exist, and detection needs governed traffic to watch.

### Days 1-30

**Foundation** — done when: Every agent is registered, owned, and given its own identity.

- [ ] **identity** (L1 → L3): Create a dedicated IAM role per agent and assign each an AgentCore Identity workload identity in the registry (set identity field). Start with inbox-assistant (high risk tier) first.
- [ ] **inventory** (L1 → L3): Register src/module-3 and src/module-5 agents in agent_registry.yaml with owners, then add a deploy-time RegistryGate check (e.g., a CDK Aspect or CI step) that blocks deployment of any agent file not present in the AWS Agent Registry.
- [ ] **infrastructure** (L1 → L3): Create a CDK or CloudFormation stack for each agent (starting with inbox-assistant given its high risk tier) targeting AgentCore Runtime, and wire it into a CodePipeline or GitHub Actions workflow so every change ships through the pipeline.

### Days 31-60

**Prevention** — done when: Every tool call routes via a gateway and prompt screening fails closed.

- [ ] **prompt_shielding** (L1 → L3): Create a Bedrock Guardrails configuration with the prompt-attack filter enabled and apply the guardrailId to every agent's Bedrock InvokeModel/Converse call — beginning with inbox-assistant (high risk) and then adlc-day1 and governance-assessor.
- [ ] **data_leaks** (L1 → L3): Enable Bedrock Guardrails sensitive-information filters (PII masking) and add domain allowlists on output for all three agents via a single centrally managed guardrail configuration; add regression tests that verify the filter fires on known PII strings.
- [ ] **circuit_breakers** (L1 → L3): Add Strands invocation limits (max_turns, token budgets) to adlc-day1 and inbox-assistant, and front all agents with an AgentCore Gateway that enforces rate limits centrally.

**Detection** — done when: OpenTelemetry traces land in a queryable sink and drift alerts are active.

- [ ] **tracing** (L1 → L3): Configure the Strands OTLP exporter with ADOT on every agent to ship spans to CloudWatch (AgentCore Observability / X-Ray), then create a CloudWatch dashboard to verify span ingestion for all three agents.
- [ ] **anomalies** (L1 → L3): Create CloudWatch anomaly-detection alarms on token usage and tool-call volume metrics for each agent, using the metrics already emitted by adlc-day1 and governance-assessor as a starting point, then extend coverage to inbox-assistant.
- [ ] **audit** (L1 → L3): Configure CloudTrail Lake (or an S3 bucket with Object Lock) as the audit sink for all agents and replace the local audit.jsonl writes with structured CloudTrail events or direct S3 + Athena ingestion.

### Days 61-90

**Response** — done when: Tested playbooks can revoke an agent in under a minute.

- [ ] **containment** (L1 → L3): Assign each agent a dedicated IAM role (prerequisite: close the Identity gap), then wire RegistryGate/ContainmentWatch into adlc-day1 and inbox-assistant so a single API call can revoke registry status, IAM role, and AgentCore Identity for any agent; run a containment drill for all three.
- [ ] **threat_alerts** (L1 → L3): Enable GuardDuty with the IAM threat-detection feature in the account, then create Security Hub custom insights scoped to each agent's IAM role ARN so anomalous API calls raise actionable findings.

**Continuous Alignment** — done when: Postmortems update policy, gated by regression evals before release.

- [ ] **drift** (L1 → L3): Wire each agent's eval suite into a CI pipeline (e.g., CodeBuild or GitHub Actions) with a daily cron trigger using Strands Evals or AgentCore Evaluations, and enforce the eval as a merge gate.
- [ ] **red_teaming** (L1 → L3): Create Strands Evals red-team / attack suites for adlc-day1 and governance-assessor, then schedule all three suites to run on a cron trigger in CI (e.g., weekly via CodeBuild) with results fed back into the eval tracking store.
- [ ] **policy_updates** (L1 → L3): Establish a version-controlled policy review process: commit the existing policy documents to a Git repository with owner history, schedule a recurring policy review meeting, and create a postmortem template linked to PLAYBOOK.md so every incident produces a policy change gated by a regression eval.
