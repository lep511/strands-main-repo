// Admin can use all tools
permit(
  principal == AgentTools::User::"admin",
  action,
  resource
);

// Developer can only use read_file and list_directory
permit(
  principal == AgentTools::User::"developer",
  action in [AgentTools::Action::"read_file", AgentTools::Action::"list_directory"],
  resource
);

// Deny access to any file in /etc/
forbid(
  principal,
  action,
  resource is AgentTools::Resource
)
when { resource.path like "/etc/*" };
