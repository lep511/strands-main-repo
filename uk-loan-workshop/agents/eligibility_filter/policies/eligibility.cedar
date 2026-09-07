// ============================================================
// RBAC - Role-based access control
// ============================================================

// Admin - unrestricted access to all tools
permit(principal, action, resource)
when { context.session.role == "admin" };

// Loan officer - full workflow access
permit(principal, action == Action::"verify_open_banking", resource)
when { context.session.role == "loan_officer" };

permit(principal, action == Action::"verify_national_insurance", resource)
when { context.session.role == "loan_officer" };

permit(principal, action == Action::"add_employment_details", resource)
when { context.session.role == "loan_officer" };

// Loan officer - eligibility check rate-limited to 10 calls per session
permit(principal, action == Action::"check_eligibility_status", resource)
when { context.session.role == "loan_officer" && context.session.call_count < 10 };

// Loan officer - can retrieve denial reasons
permit(principal, action == Action::"get_eligibility_reasons", resource)
when { context.session.role == "loan_officer" };

// Analyst - read-only verification tools, no employment data modification
permit(principal, action == Action::"verify_open_banking", resource)
when { context.session.role == "analyst" };

permit(principal, action == Action::"verify_national_insurance", resource)
when { context.session.role == "analyst" };

// Analyst - eligibility check rate-limited to 10 calls per session
permit(principal, action == Action::"check_eligibility_status", resource)
when { context.session.role == "analyst" && context.session.call_count < 10 };

// Analyst - can retrieve denial reasons
permit(principal, action == Action::"get_eligibility_reasons", resource)
when { context.session.role == "analyst" };

// ============================================================
// Business rules - enforced for ALL roles (forbid overrides permit)
// ============================================================

// Block eligibility check if Open Banking not verified
forbid(principal, action == Action::"check_eligibility_status", resource)
when { context.session has ob_verified && !(context.session.ob_verified) };

// Block eligibility check if NINO not verified
forbid(principal, action == Action::"check_eligibility_status", resource)
when { context.session has nino_verified && !(context.session.nino_verified) };

// Block eligibility check if salaried income below £1,600/month (160000 pence)
forbid(principal, action == Action::"check_eligibility_status", resource)
when {
    context.session has employment_type &&
    context.session.employment_type == "salaried" &&
    context.session has monthly_salary_pence &&
    context.session.monthly_salary_pence < 160000
};

// Block eligibility check if self-employed income below £2,500/month (250000 pence)
forbid(principal, action == Action::"check_eligibility_status", resource)
when {
    context.session has employment_type &&
    context.session.employment_type == "self_employed" &&
    context.session has monthly_salary_pence &&
    context.session.monthly_salary_pence < 250000
};

// ============================================================
// Input validation - enforced for ALL roles
// ============================================================

// Reject invalid employment type
forbid(principal, action == Action::"add_employment_details", resource)
when {
    !(context.input.employment_type == "salaried" ||
      context.input.employment_type == "self_employed")
};

// Reject negative salary
forbid(principal, action == Action::"add_employment_details", resource)
when { context.input.monthly_salary < 0 };
