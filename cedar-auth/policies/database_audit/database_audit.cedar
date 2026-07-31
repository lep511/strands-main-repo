// Admins can perform any database operation
permit(
  principal,
  action,
  resource
)
when { context.session.role == "admin" };

// Analysts can only run read-only queries
permit(
  principal,
  action == AgentTools::Action::"query_database",
  resource
)
when { context.session.role == "analyst" };

// Auditors can query and export, but not modify data
permit(
  principal,
  action in [AgentTools::Action::"query_database", AgentTools::Action::"export_report"],
  resource
)
when { context.session.role == "auditor" };

// No role or unrecognized role: all actions denied (default-deny)
