# Agent incident playbook

Scope: any agent in `agent_registry.yaml`. Target: **contain one agent in under 60 seconds**
without stopping the rest of the estate. Tested by `containment_drill.py` (result in
`drill_result.json`).

## 1. Detect

Triggers: an alert (token-volume or trajectory anomaly, GuardDuty finding on the agent's
role), a `permission_denied` / `injection_suspected` burst in the agent's audit log, or a
user report.

Record: agent id, time, trigger, who is on call.

## 2. Contain (≤ 60 s)

```bash
# Stop new and running invocations of ONE agent (RegistryGate + ContainmentWatch)
uv run src/module-4/estate_registry.py revoke <agent-id> --reason "<ticket / trigger>"
uv run src/module-4/estate_registry.py list          # confirm status=revoked
```

In AWS, also cut the agent's credentials so nothing outside the Strands process can act
for it: disable its AgentCore Identity / revoke its OAuth grants, and attach a deny-all
policy to (or remove the trust policy of) the agent's IAM role.

## 3. Investigate

- Audit trail: the agent's `audit.jsonl` (or the immutable sink once Detection is at L3).
- Traces: OpenTelemetry spans for the affected session (tool calls with arguments).
- Scope: which tools ran, which data left, which users were affected.

## 4. Eradicate and recover

- Fix the root cause (prompt, tool permission, missing control) behind a reviewed change.
- Add the incident as a regression case to the agent's eval suite.
- Restore only after the regression eval passes:

```bash
uv run src/module-4/estate_registry.py restore <agent-id>
```

## 5. Postmortem (template)

```markdown
# Postmortem: <agent-id> — <date>
- Summary:
- Timeline (detect → contain → restore), time to contain:
- Root cause:
- What the controls caught / missed (by layer: Foundation, Prevention, Detection, Response, Alignment):
- Policy change (DESIGN_SPEC / permissions / guardrail) — link to the PR:
- Regression case added — link to the eval:
```

Every postmortem must produce a policy change gated by a regression eval (Continuous
Alignment, Level 5).
