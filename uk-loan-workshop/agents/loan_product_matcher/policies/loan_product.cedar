// ============================================================
// RBAC - Role-based access control
// ============================================================

// Admin - unrestricted access to all tools
permit(principal, action, resource)
when { context.session.role == "admin" };

// Loan officer - full workflow access
permit(principal, action == Action::"get_sort_code", resource)
when { context.session.role == "loan_officer" };

permit(principal, action == Action::"create_loan", resource)
when { context.session.role == "loan_officer" };

permit(principal, action == Action::"setup_repayment", resource)
when { context.session.role == "loan_officer" };

// Analyst - read-only, can look up sort codes but not create loans or set up repayment
permit(principal, action == Action::"get_sort_code", resource)
when { context.session.role == "analyst" };

// ============================================================
// Input validation - enforced for ALL roles
// Values injected by context_enricher as long integers (pence)
// ============================================================

// Reject loan amount below £500 (50000 pence)
forbid(principal, action == Action::"create_loan", resource)
when {
    context.session has loan_amount_pence &&
    context.session.loan_amount_pence < 50000
};

// Reject loan amount exceeding max_loan from eligibility
forbid(principal, action == Action::"create_loan", resource)
when {
    context.session has max_loan_pence &&
    context.session has loan_amount_pence &&
    context.session.loan_amount_pence > context.session.max_loan_pence
};

// Reject tenure below 30 days
forbid(principal, action == Action::"create_loan", resource)
when {
    context.session has tenure_days &&
    context.session.tenure_days < 30
};

// Reject tenure above 90 days
forbid(principal, action == Action::"create_loan", resource)
when {
    context.session has tenure_days &&
    context.session.tenure_days > 90
};

// Reject repayment day outside 1-28 range
forbid(principal, action == Action::"setup_repayment", resource)
when {
    context.session has repayment_day &&
    context.session.repayment_day < 1
};

forbid(principal, action == Action::"setup_repayment", resource)
when {
    context.session has repayment_day &&
    context.session.repayment_day > 28
};
