"""Sent email analyzer — builds a writing style profile from your sent mail.

Privacy note: The style profile stores truncated email snippets (first ~2 sentences)
for AI few-shot prompting. These are saved at ~/.config/protonmail-organizer/style_profile.json
with restrictive file permissions (0o600). Snippets are also sent to the Claude API
when generating draft replies.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from typing import Optional

from rich.table import Table

from .client_ext import ProtonMailExt
from .config import STYLE_PROFILE_FILE, ensure_config_dir, write_private
from .constants import ALL_SENT
from .display import console, debug_enabled, print_info, print_success, print_warning


def build_style_profile(client: ProtonMailExt, sample_count: int = 50) -> dict:
    """Analyze the last N sent emails and build a writing style profile.

    Args:
        client: Authenticated ProtonMail client.
        sample_count: Number of recent sent emails to analyze.

    Returns:
        Style profile dict.
    """
    print_info(f"Fetching last {sample_count} sent emails...")

    sent_messages = client.search_messages(label_id=ALL_SENT, page_size=sample_count)
    if not sent_messages:
        print_warning("No sent messages found.")
        return {}

    print_info(f"Analyzing {len(sent_messages)} sent emails...")

    bodies = []
    greetings = Counter()
    signoffs = Counter()
    word_counts = []
    emoji_count = 0
    exclamation_count = 0
    total_sentences = 0
    phrases = Counter()

    for msg_summary in sent_messages:
        msg_id = msg_summary.get("ID", "")
        if not msg_id:
            continue

        try:
            msg = client.read_message(msg_id)
            body = msg.body if hasattr(msg, "body") and msg.body else ""
        except Exception as e:
            # Skipping a single unreadable message is fine, but don't hide why.
            if debug_enabled():
                console.print(f"[dim]skipped sent message {msg_id}: {e}[/dim]")
            continue

        if not body:
            continue

        # Strip HTML tags for plain text analysis
        text = _strip_html(body).strip()
        if not text or len(text) < 10:
            continue

        bodies.append(text)
        words = text.split()
        word_counts.append(len(words))

        # Detect greetings (first line patterns)
        lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
        if lines:
            first_line = lines[0]
            greeting = _extract_greeting(first_line)
            if greeting:
                greetings[greeting] += 1

        # Detect sign-offs (last non-empty lines)
        if len(lines) >= 2:
            signoff = _extract_signoff(lines[-3:] if len(lines) >= 3 else lines[-2:])
            if signoff:
                signoffs[signoff] += 1

        # Count emojis
        emoji_count += len(
            re.findall(
                r"[\U0001f600-\U0001f650\U0001f680-\U0001f6ff\u2600-\u26ff\u2700-\u27bf]", text
            )
        )

        # Count exclamation marks
        exclamation_count += text.count("!")
        total_sentences += len(re.findall(r"[.!?]+", text))

        # Common phrases
        text_lower = text.lower()
        for phrase in _COMMON_PHRASES:
            if phrase in text_lower:
                phrases[phrase] += 1

    if not bodies:
        print_warning("Could not extract text from any sent emails.")
        return {}

    avg_length = sum(word_counts) / len(word_counts) if word_counts else 0
    uses_emoji = emoji_count > len(bodies) * 0.1  # >10% of emails have emoji
    excl_ratio = exclamation_count / max(total_sentences, 1)

    # Determine formality
    formality = _assess_formality(greetings, signoffs, avg_length, excl_ratio)

    # Build sample snippets — truncate to first 2-3 sentences for privacy
    # We keep just enough for the AI to match tone, not full email bodies
    sample_snippets = [_truncate_to_sentences(b, 3) for b in sorted(bodies, key=len)[:5]]

    profile = {
        "avg_length_words": round(avg_length),
        "formality": formality,
        "greeting_patterns": [g for g, _ in greetings.most_common(5)],
        "signoff_patterns": [s for s, _ in signoffs.most_common(5)],
        "common_phrases": [p for p, _ in phrases.most_common(10)],
        "uses_emoji": uses_emoji,
        "punctuation_style": _describe_punctuation(excl_ratio),
        "sample_emails": sample_snippets,
        "emails_analyzed": len(bodies),
    }

    # Save profile with restrictive permissions from the moment it exists
    ensure_config_dir()
    write_private(STYLE_PROFILE_FILE, json.dumps(profile, indent=2))
    print_success(f"Style profile saved to {STYLE_PROFILE_FILE}")
    print_success(f"Analyzed {len(bodies)} emails, avg {round(avg_length)} words each.")
    print_info(
        "Note: Truncated email snippets are stored locally and "
        "sent to Claude API for style matching."
    )

    return profile


def get_style_profile() -> dict:
    """Load cached style profile from disk."""
    if not STYLE_PROFILE_FILE.exists():
        return {}
    try:
        return json.loads(STYLE_PROFILE_FILE.read_text())
    except (json.JSONDecodeError, OSError):
        return {}


def refresh_profile(client: ProtonMailExt, sample_count: int = 50) -> dict:
    """Rebuild the style profile from latest sent emails."""
    return build_style_profile(client, sample_count)


def show_profile() -> None:
    """Display the current style profile."""
    profile = get_style_profile()
    if not profile:
        print_warning("No style profile found. Run 'pmo respond profile --refresh' to build one.")
        return

    table = Table(title="Writing Style Profile", show_lines=True)
    table.add_column("Property", style="cyan", width=20)
    table.add_column("Value", style="white")

    table.add_row("Avg Length", f"{profile.get('avg_length_words', '?')} words")
    table.add_row("Formality", profile.get("formality", "?"))
    table.add_row("Greetings", ", ".join(profile.get("greeting_patterns", [])) or "(none detected)")
    table.add_row("Sign-offs", ", ".join(profile.get("signoff_patterns", [])) or "(none detected)")
    table.add_row(
        "Common Phrases", ", ".join(profile.get("common_phrases", [])) or "(none detected)"
    )
    table.add_row("Uses Emoji", str(profile.get("uses_emoji", False)))
    table.add_row("Punctuation", profile.get("punctuation_style", "?"))
    table.add_row("Emails Analyzed", str(profile.get("emails_analyzed", 0)))

    console.print(table)

    samples = profile.get("sample_emails", [])
    if samples:
        console.print(f"\n[dim]{len(samples)} sample email(s) stored for few-shot examples[/dim]")


# --- Helpers ---

_COMMON_PHRASES = [
    "sounds good",
    "let me know",
    "happy to",
    "thanks for",
    "looking forward",
    "no worries",
    "makes sense",
    "good to know",
    "got it",
    "will do",
    "for sure",
    "appreciate it",
    "take care",
    "hope this helps",
    "just wanted to",
    "quick question",
]

_GREETING_PATTERNS = [
    (r"^hey\b", "Hey"),
    (r"^hi\b", "Hi"),
    (r"^hello\b", "Hello"),
    (r"^good morning\b", "Good morning"),
    (r"^good afternoon\b", "Good afternoon"),
    (r"^good evening\b", "Good evening"),
    (r"^dear\b", "Dear"),
    (r"^yo\b", "Yo"),
    (r"^sup\b", "Sup"),
    (r"^what'?s up\b", "What's up"),
]

_SIGNOFF_PATTERNS = [
    (r"(?i)^best[\s,]", "Best"),
    (r"(?i)^thanks[\s,]", "Thanks"),
    (r"(?i)^thank you[\s,]", "Thank you"),
    (r"(?i)^cheers[\s,]", "Cheers"),
    (r"(?i)^regards[\s,]", "Regards"),
    (r"(?i)^sincerely[\s,]", "Sincerely"),
    (r"(?i)^take care[\s,]", "Take care"),
    (r"(?i)^talk soon[\s,]", "Talk soon"),
    (r"(?i)^sent from", None),  # skip device signatures
]


def _strip_html(html: str) -> str:
    """Remove HTML tags and decode common entities."""
    text = re.sub(r"<br\s*/?>", "\n", html, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    text = text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    text = text.replace("&nbsp;", " ").replace("&quot;", '"')
    return text


def _extract_greeting(first_line: str) -> Optional[str]:
    """Extract greeting pattern from first line."""
    line_lower = first_line.lower().strip()
    for pattern, label in _GREETING_PATTERNS:
        if re.match(pattern, line_lower):
            return label
    return None


def _extract_signoff(last_lines: list[str]) -> Optional[str]:
    """Extract sign-off pattern from last lines."""
    for line in reversed(last_lines):
        stripped = line.strip()
        if not stripped:
            continue
        for pattern, label in _SIGNOFF_PATTERNS:
            if re.match(pattern, stripped):
                return label
    return None


def _assess_formality(
    greetings: Counter,
    signoffs: Counter,
    avg_length: float,
    excl_ratio: float,
) -> str:
    """Determine formality level from style signals."""
    formal_greetings = {"Dear", "Hello", "Good morning", "Good afternoon", "Good evening"}
    casual_greetings = {"Hey", "Yo", "Sup", "What's up"}
    formal_signoffs = {"Sincerely", "Regards", "Thank you"}
    casual_signoffs = {"Cheers", "Talk soon", "Take care"}

    formal_score = 0
    casual_score = 0

    for g, count in greetings.items():
        if g in formal_greetings:
            formal_score += count
        elif g in casual_greetings:
            casual_score += count

    for s, count in signoffs.items():
        if s in formal_signoffs:
            formal_score += count
        elif s in casual_signoffs:
            casual_score += count

    if avg_length > 100:
        formal_score += 2
    elif avg_length < 30:
        casual_score += 2

    if excl_ratio > 0.3:
        casual_score += 1

    if formal_score > casual_score * 2:
        return "formal"
    elif casual_score > formal_score * 2:
        return "casual"
    else:
        return "casual-professional"


def _truncate_to_sentences(text: str, max_sentences: int = 3) -> str:
    """Truncate text to the first N sentences for privacy.

    Preserves enough for style matching without storing full email content.
    """
    # Split on sentence-ending punctuation
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    if len(sentences) <= max_sentences:
        result = text.strip()
    else:
        result = " ".join(sentences[:max_sentences])

    # Hard cap at 200 chars as additional safety
    if len(result) > 200:
        result = result[:200] + "..."
    return result


def _describe_punctuation(excl_ratio: float) -> str:
    """Describe punctuation usage style."""
    if excl_ratio > 0.5:
        return "frequent exclamation marks"
    elif excl_ratio > 0.2:
        return "moderate exclamation marks"
    else:
        return "minimal exclamation marks"
