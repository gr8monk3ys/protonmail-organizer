"""Shared fixtures for ProtonMail Organizer tests."""

from __future__ import annotations

import os
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def mock_client():
    """A MagicMock that mimics ProtonMailExt with common methods stubbed."""
    client = MagicMock()

    # Stub common read methods to return empty defaults
    client.get_filters.return_value = []
    client.get_all_labels.return_value = []
    client.get_labels_by_type_id.return_value = []
    client.search_messages.return_value = []
    client.search_messages_all.return_value = []
    client.read_message.return_value = MagicMock(body="")
    client.get_message.return_value = {}
    client.create_filter.return_value = {"ID": "filter-123"}
    client.create_label.return_value = {"ID": "label-456", "Name": "TestLabel"}
    client.delete_filter.return_value = {}
    client.delete_label.return_value = {}
    client.delete_messages.return_value = {}
    client.mark_messages_as_read.return_value = {}
    client.set_label_for_messages.return_value = {}
    client.unset_label_for_messages.return_value = {}

    return client


@pytest.fixture
def sample_messages():
    """List of message dicts matching the ProtonMail API format."""
    return [
        {
            "ID": "msg-001",
            "Subject": "Weekly Newsletter",
            "Sender": {"Name": "News Bot", "Address": "newsletter@example.com"},
            "Time": 1700000000,
            "Unread": 1,
            "NumAttachments": 0,
            "LabelIDs": ["0"],
        },
        {
            "ID": "msg-002",
            "Subject": "Meeting Tomorrow",
            "Sender": {"Name": "Alice", "Address": "alice@company.com"},
            "Time": 1700100000,
            "Unread": 0,
            "NumAttachments": 1,
            "LabelIDs": ["0"],
        },
        {
            "ID": "msg-003",
            "Subject": "GitHub notification",
            "Sender": {"Name": "GitHub", "Address": "noreply@github.com"},
            "Time": 1700200000,
            "Unread": 1,
            "NumAttachments": 0,
            "LabelIDs": ["0"],
        },
        {
            "ID": "msg-004",
            "Subject": "Your monthly digest",
            "Sender": {"Name": "Digest", "Address": "digest@updates.io"},
            "Time": 1600000000,  # Much older message
            "Unread": 1,
            "NumAttachments": 0,
            "LabelIDs": ["0"],
        },
        {
            "ID": "msg-005",
            "Subject": "Important contract",
            "Sender": {"Name": "Boss", "Address": "boss@company.com"},
            "Time": 1700300000,
            "Unread": 0,
            "NumAttachments": 2,
            "LabelIDs": ["0"],
        },
    ]


@pytest.fixture
def sample_rules():
    """List of rule dicts matching the YAML format used by the rule engine."""
    return [
        {
            "name": "Archive newsletters",
            "conditions": {
                "sender_contains": "newsletter",
            },
            "actions": {
                "archive": True,
            },
        },
        {
            "name": "Label GitHub",
            "conditions": {
                "sender_domain": "github.com",
            },
            "actions": {
                "add_label": "GitHub",
                "mark_read": True,
            },
        },
        {
            "name": "Star boss emails",
            "conditions": {
                "sender_is": "boss@company.com",
            },
            "actions": {
                "star": True,
            },
        },
        {
            "name": "Delete old unread",
            "conditions": {
                "older_than_days": 60,
                "unread": True,
            },
            "actions": {
                "delete": True,
            },
        },
    ]


@pytest.fixture
def tmp_config_dir(tmp_path):
    """Temporary directory for config files, patching PMO_CONFIG_DIR."""
    config_dir = tmp_path / "pmo-config"
    config_dir.mkdir()
    return config_dir
