"""The Day 8 access policy, in Cedar (~ the IAM Unified Access Policy of the original).

AgentCore Policy is default-deny and `forbid` always beats `permit`, exactly like the
original's DENY-evaluated-first rule. Two statements, bound to the agent's identity:

  * permit  - the agent identity may call tools on this gateway   (~ the ALLOW rule)
  * forbid  - nobody may call issue_refund or delete_account       (~ the DENY rule)
"""


def agent_principal_id(account: str, role_name: str) -> str:
    """AgentCore::IamEntity.id for callers using an assumed role (no session name)."""
    return f"arn:aws:sts::{account}:assumed-role/{role_name}"


def action(target: str, tool: str) -> str:
    return f'AgentCore::Action::"{target}___{tool}"'


def permit_agent(gateway_arn: str, principal_id: str) -> str:
    return f"""permit(
  principal is AgentCore::IamEntity,
  action,
  resource == AgentCore::Gateway::"{gateway_arn}"
) when {{
  principal.id == "{principal_id}"
}};"""


def forbid_tools(gateway_arn: str, target: str, tools: list[str]) -> str:
    actions = ",\n    ".join(action(target, t) for t in tools)
    return f"""forbid(
  principal,
  action in [
    {actions}
  ],
  resource == AgentCore::Gateway::"{gateway_arn}"
);"""


def policy_set(account: str, gateway_arn: str, agent_role: str, target: str, denied: list[str]) -> dict[str, str]:
    """name -> Cedar statement."""
    return {
        "allow_support_agent": permit_agent(gateway_arn, agent_principal_id(account, agent_role)),
        "deny_destructive_tools": forbid_tools(gateway_arn, target, denied),
    }
