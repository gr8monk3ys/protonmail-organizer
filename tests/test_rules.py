"""Tests for the rule matching engine in protonmail_organizer.rules."""

from __future__ import annotations

import time
from datetime import datetime, timedelta

from protonmail_organizer.rules import _matches_conditions


class TestMatchesConditions:
    """Tests for _matches_conditions (pure matching logic, no API calls)."""

    def _make_msg(
        self,
        sender_address="user@example.com",
        subject="Hello",
        msg_time=None,
        unread=0,
        num_attachments=0,
    ):
        """Helper to build a message dict matching the ProtonMail API format."""
        if msg_time is None:
            msg_time = int(time.time())
        return {
            "Sender": {"Name": "Test", "Address": sender_address},
            "Subject": subject,
            "Time": msg_time,
            "Unread": unread,
            "NumAttachments": num_attachments,
        }

    def test_matches_sender_is(self):
        """sender_is matches exact email address (case-insensitive)."""
        msg = self._make_msg(sender_address="Alice@Example.com")
        assert _matches_conditions(msg, {"sender_is": "alice@example.com"}) is True

    def test_matches_sender_is_no_match(self):
        """sender_is rejects non-matching address."""
        msg = self._make_msg(sender_address="bob@example.com")
        assert _matches_conditions(msg, {"sender_is": "alice@example.com"}) is False

    def test_matches_sender_contains(self):
        """sender_contains matches substring in address (case-insensitive)."""
        msg = self._make_msg(sender_address="newsletter@BigCorp.com")
        assert _matches_conditions(msg, {"sender_contains": "bigcorp"}) is True

    def test_matches_sender_contains_no_match(self):
        """sender_contains rejects when substring is absent."""
        msg = self._make_msg(sender_address="alice@example.com")
        assert _matches_conditions(msg, {"sender_contains": "bigcorp"}) is False

    def test_matches_sender_domain(self):
        """sender_domain matches the domain part of the address (case-insensitive)."""
        msg = self._make_msg(sender_address="noreply@GitHub.com")
        assert _matches_conditions(msg, {"sender_domain": "github.com"}) is True

    def test_matches_sender_domain_no_match(self):
        """sender_domain rejects non-matching domain."""
        msg = self._make_msg(sender_address="noreply@gitlab.com")
        assert _matches_conditions(msg, {"sender_domain": "github.com"}) is False

    def test_matches_subject_contains(self):
        """subject_contains matches substring in subject (case-insensitive)."""
        msg = self._make_msg(subject="Your Weekly Invoice #42")
        assert _matches_conditions(msg, {"subject_contains": "invoice"}) is True

    def test_matches_subject_contains_no_match(self):
        """subject_contains rejects when substring is absent."""
        msg = self._make_msg(subject="Meeting notes")
        assert _matches_conditions(msg, {"subject_contains": "invoice"}) is False

    def test_matches_has_attachment_true(self):
        """has_attachment=True matches messages with attachments."""
        msg = self._make_msg(num_attachments=2)
        assert _matches_conditions(msg, {"has_attachment": True}) is True

    def test_matches_has_attachment_false(self):
        """has_attachment=True rejects messages without attachments."""
        msg = self._make_msg(num_attachments=0)
        assert _matches_conditions(msg, {"has_attachment": True}) is False

    def test_matches_unread_true(self):
        """unread=True matches messages that are unread."""
        msg = self._make_msg(unread=1)
        assert _matches_conditions(msg, {"unread": True}) is True

    def test_matches_unread_false(self):
        """unread=True rejects messages that are read."""
        msg = self._make_msg(unread=0)
        assert _matches_conditions(msg, {"unread": True}) is False

    def test_matches_older_than_days(self):
        """older_than_days matches messages older than N days."""
        old_time = int((datetime.now() - timedelta(days=90)).timestamp())
        msg = self._make_msg(msg_time=old_time)
        assert _matches_conditions(msg, {"older_than_days": 60}) is True

    def test_matches_older_than_days_recent(self):
        """older_than_days rejects messages newer than N days."""
        recent_time = int((datetime.now() - timedelta(days=5)).timestamp())
        msg = self._make_msg(msg_time=recent_time)
        assert _matches_conditions(msg, {"older_than_days": 60}) is False

    def test_matches_multiple_conditions_all_match(self):
        """All conditions must match (AND logic) — all satisfied returns True."""
        msg = self._make_msg(
            sender_address="newsletter@bigcorp.com",
            subject="Weekly digest",
            unread=1,
        )
        conditions = {
            "sender_contains": "newsletter",
            "subject_contains": "digest",
            "unread": True,
        }
        assert _matches_conditions(msg, conditions) is True

    def test_matches_multiple_conditions_partial_fail(self):
        """All conditions must match — one failure returns False."""
        msg = self._make_msg(
            sender_address="newsletter@bigcorp.com",
            subject="Weekly digest",
            unread=0,  # read, not unread
        )
        conditions = {
            "sender_contains": "newsletter",
            "subject_contains": "digest",
            "unread": True,
        }
        assert _matches_conditions(msg, conditions) is False

    def test_no_conditions_matches_all(self):
        """Empty conditions dict matches every message."""
        msg = self._make_msg()
        assert _matches_conditions(msg, {}) is True

    def test_sender_missing_address_field(self):
        """Messages with non-dict Sender still work (returns empty address)."""
        msg = {
            "Sender": "plainstring",
            "Subject": "Test",
            "Time": int(time.time()),
            "Unread": 0,
            "NumAttachments": 0,
        }
        # sender_is should not match since address will be ""
        assert _matches_conditions(msg, {"sender_is": "someone@example.com"}) is False
        # But empty conditions still matches
        assert _matches_conditions(msg, {}) is True


class TestMultiValueConditions:
    """A list condition value matches if ANY of its values match (OR)."""

    def _msg(self, **kw):
        base = {"Sender": {"Address": "a@b.com"}, "Subject": "Hi", "Time": int(time.time())}
        base.update(kw)
        return base

    def test_sender_domain_list_matches_any(self):
        msg = self._msg(Sender={"Address": "noreply@github.com"})
        conds = {"sender_domain": ["gitlab.com", "github.com"]}
        assert _matches_conditions(msg, conds) is True

    def test_sender_domain_list_no_match(self):
        msg = self._msg(Sender={"Address": "noreply@example.com"})
        conds = {"sender_domain": ["gitlab.com", "github.com"]}
        assert _matches_conditions(msg, conds) is False

    def test_sender_is_list(self):
        msg = self._msg(Sender={"Address": "boss@company.com"})
        assert _matches_conditions(msg, {"sender_is": ["a@b.com", "boss@company.com"]}) is True

    def test_subject_contains_list(self):
        msg = self._msg(Subject="Your weekly digest")
        assert _matches_conditions(msg, {"subject_contains": ["invoice", "digest"]}) is True


class TestRegexConditions:
    """sender_matches / subject_matches use case-insensitive regex search."""

    def _msg(self, addr="user@example.com", subject="Hello"):
        return {"Sender": {"Address": addr}, "Subject": subject, "Time": int(time.time())}

    def test_sender_matches_regex(self):
        msg = self._msg(addr="no-reply+123@mail.example.com")
        assert _matches_conditions(msg, {"sender_matches": r"no-?reply"}) is True

    def test_sender_matches_no_match(self):
        msg = self._msg(addr="alice@example.com")
        assert _matches_conditions(msg, {"sender_matches": r"^bob@"}) is False

    def test_subject_matches_regex(self):
        msg = self._msg(subject="Invoice #4821 due")
        assert _matches_conditions(msg, {"subject_matches": r"invoice #\d+"}) is True

    def test_regex_is_case_insensitive(self):
        msg = self._msg(subject="URGENT")
        assert _matches_conditions(msg, {"subject_matches": r"urgent"}) is True
