"""Tests for the operation log / undo in protonmail_organizer.oplog."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from protonmail_organizer import oplog
from protonmail_organizer.constants import ARCHIVE, INBOX, TRASH


@pytest.fixture
def oplog_file(tmp_path, monkeypatch):
    """Redirect the operation log to a temp file."""
    path = tmp_path / "operations.json"
    monkeypatch.setattr(oplog, "OPLOG_FILE", path)
    monkeypatch.setattr(oplog, "ensure_config_dir", lambda: tmp_path)
    return path


class TestRecordAndLoad:
    def test_record_persists(self, oplog_file):
        oplog.record_operation("Archived 2", ["a", "b"], added_label=ARCHIVE, removed_label=INBOX)
        ops = oplog._load()
        assert len(ops) == 1
        assert ops[0]["description"] == "Archived 2"
        assert ops[0]["added_label"] == ARCHIVE
        assert ops[0]["removed_label"] == INBOX
        assert ops[0]["permanent"] is False

    def test_record_empty_ids_is_noop(self, oplog_file):
        oplog.record_operation("nothing", [])
        assert oplog._load() == []

    def test_log_is_capped(self, oplog_file):
        for i in range(oplog.MAX_OPS + 10):
            oplog.record_operation(f"op {i}", [str(i)], added_label=TRASH)
        assert len(oplog._load()) == oplog.MAX_OPS


class TestUndo:
    def test_undo_reverses_archive(self, oplog_file):
        client = MagicMock()
        oplog.record_operation("Archived", ["a", "b"], added_label=ARCHIVE, removed_label=INBOX)

        oplog.undo_last(client)

        # Restores the removed label (Inbox) and strips the added one (Archive).
        client.set_label_for_messages.assert_called_once_with(INBOX, ["a", "b"])
        client.unset_label_for_messages.assert_called_once_with(ARCHIVE, ["a", "b"])
        # The op is consumed.
        assert oplog._load() == []

    def test_undo_reverses_trash(self, oplog_file):
        client = MagicMock()
        oplog.record_operation("Trashed", ["x"], added_label=TRASH, removed_label=INBOX)

        oplog.undo_last(client)

        client.set_label_for_messages.assert_called_once_with(INBOX, ["x"])
        client.unset_label_for_messages.assert_called_once_with(TRASH, ["x"])

    def test_undo_refuses_permanent(self, oplog_file):
        client = MagicMock()
        oplog.record_operation("Permanently deleted", ["a"], permanent=True)

        oplog.undo_last(client)

        client.set_label_for_messages.assert_not_called()
        client.unset_label_for_messages.assert_not_called()
        # The permanent op stays in the log (audit trail, not consumed).
        assert len(oplog._load()) == 1

    def test_undo_empty_log(self, oplog_file):
        client = MagicMock()
        oplog.undo_last(client)
        client.set_label_for_messages.assert_not_called()

    def test_undo_only_added_label(self, oplog_file):
        """An add_label-style op (no removed_label) just strips the added label."""
        client = MagicMock()
        oplog.record_operation("Labeled", ["a"], added_label="99")

        oplog.undo_last(client)

        client.unset_label_for_messages.assert_called_once_with("99", ["a"])
        client.set_label_for_messages.assert_not_called()
