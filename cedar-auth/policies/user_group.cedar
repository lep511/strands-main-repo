permit (
  principal in AgentTools::UserGroup::"friendsAndFamily",
  action in [AgentTools::Action::"view", AgentTools::Action::"comment"],
  resource in AgentTools::Album::"vacationTrip"
)
unless {
  resource.tag == "private"
};