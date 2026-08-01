"""School Homework Submission - Cedar Policy Validation Tests.

Tests the Cedar policy for school homework submissions using an agent-based
approach. Each test scenario is categorized according to policy validation
outcomes:

- VALID: All policy conditions are met; submission is accepted.
- SATISFIABLE: Conditions can be met but require specific parameter values.
- INVALID: One or more policy conditions are violated; submission is rejected.
- IMPOSSIBLE: Contradictory conditions that can never be satisfied simultaneously.
- TOO COMPLEX TO VALIDATE: Edge cases where multiple interacting rules create
  ambiguity in the expected outcome.
- NO TRANSLATIONS FOUND: Scenarios where the input does not map to any known
  policy rule (e.g., unknown homework types).
- TRANSLATION AMBIGUOUS: Scenarios where the policy could interpret the input
  in multiple ways depending on context.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import cedarpy
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from school_homework_submission import (
    HomeworkSubmissionCedarAuthorization,
    _ENTITIES,
    _POLICIES,
)

console = Console()


def evaluate_submission(params: dict[str, Any]) -> dict[str, Any]:
    """Evaluate a homework submission directly against the Cedar policy.

    Returns a dict with 'allowed' (bool) and 'errors' (list of strings).
    """
    request = {
        "principal": 'AgentCore::User::"teacher_01"',
        "action": 'AgentCore::Action::"ValidateHomeworkSubmission"',
        "resource": 'AgentCore::Resource::"homework_system"',
        "context": {
            "input": {
                "hasFullName": bool(params.get("has_full_name", False)),
                "hasStudentID": bool(params.get("has_student_id", False)),
                "submissionDate": int(params.get("submission_date", 0)),
                "submissionTime": int(params.get("submission_time", 0)),
                "submittedThroughPortal": bool(params.get("submitted_through_portal", False)),
                "homeworkType": str(params.get("homework_type", "WRITTEN_RESPONSE")),
                "showsIntermediateSteps": bool(params.get("shows_intermediate_steps", False)),
                "wordCount": int(params.get("word_count", 0)),
                "quotedMaterialPercentage": int(params.get("quoted_material_percentage", 0)),
                "fileNameFollowsFormat": bool(params.get("file_name_follows_format", False)),
            },
        },
    }

    try:
        result = cedarpy.is_authorized(request, _POLICIES, _ENTITIES)
        return {"allowed": result.allowed, "errors": []}
    except Exception as e:
        return {"allowed": False, "errors": [str(e)]}


# ---------------------------------------------------------------------------
# Test scenario definitions
# ---------------------------------------------------------------------------

SCENARIOS: list[dict[str, Any]] = [
    # ===== VALID =====
    # All conditions satisfied; policy permits the submission.
    {
        "category": "VALID",
        "title": "Complete written response submitted early",
        "description": "All fields correct, 300 words, 3% quoted, 1 day early via portal",
        "params": {
            "has_full_name": True,
            "has_student_id": True,
            "submission_date": -1,
            "submission_time": 1430,
            "submitted_through_portal": True,
            "homework_type": "WRITTEN_RESPONSE",
            "shows_intermediate_steps": False,
            "word_count": 300,
            "quoted_material_percentage": 3,
            "file_name_follows_format": True,
        },
        "expected_allowed": True,
    },
    {
        "category": "VALID",
        "title": "Math solution with intermediate steps on due date",
        "description": "Submitted on the due date at 22:00 with all steps shown",
        "params": {
            "has_full_name": True,
            "has_student_id": True,
            "submission_date": 0,
            "submission_time": 2200,
            "submitted_through_portal": True,
            "homework_type": "MATHEMATICAL_SOLUTION",
            "shows_intermediate_steps": True,
            "word_count": 0,
            "quoted_material_percentage": 0,
            "file_name_follows_format": True,
        },
        "expected_allowed": True,
    },
    {
        "category": "VALID",
        "title": "Written response at exactly the deadline (23:59)",
        "description": "Submitted at the last possible moment on the due date",
        "params": {
            "has_full_name": True,
            "has_student_id": True,
            "submission_date": 0,
            "submission_time": 2359,
            "submitted_through_portal": True,
            "homework_type": "WRITTEN_RESPONSE",
            "shows_intermediate_steps": False,
            "word_count": 500,
            "quoted_material_percentage": 4,
            "file_name_follows_format": True,
        },
        "expected_allowed": True,
    },
    {
        "category": "VALID",
        "title": "Written response with exactly 250 words and 5% quoted",
        "description": "Boundary values: minimum word count and maximum allowed quoted percentage",
        "params": {
            "has_full_name": True,
            "has_student_id": True,
            "submission_date": 0,
            "submission_time": 1200,
            "submitted_through_portal": True,
            "homework_type": "WRITTEN_RESPONSE",
            "shows_intermediate_steps": False,
            "word_count": 250,
            "quoted_material_percentage": 5,
            "file_name_follows_format": True,
        },
        "expected_allowed": True,
    },

    {
        "category": "VALID",
        "title": "Essay with 300 words, 4% quoted, submitted 1 day early at 3pm",
        "description": (
            "Natural language scenario: 300-word essay with one short 12-word quote "
            "(4% of total). Name and ID included, submitted via portal one day before "
            "deadline at 15:00. File named A4_Johnson_Mary (correct format)."
        ),
        "params": {
            "has_full_name": True,
            "has_student_id": True,
            "submission_date": -1,
            "submission_time": 1500,
            "submitted_through_portal": True,
            "homework_type": "WRITTEN_RESPONSE",
            "shows_intermediate_steps": False,
            "word_count": 300,
            "quoted_material_percentage": 4,
            "file_name_follows_format": True,
        },
        "expected_allowed": True,
    },

    # ===== SATISFIABLE =====
    # Conditions that CAN be met but only under specific parameter combinations.
    {
        "category": "SATISFIABLE",
        "title": "Math solution satisfiable only with intermediate steps",
        "description": "Without steps it would be denied; with steps it passes",
        "params": {
            "has_full_name": True,
            "has_student_id": True,
            "submission_date": 0,
            "submission_time": 1500,
            "submitted_through_portal": True,
            "homework_type": "MATHEMATICAL_SOLUTION",
            "shows_intermediate_steps": True,
            "word_count": 0,
            "quoted_material_percentage": 0,
            "file_name_follows_format": True,
        },
        "expected_allowed": True,
    },
    {
        "category": "SATISFIABLE",
        "title": "Written response satisfiable only at word count boundary",
        "description": "Exactly 250 words (minimum); 249 would be denied",
        "params": {
            "has_full_name": True,
            "has_student_id": True,
            "submission_date": -2,
            "submission_time": 800,
            "submitted_through_portal": True,
            "homework_type": "WRITTEN_RESPONSE",
            "shows_intermediate_steps": False,
            "word_count": 250,
            "quoted_material_percentage": 0,
            "file_name_follows_format": True,
        },
        "expected_allowed": True,
    },
    {
        "category": "SATISFIABLE",
        "title": "Submission satisfiable only on or before due date",
        "description": "submission_date=0 is the last satisfiable value; 1 would be denied",
        "params": {
            "has_full_name": True,
            "has_student_id": True,
            "submission_date": 0,
            "submission_time": 2300,
            "submitted_through_portal": True,
            "homework_type": "WRITTEN_RESPONSE",
            "shows_intermediate_steps": False,
            "word_count": 400,
            "quoted_material_percentage": 2,
            "file_name_follows_format": True,
        },
        "expected_allowed": True,
    },

    {
        "category": "SATISFIABLE",
        "title": "Math with steps still denied when base requirements fail",
        "description": (
            "Automated Reasoning scenario: homeworkType=MATHEMATICAL_SOLUTION, "
            "showsIntermediateSteps=true, yet isSubmissionAcceptable=false. "
            "This is possible because the type-specific forbid rule is satisfied, "
            "but a base permit condition (missing student ID) is not met."
        ),
        "params": {
            "has_full_name": True,
            "has_student_id": False,
            "submission_date": 0,
            "submission_time": 1400,
            "submitted_through_portal": True,
            "homework_type": "MATHEMATICAL_SOLUTION",
            "shows_intermediate_steps": True,
            "word_count": 0,
            "quoted_material_percentage": 0,
            "file_name_follows_format": True,
        },
        "expected_allowed": False,
    },

    # ===== INVALID =====
    # Clear policy violations; submission is denied.
    {
        "category": "INVALID",
        "title": "Late submission (2 days past due date)",
        "description": "submission_date > 0 violates the on-time requirement",
        "params": {
            "has_full_name": True,
            "has_student_id": True,
            "submission_date": 2,
            "submission_time": 1000,
            "submitted_through_portal": True,
            "homework_type": "WRITTEN_RESPONSE",
            "shows_intermediate_steps": False,
            "word_count": 400,
            "quoted_material_percentage": 2,
            "file_name_follows_format": True,
        },
        "expected_allowed": False,
    },
    {
        "category": "INVALID",
        "title": "Submitted past 23:59 on due date",
        "description": "submission_time=2400 exceeds the deadline on day 0",
        "params": {
            "has_full_name": True,
            "has_student_id": True,
            "submission_date": 0,
            "submission_time": 2400,
            "submitted_through_portal": True,
            "homework_type": "WRITTEN_RESPONSE",
            "shows_intermediate_steps": False,
            "word_count": 400,
            "quoted_material_percentage": 2,
            "file_name_follows_format": True,
        },
        "expected_allowed": False,
    },
    {
        "category": "INVALID",
        "title": "Math solution without intermediate steps",
        "description": "MATHEMATICAL_SOLUTION requires shows_intermediate_steps=true",
        "params": {
            "has_full_name": True,
            "has_student_id": True,
            "submission_date": 0,
            "submission_time": 1500,
            "submitted_through_portal": True,
            "homework_type": "MATHEMATICAL_SOLUTION",
            "shows_intermediate_steps": False,
            "word_count": 0,
            "quoted_material_percentage": 0,
            "file_name_follows_format": True,
        },
        "expected_allowed": False,
    },
    {
        "category": "INVALID",
        "title": "Written response with too few words (100 < 250)",
        "description": "Word count below minimum threshold",
        "params": {
            "has_full_name": True,
            "has_student_id": True,
            "submission_date": 0,
            "submission_time": 1200,
            "submitted_through_portal": True,
            "homework_type": "WRITTEN_RESPONSE",
            "shows_intermediate_steps": False,
            "word_count": 100,
            "quoted_material_percentage": 2,
            "file_name_follows_format": True,
        },
        "expected_allowed": False,
    },
    {
        "category": "INVALID",
        "title": "Written response with excessive quoted material (10% > 5%)",
        "description": "Quoted material percentage exceeds the allowed limit",
        "params": {
            "has_full_name": True,
            "has_student_id": True,
            "submission_date": 0,
            "submission_time": 1200,
            "submitted_through_portal": True,
            "homework_type": "WRITTEN_RESPONSE",
            "shows_intermediate_steps": False,
            "word_count": 500,
            "quoted_material_percentage": 10,
            "file_name_follows_format": True,
        },
        "expected_allowed": False,
    },
    {
        "category": "INVALID",
        "title": "Missing student full name",
        "description": "has_full_name=false violates identification requirement",
        "params": {
            "has_full_name": False,
            "has_student_id": True,
            "submission_date": 0,
            "submission_time": 1000,
            "submitted_through_portal": True,
            "homework_type": "WRITTEN_RESPONSE",
            "shows_intermediate_steps": False,
            "word_count": 300,
            "quoted_material_percentage": 2,
            "file_name_follows_format": True,
        },
        "expected_allowed": False,
    },
    {
        "category": "INVALID",
        "title": "Missing student ID",
        "description": "has_student_id=false violates identification requirement",
        "params": {
            "has_full_name": True,
            "has_student_id": False,
            "submission_date": 0,
            "submission_time": 1000,
            "submitted_through_portal": True,
            "homework_type": "WRITTEN_RESPONSE",
            "shows_intermediate_steps": False,
            "word_count": 300,
            "quoted_material_percentage": 2,
            "file_name_follows_format": True,
        },
        "expected_allowed": False,
    },
    {
        "category": "INVALID",
        "title": "Not submitted through official portal",
        "description": "submitted_through_portal=false violates portal requirement",
        "params": {
            "has_full_name": True,
            "has_student_id": True,
            "submission_date": 0,
            "submission_time": 1000,
            "submitted_through_portal": False,
            "homework_type": "WRITTEN_RESPONSE",
            "shows_intermediate_steps": False,
            "word_count": 300,
            "quoted_material_percentage": 2,
            "file_name_follows_format": True,
        },
        "expected_allowed": False,
    },
    {
        "category": "INVALID",
        "title": "Incorrect file name format",
        "description": "file_name_follows_format=false violates naming convention",
        "params": {
            "has_full_name": True,
            "has_student_id": True,
            "submission_date": 0,
            "submission_time": 1000,
            "submitted_through_portal": True,
            "homework_type": "WRITTEN_RESPONSE",
            "shows_intermediate_steps": False,
            "word_count": 300,
            "quoted_material_percentage": 2,
            "file_name_follows_format": False,
        },
        "expected_allowed": False,
    },

    # ===== IMPOSSIBLE =====
    # Contradictory conditions that can never satisfy the policy simultaneously.
    {
        "category": "IMPOSSIBLE",
        "title": "Late submission can never be accepted regardless of other fields",
        "description": "Even with all other fields perfect, submission_date > 0 is always denied",
        "params": {
            "has_full_name": True,
            "has_student_id": True,
            "submission_date": 5,
            "submission_time": 800,
            "submitted_through_portal": True,
            "homework_type": "WRITTEN_RESPONSE",
            "shows_intermediate_steps": True,
            "word_count": 1000,
            "quoted_material_percentage": 0,
            "file_name_follows_format": True,
        },
        "expected_allowed": False,
    },
    {
        "category": "IMPOSSIBLE",
        "title": "Math without steps can never pass even if submitted early",
        "description": "The forbid rule for math without steps overrides any permit",
        "params": {
            "has_full_name": True,
            "has_student_id": True,
            "submission_date": -10,
            "submission_time": 100,
            "submitted_through_portal": True,
            "homework_type": "MATHEMATICAL_SOLUTION",
            "shows_intermediate_steps": False,
            "word_count": 0,
            "quoted_material_percentage": 0,
            "file_name_follows_format": True,
        },
        "expected_allowed": False,
    },
    {
        "category": "IMPOSSIBLE",
        "title": "Written response with 249 words can never be accepted",
        "description": "The forbid rule for wordCount < 250 always blocks this",
        "params": {
            "has_full_name": True,
            "has_student_id": True,
            "submission_date": -5,
            "submission_time": 900,
            "submitted_through_portal": True,
            "homework_type": "WRITTEN_RESPONSE",
            "shows_intermediate_steps": False,
            "word_count": 249,
            "quoted_material_percentage": 0,
            "file_name_follows_format": True,
        },
        "expected_allowed": False,
    },
    {
        "category": "IMPOSSIBLE",
        "title": "No portal submission can ever be accepted",
        "description": "submitted_through_portal=false is never satisfiable in any permit rule",
        "params": {
            "has_full_name": True,
            "has_student_id": True,
            "submission_date": -1,
            "submission_time": 1200,
            "submitted_through_portal": False,
            "homework_type": "MATHEMATICAL_SOLUTION",
            "shows_intermediate_steps": True,
            "word_count": 0,
            "quoted_material_percentage": 0,
            "file_name_follows_format": True,
        },
        "expected_allowed": False,
    },

    # ===== TOO COMPLEX TO VALIDATE =====
    # Edge cases where multiple interacting rules create ambiguity.
    {
        "category": "TOO COMPLEX TO VALIDATE",
        "title": "Written response at exactly 250 words and exactly 5% quoted",
        "description": (
            "Both wordCount and quotedMaterialPercentage at exact boundary. "
            "Policy uses < 250 (forbid) and > 5 (forbid), so 250 and 5 should pass, "
            "but the interaction of two boundary conditions adds validation complexity."
        ),
        "params": {
            "has_full_name": True,
            "has_student_id": True,
            "submission_date": 0,
            "submission_time": 2359,
            "submitted_through_portal": True,
            "homework_type": "WRITTEN_RESPONSE",
            "shows_intermediate_steps": False,
            "word_count": 250,
            "quoted_material_percentage": 5,
            "file_name_follows_format": True,
        },
        "expected_allowed": True,
    },
    {
        "category": "TOO COMPLEX TO VALIDATE",
        "title": "Submission at time=2359 on date=0 vs time=0 on date=1",
        "description": (
            "The policy has two permit rules: one for submissionDate < 0 (no time check) "
            "and one for submissionDate == 0 with submissionTime <= 2359. "
            "The boundary between 'on time' and 'late' requires understanding "
            "how both rules interact."
        ),
        "params": {
            "has_full_name": True,
            "has_student_id": True,
            "submission_date": 0,
            "submission_time": 2359,
            "submitted_through_portal": True,
            "homework_type": "MATHEMATICAL_SOLUTION",
            "shows_intermediate_steps": True,
            "word_count": 0,
            "quoted_material_percentage": 0,
            "file_name_follows_format": True,
        },
        "expected_allowed": True,
    },
    {
        "category": "TOO COMPLEX TO VALIDATE",
        "title": "Math type but with high word count and quoted material",
        "description": (
            "Math submission includes 500 words and 10% quoted material. "
            "The forbid rules for wordCount and quotedMaterialPercentage only apply "
            "to WRITTEN_RESPONSE, so this should pass. But the interaction between "
            "type-specific rules and generic requirements adds complexity."
        ),
        "params": {
            "has_full_name": True,
            "has_student_id": True,
            "submission_date": -1,
            "submission_time": 1000,
            "submitted_through_portal": True,
            "homework_type": "MATHEMATICAL_SOLUTION",
            "shows_intermediate_steps": True,
            "word_count": 500,
            "quoted_material_percentage": 10,
            "file_name_follows_format": True,
        },
        "expected_allowed": True,
    },

    # ===== NO TRANSLATIONS FOUND =====
    # Input does not map to any recognized policy rule or type.
    {
        "category": "NO TRANSLATIONS FOUND",
        "title": "Unknown homework type (PRESENTATION)",
        "description": (
            "The policy only defines rules for MATHEMATICAL_SOLUTION and WRITTEN_RESPONSE. "
            "An unknown type like PRESENTATION has no specific forbid rules, "
            "so it falls through to the base permit conditions only."
        ),
        "params": {
            "has_full_name": True,
            "has_student_id": True,
            "submission_date": -1,
            "submission_time": 1000,
            "submitted_through_portal": True,
            "homework_type": "PRESENTATION",
            "shows_intermediate_steps": False,
            "word_count": 0,
            "quoted_material_percentage": 0,
            "file_name_follows_format": True,
        },
        "expected_allowed": True,
    },
    {
        "category": "NO TRANSLATIONS FOUND",
        "title": "Unknown homework type (LAB_REPORT)",
        "description": (
            "LAB_REPORT is not defined in the policy types. No specific forbid rules "
            "apply, so the base permit conditions are the only gate."
        ),
        "params": {
            "has_full_name": True,
            "has_student_id": True,
            "submission_date": 0,
            "submission_time": 1400,
            "submitted_through_portal": True,
            "homework_type": "LAB_REPORT",
            "shows_intermediate_steps": False,
            "word_count": 50,
            "quoted_material_percentage": 80,
            "file_name_follows_format": True,
        },
        "expected_allowed": True,
    },
    {
        "category": "NO TRANSLATIONS FOUND",
        "title": "Empty homework type string",
        "description": (
            "An empty string for homework_type doesn't match any type-specific rules. "
            "The policy has no translation for this input."
        ),
        "params": {
            "has_full_name": True,
            "has_student_id": True,
            "submission_date": -1,
            "submission_time": 900,
            "submitted_through_portal": True,
            "homework_type": "",
            "shows_intermediate_steps": False,
            "word_count": 0,
            "quoted_material_percentage": 0,
            "file_name_follows_format": True,
        },
        "expected_allowed": True,
    },

    # ===== TRANSLATION AMBIGUOUS =====
    # Scenarios where policy interpretation is unclear or context-dependent.
    {
        "category": "TRANSLATION AMBIGUOUS",
        "title": "Math submission with shows_intermediate_steps but also 300 words",
        "description": (
            "A MATHEMATICAL_SOLUTION that also has 300 words. The wordCount forbid "
            "only applies to WRITTEN_RESPONSE, but it's ambiguous whether a math "
            "assignment with substantial written explanation should be classified "
            "as MATHEMATICAL_SOLUTION or WRITTEN_RESPONSE."
        ),
        "params": {
            "has_full_name": True,
            "has_student_id": True,
            "submission_date": 0,
            "submission_time": 1600,
            "submitted_through_portal": True,
            "homework_type": "MATHEMATICAL_SOLUTION",
            "shows_intermediate_steps": True,
            "word_count": 300,
            "quoted_material_percentage": 3,
            "file_name_follows_format": True,
        },
        "expected_allowed": True,
    },
    {
        "category": "TRANSLATION AMBIGUOUS",
        "title": "Written response with shows_intermediate_steps=true",
        "description": (
            "A WRITTEN_RESPONSE that claims to show intermediate steps. This field "
            "is only semantically relevant for math, but the policy doesn't forbid it. "
            "The 'translation' of what the student actually submitted is ambiguous."
        ),
        "params": {
            "has_full_name": True,
            "has_student_id": True,
            "submission_date": -1,
            "submission_time": 1100,
            "submitted_through_portal": True,
            "homework_type": "WRITTEN_RESPONSE",
            "shows_intermediate_steps": True,
            "word_count": 500,
            "quoted_material_percentage": 2,
            "file_name_follows_format": True,
        },
        "expected_allowed": True,
    },
    {
        "category": "TRANSLATION AMBIGUOUS",
        "title": "Submission date=-1 but time=2400 (early day, late hour)",
        "description": (
            "Submitted 1 day early but at a time value of 2400. The first permit rule "
            "(submissionDate < 0) has no time constraint, so it permits. But the time "
            "value is technically invalid (24:00 doesn't exist), creating ambiguity in "
            "how the system should interpret this submission."
        ),
        "params": {
            "has_full_name": True,
            "has_student_id": True,
            "submission_date": -1,
            "submission_time": 2400,
            "submitted_through_portal": True,
            "homework_type": "WRITTEN_RESPONSE",
            "shows_intermediate_steps": False,
            "word_count": 300,
            "quoted_material_percentage": 1,
            "file_name_follows_format": True,
        },
        "expected_allowed": True,
    },
]


# ---------------------------------------------------------------------------
# Test runner
# ---------------------------------------------------------------------------

def run_tests() -> None:
    """Execute all test scenarios and report results."""
    console.print(Panel(
        "[bold]School Homework Submission - Cedar Policy Tests[/]\n\n"
        "Categories:\n"
        "  [green]VALID[/]: All conditions met, submission accepted\n"
        "  [cyan]SATISFIABLE[/]: Conditions can be met with specific values\n"
        "  [red]INVALID[/]: Policy violations, submission denied\n"
        "  [magenta]IMPOSSIBLE[/]: Contradictory conditions, always denied\n"
        "  [yellow]TOO COMPLEX TO VALIDATE[/]: Ambiguous multi-rule interactions\n"
        "  [blue]NO TRANSLATIONS FOUND[/]: Input doesn't map to known rules\n"
        "  [white]TRANSLATION AMBIGUOUS[/]: Multiple valid interpretations",
        title="Test Suite",
    ))
    console.print()

    table = Table(show_lines=True)
    table.add_column("#", style="dim", width=3)
    table.add_column("Category", width=26)
    table.add_column("Scenario", width=50)
    table.add_column("Expected", width=8)
    table.add_column("Actual", width=8)
    table.add_column("Result", width=6)

    category_styles = {
        "VALID": "green",
        "SATISFIABLE": "cyan",
        "INVALID": "red",
        "IMPOSSIBLE": "magenta",
        "TOO COMPLEX TO VALIDATE": "yellow",
        "NO TRANSLATIONS FOUND": "blue",
        "TRANSLATION AMBIGUOUS": "white",
    }

    passed = 0
    failed = 0
    errors: list[str] = []

    for i, scenario in enumerate(SCENARIOS, 1):
        category = scenario["category"]
        title = scenario["title"]
        expected = scenario["expected_allowed"]
        style = category_styles.get(category, "white")

        result = evaluate_submission(scenario["params"])
        actual = result["allowed"]
        success = actual == expected

        if success:
            passed += 1
            result_str = "[green]OK[/]"
        else:
            failed += 1
            result_str = "[red]FAIL[/]"
            errors.append(
                f"  #{i} [{category}] {title}: "
                f"expected={'ALLOW' if expected else 'DENY'}, "
                f"got={'ALLOW' if actual else 'DENY'}"
            )

        table.add_row(
            str(i),
            f"[{style}]{category}[/]",
            title,
            "ALLOW" if expected else "DENY",
            "ALLOW" if actual else "DENY",
            result_str,
        )

    console.print(table)
    console.print()

    # Summary
    total = passed + failed
    if failed == 0:
        console.print(Panel(
            f"[bold green]ALL {total} TESTS PASSED[/]",
            border_style="green",
        ))
    else:
        error_details = "\n".join(errors)
        console.print(Panel(
            f"[bold red]{failed}/{total} TESTS FAILED[/]\n\n{error_details}",
            border_style="red",
        ))

    return failed == 0


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
