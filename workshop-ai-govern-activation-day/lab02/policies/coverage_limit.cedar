// Limitar la creación de aplicaciones de seguros
// a coberturas de hasta $1,000,000.
// Montos mayores requieren aprobación de un supervisor.
permit(
    principal,
    action == AgentCore::Action::"ApplicationToolTarget___create_application",
    resource == AgentCore::Gateway::"<GATEWAY_ARN>"
)
when {
    context.input.coverage_amount <= 1000000
};
