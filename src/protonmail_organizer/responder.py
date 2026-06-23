"""AI draft reply generator using Claude API with writing style matching."""

from __future__ import annotations

import html
import os
import re
import subprocess
import tempfile
from datetime import datetime
from typing import Optional

from rich.panel import Panel
from rich.table import Table

from .client_ext import ProtonMailExt
from .config import ANTHROPIC_API_KEY, ANTHROPIC_MODEL
from .constants import INBOX
from .display import console, print_error, print_info, print_success, print_warning
from .style_profile import get_style_profile


def generate_draft(
    message: dict,
    body: str,
    style_profile: dict,
    context: Optional[str] = None,
    model: Optional[str] = None,
) -> str:
    """Generate a draft reply using Claude API.

    Args:
        message: The message dict being replied to (sender, subject).
        body: The plain text body of the message.
        style_profile: User's writing style profile.
        context: Optional user instructions for the reply.
        model: Claude model ID (defaults to config.ANTHROPIC_MODEL / PMO_AI_MODEL).

    Returns:
        Generated draft text.
    """
    api_key = ANTHROPIC_API_KEY or os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        print_error(
            "ANTHROPIC_API_KEY not set. Export it as an environment variable:\n"
            "  export ANTHROPIC_API_KEY='sk-ant-...'"
        )
        return ""

    try:
        import anthropic
    except ImportError:
        print_error("anthropic package not installed. Run: pip install anthropic>=0.40.0")
        return ""

    # The email body and style snippets are about to leave the device for the
    # Anthropic API — require a one-time, explicit acknowledgment first.
    from .consent import require_ai_egress_ack

    if not require_ai_egress_ack():
        print_warning("AI reply cancelled (data-sharing not acknowledged).")
        return ""

    sender = message.get("Sender", {})
    sender_name = sender.get("Name", "") if isinstance(sender, dict) else ""
    sender_addr = sender.get("Address", "") if isinstance(sender, dict) else ""
    subject = message.get("Subject", "(no subject)")

    # Build system prompt with style profile
    system_prompt = _build_system_prompt(style_profile)

    # Build user message
    user_msg = f"""Reply to this email:
From: {sender_name} <{sender_addr}>
Subject: {subject}
Body:
{body}"""

    if context:
        user_msg += f"\n\nAdditional instructions: {context}"

    client = anthropic.Anthropic(api_key=api_key)
    model = model or ANTHROPIC_MODEL

    print_info(f"Generating draft reply ({model})...")

    try:
        response = client.messages.create(
            model=model,
            max_tokens=2048,
            system=system_prompt,
            messages=[{"role": "user", "content": user_msg}],
        )
        # Use the first text block rather than assuming content[0] is text.
        draft = next(
            (block.text for block in response.content if block.type == "text"),
            "",
        )
        return draft
    except Exception as e:
        print_error(f"Claude API error: {e}")
        return ""


def respond_to_message(
    client: ProtonMailExt,
    message_id: str,
    context: Optional[str] = None,
    model: Optional[str] = None,
) -> None:
    """Full flow: read message, generate draft, review, optionally send."""
    # Load style profile
    profile = get_style_profile()
    if not profile:
        print_warning("No style profile found. Building one from your sent emails...")
        from .style_profile import build_style_profile

        profile = build_style_profile(client)
        if not profile:
            print_error("Could not build style profile. Cannot generate reply.")
            return

    # Read the original message
    try:
        msg = client.read_message(message_id)
    except Exception as e:
        print_error(f"Failed to read message {message_id}: {e}")
        return

    body = msg.body if hasattr(msg, "body") and msg.body else ""
    sender = getattr(msg, "sender", None)
    sender_str = f"{sender.name} <{sender.address}>" if sender else "?"
    subject = msg.subject if hasattr(msg, "subject") else ""

    # The original message's Message-ID header (ExternalID) lets us thread the
    # reply. The library populates `extra` with the raw API dict.
    external_id = _extract_external_id(msg)

    # Show original message
    console.print(
        Panel(
            f"[cyan]From:[/cyan] {sender_str}\n"
            f"[cyan]Subject:[/cyan] {subject}\n\n"
            f"{_truncate(body, 500)}",
            title="Replying to",
            border_style="blue",
        )
    )

    # Build message dict for generate_draft
    msg_dict = {
        "Sender": {
            "Name": sender.name if sender else "",
            "Address": sender.address if sender else "",
        },
        "Subject": subject,
    }

    # Strip HTML for the AI
    plain_body = re.sub(r"<[^>]+>", "", body)
    plain_body = plain_body.replace("&nbsp;", " ").replace("&amp;", "&")

    draft = generate_draft(msg_dict, plain_body, profile, context, model)
    if not draft:
        return

    # Review and send flow
    _review_and_send(client, msg, draft, plain_body, external_id, model)


def respond_interactive(client: ProtonMailExt, model: Optional[str] = None) -> None:
    """Interactive mode: pick a message from inbox, then draft reply."""
    print_info("Fetching recent inbox messages...")
    messages = client.search_messages(label_id=INBOX, page_size=15)

    if not messages:
        print_warning("No messages in inbox.")
        return

    # Display messages for selection
    table = Table(title="Select a message to reply to", show_lines=False, expand=True)
    table.add_column("#", style="dim", width=4)
    table.add_column("From", style="cyan", max_width=30)
    table.add_column("Subject", style="white")

    for i, msg in enumerate(messages, 1):
        sender = msg.get("Sender", {})
        name = sender.get("Name", "") if isinstance(sender, dict) else ""
        addr = sender.get("Address", "") if isinstance(sender, dict) else ""
        from_str = name if name else addr
        subject = msg.get("Subject", "(no subject)")
        table.add_row(str(i), from_str, subject)

    console.print(table)

    choice = console.input("\n[bold]Message number (or q to quit): [/bold]").strip()
    if choice.lower() in ("q", "quit", ""):
        return

    try:
        idx = int(choice) - 1
        if idx < 0 or idx >= len(messages):
            print_error("Invalid selection.")
            return
    except ValueError:
        print_error("Invalid number.")
        return

    selected = messages[idx]
    msg_id = selected.get("ID", "")

    context = (
        console.input("[dim]Any instructions for the reply? (or Enter to skip): [/dim]").strip()
        or None
    )

    respond_to_message(client, msg_id, context, model)


def _review_and_send(
    client: ProtonMailExt,
    original_msg,
    draft: str,
    plain_body: str = "",
    external_id: Optional[str] = None,
    model: Optional[str] = None,
) -> None:
    """Interactive review flow: display draft, then send/draft/edit/regenerate/cancel."""
    current_draft = draft

    while True:
        console.print(
            Panel(
                current_draft,
                title="Draft Reply",
                border_style="green",
            )
        )

        console.print(
            "[bold][S][/bold]end  "
            "save as [bold][D][/bold]raft  "
            "[bold][E][/bold]dit  "
            "[bold][R][/bold]egenerate  "
            "[bold][C][/bold]ancel"
        )
        action = console.input("[bold]Action: [/bold]").strip().lower()

        if action in ("s", "send"):
            _send_reply(client, original_msg, current_draft, plain_body, external_id)
            break

        elif action in ("d", "draft"):
            _save_draft(client, original_msg, current_draft, plain_body, external_id)
            break

        elif action in ("e", "edit"):
            edited = _edit_draft(current_draft)
            if edited is not None:
                current_draft = edited

        elif action in ("r", "regenerate"):
            profile = get_style_profile()
            sender = getattr(original_msg, "sender", None)
            msg_dict = {
                "Sender": {
                    "Name": sender.name if sender else "",
                    "Address": sender.address if sender else "",
                },
                "Subject": original_msg.subject if hasattr(original_msg, "subject") else "",
            }
            new_context = console.input("[dim]New instructions? (or Enter): [/dim]").strip() or None
            new_draft = generate_draft(msg_dict, plain_body, profile, new_context, model)
            if new_draft:
                current_draft = new_draft

        elif action in ("c", "cancel"):
            print_warning("Cancelled.")
            break

        else:
            print_warning("Unknown action. Use S/D/E/R/C.")


def _build_reply_message(client: ProtonMailExt, original_msg, draft_body: str, plain_body: str):
    """Build a threaded reply Message (quoted original, In-Reply-To set).

    Returns the protonmail Message, or None if the recipient can't be determined.
    """
    sender = getattr(original_msg, "sender", None)
    if not sender:
        print_error("Cannot determine recipient from original message.")
        return None

    subject = original_msg.subject if hasattr(original_msg, "subject") else ""
    if not subject.lower().startswith("re:"):
        subject = f"Re: {subject}"

    from protonmail import ProtonMail

    return ProtonMail.create_message(
        recipients=[sender.address],
        subject=subject,
        body=_format_reply_html(draft_body, original_msg, plain_body),
        # in_reply_to threads the reply onto the original conversation; the
        # library resolves the parent message by this Message-ID.
        in_reply_to=_extract_external_id(original_msg),
    )


def _send_reply(
    client: ProtonMailExt,
    original_msg,
    draft_body: str,
    plain_body: str = "",
    external_id: Optional[str] = None,
) -> None:
    """Send the draft as a threaded reply to the original message."""
    message = _build_reply_message(client, original_msg, draft_body, plain_body)
    if message is None:
        return
    try:
        client.send_message(message)
        print_success(f"Reply sent to {message.recipients[0].address}")
    except Exception as e:
        print_error(f"Failed to send reply: {e}")


def _save_draft(
    client: ProtonMailExt,
    original_msg,
    draft_body: str,
    plain_body: str = "",
    external_id: Optional[str] = None,
) -> None:
    """Save the reply as a draft in ProtonMail instead of sending it."""
    message = _build_reply_message(client, original_msg, draft_body, plain_body)
    if message is None:
        return
    try:
        client.create_draft(message)
        print_success("Draft saved to ProtonMail. Review and send it from the web/app.")
    except Exception as e:
        print_error(f"Failed to save draft: {e}")


def _edit_draft(draft: str) -> Optional[str]:
    """Open draft in $EDITOR or fall back to inline editing."""
    editor = os.environ.get("EDITOR", "")

    if editor:
        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
                f.write(draft)
                tmp_path = f.name

            subprocess.run([editor, tmp_path], check=True)

            with open(tmp_path) as f:
                edited = f.read()

            if edited.strip():
                print_success("Draft updated.")
                return edited.strip()
            else:
                print_warning("Empty draft, keeping original.")
                return None
        except Exception as e:
            print_error(f"Editor failed: {e}")
        finally:
            if tmp_path and os.path.exists(tmp_path):
                os.unlink(tmp_path)

    # Fallback: inline editing
    console.print("[dim]Enter new draft (empty line + Enter to finish):[/dim]")
    lines = []
    while True:
        line = console.input("")
        if line == "":
            break
        lines.append(line)

    if lines:
        return "\n".join(lines)
    return None


def _build_system_prompt(profile: dict) -> str:
    """Build the Claude system prompt from the style profile."""
    formality = profile.get("formality", "casual-professional")
    avg_len = profile.get("avg_length_words", 40)
    greetings = profile.get("greeting_patterns", [])
    signoffs = profile.get("signoff_patterns", [])
    phrases = profile.get("common_phrases", [])
    uses_emoji = profile.get("uses_emoji", False)
    punctuation = profile.get("punctuation_style", "minimal exclamation marks")
    samples = profile.get("sample_emails", [])

    prompt = f"""You are drafting an email reply on behalf of the user.
Match their writing style exactly.

Style profile:
- Formality: {formality}
- Average reply length: ~{avg_len} words
- Greeting patterns: {", ".join(greetings) if greetings else "varies"}
- Sign-off patterns: {", ".join(signoffs) if signoffs else "varies"}
- Common phrases they use: {", ".join(phrases) if phrases else "none detected"}
- Emoji usage: {"yes" if uses_emoji else "no — do not use emojis"}
- Punctuation: {punctuation}

Rules:
- Write ONLY the email body — no subject line, no metadata
- Keep the reply approximately {avg_len} words unless the situation requires more
- Match the formality level: {formality}
- Use their greeting and sign-off patterns naturally
- Do not be overly verbose or formal unless their style is formal
- Be helpful and address the content of the email directly"""

    if samples:
        prompt += "\n\nExamples of their actual emails (for tone reference):"
        for i, sample in enumerate(samples[:3], 1):
            truncated = sample[:300] + "..." if len(sample) > 300 else sample
            prompt += f"\n\nExample {i}:\n{truncated}"

    return prompt


def _extract_external_id(original_msg) -> Optional[str]:
    """Return the original message's Message-ID (ExternalID), if available."""
    extra = getattr(original_msg, "extra", None)
    if isinstance(extra, dict):
        return extra.get("ExternalID")
    return None


def _format_reply_html(draft_body: str, original_msg, plain_body: str) -> str:
    """Render the reply as HTML with the original message quoted beneath it.

    ProtonMail stores message bodies as HTML, so plain-text drafts need their
    newlines converted to <br> to render correctly.
    """
    draft_html = html.escape(draft_body).replace("\n", "<br>\n")

    sender = getattr(original_msg, "sender", None)
    if sender:
        who = f"{sender.name} <{sender.address}>" if getattr(sender, "name", "") else sender.address
    else:
        who = "the sender"

    msg_time = getattr(original_msg, "time", 0)
    when = datetime.fromtimestamp(msg_time).strftime("%a, %d %b %Y at %H:%M") if msg_time else ""
    attribution = f"On {when}, {who} wrote:" if when else f"{who} wrote:"

    quoted = html.escape(_truncate(plain_body.strip(), 5000)).replace("\n", "<br>\n")

    return (
        f"{draft_html}<br><br>"
        f"{html.escape(attribution)}<br>"
        f'<blockquote type="cite" '
        f'style="margin:0 0 0 0.8ex; border-left:2px solid #ccc; padding-left:1ex;">'
        f"{quoted}</blockquote>"
    )


def _truncate(text: str, max_len: int) -> str:
    """Truncate text with ellipsis."""
    if len(text) <= max_len:
        return text
    return text[:max_len] + "..."
