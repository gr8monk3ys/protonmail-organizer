"""AI draft reply generator using Claude API with writing style matching."""

from __future__ import annotations

import os
import re
import subprocess
import tempfile
from typing import Optional

from rich.panel import Panel
from rich.table import Table

from .client_ext import ProtonMailExt
from .config import ANTHROPIC_API_KEY
from .constants import INBOX
from .display import console, print_error, print_info, print_success, print_warning
from .style_profile import get_style_profile


def generate_draft(
    message: dict,
    body: str,
    style_profile: dict,
    context: Optional[str] = None,
) -> str:
    """Generate a draft reply using Claude API.

    Args:
        message: The message dict being replied to (sender, subject).
        body: The plain text body of the message.
        style_profile: User's writing style profile.
        context: Optional user instructions for the reply.

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

    print_info("Generating draft reply...")

    try:
        response = client.messages.create(
            model="claude-sonnet-4-5-20250929",
            max_tokens=1024,
            system=system_prompt,
            messages=[{"role": "user", "content": user_msg}],
        )
        draft = response.content[0].text
        return draft
    except Exception as e:
        print_error(f"Claude API error: {e}")
        return ""


def respond_to_message(client: ProtonMailExt, message_id: str, context: Optional[str] = None) -> None:
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

    # Show original message
    console.print(Panel(
        f"[cyan]From:[/cyan] {sender_str}\n"
        f"[cyan]Subject:[/cyan] {subject}\n\n"
        f"{_truncate(body, 500)}",
        title="Replying to",
        border_style="blue",
    ))

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

    draft = generate_draft(msg_dict, plain_body, profile, context)
    if not draft:
        return

    # Review and send flow
    _review_and_send(client, msg, draft)


def respond_interactive(client: ProtonMailExt) -> None:
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

    context = console.input("[dim]Any instructions for the reply? (or Enter to skip): [/dim]").strip() or None

    respond_to_message(client, msg_id, context)


def _review_and_send(client: ProtonMailExt, original_msg, draft: str) -> None:
    """Interactive review flow: display draft, then send/edit/regenerate/cancel."""
    current_draft = draft

    while True:
        console.print(Panel(
            current_draft,
            title="Draft Reply",
            border_style="green",
        ))

        console.print(
            "[bold][S][/bold]end  "
            "[bold][E][/bold]dit  "
            "[bold][R][/bold]egenerate  "
            "[bold][C][/bold]ancel"
        )
        action = console.input("[bold]Action: [/bold]").strip().lower()

        if action in ("s", "send"):
            _send_reply(client, original_msg, current_draft)
            break

        elif action in ("e", "edit"):
            edited = _edit_draft(current_draft)
            if edited is not None:
                current_draft = edited

        elif action in ("r", "regenerate"):
            profile = get_style_profile()
            body = original_msg.body if hasattr(original_msg, "body") else ""
            plain_body = re.sub(r"<[^>]+>", "", body)
            sender = getattr(original_msg, "sender", None)
            msg_dict = {
                "Sender": {
                    "Name": sender.name if sender else "",
                    "Address": sender.address if sender else "",
                },
                "Subject": original_msg.subject if hasattr(original_msg, "subject") else "",
            }
            new_context = console.input("[dim]New instructions? (or Enter): [/dim]").strip() or None
            new_draft = generate_draft(msg_dict, plain_body, profile, new_context)
            if new_draft:
                current_draft = new_draft

        elif action in ("c", "cancel"):
            print_warning("Cancelled.")
            break

        else:
            print_warning("Unknown action. Use S/E/R/C.")


def _send_reply(client: ProtonMailExt, original_msg, draft_body: str) -> None:
    """Send the draft as a reply to the original message."""
    sender = getattr(original_msg, "sender", None)
    if not sender:
        print_error("Cannot determine recipient from original message.")
        return

    recipient_addr = sender.address
    subject = original_msg.subject if hasattr(original_msg, "subject") else ""
    if not subject.lower().startswith("re:"):
        subject = f"Re: {subject}"

    try:
        from protonmail import ProtonMail
        message = ProtonMail.create_message(
            recipients=[recipient_addr],
            subject=subject,
            body=draft_body,
        )
        client.send_message(message)
        print_success(f"Reply sent to {recipient_addr}")
    except Exception as e:
        print_error(f"Failed to send reply: {e}")


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

    prompt = f"""You are drafting an email reply on behalf of the user. Match their writing style exactly.

Style profile:
- Formality: {formality}
- Average reply length: ~{avg_len} words
- Greeting patterns: {', '.join(greetings) if greetings else 'varies'}
- Sign-off patterns: {', '.join(signoffs) if signoffs else 'varies'}
- Common phrases they use: {', '.join(phrases) if phrases else 'none detected'}
- Emoji usage: {'yes' if uses_emoji else 'no — do not use emojis'}
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


def _truncate(text: str, max_len: int) -> str:
    """Truncate text with ellipsis."""
    if len(text) <= max_len:
        return text
    return text[:max_len] + "..."
