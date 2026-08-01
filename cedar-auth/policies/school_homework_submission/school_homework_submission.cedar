// Permit homework submission when all base requirements are met
// Submission must be on or before due date AND before 11:59 PM (2359 in 24h format)
permit(
    principal is AgentCore::User,
    action == AgentCore::Action::"ValidateHomeworkSubmission",
    resource
)
when {
    context.input.hasFullName &&
    context.input.hasStudentID &&
    context.input.submittedThroughPortal &&
    context.input.fileNameFollowsFormat &&
    context.input.submissionDate < 0
};

// Also permit on the due date itself if submitted before 23:59
permit(
    principal is AgentCore::User,
    action == AgentCore::Action::"ValidateHomeworkSubmission",
    resource
)
when {
    context.input.hasFullName &&
    context.input.hasStudentID &&
    context.input.submittedThroughPortal &&
    context.input.fileNameFollowsFormat &&
    context.input.submissionDate == 0 &&
    context.input.submissionTime <= 2359
};

// Forbid math submissions without intermediate steps
forbid(
    principal,
    action == AgentCore::Action::"ValidateHomeworkSubmission",
    resource
)
when {
    context.input.homeworkType == "MATHEMATICAL_SOLUTION" &&
    !context.input.showsIntermediateSteps
};

// Forbid written responses with fewer than 250 words
forbid(
    principal,
    action == AgentCore::Action::"ValidateHomeworkSubmission",
    resource
)
when {
    context.input.homeworkType == "WRITTEN_RESPONSE" &&
    context.input.wordCount < 250
};

// Forbid written responses with excessive quoted material (> 5%)
forbid(
    principal,
    action == AgentCore::Action::"ValidateHomeworkSubmission",
    resource
)
when {
    context.input.homeworkType == "WRITTEN_RESPONSE" &&
    context.input.quotedMaterialPercentage > 5
};
