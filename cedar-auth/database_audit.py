"""Database Audit Cedar policy example.

Demonstrates authorization using both before_tool_call and after_tool_call:
- before_tool_call: Authorizes access based on role (admin/analyst/auditor)
- after_tool_call: Audits and transforms tool output:
  * Redacts sensitive columns (email, ssn, salary) for analysts
  * Enforces row limits per role
  * Logs all database operations for compliance
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from typing import Any

import cedarpy
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table

from strands import Agent, tool
from strands.hooks.events import AfterToolCallEvent, BeforeToolCallEvent
from strands.interventions.actions import Deny, Proceed, Transform
from strands.interventions.handler import InterventionHandler, OnError
from strands.vended_interventions.cedar._file_loaders import load_policies

console = Console()

TypeAndId = dict[str, str]
PrincipalResolver = Callable[[dict[str, Any]], TypeAndId | None]

_POLICIES = load_policies("./policies/database_audit/database_audit.cedar")

_ENTITIES = [
    {
        "uid": {"type": "AgentTools::User", "id": "alice"},
        "attrs": {},
        "parents": [],
    },
    {
        "uid": {"type": "AgentTools::User", "id": "bob"},
        "attrs": {},
        "parents": [],
    },
    {
        "uid": {"type": "AgentTools::User", "id": "carlos"},
        "attrs": {},
        "parents": [],
    },
    {
        "uid": {"type": "AgentTools::Resource", "id": "database"},
        "attrs": {},
        "parents": [],
    },
]

SENSITIVE_FIELDS = {"email", "ssn", "salary", "password", "credit_card"}

ROW_LIMITS = {
    "admin": 1000,
    "auditor": 500,
    "analyst": 100,
}

audit_log: list[dict[str, Any]] = []


class DatabaseAuditAuthorization(InterventionHandler):
    """Cedar authorization handler with pre and post tool-call verification.

    - before_tool_call: Evaluates Cedar policies to permit/deny the operation.
    - after_tool_call: Inspects tool output and redacts sensitive data or
      truncates results based on the caller's role.
    """

    name = "cedar-database-audit"

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
        """Authorize the tool call using Cedar policies before execution.

        Error handling:
        - Cedar engine failures (malformed policies, evaluation errors) are always
          fail-closed: the tool call is denied regardless of on_error configuration.
        - The on_error option controls what happens when user-supplied callbacks
          (principal_resolver) raise an exception:
            'throw': re-raises the exception to the caller
            'deny': treats the callback failure as a denial (fail-closed)
            'proceed': allows the tool call despite the callback error (fail-open)
        """
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
        role = invocation_state.get("role", "")

        request = {
            "principal": f'AgentTools::User::"{principal["id"]}"',
            "action": f'AgentTools::Action::"{tool_name}"',
            "resource": 'AgentTools::Resource::"database"',
            "context": {
                "session": {"role": role},
                "input": tool_input,
            },
        }

        try:
            result = cedarpy.is_authorized(request, self._policies, self._entities)
        except Exception as e:
            # Cedar engine failures are always fail-closed regardless of on_error
            return Deny(reason=f"Cedar engine error (always denied): {e}")

        if not result.allowed:
            reasons = []
            allowed_actions = {
                "admin": ["query_database", "insert_record", "delete_record", "export_report"],
                "analyst": ["query_database"],
                "auditor": ["query_database", "export_report"],
            }

            if not role:
                reasons.append("No role assigned. A valid role is required.")
            elif role not in allowed_actions:
                reasons.append(f"Role '{role}' is not recognized.")
            else:
                permitted = allowed_actions[role]
                reasons.append(
                    f"Role '{role}' is not authorized to perform '{tool_name}'. "
                    f"Permitted actions for '{role}': {', '.join(permitted)}."
                )

            if not reasons:
                reasons.append("Policy conditions not met.")

            denial_reason = f"Access denied for action '{tool_name}'. {' '.join(reasons)}"

            audit_log.append({
                "user": principal["id"],
                "role": role,
                "action": tool_name,
                "status": "DENIED",
                "reason": denial_reason,
            })
            return Deny(reason=denial_reason)

        audit_log.append({
            "user": principal["id"],
            "role": role,
            "action": tool_name,
            "status": "PERMITTED",
        })
        return Proceed()

    def after_tool_call(self, event: AfterToolCallEvent, **kwargs: Any) -> Proceed | Transform:
        """Inspect and transform tool output after execution.

        - Redacts sensitive fields for non-admin roles
        - Enforces row limits per role
        - Logs the output size for compliance auditing
        """
        invocation_state = event.invocation_state
        role = invocation_state.get("role", "analyst")
        tool_name = event.tool_use["name"]

        if tool_name not in ("query_database", "export_report"):
            return Proceed()

        result_content = ""
        for block in event.result.get("content", []):
            if "text" in block:
                result_content = block["text"]
                break

        if not result_content:
            return Proceed()

        needs_redaction = role != "admin" and any(
            field in result_content.lower() for field in SENSITIVE_FIELDS
        )
        row_limit = ROW_LIMITS.get(role, 100)
        rows = result_content.split("\n")
        needs_truncation = len(rows) > row_limit

        if not needs_redaction and not needs_truncation:
            audit_log.append({
                "action": tool_name,
                "role": role,
                "output_check": "PASS",
                "rows": len(rows),
            })
            return Proceed()

        def apply_transform(evt: Any) -> None:
            content = result_content
            redacted_fields: list[str] = []

            if needs_redaction:
                lines = content.split("\n")
                is_csv = len(lines) > 1 and "," in lines[0] and any(
                    f in lines[0].lower() for f in SENSITIVE_FIELDS
                )

                if is_csv:
                    headers = [h.strip().lower() for h in lines[0].split(",")]
                    sensitive_indices = [
                        i for i, h in enumerate(headers) if h in SENSITIVE_FIELDS
                    ]
                    redacted_fields = [headers[i] for i in sensitive_indices]
                    new_lines = [lines[0]]
                    for line in lines[1:]:
                        if not line.strip():
                            new_lines.append(line)
                            continue
                        cols = line.split(",")
                        for idx in sensitive_indices:
                            if idx < len(cols):
                                cols[idx] = "[REDACTED]"
                        new_lines.append(",".join(cols))
                    content = "\n".join(new_lines)
                else:
                    for field in SENSITIVE_FIELDS:
                        pattern = re.compile(
                            rf'("{field}"\s*:\s*)"[^"]*"',
                            re.IGNORECASE,
                        )
                        if pattern.search(content):
                            content = pattern.sub(rf'\1"[REDACTED]"', content)
                            redacted_fields.append(field)

                        pattern_plain = re.compile(
                            rf"({field})\s*[:=]\s*\S+",
                            re.IGNORECASE,
                        )
                        if pattern_plain.search(content):
                            content = pattern_plain.sub(rf"\1: [REDACTED]", content)
                            if field not in redacted_fields:
                                redacted_fields.append(field)

            if needs_truncation:
                content = "\n".join(rows[:row_limit])
                content += f"\n\n[TRUNCATED: showing {row_limit} of {len(rows)} rows for role '{role}']"

            annotations: list[str] = []
            if redacted_fields:
                annotations.append(f"Redacted fields: {', '.join(sorted(redacted_fields))}")
            if needs_truncation:
                annotations.append(f"Truncated to {row_limit} rows (limit for '{role}')")

            footer = "\n---\n[Audit] " + " | ".join(annotations)
            final_content = content + footer

            for block in evt.result.get("content", []):
                if "text" in block:
                    block["text"] = final_content
                    break

            audit_log.append({
                "action": tool_name,
                "role": role,
                "output_check": "TRANSFORMED",
                "redacted_fields": redacted_fields,
                "truncated": needs_truncation,
                "original_rows": len(rows),
                "returned_rows": min(len(rows), row_limit),
            })

        return Transform(
            apply=apply_transform,
            reason="Output modified: sensitive data redacted and/or row limit enforced",
        )


SAMPLE_DB = {
    "employees": [
        {"id": 1, "name": "Alice Smith", "email": "alice@corp.com", "salary": "120000", "department": "Engineering"},
        {"id": 2, "name": "Bob Jones", "email": "bob@corp.com", "salary": "95000", "department": "Marketing"},
        {"id": 3, "name": "Carlos Ruiz", "email": "carlos@corp.com", "salary": "110000", "department": "Engineering"},
        {"id": 4, "name": "Diana Lee", "email": "diana@corp.com", "salary": "130000", "department": "Management"},
        {"id": 5, "name": "Eve Taylor", "email": "eve@corp.com", "salary": "88000", "department": "Support"},
    ],
    "orders": [
        {"id": 101, "customer": "Acme Corp", "amount": 5000, "status": "completed"},
        {"id": 102, "customer": "Globex", "amount": 12000, "status": "pending"},
        {"id": 103, "customer": "Initech", "amount": 3200, "status": "completed"},
    ],
}


@tool
def query_database(sql: str) -> str:
    """Execute a read-only SQL query against the database. Returns results as JSON."""
    sql_lower = sql.lower().strip()

    if "employees" in sql_lower:
        results = SAMPLE_DB["employees"]
    elif "orders" in sql_lower:
        results = SAMPLE_DB["orders"]
    else:
        results = [{"message": "No matching table found"}]

    if "where" in sql_lower and "department" in sql_lower:
        dept_match = re.search(r"department\s*=\s*'(\w+)'", sql_lower)
        if dept_match:
            dept = dept_match.group(1)
            results = [r for r in results if r.get("department", "").lower() == dept]

    return json.dumps(results, indent=2)


@tool
def insert_record(table: str, data: str) -> str:
    """Insert a new record into a database table."""
    return f"INSERT OK: 1 row inserted into '{table}' with data: {data}"


@tool
def delete_record(table: str, record_id: str) -> str:
    """Delete a record from a database table by ID."""
    return f"DELETE OK: record '{record_id}' removed from '{table}'"


@tool
def export_report(report_name: str, format: str = "csv") -> str:
    """Export a database report in the specified format."""
    rows = SAMPLE_DB["employees"]
    if format == "csv":
        header = ",".join(rows[0].keys())
        lines = [header] + [",".join(str(v) for v in r.values()) for r in rows]
        return "\n".join(lines)
    return json.dumps(rows, indent=2)


cedar = DatabaseAuditAuthorization(
    policies=_POLICIES,
    entities=_ENTITIES,
    principal_resolver=lambda state: (
        {"type": "User", "id": state["user_id"]}
        if state.get("user_id")
        else None
    ),
)

ALL_TOOLS = [query_database, insert_record, delete_record, export_report]


def run_scenario(title: str, style: str, prompt: str, invocation_state: dict):
    console.rule(f"[bold {style}]{title}[/]")
    agent = Agent(
        tools=ALL_TOOLS,
        interventions=[cedar],
        callback_handler=lambda **kwargs: None,
    )
    result = agent(prompt, invocation_state=invocation_state)
    console.print(Panel(Markdown(str(result)), border_style=style))
    console.print()


def print_audit_log():
    table = Table(title="Audit Log", show_lines=True)
    table.add_column("User", style="cyan")
    table.add_column("Role", style="magenta")
    table.add_column("Action", style="blue")
    table.add_column("Status", style="bold")
    table.add_column("Details")

    for entry in audit_log:
        user = entry.get("user", "-")
        role = entry.get("role", "-")
        action = entry.get("action", "-")
        status = entry.get("status", entry.get("output_check", "-"))

        details = ""
        if "reason" in entry:
            details = entry["reason"]
        elif "redacted_fields" in entry:
            details = f"Redacted: {entry['redacted_fields']}, Rows: {entry['returned_rows']}/{entry['original_rows']}"
        elif "rows" in entry:
            details = f"Rows: {entry['rows']}"

        status_style = "green" if status in ("PERMITTED", "PASS") else "red" if status == "DENIED" else "yellow"
        table.add_row(user, role, action, f"[{status_style}]{status}[/]", details)

    console.print(table)


if __name__ == "__main__":
    console.print(Panel(
        "[bold]Cedar Database Audit Policy[/]\n"
        "Policy: policies/database_audit/database_audit.cedar\n\n"
        "Hooks:\n"
        "  [cyan]before_tool_call[/]: Cedar policy authorization (role-based access)\n"
        "  [cyan]after_tool_call[/]: Output verification (redact sensitive data, enforce row limits)\n\n"
        "Roles:\n"
        "  - Admin: full access, sees all data\n"
        "  - Analyst: query only, sensitive fields redacted, 100 row limit\n"
        "  - Auditor: query + export, sensitive fields redacted, 500 row limit\n"
        "  - No role: all access denied",
        title="Demo",
    ))
    console.print()

    # Scenario 1: Admin queries employees - full access, no redaction
    run_scenario(
        title="Alice (admin): query employees - PERMITTED, full data",
        style="green",
        prompt="Query all employees from the employees table and delete record id 101 from the orders table",
        invocation_state={"user_id": "alice", "role": "admin"},
    )

    # Scenario 2: Analyst queries employees - permitted but sensitive fields redacted
    run_scenario(
        title="Bob (analyst): query employees - PERMITTED, sensitive data REDACTED",
        style="yellow",
        prompt="Query all employees from the employees table",
        invocation_state={"user_id": "bob", "role": "analyst"},
    )

    # Scenario 3: Analyst tries to insert - DENIED by Cedar policy
    run_scenario(
        title="Bob (analyst): insert record - DENIED (read-only role)",
        style="red",
        prompt="Insert a new employee record with name 'Mallory' into the employees table",
        invocation_state={"user_id": "bob", "role": "analyst"},
    )

    # Scenario 4: Auditor exports report - permitted, sensitive fields redacted
    run_scenario(
        title="Carlos (auditor): export report - PERMITTED, sensitive data REDACTED",
        style="yellow",
        prompt="Export the employees report in csv format",
        invocation_state={"user_id": "carlos", "role": "auditor"},
    )

    # Scenario 5: Auditor tries to delete - DENIED
    run_scenario(
        title="Carlos (auditor): delete record - DENIED (auditor cannot delete)",
        style="red",
        prompt="Delete record id 101 from the orders table",
        invocation_state={"user_id": "carlos", "role": "auditor"},
    )

    # Scenario 6: No identity - all denied
    run_scenario(
        title="Unknown user: query - DENIED (no identity)",
        style="red",
        prompt="Query the orders table",
        invocation_state={},
    )

    console.print()
    print_audit_log()
