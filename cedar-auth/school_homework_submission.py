"""School Homework Submission Cedar policy example.

Demonstrates authorization for validating homework submissions where:
- Student must include full name and student ID
- Submission must be through the official portal with correct file naming
- Submission must be on or before the due date
- Math solutions must show intermediate steps
- Written responses must have >= 250 words and <= 5% quoted material
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import cedarpy
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel

from strands import Agent, tool
from strands.hooks.events import BeforeToolCallEvent
from strands.interventions.actions import Deny, Proceed
from strands.interventions.handler import InterventionHandler, OnError
from strands.vended_interventions.cedar._file_loaders import load_policies

console = Console()

TypeAndId = dict[str, str]
PrincipalResolver = Callable[[dict[str, Any]], TypeAndId | None]

_POLICIES = load_policies("./policies/school_homework_submission/school_homework_submission.cedar")

_ENTITIES = [
    {
        "uid": {"type": "AgentCore::User", "id": "teacher_01"},
        "attrs": {},
        "parents": [],
    },
    {
        "uid": {"type": "AgentCore::Resource", "id": "homework_system"},
        "attrs": {},
        "parents": [],
    },
]


class HomeworkSubmissionCedarAuthorization(InterventionHandler):
    """Cedar authorization handler for homework submission validation."""

    name = "cedar-homework-submission-authorization"

    @property
    def on_error(self) -> OnError:
        return self._on_error

    def __init__(
        self,
        *,
        policies: str,
        entities: list[dict[str, Any]],
        principal_resolver: PrincipalResolver,
        on_error: OnError = "throw",
    ) -> None:
        self._on_error = on_error
        self._policies = policies
        self._entities = entities
        self._principal_resolver = principal_resolver

    def before_tool_call(self, event: BeforeToolCallEvent, **kwargs: Any) -> Proceed | Deny:
        invocation_state = event.invocation_state

        try:
            principal = self._principal_resolver(invocation_state)
        except Exception as e:
            if self._on_error == "proceed":
                return Proceed(reason=f"principal_resolver failed but on_error='proceed': {e}")
            if self._on_error == "deny":
                return Deny(reason=f"principal_resolver failed: {e}")
            raise

        if not principal or not principal.get("type") or not principal.get("id"):
            return Deny(reason="No principal identity found in invocation state")

        tool_name = event.tool_use["name"]
        tool_input = event.tool_use.get("input") or {}

        request = {
            "principal": f'AgentCore::User::"{principal["id"]}"',
            "action": f'AgentCore::Action::"{tool_name}"',
            "resource": 'AgentCore::Resource::"homework_system"',
            "context": {
                "input": {
                    "hasFullName": bool(tool_input.get("has_full_name", False)),
                    "hasStudentID": bool(tool_input.get("has_student_id", False)),
                    "submissionDate": int(tool_input.get("submission_date", 0)),
                    "submissionTime": int(tool_input.get("submission_time", 0)),
                    "submittedThroughPortal": bool(tool_input.get("submitted_through_portal", False)),
                    "homeworkType": str(tool_input.get("homework_type", "WRITTEN_RESPONSE")),
                    "showsIntermediateSteps": bool(tool_input.get("shows_intermediate_steps", False)),
                    "wordCount": int(tool_input.get("word_count", 0)),
                    "quotedMaterialPercentage": int(tool_input.get("quoted_material_percentage", 0)),
                    "fileNameFollowsFormat": bool(tool_input.get("file_name_follows_format", False)),
                },
            },
        }

        try:
            result = cedarpy.is_authorized(request, self._policies, self._entities)
        except Exception as e:
            return Deny(reason=f"Cedar engine error (always denied): {e}")

        if not result.allowed:
            reasons = []
            hw_type = tool_input.get("homework_type", "WRITTEN_RESPONSE")

            if not tool_input.get("has_full_name", False):
                reasons.append("Student full name is MISSING from the first page.")
            if not tool_input.get("has_student_id", False):
                reasons.append("Student ID is MISSING from the first page.")
            if not tool_input.get("submitted_through_portal", False):
                reasons.append("Submission was NOT made through the official school portal.")
            if not tool_input.get("file_name_follows_format", False):
                reasons.append(
                    "File name does NOT follow the required format 'AssignmentNumber_LastName_FirstName'."
                )
            sub_date = int(tool_input.get("submission_date", 0))
            sub_time = int(tool_input.get("submission_time", 0))
            if sub_date > 0:
                reasons.append(
                    f"Submission is {sub_date} day(s) LATE (due date already passed)."
                )
            elif sub_date == 0 and sub_time > 2359:
                reasons.append(
                    f"Submission time is {sub_time} (past 23:59 deadline on the due date)."
                )
            if hw_type == "MATHEMATICAL_SOLUTION" and not tool_input.get("shows_intermediate_steps", False):
                reasons.append(
                    "Mathematical solution is MISSING intermediate calculation steps "
                    "(all work must be shown)."
                )
            if hw_type == "WRITTEN_RESPONSE":
                wc = tool_input.get("word_count", 0)
                if wc < 250:
                    reasons.append(
                        f"Word count is {wc}, BELOW the minimum of 250 words required."
                    )
                qm = tool_input.get("quoted_material_percentage", 0)
                if qm > 5:
                    reasons.append(
                        f"Quoted material is {qm}%, EXCEEDS the maximum allowed of 5%."
                    )

            if not reasons:
                reasons.append("Policy conditions not met.")

            denial_msg = (
                f"Access denied for action '{tool_name}'. "
                f"Homework type: {hw_type}. "
                f"Violations found: {' | '.join(reasons)}"
            )
            return Deny(reason=denial_msg)

        return Proceed()


@tool
def ValidateHomeworkSubmission(
    has_full_name: bool,
    has_student_id: bool,
    submission_date: int,
    submission_time: int,
    submitted_through_portal: bool,
    homework_type: str,
    shows_intermediate_steps: bool,
    word_count: int,
    quoted_material_percentage: int,
    file_name_follows_format: bool,
) -> str:
    """Validate a homework submission against school policy.

    Args:
        has_full_name: Whether the student's full name is on the first page
        has_student_id: Whether the student ID is on the first page
        submission_date: Days relative to due date (0=on time, negative=early, positive=late)
        submission_time: Time of submission in 24h format without colon (e.g. 2359 for 11:59 PM)
        submitted_through_portal: Whether submitted through the official school portal
        homework_type: MATHEMATICAL_SOLUTION or WRITTEN_RESPONSE
        shows_intermediate_steps: For math, whether intermediate steps are shown
        word_count: For written responses, the total word count
        quoted_material_percentage: For written responses, percentage of quoted material
        file_name_follows_format: Whether file follows AssignmentNumber_LastName_FirstName format
    """
    return (
        f"Homework submission ACCEPTED: type={homework_type}, "
        f"submitted {abs(submission_date)} day(s) {'early' if submission_date < 0 else 'on time'}, "
        f"time={submission_time:04d}, word_count={word_count}, quoted={quoted_material_percentage}%"
    )


cedar = HomeworkSubmissionCedarAuthorization(
    policies=_POLICIES,
    entities=_ENTITIES,
    principal_resolver=lambda state: (
        {"type": "User", "id": state["teacher_id"]}
        if state.get("teacher_id")
        else None
    ),
)

ALL_TOOLS = [ValidateHomeworkSubmission]


def run_scenario(title: str, style: str, prompt: str, invocation_state: dict):
    console.rule(f"[bold]{title}", style=style)
    agent = Agent(
        tools=ALL_TOOLS,
        interventions=[cedar],
        callback_handler=lambda **kwargs: None,
    )
    result = agent(prompt, invocation_state=invocation_state)
    console.print(Panel(Markdown(str(result)), border_style=style))
    console.print()


if __name__ == "__main__":
    console.print(Panel(
        "[bold]Cedar School Homework Submission Policy[/]\n"
        "Policy: policies/school_homework_submission/school_homework_submission.cedar\n\n"
        "Rules:\n"
        "  - Must include student full name and ID\n"
        "  - Must be submitted through the official portal\n"
        "  - File name must follow format: AssignmentNumber_LastName_FirstName\n"
        "  - Must be received by 11:59 PM on the due date (submission_time <= 2359)\n"
        "  - Math solutions must show intermediate steps\n"
        "  - Written responses: >= 250 words, <= 5% quoted material",
        title="Demo",
    ))
    console.print()

    # Scenario 1: Valid written response - PERMITTED
    run_scenario(
        title="Valid written response (300 words, 3% quoted, on time) - PERMITTED",
        style="green",
        prompt=(
            "Validate a homework submission: has_full_name=true, has_student_id=true, "
            "submission_date=-1, submission_time=1430, submitted_through_portal=true, "
            "homework_type=WRITTEN_RESPONSE, shows_intermediate_steps=false, word_count=300, "
            "quoted_material_percentage=3, file_name_follows_format=true"
        ),
        invocation_state={"teacher_id": "teacher_01"},
    )

    # Scenario 2: Valid math submission - PERMITTED
    run_scenario(
        title="Valid math submission (due date at 22:00, shows steps) - PERMITTED",
        style="green",
        prompt=(
            "Validate a homework submission: has_full_name=true, has_student_id=true, "
            "submission_date=0, submission_time=2200, submitted_through_portal=true, "
            "homework_type=MATHEMATICAL_SOLUTION, shows_intermediate_steps=true, word_count=0, "
            "quoted_material_percentage=0, file_name_follows_format=true"
        ),
        invocation_state={"teacher_id": "teacher_01"},
    )

    # Scenario 3: Late submission - DENIED
    run_scenario(
        title="Late submission (2 days after due date) - DENIED",
        style="red",
        prompt=(
            "Validate a homework submission: has_full_name=true, has_student_id=true, "
            "submission_date=2, submission_time=1000, submitted_through_portal=true, "
            "homework_type=WRITTEN_RESPONSE, shows_intermediate_steps=false, word_count=400, "
            "quoted_material_percentage=2, file_name_follows_format=true"
        ),
        invocation_state={"teacher_id": "teacher_01"},
    )

    # Scenario 4: Submitted past 11:59 PM on due date - DENIED
    run_scenario(
        title="Submitted at 00:30 past deadline on due date - DENIED",
        style="red",
        prompt=(
            "Validate a homework submission: has_full_name=true, has_student_id=true, "
            "submission_date=0, submission_time=2400, submitted_through_portal=true, "
            "homework_type=WRITTEN_RESPONSE, shows_intermediate_steps=false, word_count=400, "
            "quoted_material_percentage=2, file_name_follows_format=true"
        ),
        invocation_state={"teacher_id": "teacher_01"},
    )

    # Scenario 5: Math without intermediate steps - DENIED
    run_scenario(
        title="Math submission without intermediate steps - DENIED",
        style="red",
        prompt=(
            "Validate a homework submission: has_full_name=true, has_student_id=true, "
            "submission_date=0, submission_time=1500, submitted_through_portal=true, "
            "homework_type=MATHEMATICAL_SOLUTION, shows_intermediate_steps=false, word_count=0, "
            "quoted_material_percentage=0, file_name_follows_format=true"
        ),
        invocation_state={"teacher_id": "teacher_01"},
    )

    # Scenario 6: Written response with too much quoted material - DENIED
    run_scenario(
        title="Written response with 10% quoted material - DENIED",
        style="red",
        prompt=(
            "Validate a homework submission: has_full_name=true, has_student_id=true, "
            "submission_date=0, submission_time=1200, submitted_through_portal=true, "
            "homework_type=WRITTEN_RESPONSE, shows_intermediate_steps=false, word_count=500, "
            "quoted_material_percentage=10, file_name_follows_format=true"
        ),
        invocation_state={"teacher_id": "teacher_01"},
    )

    # Scenario 7: Missing student name and ID - DENIED
    run_scenario(
        title="Missing student name and ID - DENIED",
        style="red",
        prompt=(
            "Validate a homework submission: has_full_name=false, has_student_id=false, "
            "submission_date=0, submission_time=1000, submitted_through_portal=true, "
            "homework_type=WRITTEN_RESPONSE, shows_intermediate_steps=false, word_count=300, "
            "quoted_material_percentage=2, file_name_follows_format=true"
        ),
        invocation_state={"teacher_id": "teacher_01"},
    )
