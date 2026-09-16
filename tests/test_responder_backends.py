"""Tests for the AI backend selection and the local (OpenAI-compatible) path."""

from __future__ import annotations

import pytest

from protonmail_organizer import config, consent, responder

SAMPLE_MSG = {"Sender": {"Name": "Alice", "Address": "alice@example.com"}, "Subject": "Hi"}


class _Resp:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class TestBackendHelpers:
    def test_resolve_backend_uses_config_default(self, monkeypatch):
        monkeypatch.setattr(config, "AI_BACKEND", "anthropic")
        assert responder._resolve_backend(None) == "anthropic"

    def test_resolve_backend_override_is_normalized(self):
        assert responder._resolve_backend("  LOCAL ") == "local"

    def test_resolve_model_backend_defaults(self, monkeypatch):
        monkeypatch.setattr(config, "AI_MODEL", "")
        assert responder._resolve_model("anthropic", None) == config.DEFAULT_ANTHROPIC_MODEL
        assert responder._resolve_model("local", None) == config.DEFAULT_LOCAL_MODEL

    def test_resolve_model_override_wins(self):
        assert responder._resolve_model("local", "custom-model") == "custom-model"

    def test_resolve_model_env_model_applies_to_both(self, monkeypatch):
        monkeypatch.setattr(config, "AI_MODEL", "shared")
        assert responder._resolve_model("anthropic", None) == "shared"
        assert responder._resolve_model("local", None) == "shared"

    def test_is_local_url(self):
        assert responder._is_local_url("http://localhost:11434/v1") is True
        assert responder._is_local_url("http://127.0.0.1:1234/v1") is True
        assert responder._is_local_url("http://[::1]:8080/v1") is True
        assert responder._is_local_url("https://api.example.com/v1") is False

    def test_backend_is_remote(self, monkeypatch):
        assert responder._backend_is_remote("anthropic") is True
        assert responder._backend_is_remote("unknown") is True
        monkeypatch.setattr(config, "AI_BASE_URL", "http://localhost:11434/v1")
        assert responder._backend_is_remote("local") is False
        monkeypatch.setattr(config, "AI_BASE_URL", "https://gateway.example.com/v1")
        assert responder._backend_is_remote("local") is True

    def test_build_user_message_includes_fields_and_context(self):
        msg = responder._build_user_message(SAMPLE_MSG, "Body text", "be brief")
        assert "alice@example.com" in msg
        assert "Hi" in msg
        assert "Body text" in msg
        assert "be brief" in msg

    def test_build_user_message_without_context(self):
        msg = responder._build_user_message(SAMPLE_MSG, "Body", None)
        assert "Additional instructions" not in msg


class TestUnknownBackend:
    def test_unknown_backend_returns_empty(self, capsys):
        out = responder.generate_draft(SAMPLE_MSG, "body", {}, backend="weird")
        assert out == ""
        assert "Unknown AI backend" in capsys.readouterr().out


class TestLocalBackend:
    @pytest.fixture(autouse=True)
    def _localhost(self, monkeypatch):
        monkeypatch.setattr(config, "AI_BASE_URL", "http://localhost:11434/v1")
        monkeypatch.setattr(config, "AI_API_KEY", "")
        monkeypatch.setattr(config, "AI_MODEL", "")

    def _no_egress(self, monkeypatch):
        def _boom():
            raise AssertionError("egress consent must not be requested for localhost")

        monkeypatch.setattr(consent, "require_ai_egress_ack", _boom)

    def test_posts_openai_chat_completions_and_parses(self, monkeypatch):
        self._no_egress(monkeypatch)
        captured = {}

        def fake_post(url, json=None, headers=None, timeout=None):
            captured.update(url=url, json=json, headers=headers)
            return _Resp({"choices": [{"message": {"content": "  Drafted reply  "}}]})

        monkeypatch.setattr(responder.requests, "post", fake_post)
        out = responder.generate_draft(SAMPLE_MSG, "Question?", {}, backend="local")

        assert out == "Drafted reply"
        assert captured["url"] == "http://localhost:11434/v1/chat/completions"
        assert captured["json"]["model"] == "llama3.1"
        roles = [m["role"] for m in captured["json"]["messages"]]
        assert roles == ["system", "user"]
        assert "Question?" in captured["json"]["messages"][1]["content"]
        assert "Authorization" not in captured["headers"]

    def test_api_key_sets_bearer_header(self, monkeypatch):
        self._no_egress(monkeypatch)
        monkeypatch.setattr(config, "AI_API_KEY", "secret-token")
        captured = {}

        def fake_post(url, json=None, headers=None, timeout=None):
            captured.update(headers=headers)
            return _Resp({"choices": [{"message": {"content": "ok"}}]})

        monkeypatch.setattr(responder.requests, "post", fake_post)
        responder.generate_draft(SAMPLE_MSG, "q", {}, backend="local")
        assert captured["headers"]["Authorization"] == "Bearer secret-token"

    def test_request_error_returns_empty(self, monkeypatch):
        self._no_egress(monkeypatch)

        def boom(*args, **kwargs):
            raise responder.requests.RequestException("connection refused")

        monkeypatch.setattr(responder.requests, "post", boom)
        assert responder.generate_draft(SAMPLE_MSG, "q", {}, backend="local") == ""

    def test_unexpected_response_returns_empty(self, monkeypatch):
        self._no_egress(monkeypatch)
        monkeypatch.setattr(responder.requests, "post", lambda *a, **k: _Resp({"unexpected": True}))
        assert responder.generate_draft(SAMPLE_MSG, "q", {}, backend="local") == ""


class TestLocalBackendRemoteHost:
    def test_remote_base_url_requires_egress_and_aborts_on_decline(self, monkeypatch):
        monkeypatch.setattr(config, "AI_BASE_URL", "https://gateway.example.com/v1")
        calls = []
        monkeypatch.setattr(
            consent,
            "require_ai_egress_ack",
            lambda *a, **k: calls.append(a) is None and False,
        )

        def must_not_post(*args, **kwargs):
            raise AssertionError("must not POST when egress consent is declined")

        monkeypatch.setattr(responder.requests, "post", must_not_post)
        out = responder.generate_draft(SAMPLE_MSG, "q", {}, backend="local")
        assert out == ""
        assert calls == [("gateway.example.com",)]


class TestLocalBackendErrorPrivacy:
    def test_unexpected_response_does_not_leak_content(self, monkeypatch, capsys):
        from protonmail_organizer import config

        monkeypatch.setattr(config, "AI_BASE_URL", "http://localhost:11434/v1")
        monkeypatch.setattr(config, "AI_API_KEY", "")
        monkeypatch.setattr(config, "AI_MODEL", "")
        monkeypatch.setattr(
            responder.requests,
            "post",
            lambda *a, **k: _Resp({"error": "PRIVATE-DRAFT-CONTENT"}),
        )
        assert responder.generate_draft(SAMPLE_MSG, "q", {}, backend="local") == ""
        assert "PRIVATE-DRAFT-CONTENT" not in capsys.readouterr().out
