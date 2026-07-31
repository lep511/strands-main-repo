// Only allow bulk discounts for premium customers with sufficient quantity
permit (
    principal is AgentCore::OAuthUser,
    action == AgentCore::Action::"ApplyBulkDiscount",
    resource
)
when {
    principal.hasTag("customer_tier") &&
    principal.getTag("customer_tier") == "Platinum" &&
    context.input.orderQuantity >= 50
}
unless {
    context.input
        .productTypes
        .containsAny([
            "limited_edition",
            "seasonal_specials"
        ])
};