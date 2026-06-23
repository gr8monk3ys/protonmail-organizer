"""Tests for the Sieve compiler in protonmail_organizer.filters."""

from __future__ import annotations

from protonmail_organizer.filters import (
    _build_sieve_actions,
    _build_sieve_condition,
    compile_rules_to_sieve,
)

# ---------------------------------------------------------------------------
# Condition compilation tests
# ---------------------------------------------------------------------------


class TestBuildSieveCondition:
    """Tests for _build_sieve_condition (individual condition types)."""

    def test_compile_sender_is(self):
        """sender_is condition produces address :is 'from' test."""
        cond_str, needs_flags, needs_mime = _build_sieve_condition(
            {"sender_is": "alice@example.com"}
        )
        assert cond_str == 'address :is "from" "alice@example.com"'
        assert needs_flags is False
        assert needs_mime is False

    def test_compile_sender_contains(self):
        """sender_contains condition produces address :contains 'from' test."""
        cond_str, needs_flags, needs_mime = _build_sieve_condition({"sender_contains": "promo"})
        assert cond_str == 'address :contains "from" "promo"'
        assert needs_flags is False
        assert needs_mime is False

    def test_compile_sender_domain(self):
        """sender_domain condition produces address :matches 'from' '*@domain' test."""
        cond_str, needs_flags, needs_mime = _build_sieve_condition({"sender_domain": "github.com"})
        assert cond_str == 'address :matches "from" "*@github.com"'
        assert needs_flags is False
        assert needs_mime is False

    def test_compile_subject_contains(self):
        """subject_contains condition produces header :contains 'subject' test."""
        cond_str, needs_flags, needs_mime = _build_sieve_condition({"subject_contains": "invoice"})
        assert cond_str == 'header :contains "subject" "invoice"'
        assert needs_flags is False
        assert needs_mime is False

    def test_compile_has_attachment(self):
        """has_attachment=True produces MIME extension test for Content-Disposition."""
        cond_str, needs_flags, needs_mime = _build_sieve_condition({"has_attachment": True})
        assert 'header :mime :anychild :type "Content-Disposition" "attachment"' in cond_str
        assert "not" not in cond_str
        assert needs_mime is True

    def test_compile_has_attachment_false(self):
        """has_attachment=False produces negated MIME extension test."""
        cond_str, needs_flags, needs_mime = _build_sieve_condition({"has_attachment": False})
        assert cond_str.startswith("not ")
        assert needs_mime is True

    def test_compile_unread(self):
        """unread=True produces hasflag test for \\Seen (negated — unread means NOT Seen)."""
        cond_str, needs_flags, needs_mime = _build_sieve_condition({"unread": True})
        assert 'not hasflag "\\\\Seen"' == cond_str
        assert needs_flags is True
        assert needs_mime is False

    def test_compile_unread_false(self):
        """unread=False produces hasflag \\Seen (read messages)."""
        cond_str, needs_flags, needs_mime = _build_sieve_condition({"unread": False})
        assert cond_str == 'hasflag "\\\\Seen"'
        assert needs_flags is True

    def test_compile_multiple_conditions(self):
        """Multiple conditions are wrapped in allof()."""
        cond_str, needs_flags, needs_mime = _build_sieve_condition(
            {"sender_is": "alice@example.com", "subject_contains": "invoice"}
        )
        assert cond_str.startswith("allof (")
        assert 'address :is "from" "alice@example.com"' in cond_str
        assert 'header :contains "subject" "invoice"' in cond_str

    def test_empty_conditions(self):
        """Empty conditions dict produces empty string."""
        cond_str, needs_flags, needs_mime = _build_sieve_condition({})
        assert cond_str == ""
        assert needs_flags is False
        assert needs_mime is False


# ---------------------------------------------------------------------------
# Action compilation tests
# ---------------------------------------------------------------------------


class TestBuildSieveActions:
    """Tests for _build_sieve_actions (individual action types)."""

    def test_compile_move_to_action(self):
        """move_to action produces fileinto statement."""
        lines, needs_fileinto, needs_flags = _build_sieve_actions({"move_to": "Work"})
        assert 'fileinto "Work";' in lines
        assert needs_fileinto is True
        assert needs_flags is False

    def test_compile_mark_read_action(self):
        """mark_read=True produces addflag \\Seen."""
        lines, needs_fileinto, needs_flags = _build_sieve_actions({"mark_read": True})
        assert 'addflag "\\\\Seen";' in lines
        assert needs_flags is True
        assert needs_fileinto is False

    def test_compile_mark_read_false(self):
        """mark_read=False produces no action."""
        lines, needs_fileinto, needs_flags = _build_sieve_actions({"mark_read": False})
        assert lines == []

    def test_compile_delete_action(self):
        """delete=True produces discard statement."""
        lines, needs_fileinto, needs_flags = _build_sieve_actions({"delete": True})
        assert "discard;" in lines
        assert needs_fileinto is False
        assert needs_flags is False

    def test_compile_archive_action(self):
        """archive=True produces fileinto 'Archive'."""
        lines, needs_fileinto, needs_flags = _build_sieve_actions({"archive": True})
        assert 'fileinto "Archive";' in lines
        assert needs_fileinto is True

    def test_compile_star_action(self):
        """star=True produces addflag \\Flagged."""
        lines, needs_fileinto, needs_flags = _build_sieve_actions({"star": True})
        assert 'addflag "\\\\Flagged";' in lines
        assert needs_flags is True

    def test_compile_add_label_action(self):
        """add_label action produces fileinto with the label name."""
        lines, needs_fileinto, needs_flags = _build_sieve_actions({"add_label": "GitHub"})
        assert 'fileinto "GitHub";' in lines
        assert needs_fileinto is True

    def test_empty_actions(self):
        """Empty actions dict produces no lines."""
        lines, needs_fileinto, needs_flags = _build_sieve_actions({})
        assert lines == []
        assert needs_fileinto is False
        assert needs_flags is False


# ---------------------------------------------------------------------------
# Full Sieve compilation tests
# ---------------------------------------------------------------------------


class TestCompileRulesToSieve:
    """Tests for compile_rules_to_sieve (end-to-end compilation)."""

    def test_runtime_only_skipped(self):
        """Rules with only runtime conditions (older_than_days) are skipped entirely."""
        rules = [
            {
                "name": "Old mail only",
                "conditions": {"older_than_days": 30},
                "actions": {"delete": True},
            }
        ]
        result = compile_rules_to_sieve(rules)
        assert result == ""

    def test_require_statement_fileinto(self):
        """Sieve output includes require for fileinto when move_to is used."""
        rules = [
            {
                "name": "Move newsletters",
                "conditions": {"sender_contains": "newsletter"},
                "actions": {"move_to": "Newsletters"},
            }
        ]
        result = compile_rules_to_sieve(rules)
        assert 'require ["fileinto"]' in result
        assert "fileinto" in result

    def test_require_statement_imap4flags(self):
        """Sieve output includes require for imap4flags when mark_read is used."""
        rules = [
            {
                "name": "Mark read",
                "conditions": {"sender_is": "bot@example.com"},
                "actions": {"mark_read": True},
            }
        ]
        result = compile_rules_to_sieve(rules)
        assert '"imap4flags"' in result

    def test_require_statement_mime(self):
        """Sieve output includes require for mime and foreverypart when has_attachment is used."""
        rules = [
            {
                "name": "Attachment rule",
                "conditions": {"has_attachment": True},
                "actions": {"move_to": "Attachments"},
            }
        ]
        result = compile_rules_to_sieve(rules)
        assert '"mime"' in result
        assert '"foreverypart"' in result

    def test_require_statement_combined(self):
        """Sieve output includes all needed require extensions."""
        rules = [
            {
                "name": "Complex rule",
                "conditions": {"has_attachment": True, "unread": True},
                "actions": {"move_to": "Folder", "mark_read": True},
            }
        ]
        result = compile_rules_to_sieve(rules)
        assert '"fileinto"' in result
        assert '"imap4flags"' in result
        assert '"mime"' in result
        assert '"foreverypart"' in result

    def test_empty_rules(self):
        """Empty rules list returns empty string."""
        result = compile_rules_to_sieve([])
        assert result == ""

    def test_rule_name_in_comment(self):
        """The rule name appears as a comment in the generated Sieve."""
        rules = [
            {
                "name": "My Custom Rule",
                "conditions": {"sender_is": "test@example.com"},
                "actions": {"archive": True},
            }
        ]
        result = compile_rules_to_sieve(rules)
        assert "# My Custom Rule" in result

    def test_if_block_structure(self):
        """The compiled Sieve has proper if-block structure."""
        rules = [
            {
                "name": "Test rule",
                "conditions": {"sender_is": "test@test.com"},
                "actions": {"delete": True},
            }
        ]
        result = compile_rules_to_sieve(rules)
        assert "if " in result
        assert "{" in result
        assert "}" in result
        assert "discard;" in result

    def test_partial_runtime_conditions(self):
        """Rules with both runtime and sieve conditions compile the sieve-compatible parts."""
        rules = [
            {
                "name": "Partial runtime",
                "conditions": {
                    "sender_contains": "promo",
                    "older_than_days": 30,
                },
                "actions": {"archive": True},
            }
        ]
        result = compile_rules_to_sieve(rules)
        # The sieve-compatible part (sender_contains) should still compile
        assert 'address :contains "from" "promo"' in result
        assert 'fileinto "Archive"' in result

    def test_multiple_rules_output(self, sample_rules):
        """Multiple rules produce multiple if-blocks (minus runtime-only ones)."""
        result = compile_rules_to_sieve(sample_rules)
        # The sample_rules fixture has 4 rules:
        # 1. sender_contains newsletter -> archive (compilable)
        # 2. sender_domain github.com -> add_label + mark_read (compilable)
        # 3. sender_is boss@company.com -> star (compilable)
        # 4. older_than_days + unread -> delete (partial — unread part compiles)
        # Count if-blocks
        assert result.count("if ") >= 3
