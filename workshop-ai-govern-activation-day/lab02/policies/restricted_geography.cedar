// Denegar TODO acceso a herramientas desde geografías restringidas.
// Aplica a todas las acciones del target de datos.
forbid(
    principal,
    action in [
        AgentCore::Action::"DataTarget___query_customer_records",
        AgentCore::Action::"DataTarget___get_customer_details",
        AgentCore::Action::"DataTarget___get_summary",
        AgentCore::Action::"DataTarget___query_audit_log"
    ],
    resource == AgentCore::Gateway::"<GATEWAY_ARN>"
)
when {
    context.input has geography &&
    context.input.geography == "RESTRICTED"
};
