"""Homework Submission Policy chatbot (Cedar-governed).

An interactive, student-facing assistant that answers questions about the
school's homework submission policy AND checks a submission a student
describes in plain language. The policy is NOT enforced by the model's
good behaviour — every acceptance decision is made by the same Cedar
policy used in ``school_homework_submission.py``.

Two things happen in one chat:

1.  **Questions** ("How many words does my essay need?", "Can I submit by
    email?") are answered from the policy encoded in the system prompt.
2.  **Submission checks** ("I'm turning in a 300-word essay with my name
    and ID, 3% quoted, via the portal, due today at 4pm, file A2_Lee_Ana")
    cause the model to call the ``ValidateHomeworkSubmission`` tool. That
    tool call is intercepted by the Cedar ``InterventionHandler``: if the
    submission violates the policy the call is *denied* with a precise,
    rule-by-rule explanation, and the assistant relays that to the student.

Because the verdict comes from Cedar, the assistant cannot "talk itself
into" accepting a late or under-length submission — the authorization
layer has the final say.

The Cedar policy, schema, and the validation tool are reused from
``school_homework_submission.py``; this file only adds the conversational
front end and a student (rather than teacher) principal.

Usage:

    uv run python homework_policy_chatbot.py          # interactive chat
    uv run python homework_policy_chatbot.py --demo    # scripted Q&A, no input

Both modes need Amazon Bedrock access for the default Strands model.
"""

from __future__ import annotations

import sys
from typing import Any

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel

from strands import Agent

# Reuse the Cedar policy, the authorization handler, and the validation tool
# from the companion example so there is a single source of truth for the rules.
from school_homework_submission import (
    HomeworkSubmissionCedarAuthorization,
    ValidateHomeworkSubmission,
    _POLICIES,
)

console = Console()

# The student acting in this chat. The Cedar policy permits any
# ``AgentCore::User``, so a student principal is authorized just like the
# teacher principal in the companion example; the submission's *attributes*
# are what the policy actually checks.
STUDENT_ID = "student_42"

# Entity store for the Cedar engine. The principal (student) and the resource
# must exist as entities for the request to evaluate.
_ENTITIES: list[dict[str, Any]] = [
    {
        "uid": {"type": "AgentCore::User", "id": STUDENT_ID},
        "attrs": {},
        "parents": [],
    },
    {
        "uid": {"type": "AgentCore::Resource", "id": "homework_system"},
        "attrs": {},
        "parents": [],
    },
]

# A student-facing Cedar handler: same policy, but the principal is resolved
# from ``student_id`` in the invocation state.
cedar = HomeworkSubmissionCedarAuthorization(
    policies=_POLICIES,
    entities=_ENTITIES,
    principal_resolver=lambda state: (
        {"type": "User", "id": state["student_id"]}
        if state.get("student_id")
        else None
    ),
)

SYSTEM_PROMPT = """You are the Homework Help Desk assistant for Maple Ridge School.
You help students understand and comply with the Homework Submission Policy.

THE POLICY — a submission is acceptable only when ALL of these hold:
1. Attribution: the student's full name AND student ID number appear at the top
   of the first page.
2. On time + channel: it is received by 11:59 PM on the due date, submitted
   through the official school portal (email, printouts, or shared drives do
   NOT count).
3. File name: it follows the format "AssignmentNumber_LastName_FirstName"
   (for example "A1_Smith_John").
4. Mathematical solutions: all intermediate calculation steps are shown.
5. Written responses: at least 250 words AND no more than 5% quoted material.
   (Exactly 250 words is fine; exactly 5% quoted is fine.)

HOW TO HELP:
- If the student asks a general question about the rules, answer it directly
  and accurately from the policy above. Be friendly, concise, and specific
  (cite the exact threshold, e.g. "at least 250 words").
- If the student describes a SPECIFIC submission they want to check, call the
  ValidateHomeworkSubmission tool to get an authoritative accept/deny verdict.
  Map what they told you onto the tool's arguments:
    * has_full_name / has_student_id: whether each is on the first page.
    * submission_date: days relative to the due date — 0 = on the due date,
      negative = early (e.g. -1 = one day early), positive = late.
    * submission_time: 24-hour clock with no colon, e.g. 2359 for 11:59 PM,
      1430 for 2:30 PM. Use 0 if they only said it was early.
    * submitted_through_portal: true only if the official portal is used.
    * homework_type: "MATHEMATICAL_SOLUTION" for math/calculation work,
      otherwise "WRITTEN_RESPONSE" (essays, prose answers).
    * shows_intermediate_steps: for math, whether all steps are shown.
    * word_count / quoted_material_percentage: for written responses.
    * file_name_follows_format: whether the file name matches the pattern.
  If the student didn't mention a field, ask a brief follow-up rather than
  guessing. Use sensible neutral defaults only for fields that cannot affect
  the verdict for their homework type.
- If the tool DENIES the submission, do not argue with it or override it. Relay
  the specific violations it reports and tell the student exactly what to fix.
- If the tool ACCEPTS, congratulate them and note anything that was close to a
  limit (e.g. submitting near the deadline).

Never claim a submission is acceptable unless the tool accepted it.
"""


def build_agent() -> Agent:
    """Create a fresh Cedar-governed homework assistant agent."""
    return Agent(
        system_prompt=SYSTEM_PROMPT,
        tools=[ValidateHomeworkSubmission],
        interventions=[cedar],
        callback_handler=lambda **kwargs: None,
    )


def ask(agent: Agent, question: str) -> None:
    """Send one student message and print the assistant's reply."""
    result = agent(question, invocation_state={"student_id": STUDENT_ID})
    console.print(Panel(Markdown(str(result)), border_style="cyan"))
    console.print()


DEMO_QUESTIONS = [
    "How many words does my essay need to be, and how much can I quote?",
    "Can I just email my homework to the teacher instead of using the portal?",
    (
        "Please check this submission: it's a written essay, 180 words, 2% quoted, "
        "my name and ID are on the first page, submitted through the portal one day "
        "early, file named A3_Nguyen_Minh. Is it acceptable?"
    ),
    (
        "Now check this one: a math assignment submitted on the due date at 9pm "
        "through the portal, with my name and ID, file A5_Garcia_Luis, but I only "
        "wrote the final answers without showing my working. Will it be accepted?"
    ),
    (
        "And this: a 300-word essay, 3% quoted, name and ID included, via the portal, "
        "submitted one day early, file A2_Lee_Ana. Good to go?"
    ),
]


def run_demo() -> None:
    """Run a scripted conversation that needs no interactive input."""
    console.print(Panel(
        "[bold]Maple Ridge Homework Help Desk — scripted demo[/]\n"
        "Every acceptance verdict is decided by the Cedar policy, not the model.",
        title="Demo",
    ))
    console.print()
    agent = build_agent()
    for q in DEMO_QUESTIONS:
        console.print(Panel(q, title="Student", border_style="yellow"))
        ask(agent, q)


def run_interactive() -> None:
    """Run an interactive terminal chat."""
    console.print(Panel(
        "[bold]Maple Ridge Homework Help Desk[/]\n\n"
        "Ask me about the homework submission policy, or describe a submission\n"
        "and I'll check it against the rules. Type 'exit' to quit.\n\n"
        "Try:\n"
        "  - \"How much quoted material am I allowed?\"\n"
        "  - \"Check my 260-word essay, name and ID on page 1, via the portal,\n"
        "     3% quoted, due today at 11pm, file A1_Smith_John.\"",
        title="Homework Help Desk",
    ))
    console.print()
    agent = build_agent()
    while True:
        try:
            user_input = input("student> ").strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\nGoodbye! 👋")
            break
        if not user_input:
            continue
        if user_input.lower() in {"exit", "quit"}:
            console.print("Goodbye! 👋")
            break
        try:
            ask(agent, user_input)
        except Exception as e:  # noqa: BLE001 - keep the chat alive on model errors
            console.print(Panel(f"[red]Error:[/] {e}", border_style="red"))


if __name__ == "__main__":
    if "--demo" in sys.argv[1:]:
        run_demo()
    else:
        run_interactive()
