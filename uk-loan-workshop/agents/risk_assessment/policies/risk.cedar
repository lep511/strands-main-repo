// ============================================================
// RBAC - Role-based access control
// ============================================================

// Admin - unrestricted access to all tools
permit(principal, action, resource)
when { context.session.role == "admin" };

// Loan officer - full access to PIN tools
permit(principal, action == Action::"create_pin", resource)
when { context.session.role == "loan_officer" };

permit(principal, action == Action::"validate_pin_for_disbursement", resource)
when { context.session.role == "loan_officer" };

// Analyst - no access to PIN tools (no permit rules)

// ============================================================
// Security rules - enforced for ALL roles
// ============================================================

// Rate limit PIN validation to 5 attempts (anti brute-force)
forbid(principal, action == Action::"validate_pin_for_disbursement", resource)
when { context.session.call_count > 5 };

// Block validation if PIN has not been created yet
forbid(principal, action == Action::"validate_pin_for_disbursement", resource)
when { context.session has pin_created && !(context.session.pin_created) };
