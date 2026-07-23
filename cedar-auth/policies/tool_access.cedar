// Admin can use all tools
permit(
  principal == User::"admin",
  action,
  resource
);

// Developer can only use read_file and list_directory
permit(
  principal == User::"developer",
  action in [Action::"read_file", Action::"list_directory"],
  resource
);

// Deny access to any file in /etc/
forbid(
  principal,
  action,
  resource
)
when { resource.path like "/etc/*" };
