"""Tests for the one-time risk-acknowledgment logic in protonmail_organizer.consent."""

from __future__ import annotations

import json

import pytest

from protonmail_organizer import consent


@pytest.fixture
def consent_file(tmp_path, monkeypatch):
    """Point CONSENT_FILE at a temp path and default to non-interactive, no env."""
    f = tmp_path / "consent.json"
    monkeypatch.setattr(consent, "CONSENT_FILE", f)
    monkeypatch.delenv(consent.ACCEPT_ENV, raising=False)
    monkeypatch.setattr(consent, "_is_interactive", lambda: False)
    return f


class TestPersistence:
    def test_no_consent_initially(self, consent_file):
        assert consent.has_consent(consent.UNOFFICIAL_USE) is False

    def test_record_then_has_consent(self, consent_file):
        consent.record_consent(consent.UNOFFICIAL_USE)
        assert consent.has_consent(consent.UNOFFICIAL_USE) is True
        assert json.loads(consent_file.read_text())[consent.UNOFFICIAL_USE] is True

    def test_corrupt_file_is_treated_as_empty(self, consent_file):
        consent_file.write_text("{not json")
        assert consent.has_consent(consent.UNOFFICIAL_USE) is False


class TestRequireConsent:
    def test_returns_true_when_already_granted_without_prompting(self, consent_file):
        consent.record_consent(consent.AI_EGRESS)
        # _is_interactive is False and no env set; must still return True.
        assert consent.require_consent(consent.AI_EGRESS, "d", "p") is True

    def test_env_override_records_and_grants(self, consent_file, monkeypatch):
        monkeypatch.setenv(consent.ACCEPT_ENV, "1")
        assert consent.require_consent(consent.UNOFFICIAL_USE, "d", "p") is True
        assert consent.has_consent(consent.UNOFFICIAL_USE) is True

    def test_non_interactive_without_env_declines(self, consent_file):
        assert consent.require_consent(consent.UNOFFICIAL_USE, "d", "p") is False
        assert consent.has_consent(consent.UNOFFICIAL_USE) is False

    def test_interactive_yes_grants_and_persists(self, consent_file, monkeypatch):
        monkeypatch.setattr(consent, "_is_interactive", lambda: True)
        monkeypatch.setattr(consent.click, "confirm", lambda *a, **k: True)
        assert consent.require_consent("custom", "d", "p") is True
        assert consent.has_consent("custom") is True

    def test_interactive_no_declines_and_does_not_persist(self, consent_file, monkeypatch):
        monkeypatch.setattr(consent, "_is_interactive", lambda: True)
        monkeypatch.setattr(consent.click, "confirm", lambda *a, **k: False)
        assert consent.require_consent("custom", "d", "p") is False
        assert consent.has_consent("custom") is False


class TestWrappers:
    def test_unofficial_use_wrapper_uses_its_key(self, consent_file, monkeypatch):
        monkeypatch.setenv(consent.ACCEPT_ENV, "1")
        assert consent.require_unofficial_use_ack() is True
        assert consent.has_consent(consent.UNOFFICIAL_USE) is True

    def test_ai_egress_wrapper_uses_its_key(self, consent_file, monkeypatch):
        monkeypatch.setenv(consent.AI_EGRESS_ENV, "1")
        assert consent.require_ai_egress_ack() is True
        assert consent.has_consent(consent.AI_EGRESS) is True


class TestEgressConsentIsolation:
    """AI egress needs its own opt-in, keyed to where the data actually goes."""

    def test_accept_risks_env_does_not_cover_ai_egress(self, consent_file, monkeypatch):
        monkeypatch.setenv(consent.ACCEPT_ENV, "1")
        assert consent.require_ai_egress_ack() is False

    def test_dedicated_env_grants_ai_egress(self, consent_file, monkeypatch):
        monkeypatch.setenv(consent.AI_EGRESS_ENV, "1")
        assert consent.require_ai_egress_ack() is True

    def test_remote_destination_gets_its_own_key(self, consent_file, monkeypatch):
        monkeypatch.setenv(consent.AI_EGRESS_ENV, "1")
        assert consent.require_ai_egress_ack("gateway.example.com") is True
        assert consent.has_consent("ai_egress:gateway.example.com")
        # An ack for one gateway must not silently cover Anthropic or others.
        assert not consent.has_consent(consent.AI_EGRESS)

    def test_details_name_the_destination(self, consent_file, monkeypatch, capsys):
        monkeypatch.setenv(consent.AI_EGRESS_ENV, "1")
        consent.require_ai_egress_ack("gateway.example.com")
        assert "gateway.example.com" in capsys.readouterr().out

    def test_consent_file_is_owner_only(self, consent_file, monkeypatch):
        monkeypatch.setenv(consent.ACCEPT_ENV, "1")
        consent.require_unofficial_use_ack()
        assert (consent_file.stat().st_mode & 0o777) == 0o600
