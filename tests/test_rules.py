"""Tests for the rule matching engine in protonmail_organizer.rules."""

from __future__ import annotations

import time
from datetime import datetime, timedelta

import pytest

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


# ---------------------------------------------------------------------------
# Action safety tests: rule "delete" must be recoverable, moves must file
# into folders, and destructive runs must be confirmed and logged.
# ---------------------------------------------------------------------------

DELETE_RULE_YAML = """\
rules:
  - name: "Delete newsletters"
    conditions:
      sender_contains: "newsletter"
    actions:
      delete: true
"""


@pytest.mark.usefixtures("oplog_file")
class TestApplyActionsSafety:
    """The delete action must move to Trash (recoverable), never hard-delete."""

    def test_delete_action_moves_to_trash_not_permanent(self, mock_client, sample_messages):
        from protonmail_organizer.constants import TRASH
        from protonmail_organizer.rules import _apply_actions

        _apply_actions(mock_client, [sample_messages[0]], {"delete": True}, {})

        mock_client.delete_messages.assert_not_called()
        mock_client.set_label_for_messages.assert_called_once_with(TRASH, ["msg-001"])

    def test_delete_action_records_undoable_operation(
        self, mock_client, sample_messages, monkeypatch
    ):
        from protonmail_organizer import rules
        from protonmail_organizer.constants import INBOX, TRASH

        recorded = []
        monkeypatch.setattr(
            rules, "record_operation", lambda *a, **k: recorded.append((a, k))
        )
        rules._apply_actions(
            mock_client, [sample_messages[0]], {"delete": True}, {}, source_folder=INBOX
        )

        assert len(recorded) == 1
        _args, kwargs = recorded[0]
        assert kwargs.get("added_label") == TRASH
        assert kwargs.get("removed_label") == INBOX

    def test_archive_action_records_undoable_operation(
        self, mock_client, sample_messages, monkeypatch
    ):
        from protonmail_organizer import rules
        from protonmail_organizer.constants import ARCHIVE, INBOX

        recorded = []
        monkeypatch.setattr(
            rules, "record_operation", lambda *a, **k: recorded.append((a, k))
        )
        rules._apply_actions(
            mock_client, [sample_messages[0]], {"archive": True}, {}, source_folder=INBOX
        )

        assert len(recorded) == 1
        _args, kwargs = recorded[0]
        assert kwargs.get("added_label") == ARCHIVE
        assert kwargs.get("removed_label") == INBOX

    def test_move_to_creates_missing_target_as_folder(
        self, mock_client, sample_messages, monkeypatch
    ):
        from protonmail_organizer import labels
        from protonmail_organizer.constants import (
            DEFAULT_LABEL_COLOR,
            LABEL_TYPE_FOLDER,
            LABEL_TYPE_LABEL,
        )
        from protonmail_organizer.rules import _apply_actions

        created = {}

        def fake_create_label(
            client, name, color=DEFAULT_LABEL_COLOR, label_type=LABEL_TYPE_LABEL
        ):
            created["name"] = name
            created["label_type"] = label_type
            return {"ID": "new-folder-id"}

        monkeypatch.setattr(labels, "create_label", fake_create_label)

        _apply_actions(mock_client, [sample_messages[0]], {"move_to": "Receipts"}, {})

        assert created["name"] == "Receipts"
        assert created["label_type"] == LABEL_TYPE_FOLDER


@pytest.mark.usefixtures("oplog_file")
class TestRunRulesConfirmation:
    """Non-dry-run destructive rules must be confirmed before applying."""

    def _setup(self, mock_client, tmp_path, sample_messages):
        rules_file = tmp_path / "rules.yaml"
        rules_file.write_text(DELETE_RULE_YAML)
        mock_client.search_messages_all.return_value = [sample_messages[0]]
        mock_client.get_all_labels.return_value = []
        return str(rules_file)

    def test_declined_confirmation_applies_nothing(
        self, mock_client, sample_messages, monkeypatch, tmp_path
    ):
        from protonmail_organizer import rules

        rules_file = self._setup(mock_client, tmp_path, sample_messages)
        monkeypatch.setattr(rules, "confirm_action", lambda *a, **k: False)

        rules.run_rules(mock_client, rules_file=rules_file)

        mock_client.delete_messages.assert_not_called()
        mock_client.set_label_for_messages.assert_not_called()

    def test_confirmed_delete_moves_to_trash(
        self, mock_client, sample_messages, monkeypatch, tmp_path
    ):
        from protonmail_organizer import rules
        from protonmail_organizer.constants import TRASH

        rules_file = self._setup(mock_client, tmp_path, sample_messages)
        monkeypatch.setattr(rules, "confirm_action", lambda *a, **k: True)
        monkeypatch.setattr(rules, "record_operation", lambda *a, **k: None)

        rules.run_rules(mock_client, rules_file=rules_file)

        mock_client.delete_messages.assert_not_called()
        mock_client.set_label_for_messages.assert_called_once_with(TRASH, ["msg-001"])


class TestRunRulesDryRun:
    """--dry-run must never call any mutating client method."""

    MUTATING_METHODS = (
        "delete_messages",
        "set_label_for_messages",
        "unset_label_for_messages",
        "mark_messages_as_read",
        "create_label",
    )

    def test_dry_run_never_mutates(self, mock_client, sample_messages, tmp_path):
        from protonmail_organizer.rules import run_rules

        rules_file = tmp_path / "rules.yaml"
        rules_file.write_text(DELETE_RULE_YAML)
        mock_client.search_messages_all.return_value = [sample_messages[0]]
        mock_client.get_all_labels.return_value = []

        run_rules(mock_client, rules_file=str(rules_file), dry_run=True)

        for method in self.MUTATING_METHODS:
            assert not getattr(mock_client, method).called, f"{method} called in dry run"


class TestBatchErrorTolerance:
    """A failed batch must not abort later batches or skip the oplog record."""

    @pytest.mark.usefixtures("oplog_file")
    def test_record_survives_partial_batch_failure(self, mock_client, monkeypatch):
        from protonmail_organizer import rules
        from protonmail_organizer.constants import BATCH_SIZE

        monkeypatch.setattr(rules, "BATCH_DELAY_SECONDS", 0)
        recorded = []
        monkeypatch.setattr(rules, "record_operation", lambda *a, **k: recorded.append(a))
        mock_client.set_label_for_messages.side_effect = [Exception("API 500"), {}]

        msgs = [{"ID": f"m{i}", "Sender": {}, "Subject": ""} for i in range(BATCH_SIZE + 1)]
        rules._apply_actions(mock_client, msgs, {"delete": True}, {})

        assert mock_client.set_label_for_messages.call_count == 2
        assert len(recorded) == 1

    def test_batch_operation_continues_after_failure(self, mock_client, monkeypatch):
        from protonmail_organizer import rules
        from protonmail_organizer.constants import BATCH_SIZE

        monkeypatch.setattr(rules, "BATCH_DELAY_SECONDS", 0)
        calls = []

        def flaky(batch):
            calls.append(batch)
            if len(calls) == 1:
                raise Exception("boom")

        ids = [str(i) for i in range(BATCH_SIZE * 2)]
        rules._batch_operation(flaky, ids, "Testing")
        assert len(calls) == 2
