// Who can call which tool of the portfolio analyst agent.
//
// Cedar is default-deny: a tool call is allowed only if a permit matches
// and no forbid does. Roles come from the entity hierarchy in
// analytics_entities.json (User::"alice" in Role::"manager"), not from the
// prompt, so the model cannot talk its way into another role.

// Managers can use every tool.
@id("manager-full-access")
permit (
  principal in Role::"manager",
  action,
  resource
);

// Advisors can look customers up and see bank-wide activity...
@id("advisor-lookups")
permit (
  principal in Role::"advisor",
  action in [Action::"find_customers", Action::"symbol_activity"],
  resource
);

// ...but may only open the portfolios of the customers in their book.
// The book is an attribute of the User entity; the name is a tool argument.
@id("advisor-own-book")
permit (
  principal in Role::"advisor",
  action == Action::"customer_portfolio",
  resource
)
when {
  principal has book && principal.book.contains(context.input.name)
};

// Analysts see aggregates only: no customer data of any kind.
@id("analyst-aggregates-only")
permit (
  principal in Role::"analyst",
  action == Action::"symbol_activity",
  resource
);

// Nobody opens more than three portfolios in one agent run, managers
// included: a forbid overrides every permit. call_count is the number of
// calls to this tool so far in the run, including the current one.
@id("portfolio-cap-per-run")
forbid (
  principal,
  action == Action::"customer_portfolio",
  resource
)
when {
  context.session.call_count > 3
};
