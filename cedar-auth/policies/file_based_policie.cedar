@id("analyst-read-json-files")
// Analysts can read files only if the path ends with .json
permit(
  principal,
  action == AgentTools::Action::"read_file",
  resource is AgentTools::Resource
)
when {
  context.session.role == "analyst" &&
  context.input.path like "*.json"
};

@id("admin-read-any-file")
// Admins can read any file
permit(
  principal,
  action == AgentTools::Action::"read_file",
  resource is AgentTools::Resource
)
when { context.session.role == "admin" };

@id("admin-write-json-files")
// Admins can write to .json files
permit(
  principal,
  action == AgentTools::Action::"write_file",
  resource is AgentTools::Resource
)
when {
  context.session.role == "admin" &&
  context.input.path like "*.json"
};

@id("block-sensitive-read")
// Deny read access to files under /etc/ or /secrets/ regardless of role
forbid(
  principal,
  action == AgentTools::Action::"read_file",
  resource is AgentTools::Resource
)
when {
  context.input.path like "/etc/*" ||
  context.input.path like "/secrets/*"
};

@id("block-sensitive-write")
// Deny write access to files under /etc/ or /secrets/ regardless of role
forbid(
  principal,
  action == AgentTools::Action::"write_file",
  resource is AgentTools::Resource
)
when {
  context.input.path like "/etc/*" ||
  context.input.path like "/secrets/*"
};
