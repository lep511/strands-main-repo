// GDPR: Bloquear acceso a registros individuales de clientes
// cuando la solicitud proviene de un usuario en la UE.
// Los resúmenes agregados siguen permitidos.
forbid(
    principal,
    action in [
        AgentCore::Action::"DataTarget___query_customer_records",
        AgentCore::Action::"DataTarget___get_customer_details"
    ],
    resource == AgentCore::Gateway::"<GATEWAY_ARN>"
)
when {
    context.input has geography &&
    context.input.geography == "EU"
};
