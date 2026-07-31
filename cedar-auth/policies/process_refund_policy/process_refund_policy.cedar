// Policy evaluation order does not affect the authorization decision

permit(
    principal,
    action == AgentCore::Action::"ProcessRefund",
    resource
)
when {
    context.input.refundAmount < 500
};

forbid(
    principal,
    action == AgentCore::Action::"ProcessRefund",
    resource
)
when {
    context.input.orderDate.offset(duration("90d")) < context.system.now
};