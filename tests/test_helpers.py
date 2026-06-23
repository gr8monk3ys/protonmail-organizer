"""Tests for small pure helpers across display, rule_analytics, and templates."""

from __future__ import annotations

import time
from datetime import datetime
from types import SimpleNamespace

from protonmail_organizer.display import (
    _format_time,
    _get_field,
    _get_sender,
    debug_enabled,
)
from protonmail_organizer.rule_analytics import _extract_domain, _extract_sender
from protonmail_organizer.templates import _validate_name


class TestGetSender:
    def test_dict_prefers_name(self):
        msg = {"Sender": {"Name": "Alice", "Address": "alice@x.com"}}
        assert _get_sender(msg) == "Alice"

    def test_dict_falls_back_to_address(self):
        msg = {"Sender": {"Name": "", "Address": "alice@x.com"}}
        assert _get_sender(msg) == "alice@x.com"

    def test_object_sender(self):
        msg = SimpleNamespace(sender=SimpleNamespace(name="Bob", address="b@x.com"))
        assert _get_sender(msg) == "Bob"

    def test_missing_sender(self):
        assert _get_sender(SimpleNamespace(sender=None)) == "?"


class TestGetField:
    def test_dict_lookup(self):
        assert _get_field({"Subject": "Hi"}, "Subject", "subject", "?") == "Hi"

    def test_object_lookup(self):
        assert _get_field(SimpleNamespace(subject="Hi"), "Subject", "subject", "?") == "Hi"

    def test_default(self):
        assert _get_field({}, "Subject", "subject", "fallback") == "fallback"


class TestFormatTime:
    def test_empty_timestamp(self):
        assert _format_time(0) == ""
        assert _format_time(None) == ""

    def test_today_shows_time(self):
        result = _format_time(int(time.time()))
        assert ":" in result  # HH:MM

    def test_previous_year_shows_iso_date(self):
        past = int(datetime(2020, 1, 15, 9, 0).timestamp())
        assert _format_time(past) == "2020-01-15"


class TestExtractSenderDomain:
    def test_extract_sender_lowercased(self):
        assert _extract_sender({"Sender": {"Address": "Bob@Example.COM"}}) == "bob@example.com"

    def test_extract_sender_non_dict(self):
        assert _extract_sender({"Sender": "weird"}) == ""

    def test_extract_domain(self):
        assert _extract_domain("alice@example.com") == "example.com"

    def test_extract_domain_no_at(self):
        assert _extract_domain("not-an-email") == ""


class TestDebugEnabled:
    def test_off_by_default(self, monkeypatch):
        monkeypatch.delenv("PMO_DEBUG", raising=False)
        assert debug_enabled() is False

    def test_on_when_set_to_one(self, monkeypatch):
        monkeypatch.setenv("PMO_DEBUG", "1")
        assert debug_enabled() is True

    def test_off_for_other_values(self, monkeypatch):
        monkeypatch.setenv("PMO_DEBUG", "true")
        assert debug_enabled() is False


class TestValidateTemplateName:
    def test_valid_name(self):
        assert _validate_name("thanks-reply") is None

    def test_empty_name(self):
        assert _validate_name("") is not None

    def test_name_with_spaces_invalid(self):
        assert _validate_name("my template") is not None

    def test_name_with_slash_invalid(self):
        assert _validate_name("a/b") is not None
