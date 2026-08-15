"""Tests for watch-mode polling in protonmail_organizer.watch."""

from __future__ import annotations


def _newsletter(msg_id):
    return {
        "ID": msg_id,
        "Subject": "Weekly Newsletter",
        "Sender": {"Name": "News Bot", "Address": "newsletter@example.com"},
        "Time": 1700000000,
        "Unread": 1,
        "NumAttachments": 0,
    }


DELETE_RULE = {
    "name": "Delete newsletters",
    "conditions": {"sender_contains": "newsletter"},
    "actions": {"delete": True},
}


class TestPollCycle:
    def test_groups_new_messages_per_rule(self, mock_client, monkeypatch):
        """One _apply_actions call per rule per cycle, not per message.

        Per-message calls would write one oplog entry each, flooding the
        50-entry undo ring during a busy watch session.
        """
        from protonmail_organizer import watch

        calls = []
        monkeypatch.setattr(
            watch,
            "_apply_actions",
            lambda client, msgs, actions, label_map, **kw: calls.append(list(msgs)),
        )
        mock_client.search_messages.return_value = [_newsletter("w1"), _newsletter("w2")]

        watch._poll_cycle(mock_client, [DELETE_RULE], {}, set(), [])

        assert len(calls) == 1
        assert [m["ID"] for m in calls[0]] == ["w1", "w2"]

    def test_seen_messages_are_not_reprocessed(self, mock_client, monkeypatch):
        from protonmail_organizer import watch

        calls = []
        monkeypatch.setattr(
            watch,
            "_apply_actions",
            lambda client, msgs, actions, label_map, **kw: calls.append(list(msgs)),
        )
        mock_client.search_messages.return_value = [_newsletter("w1")]
        seen = {"w1"}

        watch._poll_cycle(mock_client, [DELETE_RULE], {}, seen, [])

        assert calls == []
