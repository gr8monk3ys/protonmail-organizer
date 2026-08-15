"""Tests for newsletter detection helpers in protonmail_organizer.cleanup."""

from __future__ import annotations

from protonmail_organizer.cleanup import _is_newsletter


class TestIsNewsletter:
    """Tests for _is_newsletter heuristic detection."""

    def test_newsletter_sender_pattern_noreply(self):
        """noreply@ sender is detected as newsletter."""
        msg = {
            "Sender": {"Name": "Service", "Address": "noreply@service.com"},
            "Subject": "Your account update",
        }
        assert _is_newsletter(msg) is True

    def test_newsletter_sender_pattern_no_reply(self):
        """no-reply@ sender is detected as newsletter."""
        msg = {
            "Sender": {"Name": "Service", "Address": "no-reply@example.com"},
            "Subject": "New features available",
        }
        assert _is_newsletter(msg) is True

    def test_newsletter_sender_pattern_newsletter(self):
        """newsletter@ sender is detected as newsletter."""
        msg = {
            "Sender": {"Name": "Weekly Update", "Address": "newsletter@digest.io"},
            "Subject": "This week in tech",
        }
        assert _is_newsletter(msg) is True

    def test_newsletter_sender_pattern_digest(self):
        """digest@ sender is detected as newsletter."""
        msg = {
            "Sender": {"Name": "Daily Digest", "Address": "digest@news.com"},
            "Subject": "Your daily reading",
        }
        assert _is_newsletter(msg) is True

    def test_newsletter_sender_pattern_notifications(self):
        """notifications@ sender is detected as newsletter."""
        msg = {
            "Sender": {"Name": "Alerts", "Address": "notifications@app.io"},
            "Subject": "Activity summary",
        }
        assert _is_newsletter(msg) is True

    def test_newsletter_sender_pattern_marketing(self):
        """marketing@ sender is detected as newsletter."""
        msg = {
            "Sender": {"Name": "Promo", "Address": "marketing@brand.com"},
            "Subject": "Special offer for you",
        }
        assert _is_newsletter(msg) is True

    def test_newsletter_sender_pattern_mailchimp(self):
        """mailchimp in sender domain is detected as newsletter."""
        msg = {
            "Sender": {"Name": "Newsletter", "Address": "bounce@mail.mailchimp.com"},
            "Subject": "Monthly update",
        }
        assert _is_newsletter(msg) is True

    def test_newsletter_subject_pattern_newsletter(self):
        """Subject containing 'newsletter' is detected as newsletter."""
        msg = {
            "Sender": {"Name": "Alice", "Address": "alice@company.com"},
            "Subject": "Company Newsletter - January",
        }
        assert _is_newsletter(msg) is True

    def test_newsletter_subject_pattern_digest(self):
        """Subject containing 'digest' is detected as newsletter."""
        msg = {
            "Sender": {"Name": "Bob", "Address": "bob@company.com"},
            "Subject": "Your weekly digest",
        }
        assert _is_newsletter(msg) is True

    def test_newsletter_subject_pattern_weekly_update(self):
        """Subject matching 'weekly.*update' is detected as newsletter."""
        msg = {
            "Sender": {"Name": "Team", "Address": "team@company.com"},
            "Subject": "Weekly status update",
        }
        assert _is_newsletter(msg) is True

    def test_newsletter_subject_pattern_unsubscribe(self):
        """Subject containing 'unsubscribe' is detected as newsletter."""
        msg = {
            "Sender": {"Name": "Service", "Address": "service@example.com"},
            "Subject": "Click to unsubscribe from updates",
        }
        assert _is_newsletter(msg) is True

    def test_not_newsletter_personal(self):
        """Personal email from a person is not detected as newsletter."""
        msg = {
            "Sender": {"Name": "Alice Smith", "Address": "alice@example.com"},
            "Subject": "Re: Lunch tomorrow?",
        }
        assert _is_newsletter(msg) is False

    def test_not_newsletter_work(self):
        """Work email with normal sender/subject is not detected as newsletter."""
        msg = {
            "Sender": {"Name": "Bob Jones", "Address": "bob@company.com"},
            "Subject": "Q4 Budget Review",
        }
        assert _is_newsletter(msg) is False

    def test_newsletter_case_insensitive_sender(self):
        """Sender pattern matching is case-insensitive."""
        msg = {
            "Sender": {"Name": "Service", "Address": "NoReply@Service.COM"},
            "Subject": "Account notice",
        }
        assert _is_newsletter(msg) is True

    def test_newsletter_case_insensitive_subject(self):
        """Subject pattern matching is case-insensitive."""
        msg = {
            "Sender": {"Name": "Team", "Address": "team@example.com"},
            "Subject": "Your Monthly NEWSLETTER",
        }
        assert _is_newsletter(msg) is True

    def test_newsletter_non_dict_sender(self):
        """Handles non-dict Sender gracefully (falls back to empty address)."""
        msg = {
            "Sender": "plainstring",
            "Subject": "newsletter digest",
        }
        # Subject still matches
        assert _is_newsletter(msg) is True

    def test_newsletter_empty_fields(self):
        """Message with empty sender and subject is not a newsletter."""
        msg = {
            "Sender": {"Name": "", "Address": ""},
            "Subject": "",
        }
        assert _is_newsletter(msg) is False


class TestAssumeYes:
    """--yes must bypass the prompt on permanent-capable cleanup commands."""

    def test_delete_old_assume_yes_skips_prompt(
        self, mock_client, sample_messages, monkeypatch, oplog_file
    ):
        from protonmail_organizer import cleanup

        mock_client.search_messages_all.return_value = sample_messages[:2]
        monkeypatch.setattr(cleanup, "BATCH_DELAY_SECONDS", 0)

        def no_prompt(*a, **k):
            raise AssertionError("confirm_action must not be called with assume_yes")

        monkeypatch.setattr(cleanup, "confirm_action", no_prompt)
        cleanup.delete_old_messages(mock_client, days=30, assume_yes=True)
        mock_client.set_label_for_messages.assert_called()

    def test_newsletters_assume_yes_skips_prompt(
        self, mock_client, sample_messages, monkeypatch, oplog_file
    ):
        from protonmail_organizer import cleanup

        mock_client.search_messages_all.return_value = [sample_messages[0]]
        monkeypatch.setattr(cleanup, "BATCH_DELAY_SECONDS", 0)

        def no_prompt(*a, **k):
            raise AssertionError("confirm_action must not be called with assume_yes")

        monkeypatch.setattr(cleanup, "confirm_action", no_prompt)
        cleanup.handle_newsletters(mock_client, do_delete=True, assume_yes=True)
        mock_client.set_label_for_messages.assert_called()
