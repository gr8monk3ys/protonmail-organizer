"""Tests for reply threading and quoting helpers in protonmail_organizer.responder."""

from __future__ import annotations

from types import SimpleNamespace

from protonmail_organizer.responder import (
    _extract_external_id,
    _format_reply_html,
)


def _make_msg(name="Alice", address="alice@example.com", time=1700000000, external_id="<abc@mail>"):
    """Build a minimal message object resembling the protonmail Message model."""
    sender = SimpleNamespace(name=name, address=address)
    extra = {"ExternalID": external_id} if external_id is not None else {}
    return SimpleNamespace(sender=sender, subject="Hello", time=time, body="", extra=extra)


class TestExtractExternalId:
    """Tests for _extract_external_id."""

    def test_extracts_message_id_from_extra(self):
        msg = _make_msg(external_id="<msg-123@proton.me>")
        assert _extract_external_id(msg) == "<msg-123@proton.me>"

    def test_returns_none_when_absent(self):
        msg = _make_msg(external_id=None)
        assert _extract_external_id(msg) is None

    def test_returns_none_when_no_extra(self):
        msg = SimpleNamespace(sender=None)
        assert _extract_external_id(msg) is None


class TestFormatReplyHtml:
    """Tests for _format_reply_html (threaded, quoted HTML body)."""

    def test_draft_newlines_become_br(self):
        html = _format_reply_html("Line one\nLine two", _make_msg(), "")
        assert "Line one<br>" in html
        assert "Line two" in html

    def test_quotes_original_in_blockquote(self):
        html = _format_reply_html("My reply", _make_msg(), "Original question here")
        assert "<blockquote" in html
        assert "Original question here" in html

    def test_includes_attribution_line(self):
        html = _format_reply_html("Reply", _make_msg(name="Bob", address="bob@x.com"), "hi")
        assert "wrote:" in html
        assert "bob@x.com" in html

    def test_escapes_html_in_draft_and_original(self):
        html = _format_reply_html("<script>alert(1)</script>", _make_msg(), "<b>bold</b>")
        # Raw tags from user/original content must be escaped, not emitted as HTML.
        assert "<script>" not in html
        assert "&lt;script&gt;" in html
        assert "&lt;b&gt;bold&lt;/b&gt;" in html

    def test_quoted_original_is_truncated(self):
        long_body = "x" * 9000
        html = _format_reply_html("Reply", _make_msg(), long_body)
        # _truncate caps the quoted original at 5000 chars (+ ellipsis).
        assert "..." in html
        assert ("x" * 5001) not in html

    def test_handles_missing_sender_gracefully(self):
        msg = SimpleNamespace(sender=None, subject="", time=0, extra={})
        html = _format_reply_html("Reply", msg, "orig")
        assert "the sender" in html
