// Permitir reembolsos solo cuando el monto sea menor a $1000.
// El agente puede procesar reembolsos pequeños automáticamente,
// pero montos mayores requieren aprobación humana.
permit(
    principal,
    action == AgentCore::Action::"RefundTarget___process_refund",
    resource == AgentCore::Gateway::"<GATEWAY_ARN>"
)
when {
    context.input.amount < 1000
};
