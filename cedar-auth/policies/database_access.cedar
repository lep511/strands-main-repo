// Admins can perform any database operation
permit(
  principal,
  action,
  resource
)
when { context.session.role == "admin" };

// Analysts can only query the database (read-only)
permit(
  principal,
  action == Action::"query_database",
  resource
)
when { context.session.role == "analyst" };

// No role or unrecognized role: all actions denied (default-deny)
