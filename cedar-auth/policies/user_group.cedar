permit (
  principal in UserGroup::"friendsAndFamily",
  action in [Action::"view", Action::"comment"], 
  resource in Album::"vacationTrip"
)
unless {
  resource.tag =="private"
};