"""Tests for style analysis helpers in protonmail_organizer.style_profile."""

from __future__ import annotations

from collections import Counter

from protonmail_organizer.style_profile import (
    _assess_formality,
    _describe_punctuation,
    _extract_greeting,
    _extract_signoff,
    _strip_html,
    _truncate_to_sentences,
)

# ---------------------------------------------------------------------------
# HTML stripping
# ---------------------------------------------------------------------------


class TestStripHtml:
    """Tests for _strip_html helper."""

    def test_strip_html(self):
        """Removes HTML tags and decodes common entities."""
        html = "<p>Hello &amp; <b>world</b>!</p>"
        result = _strip_html(html)
        assert "<p>" not in result
        assert "<b>" not in result
        assert "Hello & world!" in result

    def test_strip_br_to_newline(self):
        """Converts <br> tags to newlines."""
        html = "Line one<br>Line two<br/>Line three"
        result = _strip_html(html)
        assert "Line one\nLine two\nLine three" == result

    def test_strip_entities(self):
        """Decodes HTML entities: &lt; &gt; &nbsp; &quot;."""
        html = "&lt;tag&gt; &nbsp; &quot;quoted&quot;"
        result = _strip_html(html)
        assert "<tag>" in result
        assert '"quoted"' in result

    def test_strip_empty(self):
        """Empty string returns empty string."""
        assert _strip_html("") == ""

    def test_strip_plain_text(self):
        """Plain text without HTML passes through unchanged."""
        text = "Just plain text, nothing special."
        assert _strip_html(text) == text


# ---------------------------------------------------------------------------
# Greeting extraction
# ---------------------------------------------------------------------------


class TestExtractGreeting:
    """Tests for _extract_greeting pattern matching."""

    def test_extract_greeting_hey(self):
        """Detects 'Hey' greeting."""
        assert _extract_greeting("Hey there!") == "Hey"

    def test_extract_greeting_hi(self):
        """Detects 'Hi' greeting."""
        assert _extract_greeting("Hi team,") == "Hi"

    def test_extract_greeting_hello(self):
        """Detects 'Hello' greeting."""
        assert _extract_greeting("Hello everyone") == "Hello"

    def test_extract_greeting_dear(self):
        """Detects 'Dear' greeting."""
        assert _extract_greeting("Dear Mr. Smith,") == "Dear"

    def test_extract_greeting_good_morning(self):
        """Detects 'Good morning' greeting."""
        assert _extract_greeting("Good morning all,") == "Good morning"

    def test_extract_greeting_none(self):
        """Returns None when no greeting pattern matches."""
        assert _extract_greeting("I wanted to follow up on...") is None

    def test_extract_greeting_case_insensitive(self):
        """Greeting detection is case-insensitive."""
        assert _extract_greeting("HEY Bob") == "Hey"

    def test_extract_greeting_yo(self):
        """Detects 'Yo' greeting."""
        assert _extract_greeting("Yo what's happening") == "Yo"


# ---------------------------------------------------------------------------
# Sign-off extraction
# ---------------------------------------------------------------------------


class TestExtractSignoff:
    """Tests for _extract_signoff pattern matching."""

    def test_extract_signoff_best(self):
        """Detects 'Best' sign-off."""
        assert _extract_signoff(["Best,", "Alice"]) == "Best"

    def test_extract_signoff_thanks(self):
        """Detects 'Thanks' sign-off."""
        assert _extract_signoff(["Thanks,", "Bob"]) == "Thanks"

    def test_extract_signoff_cheers(self):
        """Detects 'Cheers' sign-off."""
        assert _extract_signoff(["Cheers,", "Charlie"]) == "Cheers"

    def test_extract_signoff_regards(self):
        """Detects 'Regards' sign-off."""
        assert _extract_signoff(["Regards,", "Dana"]) == "Regards"

    def test_extract_signoff_sincerely(self):
        """Detects 'Sincerely' sign-off."""
        assert _extract_signoff(["Sincerely,", "Eve"]) == "Sincerely"

    def test_extract_signoff_none(self):
        """Returns None when no sign-off pattern matches."""
        assert _extract_signoff(["Alice Smith"]) is None

    def test_extract_signoff_skips_sent_from(self):
        """'Sent from' device signatures return None, not a sign-off."""
        result = _extract_signoff(["Sent from my iPhone"])
        assert result is None

    def test_extract_signoff_empty_lines(self):
        """Skips empty lines when searching for sign-off."""
        assert _extract_signoff(["Thanks,", "", ""]) == "Thanks"


# ---------------------------------------------------------------------------
# Truncation
# ---------------------------------------------------------------------------


class TestTruncateToSentences:
    """Tests for _truncate_to_sentences helper."""

    def test_truncate_to_sentences(self):
        """Respects sentence count limit."""
        text = "First sentence. Second sentence. Third sentence. Fourth sentence."
        result = _truncate_to_sentences(text, 2)
        assert "First sentence." in result
        assert "Second sentence." in result
        assert "Third" not in result

    def test_truncate_short_text(self):
        """Short text with fewer sentences than the limit is returned as-is."""
        text = "Just one sentence."
        result = _truncate_to_sentences(text, 3)
        assert result == "Just one sentence."

    def test_truncate_200_char_cap(self):
        """Result is capped at 200 characters with '...' appended."""
        text = "A" * 100 + ". " + "B" * 100 + ". " + "C" * 100 + "."
        result = _truncate_to_sentences(text, 10)
        assert len(result) <= 203  # 200 + "..."
        assert result.endswith("...")

    def test_truncate_preserves_full_sentences(self):
        """When within limits, full sentences are preserved."""
        text = "Hello there. How are you? I am fine!"
        result = _truncate_to_sentences(text, 3)
        assert result == text


# ---------------------------------------------------------------------------
# Formality assessment
# ---------------------------------------------------------------------------


class TestAssessFormality:
    """Tests for _assess_formality style classification."""

    def test_assess_formality_formal(self):
        """Predominantly formal greetings/signoffs yield 'formal'."""
        greetings = Counter({"Dear": 10, "Hello": 5})
        signoffs = Counter({"Sincerely": 8, "Regards": 5})
        result = _assess_formality(greetings, signoffs, avg_length=120, excl_ratio=0.1)
        assert result == "formal"

    def test_assess_formality_casual(self):
        """Predominantly casual greetings/signoffs yield 'casual'."""
        greetings = Counter({"Hey": 10, "Yo": 5})
        signoffs = Counter({"Cheers": 8, "Talk soon": 5})
        result = _assess_formality(greetings, signoffs, avg_length=20, excl_ratio=0.5)
        assert result == "casual"

    def test_assess_formality_casual_professional(self):
        """Mixed signals yield 'casual-professional'."""
        greetings = Counter({"Hi": 5, "Hey": 3, "Hello": 2})
        signoffs = Counter({"Thanks": 5, "Best": 3})
        result = _assess_formality(greetings, signoffs, avg_length=60, excl_ratio=0.15)
        assert result == "casual-professional"

    def test_assess_formality_empty_counters(self):
        """Empty counters with moderate length yield 'casual-professional'."""
        result = _assess_formality(Counter(), Counter(), avg_length=50, excl_ratio=0.1)
        assert result == "casual-professional"


# ---------------------------------------------------------------------------
# Punctuation description
# ---------------------------------------------------------------------------


class TestDescribePunctuation:
    """Tests for _describe_punctuation style description."""

    def test_describe_punctuation_frequent(self):
        """High exclamation ratio returns 'frequent exclamation marks'."""
        assert _describe_punctuation(0.6) == "frequent exclamation marks"

    def test_describe_punctuation_moderate(self):
        """Moderate exclamation ratio returns 'moderate exclamation marks'."""
        assert _describe_punctuation(0.3) == "moderate exclamation marks"

    def test_describe_punctuation_minimal(self):
        """Low exclamation ratio returns 'minimal exclamation marks'."""
        assert _describe_punctuation(0.1) == "minimal exclamation marks"

    def test_describe_punctuation_zero(self):
        """Zero ratio returns 'minimal exclamation marks'."""
        assert _describe_punctuation(0.0) == "minimal exclamation marks"

    def test_describe_punctuation_boundary_05(self):
        """Ratio of exactly 0.5 returns 'moderate exclamation marks' (not frequent)."""
        assert _describe_punctuation(0.5) == "moderate exclamation marks"

    def test_describe_punctuation_boundary_02(self):
        """Ratio of exactly 0.2 returns 'minimal exclamation marks' (not moderate)."""
        assert _describe_punctuation(0.2) == "minimal exclamation marks"
